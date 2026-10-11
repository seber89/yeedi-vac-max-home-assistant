"""Observed docking edges across normal and post-write status paths."""
import time
import pytest
from tests.test_coordinator import coordinator
from tests.test_beta6 import install_raw
from tests.test_rc4 import raw_fixture


@pytest.mark.parametrize('activity',['cleaning','returning'])
async def test_post_write_active_state_then_poll_docked_is_fresh(coordinator,activity):
    await install_raw(coordinator)
    robot = coordinator.robots[0]
    coordinator.client.snapshot.return_value = {'online':True,'activity':'docked'}
    await coordinator._poll_robot(robot)
    coordinator.client.snapshot.return_value = {'online':True,'activity':activity}
    await coordinator._refresh_after_write(robot)
    coordinator.client.snapshot.return_value = {'online':True,'activity':'docked'}
    coordinator.client.load_raw_map.return_value = raw_fixture()
    await coordinator._poll_robot(robot)
    assert coordinator.client.load_raw_map.await_count == 1
    assert coordinator.client.load_raw_map.await_args.args[2] is None
    assert coordinator.spatial['vac'].raw_refresh_probe.fresh_attempts == 1


async def test_docking_observed_after_write_edge_survives_until_poll(coordinator):
    await install_raw(coordinator)
    robot = coordinator.robots[0]
    for activity in ('cleaning','docked','docked'):
        coordinator.client.snapshot.return_value = {'online':True,'activity':activity}
        await coordinator._refresh_after_write(robot)
    coordinator.client.load_raw_map.return_value = raw_fixture()
    for _ in range(3):
        await coordinator._poll_robot(robot)
    coordinator.client.load_raw_map.assert_awaited_once()
    assert coordinator.client.load_raw_map.await_args.args[2] is None


@pytest.mark.parametrize('activities',[
    ('cleaning','docked'),('returning','docked'),('cleaning','returning','docked')])
async def test_normal_edges_once_despite_future_cache(coordinator,activities):
    state = await install_raw(coordinator)
    coordinator.client.load_raw_map.return_value = raw_fixture()
    for activity in (*activities,'docked','docked'):
        coordinator.client.snapshot.return_value = {'online':True,'activity':activity}
        await coordinator._poll_robot(coordinator.robots[0])
    assert state.raw_refresh_probe.fresh_attempts == 1
    coordinator.client.load_raw_map.assert_awaited_once()


@pytest.mark.parametrize('next_state',[{'online':False}, {'online':True,'activity':'cleaning'}])
async def test_pending_edge_cancelled_when_no_longer_docked(coordinator,next_state):
    await install_raw(coordinator)
    robot = coordinator.robots[0]
    coordinator._remember(robot,{'online':True,'activity':'cleaning'})
    coordinator._remember(robot,{'online':True,'activity':'docked'})
    coordinator._remember(robot,next_state)
    assert robot.did not in coordinator._docking_refresh_pending
    coordinator.client.snapshot.return_value = next_state
    await coordinator._poll_robot(robot)
    coordinator.client.load_raw_map.assert_not_awaited()


async def test_fast_stop_and_unload_clear_pending(coordinator):
    robot = coordinator.robots[0]
    coordinator._remember(robot,{'online':True,'activity':'cleaning'})
    assert coordinator.fast_positions[robot.did].wanted
    coordinator._remember(robot,{'online':True,'activity':'docked'})
    assert not coordinator.fast_positions[robot.did].wanted
    assert robot.did in coordinator._docking_refresh_pending
    await coordinator.async_shutdown()
    assert not coordinator._docking_refresh_pending
    coordinator.client.load_raw_map.assert_not_awaited()


async def test_recent_normal_build_does_not_block_edge(coordinator):
    state = await install_raw(coordinator)
    robot = coordinator.robots[0]
    coordinator.client.load_raw_map.return_value = raw_fixture()
    state.next_raw_refresh = 0
    coordinator.client.snapshot.return_value = {'online':True,'activity':'docked'}
    await coordinator._poll_robot(robot)
    assert coordinator.client.load_raw_map.await_args.args[2] is not None
    for activity in ('returning','docked','docked'):
        coordinator.client.snapshot.return_value = {'online':True,'activity':activity}
        await coordinator._poll_robot(robot)
    assert coordinator.client.load_raw_map.await_count == 2
    assert coordinator.client.load_raw_map.await_args.args[2] is None


async def test_startup_docked_and_cleaning_cycles_no_fresh(coordinator):
    await install_raw(coordinator)
    for activity in ('docked','docked','cleaning','cleaning','returning'):
        coordinator.client.snapshot.return_value = {'online':True,'activity':activity}
        await coordinator._poll_robot(coordinator.robots[0])
    coordinator.client.load_raw_map.assert_not_awaited()


async def test_failed_fresh_keeps_map_then_normal_retry(coordinator):
    state = await install_raw(coordinator)
    old = state.raw_map
    coordinator.client.load_raw_map.side_effect = TimeoutError()
    for activity in ('cleaning','docked','docked'):
        coordinator.client.snapshot.return_value = {'online':True,'activity':activity}
        await coordinator._poll_robot(coordinator.robots[0])
    assert state.raw_map is old
    assert state.raw_refresh_probe.fresh_attempts == 1
    assert state.next_raw_refresh > time.monotonic()
    state.next_raw_refresh = 0
    await coordinator._poll_robot(coordinator.robots[0])
    assert coordinator.client.load_raw_map.await_count == 2
    assert coordinator.client.load_raw_map.await_args.args[2] is old
    assert state.raw_refresh_probe.fresh_attempts == 1
