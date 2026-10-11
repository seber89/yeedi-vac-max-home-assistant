"""Synthetic zero-cell projection regressions; no real device/map data."""
import pytest
from tests.test_rc4 import raw_fixture
from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max.raw_overlay import RawOverlay
from custom_components.yeedi_vac_max.map_data import RobotPosition, DockPosition, YeediMap
from custom_components.yeedi_vac_max.image import YeediMapImage


def hole_map():
    return raw_fixture({(3,5),(7,5),(3,9),(7,9)})


def resolved_overlay():
    overlay = RawOverlay(hole_map())
    overlay.render(RobotPosition(-250,150),None)
    assert overlay.candidates == {0}
    return overlay


def test_robot_on_zero_cell_after_proven_rotation():
    overlay = resolved_overlay()
    assert overlay._raster[7*16+5] == 0
    svg,kind = overlay.render(RobotPosition(-150,50),None)
    assert kind == 'image/svg+xml' and b'id="robot"' in svg


def test_nonzero_zero_nonzero_movement():
    overlay = resolved_overlay()
    images = [overlay.render(p,None)[0] for p in
              (RobotPosition(-250,150),RobotPosition(-150,50),RobotPosition(-50,-50))]
    assert all(b'id="robot"' in image for image in images)
    assert len(set(images)) == 3


def test_dock_and_robot_on_zero_cells():
    overlay = resolved_overlay()
    svg,kind = overlay.render(RobotPosition(-150,50),DockPosition(-150,50))
    assert kind == 'image/svg+xml'
    assert b'id="robot"' in svg and b'id="dock"' in svg


def test_retained_rotation_can_anchor_zero_cell_dock():
    overlay = RawOverlay(hole_map())
    assert overlay.check_retained_rotation(0,None,DockPosition(-150,50),()) is True


@pytest.mark.parametrize('position',[
    None,RobotPosition(float('nan'),0),RobotPosition(float('inf'),0),
    RobotPosition(999999,0),RobotPosition(-400,0),RobotPosition(-300,50)])
def test_invalid_major_or_crop_outside_hidden(position):
    overlay = resolved_overlay()
    image,kind = overlay.render(position,None)
    assert kind == 'image/png' and image == overlay.raw.png


def test_zero_cell_cannot_resolve_rotation():
    overlay = RawOverlay(raw_fixture({(3,3),(12,12)}))
    svg,kind = overlay.render(RobotPosition(-50,100),None)
    assert overlay.candidates == {0,90,180,270}
    assert kind == 'image/png' and svg == overlay.raw.png


def test_identical_zero_cell_projection_without_angle():
    overlay = RawOverlay(raw_fixture({(3,3),(12,12)}))
    assert overlay._raster[8*16+8] == 0
    svg,kind = overlay.render(RobotPosition(0,0),DockPosition(0,0))
    assert overlay.candidates == {0,90,180,270}
    assert kind == 'image/svg+xml'
    assert b'id="robot"' in svg and b'id="dock"' in svg


async def test_fresh_same_map_retention_with_zero_dock_and_listener(coordinator):
    state = coordinator.spatial['vac']
    state.active_map = YeediMap('PRIVATE_MAP',None,True)
    state.metadata_valid = True
    state.raw_map = hole_map()
    state.robot_position = RobotPosition(-250,150)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert state.orientation_evidence.rotation_for('PRIVATE_MAP') == 0
    state.raw_map = raw_fixture({(3,5),(7,5),(3,9),(7,9)},generation=2)
    state.robot_position = RobotPosition(-150,50)
    state.dock_position = DockPosition(-150,50)
    image.async_write_ha_state = lambda:None
    remove = coordinator.async_add_listener(image._handle_coordinator_update)
    coordinator.async_update_listeners()
    svg = await image.async_image()
    assert b'id="robot"' in svg and b'id="dock"' in svg
    assert image.available
    coordinator.client.load_raw_map.assert_not_awaited()
    remove()
