"""Original synthetic position overlays; no real map data or foreign fixtures."""
import base64
from dataclasses import FrozenInstanceError
import json
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from tests.test_coordinator import coordinator
from tests.test_beta6 import install_raw
from tests.test_beta64 import raster, png_pixels
from custom_components.yeedi_vac_max.raw_map import Major, display_geometry, _display_raster, _encode_png
from custom_components.yeedi_vac_max.raw_overlay import marker_position
from custom_components.yeedi_vac_max.map_data import RobotPosition, DockPosition
from custom_components.yeedi_vac_max.image import YeediMapImage
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.parametrize("pixel", [10, 25, 50, 100])
def test_center_axes_resolution_crop_padding_scale(pixel):
    major = Major("private", 20, 1, pixel, (1,))
    source = raster(20, 5, 6, 10, 8)
    g = display_geometry(source, 20)
    assert (g.left,g.top,g.padding,g.scale) == (5,6,1,8)
    assert marker_position(RobotPosition(0,0),major,g) == (48,40)
    assert marker_position(RobotPosition(pixel,0),major,g) == (56,40)
    assert marker_position(DockPosition(0,pixel),major,g) == (48,32)
    assert _display_raster(source,20)[:2] == (g.width,g.height)
    assert png_pixels(_encode_png(source,20)) == _display_raster(source,20)
    with pytest.raises(FrozenInstanceError):
        g.left = 0


@pytest.mark.parametrize("position", [None, {}, RobotPosition(float("nan"),0),
    RobotPosition(float("inf"),0), RobotPosition("private",0), RobotPosition(True,0),
    RobotPosition(10000,0), DockPosition(-10000,0), RobotPosition(-90,0),
    RobotPosition(10**400,0)])
def test_invalid_or_outside_marker_omitted(position):
    g = display_geometry(raster(20,5,6,10,8),20)
    assert marker_position(position,Major("private",20,1,10,(1,)),g) is None


async def test_position_only_update_and_stationary_dock_no_reassembly(coordinator,monkeypatch):
    from custom_components.yeedi_vac_max import raw_overlay
    state = await install_raw(coordinator)
    state.robot_position = RobotPosition(0,0)
    state.dock_position = DockPosition(-50,-50)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    first = await image.async_image()
    first_updated = image.image_last_updated
    dock = ET.fromstring(first).find(".//*[@id='dock']").attrib
    def forbidden(*args):
        raise AssertionError("Position update rebuilt raster")
    monkeypatch.setattr(raw_overlay,"assemble",forbidden)
    state.robot_position = RobotPosition(25,0,180)
    image._sync_image()
    second = await image.async_image()
    assert first != second and image.image_last_updated >= first_updated
    assert ET.fromstring(second).find(".//*[@id='dock']").attrib == dock
    assert ET.fromstring(second).find(".//*[@id='robot']").get("cx") == "28.000"
    state.dock_position = DockPosition(0,-50)
    image._sync_image()
    assert await image.async_image() != second
    stable = await image.async_image()
    image._sync_image()
    assert await image.async_image() is stable
    assert not coordinator.client.mock_calls


@pytest.mark.parametrize("robot,dock", [(None,None),(RobotPosition(0,0),None),
    (None,DockPosition(0,0)),(RobotPosition(999999,0),DockPosition(0,0)),
    (RobotPosition(float("nan"),0),None)])
async def test_optional_markers_keep_map_and_private_diagnostics(coordinator,caplog,robot,dock):
    state = await install_raw(coordinator)
    state.robot_position,state.dock_position = robot,dock
    image = YeediMapImage(coordinator,coordinator.robots[0])
    output = await image.async_image()
    assert image.available and not state.rooms
    if image.content_type == "image/svg+xml":
        svg = ET.fromstring(output)
        assert svg.find(".//*[@id='robot']") is not None if robot == RobotPosition(0,0) else svg.find(".//*[@id='robot']") is None
        embedded = svg.find("{http://www.w3.org/2000/svg}image").get("href")
        assert base64.b64decode(embedded.split(",",1)[1]) == state.raw_map.png
        assert all("on" != key[:2] for node in svg.iter() for key in node.attrib)
        assert not any(tag in output for tag in (b"<script",b"foreignObject",b"rotate",b"PRIVATE"))
    else:
        assert output == state.raw_map.png
    report = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    assert "999999" not in json.dumps(report)+caplog.text
    assert not any(k in json.dumps(report) for k in ("coordinates","pieceIndex","PRIVATE","<svg"))
