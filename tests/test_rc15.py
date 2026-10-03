"""Original marker recovery and consensus regressions on synthetic geometry."""
import pytest
from types import SimpleNamespace
from tests.test_coordinator import coordinator
from tests.test_rc4 import raw_fixture
from custom_components.yeedi_vac_max.raw_overlay import RawOverlay
from custom_components.yeedi_vac_max.map_data import RobotPosition, DockPosition, YeediMap
from custom_components.yeedi_vac_max.image import YeediMapImage
from custom_components.yeedi_vac_max.map_storage import SavedMap


def test_conflicting_observations_do_not_poison_next_valid_position():
    overlay = RawOverlay(raw_fixture({(3,5),(4,5)}))
    robot = RobotPosition(-250,150)
    dock = DockPosition(-100,-250)
    overlay.render(robot,dock)
    assert overlay.candidates  # Conflict is not proof that every orientation is invalid.
    svg,content = overlay.render(robot,None)
    assert content == 'image/svg+xml' and b'id="robot"' in svg
    assert overlay.candidates == {0}


def test_ambiguous_rotation_identical_center_projection_draws_without_angle():
    overlay = RawOverlay(raw_fixture({(8,8)}))
    svg,content = overlay.render(RobotPosition(0,0),DockPosition(0,0))
    assert overlay.candidates == {0,90,180,270}
    assert content == 'image/svg+xml'
    assert b'id="robot"' in svg and b'id="dock"' in svg


async def test_position_listener_updates_and_missing_position_recovery(coordinator):
    state = coordinator.spatial['vac']
    state.raw_map = raw_fixture({(3,5),(4,5)})
    state.active_map = YeediMap('PRIVATE_MAP',None,True)
    state.metadata_valid = True
    state.robot_position = RobotPosition(-250,150)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    image.async_write_ha_state = lambda: None
    remove = coordinator.async_add_listener(image._handle_coordinator_update)
    first = await image.async_image()
    state.robot_position = RobotPosition(-200,150)
    coordinator.async_update_listeners()
    second = await image.async_image()
    assert b'id="robot"' in first and b'id="robot"' in second and first != second
    state.robot_position = None
    coordinator.async_update_listeners()
    assert image.available and b'id="robot"' not in await image.async_image()
    state.robot_position = RobotPosition(-250,150)
    coordinator.async_update_listeners()
    assert b'id="robot"' in await image.async_image()
    coordinator.client.load_raw_map.assert_not_awaited()
    remove()


@pytest.mark.parametrize('position',[None,RobotPosition(float('nan'),0),RobotPosition(99999,99999)])
def test_missing_invalid_outside_keeps_base_map(position):
    raw = raw_fixture({(3,5)})
    assert RawOverlay(raw).render(position,None) == (raw.png,'image/png')


def test_distinct_ambiguous_robot_but_consensus_dock():
    overlay = RawOverlay(raw_fixture({(3,5),(11,3),(13,11),(5,13),(8,8)}))
    svg,content = overlay.render(RobotPosition(-250,150),DockPosition(0,0))
    assert content == 'image/svg+xml' and b'id="dock"' in svg
    assert b'id="robot"' not in svg and len(overlay.candidates) == 4


def test_unique_robot_and_dock():
    overlay = RawOverlay(raw_fixture({(3,5)}))
    svg,content = overlay.render(RobotPosition(-250,150),DockPosition(-250,150))
    assert content == 'image/svg+xml'
    assert b'id="robot"' in svg and b'id="dock"' in svg


def test_legacy_empty_candidates_recover():
    overlay = RawOverlay(raw_fixture({(3,5)}))
    overlay.candidates.clear()
    assert b'id="robot"' in overlay.render(RobotPosition(-250,150),None)[0]


async def test_wrong_retained_angle_falls_back_to_current_unique_geometry(coordinator):
    state = coordinator.spatial['vac']
    state.active_map = YeediMap('PRIVATE_MAP',None,True)
    state.metadata_valid = True
    state.orientation_evidence.confirm_rotation('PRIVATE_MAP',180)
    state.raw_map = raw_fixture({(3,5)})
    state.robot_position = RobotPosition(-250,150)
    state.dock_position = DockPosition(-250,150)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image._raw_overlay.candidates == {0}
    assert b'id="robot"' in await image.async_image()
    assert b'id="dock"' in await image.async_image()
    state.raw_map = raw_fixture({(11,3)},generation=2)
    image._sync_image()
    assert image._raw_overlay.candidates == {90}
    assert b'id="robot"' in await image.async_image()


async def test_saved_only_no_overlay(coordinator):
    state = coordinator.spatial['vac']
    state.saved_map = SavedMap('PRIVATE_MAP',raw_fixture().png)
    state.robot_position = RobotPosition(0,0)
    state.dock_position = DockPosition(0,0)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image.content_type == 'image/png'
    assert await image.async_image() == state.saved_map.png


async def test_actual_fast_cycle_notifies_image_without_map_io(coordinator,monkeypatch):
    from custom_components.yeedi_vac_max import fast_position
    clock = [100.0]
    monkeypatch.setattr(fast_position,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    state = coordinator.spatial['vac']
    state.active_map = YeediMap('PRIVATE_MAP',None,True)
    state.metadata_valid = True
    state.raw_map = raw_fixture({(3,5),(4,5)})
    image = YeediMapImage(coordinator,coordinator.robots[0])
    image.async_write_ha_state = lambda:None
    remove = coordinator.async_add_listener(image._handle_coordinator_update)
    poll = coordinator.fast_positions['vac']
    poll.wanted = True
    images = []
    for position in (RobotPosition(-250,150),RobotPosition(-200,150),None,RobotPosition(-250,150)):
        coordinator.client.positions.return_value = (position,DockPosition(-250,150))
        await poll._cycle()
        images.append(await image.async_image())
        clock[0] += 5
    assert images[0] != images[1]
    assert all(b'id="robot"' in images[i] for i in (0,1,3))
    assert b'id="robot"' not in images[2]
    assert all(b'id="dock"' in svg for svg in images)
    assert coordinator.client.positions.await_count == 4
    assert all(call.kwargs == {'retry':False} for call in coordinator.client.positions.await_args_list)
    coordinator.client.load_raw_map.assert_not_awaited()
    coordinator.client.maps.assert_not_awaited()
    coordinator.client.rooms.assert_not_awaited()
    remove()
