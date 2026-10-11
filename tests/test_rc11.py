"""Original bounded RAM evidence fixtures; no hardware coordinates or maps."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import xml.etree.ElementTree as ET

import pytest

from tests.test_coordinator import coordinator
from tests.test_rc4 import raw_fixture
from custom_components.yeedi_vac_max.orientation_evidence import OrientationEvidence, LIMIT
from custom_components.yeedi_vac_max.map_data import RobotPosition, DockPosition, YeediMap
from custom_components.yeedi_vac_max.raw_overlay import RawOverlay
from custom_components.yeedi_vac_max.map_storage import SavedMap
from custom_components.yeedi_vac_max.image import YeediMapImage
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

MID = 'PRIVATE_MAP'
P1, P2 = RobotPosition(-250, 150), RobotPosition(-200, 150)


def test_buffer_bounded_deduplicated_angle_not_evidence():
    evidence = OrientationEvidence()
    for i in range(40):
        evidence.record(MID, RobotPosition(i, 2*i))
    assert len(evidence.points_for(MID)) == LIMIT
    before = evidence.points_for(MID)
    evidence.record(MID, RobotPosition(39, 78, 90))
    assert evidence.points_for(MID) == before
    assert all(p.angle is None for p in before)


@pytest.mark.parametrize('position', [None, DockPosition(1,2), RobotPosition(float('nan'),0),
    RobotPosition(0,float('inf')), RobotPosition(True,0), RobotPosition('1',2)])
def test_invalid_points_not_retained(position):
    evidence = OrientationEvidence()
    evidence.record(MID, position)
    assert evidence.points_for(MID) == ()


@pytest.mark.parametrize('mid', [None, '', '0', ' padded ', 123])
def test_invalid_map_not_bound(mid):
    evidence = OrientationEvidence()
    evidence.record(mid, P1)
    assert evidence.points_for(mid) == ()


def test_exact_map_binding_and_reset():
    evidence = OrientationEvidence()
    evidence.record(MID, P1)
    assert evidence.points_for('other') == ()
    evidence.bind('other')
    assert evidence.points_for(MID) == ()
    evidence.bind(MID)
    assert evidence.points_for(MID) == ()


def test_points_intersection_resolves_ambiguous_orientation():
    raw = raw_fixture({(3,5),(11,3),(4,5),(12,11)})
    overlay = RawOverlay(raw)
    # Individually {0,90} and {0,180}; only their intersection identifies 0.
    assert {a for a in (0,90,180,270) if overlay._plausible(P1,a,0)} == {0,90}
    assert {a for a in (0,90,180,270) if overlay._plausible(P2,a,0)} == {0,180}
    data, kind = overlay.render(P1, DockPosition(-250,150), (P1,P2))
    assert overlay.candidates == {0} and kind == 'image/svg+xml'
    svg = ET.fromstring(data)
    assert svg.find(".//*[@id='robot']") is not None
    assert svg.find(".//*[@id='dock']") is not None


def test_contradictory_batch_is_ignored_atomically():
    overlay = RawOverlay(raw_fixture({(3,5),(12,11)}))
    data, kind = overlay.render(None,None,(P1,P2,P1))
    assert data == overlay.raw.png and kind == 'image/png'
    assert overlay.candidates == {0,90,180,270}  # No majority/first-point choice.


def test_ambiguous_and_wholly_outside_points_never_guess():
    overlay = RawOverlay(raw_fixture({(3,5),(11,3)}))
    data, kind = overlay.render(None,None,(P1,RobotPosition(999999,0)))
    assert kind == 'image/png' and data == overlay.raw.png
    assert overlay.candidates == {0,90}


def test_current_marker_still_requires_geometry_plausibility():
    overlay = RawOverlay(raw_fixture({(3,5),(11,3),(4,5),(12,11)}))
    data, kind = overlay.render(RobotPosition(999999,0),DockPosition(-250,150),(P1,P2))
    svg = ET.fromstring(data)
    assert kind == 'image/svg+xml' and svg.find(".//*[@id='robot']") is None
    assert svg.find(".//*[@id='dock']") is not None


async def record_fast(coordinator, position, activity='cleaning'):
    poll = coordinator.fast_positions['vac']
    coordinator._remember(coordinator.robots[0], {'online':True,'activity':activity})
    coordinator.client.positions.return_value = (position,DockPosition(-250,150))
    poll.next_read = 0
    await poll._cycle()


async def test_evidence_survives_docking_raw_build_and_saved_map_has_no_overlay(coordinator):
    state = coordinator.spatial['vac']
    raw = raw_fixture({(3,5),(11,3),(4,5),(12,11)})
    state.active_map = YeediMap(MID,None,True)
    state.metadata_valid = True
    state.saved_map = SavedMap(MID,raw.png)
    await record_fast(coordinator,P1)
    await record_fast(coordinator,P2,'returning')
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image.content_type == 'image/png' and await image.async_image() == raw.png
    assert image._raw_overlay is None
    state.next_map_refresh = float('inf')
    coordinator._map_activity['vac'] = 'returning'
    coordinator.client.snapshot.return_value = {'online':True,'activity':'docked'}
    coordinator.client.load_raw_map.return_value = raw
    coordinator.map_storage.save = AsyncMock(return_value=True)
    await coordinator._poll_robot(coordinator.robots[0])
    assert state.orientation_evidence.points_for(MID) == (P1,P2)
    image._sync_image()
    assert image.content_type == 'image/svg+xml'
    assert image._raw_overlay.candidates == {0}
    coordinator.client.load_raw_map.assert_awaited_once()
    coordinator.client.positions.assert_any_await(coordinator.robots[0],retry=False)


async def test_evidence_change_alone_updates_render_key_no_map_reload(coordinator):
    state = coordinator.spatial['vac']
    state.active_map = YeediMap(MID,None,True)
    state.metadata_valid = True
    state.raw_map = raw_fixture({(3,5),(11,3),(4,5),(12,11)})
    state.robot_position, state.dock_position = P1,None
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image.content_type == 'image/png'
    before = image._raw_overlay
    state.orientation_evidence.record(MID,P2)
    image._sync_image()
    assert image._raw_overlay is before and image.content_type == 'image/svg+xml'
    coordinator.client.load_raw_map.assert_not_awaited()


async def test_confirmed_map_change_clears_old_evidence(coordinator):
    state = coordinator.spatial['vac']
    state.orientation_evidence.record(MID,P1)
    await coordinator._confirm_image_map(state,coordinator.robots[0],YeediMap('other',None,True))
    assert state.orientation_evidence.points_for(MID) == ()


async def test_other_map_evidence_never_reaches_overlay(coordinator):
    state = coordinator.spatial['vac']
    state.raw_map = raw_fixture({(3,5),(11,3),(4,5),(12,11)})
    state.orientation_evidence.record('other',P1)
    state.orientation_evidence.record('other',P2)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image.content_type == 'image/png'
    assert image._raw_overlay.candidates == {0,90,180,270}


async def test_new_raw_generation_rechecks_same_map_evidence(coordinator):
    state = coordinator.spatial['vac']
    state.orientation_evidence.record(MID,P1)
    state.orientation_evidence.record(MID,P2)
    state.robot_position = P1
    state.raw_map = raw_fixture({(3,5),(11,3),(4,5),(12,11)},generation=1)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image._raw_overlay.candidates == {0}
    previous = image._raw_overlay
    # Same device-coordinate evidence now uniquely supports rotation 90.
    state.raw_map = raw_fixture({(11,3),(11,4)},generation=2)
    image._sync_image()
    assert image._raw_overlay is not previous
    assert image._raw_overlay.candidates == {90}
    assert image.content_type == 'image/svg+xml'


async def test_metadata_failure_keeps_existing_evidence_but_does_not_add(coordinator):
    state = coordinator.spatial['vac']
    state.active_map = YeediMap(MID,None,True)
    state.orientation_evidence.record(MID,P1)
    state.metadata_valid = False
    await record_fast(coordinator,P2)
    assert state.orientation_evidence.points_for(MID) == (P1,)


async def test_normal_active_position_read_also_records_without_extra_requests(coordinator):
    state = coordinator.spatial['vac']
    state.active_map = YeediMap(MID,None,True)
    state.metadata_valid = True
    state.next_map_refresh = state.next_raw_refresh = float('inf')
    coordinator._remember(coordinator.robots[0],{'online':True,'activity':'returning'})
    coordinator.client.positions.return_value = (P1,None)
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert state.orientation_evidence.points_for(MID) == (P1,)
    coordinator.client.positions.assert_awaited_once_with(coordinator.robots[0])
    coordinator.client.maps.assert_not_awaited()
    coordinator.client.rooms.assert_not_awaited()


async def test_unload_erases_evidence_and_privacy(coordinator,caplog):
    state = coordinator.spatial['vac']
    state.orientation_evidence.record(MID,P1)
    report = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    text = json.dumps(report) + caplog.text
    assert MID not in text and '-250' not in text and '150' not in text
    assert 'orientation_evidence' not in text
    await coordinator.async_shutdown()
    assert state.orientation_evidence.points_for(MID) == ()
