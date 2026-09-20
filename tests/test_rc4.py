"""Original lifecycle and orientation fixtures; no live map contents."""
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import xml.etree.ElementTree as ET

import pytest

from tests.test_coordinator import coordinator
from tests.test_beta6 import install_raw
from custom_components.yeedi_vac_max.raw_map import Major, RawMap, render_png
from custom_components.yeedi_vac_max.raw_overlay import RawOverlay, source_position
from custom_components.yeedi_vac_max.map_data import RobotPosition, DockPosition
from custom_components.yeedi_vac_max.image import YeediMapImage
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics


def raw_fixture(points=None, generation=1, pixel=50):
    side = 16
    if points is None:
        points = {(x,y) for x in range(2,6) for y in range(4,8)}
    piece = bytes(int((x,side-1-y) in points) for x in range(side) for y in range(side))
    major = Major("PRIVATE_MAP",side,1,pixel,(generation,))
    return RawMap(major,(piece,),render_png(major,(piece,)))


@pytest.mark.parametrize("activity", ["cleaning","paused","returning"])
async def test_active_background_retained_positions_still_polled(coordinator,activity):
    state = await install_raw(coordinator)
    before = state.raw_map
    state.next_raw_refresh = 0
    coordinator.client.snapshot.return_value = {"online":True,"activity":activity}
    coordinator.client.positions.return_value = (RobotPosition(1,2),DockPosition(3,4))
    await coordinator._poll_robot(coordinator.robots[0])
    assert state.raw_map is before and state.robot_position == RobotPosition(1,2)
    coordinator.client.prepare_raw_map.assert_not_awaited()
    coordinator.client.load_raw_map.assert_not_awaited()


async def test_no_background_loads_during_cleaning(coordinator):
    state = await install_raw(coordinator)
    replacement = state.raw_map
    state.raw_map = None
    state.next_raw_refresh = 0
    coordinator.client.snapshot.return_value = {"online":True,"activity":"cleaning"}
    coordinator.client.load_raw_map.return_value = replacement
    await coordinator._poll_robot(coordinator.robots[0])
    assert state.raw_map is replacement
    coordinator.client.prepare_raw_map.assert_awaited_once()
    coordinator.client.load_raw_map.assert_awaited_once()


@pytest.mark.parametrize("failure", [False,True])
async def test_docking_edge_once_atomic_replacement_or_retention(coordinator,failure):
    state = await install_raw(coordinator)
    old = state.raw_map
    replacement = raw_fixture()
    coordinator.client.snapshot.side_effect = [
        {"online":True,"activity":activity} for activity in ("returning","docked","docked","docked")]
    async def load(*args):
        assert state.raw_map is old
        assert args[2] is None  # Fresh pieces, not the prior cached generation.
        if failure:
            raise RuntimeError("PRIVATE")
        return replacement
    coordinator.client.load_raw_map.side_effect = load
    for _ in range(4):
        result = await coordinator._poll_robot(coordinator.robots[0])
        assert result["online"]
    coordinator.client.load_raw_map.assert_awaited_once()
    coordinator.client.prepare_raw_map.assert_awaited_once()
    assert state.raw_map is (old if failure else replacement)
    assert state.raw_valid_until > time.monotonic()


@pytest.mark.parametrize("angle,expected",[(0,(11,6)),(90,(10,11)),(180,(5,10)),(270,(6,5))])
@pytest.mark.parametrize("pixel",[10,25,100])
def test_quarter_turns_use_actual_resolution(angle,expected,pixel):
    assert source_position(RobotPosition(3*pixel,2*pixel),Major("x",16,1,pixel,(1,)),angle) == expected


def test_ambiguous_then_unique_accumulates_candidates():
    overlay = RawOverlay(raw_fixture({(3,5),(11,3),(4,5)}))
    assert overlay.render(RobotPosition(-250,150),None)[1] == "image/png"
    assert overlay.candidates == {0,90}
    data,kind = overlay.render(RobotPosition(-200,150),None)
    assert kind == "image/svg+xml" and overlay.candidates == {0}
    assert ET.fromstring(data).find(".//*[@id='robot']") is not None


def test_bounding_box_hole_not_evidence_and_invalid_does_not_narrow():
    overlay = RawOverlay(raw_fixture({(2,4),(5,7)}))
    before = set(overlay.candidates)
    for position in (None,RobotPosition(float("nan"),0),RobotPosition(-250,150),RobotPosition(999999,0)):
        assert overlay.render(position,None)[1] == "image/png"
        assert overlay.candidates == before


def test_dock_tolerance_and_independent_marker():
    overlay = RawOverlay(raw_fixture())
    data,kind = overlay.render(RobotPosition(-250,150),DockPosition(-350,150))
    assert kind == "image/svg+xml" and overlay.candidates == {0}
    svg = ET.fromstring(data)
    assert svg.find(".//*[@id='dock']") is not None
    assert svg.find(".//*[@id='robot']") is not None
    data,_ = overlay.render(RobotPosition(999999,0),DockPosition(-350,150))
    assert ET.fromstring(data).find(".//*[@id='dock']") is not None
    assert ET.fromstring(data).find(".//*[@id='robot']") is None


@pytest.mark.parametrize("angle,point",[(0,(3,5)),(90,(11,3)),(180,(13,11)),(270,(5,13))])
def test_each_orientation_can_be_uniquely_selected(angle,point):
    overlay = RawOverlay(raw_fixture({point}))
    assert overlay.render(RobotPosition(-250,150),None)[1] == "image/svg+xml"
    assert overlay.candidates == {angle}


def test_conflicting_observations_do_not_choose_orientation():
    overlay = RawOverlay(raw_fixture({(3,5),(10,6)}))
    data,kind = overlay.render(RobotPosition(-100,100),DockPosition(-250,150))
    assert kind == "image/png"
    assert data == overlay.raw.png


async def test_initial_docked_is_not_a_transition(coordinator):
    state = await install_raw(coordinator)
    coordinator.client.snapshot.return_value = {"online":True,"activity":"docked"}
    await coordinator._poll_robot(coordinator.robots[0])
    coordinator.client.load_raw_map.assert_not_awaited()


async def test_generation_reset_and_privacy(coordinator,caplog):
    state = await install_raw(coordinator)
    state.raw_map = raw_fixture()
    state.robot_position = RobotPosition(-250,150)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image._raw_overlay.candidates == {0}
    state.raw_map = raw_fixture({(3,5),(11,3),(13,11),(5,13)},generation=2)
    image._sync_image()
    assert image.available and image.content_type == "image/png"
    assert image._raw_overlay.candidates == {0,90,180,270}
    report = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    text = json.dumps(report)+caplog.text
    for private in ("PRIVATE","-250","150","candidates","history","rotation"):
        assert private not in text
