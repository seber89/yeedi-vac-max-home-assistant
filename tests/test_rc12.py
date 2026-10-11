"""Synthetic post-docking orientation lifecycle; no real map/position data."""
import json
from types import SimpleNamespace
import pytest
from tests.test_coordinator import coordinator
from tests.test_rc4 import raw_fixture
from custom_components.yeedi_vac_max.map_data import YeediMap, RobotPosition, DockPosition
from custom_components.yeedi_vac_max.image import YeediMapImage
from custom_components.yeedi_vac_max.orientation_evidence import OrientationEvidence
from custom_components.yeedi_vac_max.map_storage import SavedMap
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

MID = 'PRIVATE_MAP'
POS = RobotPosition(-250,150)
DOCK = DockPosition(-250,150)


async def test_post_docking_new_major_keeps_proven_rotation_and_dock(coordinator):
    state = coordinator.spatial['vac']
    state.active_map = YeediMap(MID,None,True)
    state.metadata_valid = True
    state.raw_map = raw_fixture({(3,5)},generation=1)
    state.robot_position = POS
    state.orientation_evidence.record(MID,POS)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image.content_type == 'image/svg+xml'
    assert image._raw_overlay.candidates == {0}
    # Fresh CRC generation and geometry make retained points ambiguous again.
    state.raw_map = raw_fixture({(3,5),(11,3)},generation=2)
    state.robot_position = None
    state.dock_position = DOCK
    image._sync_image()
    assert image.content_type == 'image/svg+xml'
    assert b'id="dock"' in await image.async_image()
    assert b'id="robot"' not in await image.async_image()
    assert state.orientation_evidence.rotation_for(MID) == 0
    assert image.available  # Internal confirmation must not leave a stale key.


def test_rotation_binding_reset_and_clear():
    evidence = OrientationEvidence()
    evidence.record(MID,POS)
    evidence.confirm_rotation(MID,90)
    assert evidence.rotation_for(MID) == 90
    assert evidence.rotation_for('other') is None
    evidence.bind('other')
    assert evidence.rotation_for(MID) is None and evidence.points_for(MID) == ()
    evidence.confirm_rotation('other',270)
    evidence.clear()
    assert evidence.rotation_for('other') is None and evidence.points_for('other') == ()


@pytest.mark.parametrize('angle',[None,True,45,360,'90',90.0])
def test_only_fixed_integer_rotations_can_be_retained(angle):
    evidence = OrientationEvidence()
    evidence.confirm_rotation(MID,angle)
    assert evidence.rotation_for(MID) is None


def install_proven(coordinator):
    state = coordinator.spatial['vac']
    state.active_map = YeediMap(MID,None,True)
    state.metadata_valid = True
    state.raw_map = raw_fixture({(3,5)},generation=1)
    state.robot_position = POS
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert state.orientation_evidence.rotation_for(MID) == 0
    return state,image


async def test_contradictory_new_geometry_rejects_rotation_no_guess(coordinator):
    state,image = install_proven(coordinator)
    # Position now fits 90/180, not the retained 0; no unique replacement.
    state.raw_map = raw_fixture({(11,3),(13,11)},generation=2)
    state.robot_position = None
    state.dock_position = DOCK
    image._sync_image()
    assert state.orientation_evidence.rotation_for(MID) is None
    assert image._raw_overlay.candidates == {90,180}
    assert image.content_type == 'image/png' and image.available


async def test_current_robot_contradiction_cannot_be_overruled_by_dock(coordinator):
    state,image = install_proven(coordinator)
    state.raw_map = raw_fixture({(3,5),(11,3),(11,4),(12,11)},generation=2)
    state.dock_position = DOCK
    # Robot position permits 90/180 only; dock tolerance also admits 180.
    state.robot_position = RobotPosition(-200,150)
    image._sync_image()
    assert state.orientation_evidence.rotation_for(MID) != 0
    assert image._raw_overlay.candidates == {90,180}
    assert image.content_type == 'image/png'


@pytest.mark.parametrize('dock',[None,DockPosition(float('nan'),0),DockPosition(999999,0)])
async def test_missing_invalid_outside_dock_does_not_force_marker(coordinator,dock):
    state,image = install_proven(coordinator)
    state.raw_map = raw_fixture({(3,5),(11,3)},generation=2)
    state.robot_position = None
    state.dock_position = dock
    image._sync_image()
    assert image.available and image.content_type == 'image/png'
    assert await image.async_image() == state.raw_map.png


async def test_map_change_and_unload_erase_rotation_and_points(coordinator):
    state,image = install_proven(coordinator)
    state.orientation_evidence.record(MID,POS)
    await coordinator._confirm_image_map(state,coordinator.robots[0],YeediMap('other',None,True))
    assert state.orientation_evidence.rotation_for(MID) is None
    assert state.orientation_evidence.points_for(MID) == ()
    state.orientation_evidence.record('other',POS)
    state.orientation_evidence.confirm_rotation('other',90)
    await coordinator.async_shutdown()
    assert state.orientation_evidence.rotation_for('other') is None
    assert state.orientation_evidence.points_for('other') == ()


async def test_saved_only_never_projects_retained_rotation(coordinator):
    state,image = install_proven(coordinator)
    saved = SavedMap(MID,state.raw_map.png)
    state.raw_map = None
    state.saved_map = saved
    state.dock_position = DOCK
    state.robot_position = None
    image._sync_image()
    assert image._raw_overlay is None and image.content_type == 'image/png'
    assert await image.async_image() == saved.png
    # Returning real geometry can use RAM confirmation even after PNG fallback.
    state.raw_map = raw_fixture({(3,5),(11,3)},generation=2)
    image._sync_image()
    assert image.content_type == 'image/svg+xml'
    assert b'id="dock"' in await image.async_image()


async def test_rotation_not_confirmed_without_valid_active_map(coordinator):
    state = coordinator.spatial['vac']
    state.raw_map = raw_fixture({(3,5)})
    state.robot_position = POS
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image.content_type == 'image/svg+xml'
    assert state.orientation_evidence.rotation_for(MID) is None


async def test_retention_never_persisted_or_exported(coordinator,caplog):
    state,image = install_proven(coordinator)
    state.orientation_evidence.record(MID,POS)
    assert await coordinator.map_storage.save('vac',SavedMap(MID,state.raw_map.png))
    record = coordinator.map_storage.records['vac']
    assert set(record) == {'map_id','png'}  # Existing private storage schema.
    report = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    exported = json.dumps(report)+caplog.text
    for private in (MID,'-250','150','rotation','orientation','candidates'):
        assert private not in exported


async def test_render_key_stable_after_confirmation_and_invalidation(coordinator):
    state,image = install_proven(coordinator)
    before = image._attr_image_last_updated
    image._sync_image()
    assert image._attr_image_last_updated == before
    state.raw_map = raw_fixture({(11,3),(13,11)},generation=2)
    state.robot_position,state.dock_position = None,DOCK
    image._sync_image()
    assert image.available and state.orientation_evidence.rotation_for(MID) is None
    before = image._attr_image_last_updated
    image._sync_image()
    assert image._attr_image_last_updated == before
