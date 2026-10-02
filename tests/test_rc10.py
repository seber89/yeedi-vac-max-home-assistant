"""Synthetic position-only lifecycle, pacing, privacy and transport regression."""
import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_coordinator import coordinator
from tests.test_client import ROBOT, Session
from tests.test_rc4 import raw_fixture
from custom_components.yeedi_vac_max import fast_position as module
from custom_components.yeedi_vac_max.client import (
    YeediClient, CloudError, CommandTimeout, RateLimited, InvalidAuth, VerificationRequired)
from custom_components.yeedi_vac_max.map_data import RobotPosition, DockPosition
from custom_components.yeedi_vac_max.image import YeediMapImage
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.parametrize('activity',['cleaning','returning'])
async def test_confirmed_activity_one_task(coordinator,activity):
    robot = coordinator.robots[0]
    coordinator._remember(robot,{'online':True,'activity':activity})
    poll = coordinator.fast_positions['vac']
    task = poll.task
    assert task is not None
    coordinator._remember(robot,{'online':True,'activity':activity})
    assert poll.task is task
    await asyncio.sleep(0)
    coordinator.client.positions.assert_not_awaited()  # Initial cadence, no burst.
    assert coordinator.update_interval.total_seconds() == 60


@pytest.mark.parametrize('snapshot',[
    {'online':True,'activity':a} for a in ('paused','docked','idle','error','unknown',None)
] + [{'online':False,'activity':'cleaning'},{}])
async def test_nonactive_never_starts(coordinator,snapshot):
    coordinator._remember(coordinator.robots[0],snapshot)
    assert coordinator.fast_positions['vac'].task is None


@pytest.mark.parametrize('start,end',[('cleaning','docked'),('cleaning','paused'),
    ('cleaning','error'),('returning','docked'),('cleaning','idle'),('cleaning',None)])
async def test_observed_stop_cancels_task(coordinator,start,end):
    poll = coordinator.fast_positions['vac']
    poll.observe({'online':True,'activity':start})
    task = poll.task
    await asyncio.sleep(0)
    poll.observe({'online':True,'activity':end})
    await asyncio.gather(task,return_exceptions=True)
    assert task.done() and poll.task is None and not poll.wanted
    assert poll.last_result == 'stopped'


async def test_unload_awaits_request_cleanup(coordinator,monkeypatch):
    from custom_components.yeedi_vac_max import async_unload_entry
    monkeypatch.setattr(module,'INTERVAL',0.001)
    coordinator.client.close = MagicMock()
    entered, cleaned = asyncio.Event(), asyncio.Event()
    async def positions(*args,**kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()
    coordinator.client.positions.side_effect = positions
    poll = coordinator.fast_positions['vac']
    poll.observe({'online':True,'activity':'cleaning'})
    await asyncio.wait_for(entered.wait(),1)
    task = poll.task
    with patch.object(coordinator.hass.config_entries,'async_unload_platforms',new=AsyncMock(return_value=True)):
        assert await async_unload_entry(coordinator.hass,SimpleNamespace(runtime_data=coordinator))
    assert cleaned.is_set() and task.done() and poll.task is None and poll.closed
    assert not coordinator.commands['vac'].lock.locked()
    poll.observe({'online':True,'activity':'cleaning'})
    assert poll.task is None
    replacement = module.FastPosition(coordinator,coordinator.robots[0])
    replacement.observe({'online':True,'activity':'cleaning'})
    assert replacement.task is not None and replacement.task is not task
    await replacement.shutdown()


async def test_rapid_stop_restart_no_duplicate(coordinator):
    poll = coordinator.fast_positions['vac']
    poll.observe({'online':True,'activity':'cleaning'})
    first = poll.task
    poll.observe({'online':True,'activity':'paused'})
    poll.observe({'online':True,'activity':'returning'})
    assert poll.task is first
    await asyncio.gather(first,return_exceptions=True)
    assert poll.task is not None and poll.task is not first and first.done()


async def test_external_cancellation_does_not_respawn(coordinator):
    poll = coordinator.fast_positions['vac']
    poll.observe({'online':True,'activity':'cleaning'})
    task = poll.task
    task.cancel()
    await asyncio.gather(task,return_exceptions=True)
    assert poll.task is None


def cycle_setup(coordinator):
    poll = coordinator.fast_positions['vac']
    poll.wanted = True
    poll.next_read = 0
    return poll


async def test_position_only_update_and_listener(coordinator):
    poll = cycle_setup(coordinator)
    robot, dock = RobotPosition(12345,67890), DockPosition(34567,45678)
    coordinator.client.positions.return_value = (robot,dock)
    events = []
    coordinator.async_update_listeners = lambda: events.append(True)
    await poll._cycle()
    state = coordinator.spatial['vac']
    assert (state.robot_position,state.dock_position) == (robot,dock)
    assert events == [True]
    assert [call[0] for call in coordinator.client.mock_calls] == ['positions']
    coordinator.client.positions.assert_awaited_once_with(coordinator.robots[0],retry=False)
    assert poll.last_result == 'success'


async def test_five_seconds_between_starts_and_normal_guard(coordinator,monkeypatch):
    clock = SimpleNamespace(now=100.)
    monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:clock.now))
    poll = cycle_setup(coordinator)
    assert module.INTERVAL == module.TIMEOUT == 5
    await poll._cycle()
    clock.now = 104.99
    await poll._cycle()
    assert coordinator.client.positions.await_count == 1 and not poll.normal_read_due()
    clock.now = 105
    assert poll.normal_read_due()
    poll.note_normal_read()
    await poll._cycle()
    assert coordinator.client.positions.await_count == 1
    clock.now = 110
    await poll._cycle()
    assert coordinator.client.positions.await_count == 2


async def test_slow_read_never_parallel_and_skips_locked(coordinator):
    poll = cycle_setup(coordinator)
    entered,release = asyncio.Event(),asyncio.Event()
    async def positions(*args,**kwargs):
        entered.set()
        await release.wait()
        return None,None
    coordinator.client.positions.side_effect = positions
    first = asyncio.create_task(poll._cycle())
    await asyncio.wait_for(entered.wait(),1)
    poll.next_read = 0
    await poll._cycle()
    assert coordinator.client.positions.await_count == 1
    release.set()
    await first


@pytest.mark.parametrize('busy',['lock','pending'])
async def test_no_fast_queue_priority_to_commands(coordinator,busy):
    poll = cycle_setup(coordinator)
    command = coordinator.commands['vac']
    if busy == 'lock':
        await command.lock.acquire()
    else:
        command.pending = 1
    try:
        await asyncio.wait_for(poll._cycle(),0.1)
        coordinator.client.positions.assert_not_awaited()
    finally:
        if busy == 'lock':
            command.lock.release()
        command.pending = 0


@pytest.mark.parametrize('error,result,delay',[
    (TimeoutError,'timeout',15),(CommandTimeout,'timeout',15),
    (CloudError,'cloud_error',15),(RuntimeError,'cloud_error',15),
    (RateLimited,'rate_limited',300)])
async def test_failure_keeps_position_and_backoff(coordinator,monkeypatch,error,result,delay,caplog):
    clock = SimpleNamespace(now=100.)
    monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:clock.now))
    poll = cycle_setup(coordinator)
    state = coordinator.spatial['vac']
    state.robot_position,state.dock_position = RobotPosition(12345,67890),DockPosition(34567,45678)
    old = (state.robot_position,state.dock_position)
    state.metadata_valid = state.rooms_valid = True
    coordinator.client.positions.side_effect = error('PRIVATE_COORDINATES_12345')
    await poll._cycle()
    assert poll.last_result == result and poll.next_read >= 100+delay
    assert (state.robot_position,state.dock_position) == old
    assert state.metadata_valid and state.rooms_valid and coordinator.last_update_success
    clock.now = 100+delay-0.1
    await poll._cycle()
    assert coordinator.client.positions.await_count == 1
    clock.now = 100+delay
    coordinator.client.positions.side_effect = None
    coordinator.client.positions.return_value = (RobotPosition(1,2),None)
    await poll._cycle()
    assert poll.last_result == 'success' and poll.next_read == clock.now+5
    assert not poll.rate_limited and 'PRIVATE' not in caplog.text


@pytest.mark.parametrize('error',[InvalidAuth,VerificationRequired])
async def test_auth_failure_suspends_cycle(coordinator,error):
    poll = cycle_setup(coordinator)
    coordinator.client.positions.side_effect = error('PRIVATE')
    await poll._cycle()
    assert poll.auth_blocked and poll.last_result == 'auth_error'
    poll.observe({'online':True,'activity':'cleaning'})
    assert poll.task is None
    await poll._cycle()
    coordinator.client.positions.assert_awaited_once()
    assert coordinator.last_update_success


async def test_bounded_timeout(coordinator,monkeypatch):
    monkeypatch.setattr(module,'TIMEOUT',0.01)
    poll = cycle_setup(coordinator)
    async def blocked(*args,**kwargs):
        await asyncio.Event().wait()
    coordinator.client.positions.side_effect = blocked
    await asyncio.wait_for(poll._cycle(),1)
    assert poll.last_result == 'timeout' and not coordinator.commands['vac'].lock.locked()


async def test_missing_position_is_successful_update(coordinator):
    poll = cycle_setup(coordinator)
    coordinator.spatial['vac'].robot_position = RobotPosition(1,2)
    coordinator.client.positions.return_value = (None,DockPosition(3,4))
    await poll._cycle()
    assert coordinator.spatial['vac'].robot_position is None
    assert coordinator.spatial['vac'].dock_position == DockPosition(3,4)
    assert poll.last_result == 'missing_position'


async def test_transport_exact_getpos_no_retry_no_relogin():
    client = YeediClient(None,'private','secret','DE','resource')
    client.token,client.user_id,client.expires = 'PRIVATE_TOKEN','PRIVATE_USER',time.monotonic()+3600
    client._request = AsyncMock(return_value={'ret':'ok','resp':{'body':{'data':{}}}})
    for _ in range(3):
        assert await client.positions(ROBOT,retry=False) == (None,None)
    assert client._request.await_count == 3
    for call in client._request.call_args_list:
        assert call.args == ('POST','https://portal-eu.ecouser.net/api/iot/devmanager.do')
        assert call.kwargs['retry'] is False
        assert call.kwargs['json']['cmdName'] == 'getPos'
        assert call.kwargs['json']['payload']['body']['data'] == ['chargePos','deebotPos']


async def test_fast_transport_timeout_attempted_once():
    client = YeediClient(Session(100),'a','b','DE','c')
    client.token,client.expires = 'valid',time.monotonic()+3600
    with pytest.raises(CommandTimeout):
        await client.positions(ROBOT,retry=False)
    assert client.session.calls == 1


async def test_default_position_retry_unchanged():
    client = YeediClient(None,'a','b','DE','c')
    client.token,client.expires = 'valid',time.monotonic()+3600
    client._request = AsyncMock(return_value={'ret':'ok','resp':{'body':{'data':{}}}})
    await client.positions(ROBOT)
    assert client._request.call_args.kwargs['retry'] is True


async def test_auth_rate_limit_not_hidden_from_fast_poll():
    client = YeediClient(None,'a','b','DE','c')
    client.authenticate = AsyncMock(side_effect=RateLimited('PRIVATE'))
    with pytest.raises(RateLimited):
        await client.positions(ROBOT,retry=False)


async def test_after_write_observation_not_write_itself_starts(coordinator):
    coordinator.client.snapshot.return_value = {'online':True,'activity':'cleaning'}
    assert coordinator.fast_positions['vac'].task is None
    await coordinator._refresh_after_write(coordinator.robots[0])
    assert coordinator.fast_positions['vac'].task is not None
    coordinator.client.snapshot.return_value = {'online':True,'activity':'docked'}
    task = coordinator.fast_positions['vac'].task
    await coordinator._refresh_after_write(coordinator.robots[0])
    await asyncio.gather(task,return_exceptions=True)
    assert coordinator.fast_positions['vac'].task is None


async def test_overlay_updates_without_raw_build_or_persistence(coordinator):
    poll = cycle_setup(coordinator)
    state = coordinator.spatial['vac']
    state.raw_map = raw_fixture()
    image = YeediMapImage(coordinator,coordinator.robots[0])
    key = image._render_key
    coordinator.async_update_listeners = image._sync_image
    coordinator.client.positions.return_value = (RobotPosition(10,20),DockPosition(30,40))
    await poll._cycle()
    assert image._render_key != key and image.available
    assert image._raw_overlay.raw is state.raw_map
    assert [call[0] for call in coordinator.client.mock_calls] == ['positions']
    assert not state.has_persisted_map


async def test_privacy_allowlist_no_history(coordinator,caplog):
    poll = cycle_setup(coordinator)
    coordinator.client.positions.return_value = (RobotPosition(1234567,7654321),DockPosition(333333,444444))
    await poll._cycle()
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    probe = output['fast_position'][0]
    assert set(probe) == {'fast_position_poll_active','fast_position_last_result',
        'fast_position_success_bucket','fast_position_failure_bucket','fast_position_rate_limited'}
    assert probe['fast_position_success_bucket'] == '1'
    exported = json.dumps(output)+caplog.text
    for secret in ('1234567','7654321','333333','444444','PRIVATE'):
        assert secret not in exported
    assert not any('history' in key or 'coordinate' in key for key in vars(poll))


@pytest.mark.parametrize('count,expected',[(0,'0'),(1,'1'),(2,'2-8'),(8,'2-8'),
    (9,'9-32'),(32,'9-32'),(33,'>32')])
def test_counter_buckets(count,expected):
    assert module.bucket(count) == expected


async def test_normal_snapshot_stops_on_offline(coordinator):
    poll = coordinator.fast_positions['vac']
    poll.observe({'online':True,'activity':'cleaning'})
    task = poll.task
    coordinator.client.snapshot.return_value = {'online':False}
    await coordinator._poll_robot(coordinator.robots[0])
    await asyncio.gather(task,return_exceptions=True)
    assert poll.task is None and not poll.wanted


async def test_write_without_confirmed_activity_never_starts(coordinator):
    coordinator.client.snapshot.return_value = {'online':True,'activity':'idle'}
    await coordinator.execute(coordinator.robots[0],'clean',{'act':'start'})
    assert coordinator.fast_positions['vac'].task is None


async def test_saved_png_never_gains_overlay(coordinator):
    from custom_components.yeedi_vac_max.map_storage import SavedMap
    poll = cycle_setup(coordinator)
    state = coordinator.spatial['vac']
    raw = raw_fixture()
    state.saved_map = SavedMap(raw.major.map_id,raw.png)
    state.has_persisted_map = True
    image = YeediMapImage(coordinator,coordinator.robots[0])
    coordinator.async_update_listeners = image._sync_image
    coordinator.client.positions.return_value = (RobotPosition(12,34),DockPosition(56,78))
    before = image._render_key
    await poll._cycle()
    assert image._render_key == before and image._raw_overlay is None
    assert await image.async_image() == raw.png


async def test_running_task_recovers_after_transient_error(coordinator,monkeypatch):
    monkeypatch.setattr(module,'INTERVAL',0.01)
    monkeypatch.setattr(module,'ERROR_BACKOFF',0.02)
    completed = asyncio.Event()
    calls = 0
    async def positions(*args,**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise CloudError('PRIVATE')
        completed.set()
        return RobotPosition(1,2),None
    coordinator.client.positions.side_effect = positions
    poll = coordinator.fast_positions['vac']
    poll.observe({'online':True,'activity':'cleaning'})
    await asyncio.wait_for(completed.wait(),1)
    assert poll.last_result == 'success' and poll.failures == poll.successes == 1
    await poll.shutdown()


async def test_config_setup_failure_joins_fast_task(coordinator):
    from custom_components.yeedi_vac_max import async_setup_entry
    entry = SimpleNamespace(data={'username':'a','password':'b','country':'DE','device_id':'local'})
    client = MagicMock()
    client.devices = AsyncMock(return_value=coordinator.robots)
    coordinator.async_load_saved_maps = AsyncMock(return_value=False)
    tasks = []
    async def refresh():
        poll = coordinator.fast_positions['vac']
        poll.observe({'online':True,'activity':'cleaning'})
        tasks.append(poll.task)
        raise RuntimeError('synthetic setup failure')
    coordinator.async_config_entry_first_refresh = AsyncMock(side_effect=refresh)
    with patch('custom_components.yeedi_vac_max.YeediClient',return_value=client), \
         patch('custom_components.yeedi_vac_max.YeediCoordinator',return_value=coordinator), \
         patch('custom_components.yeedi_vac_max.async_get_clientsession'):
        with pytest.raises(RuntimeError,match='synthetic setup failure'):
            await async_setup_entry(coordinator.hass,entry)
    assert tasks[0].done() and coordinator.fast_positions['vac'].closed


async def test_rate_pause_not_reset_by_active_status_poll(coordinator):
    poll = cycle_setup(coordinator)
    coordinator.client.positions.side_effect = RateLimited('PRIVATE')
    await poll._cycle()
    deadline = poll.next_read
    poll.observe({'online':True,'activity':'returning'})
    assert poll.next_read == deadline and poll.rate_limited
    await poll._cycle()
    coordinator.client.positions.assert_awaited_once()
