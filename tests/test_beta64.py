"""Synthetic visual-only regressions; no hardware map or coordinate fixtures."""
import json
import base64
import xml.etree.ElementTree as ET
import struct
import time
import zlib
from types import SimpleNamespace

import pytest

from tests.test_coordinator import coordinator
from tests.test_beta6 import install_raw, client, ROBOT, MID
from custom_components.yeedi_vac_max.raw_map import (
    _display_raster, _encode_png, MAX_DISPLAY_SIDE, MAX_DISPLAY_SCALE, MapFormatError)
from custom_components.yeedi_vac_max.map_data import RobotPosition, DockPosition, YeediMap
from custom_components.yeedi_vac_max.coordinator import SpatialState
from custom_components.yeedi_vac_max.image import YeediMapImage
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics
from custom_components.yeedi_vac_max.raw_map import safe_status


def raster(side, left, top, width, height, color=1):
    data = bytearray(side * side)
    for y in range(top, top + height):
        data[y*side+left:y*side+left+width] = bytes([color]) * width
    return bytes(data)


def png_pixels(png):
    offset, chunks = 8, {}
    assert png[:8] == b'\x89PNG\r\n\x1a\n'
    while offset < len(png):
        size = int.from_bytes(png[offset:offset+4], 'big')
        kind = png[offset+4:offset+8]
        body = png[offset+8:offset+8+size]
        crc = int.from_bytes(png[offset+8+size:offset+12+size], 'big')
        assert crc == zlib.crc32(kind + body)
        chunks[kind] = body
        offset += 12 + size
    assert set(chunks) == {b'IHDR', b'PLTE', b'IDAT', b'IEND'}
    w,h,depth,color,compression,filtering,interlace = struct.unpack('>IIBBBBB', chunks[b'IHDR'])
    assert (depth,color,compression,filtering,interlace) == (8,3,0,0,0)
    raw = zlib.decompress(chunks[b'IDAT'])
    assert len(raw) == (w+1)*h
    assert all(raw[y*(w+1)] == 0 for y in range(h))
    return w,h,b''.join(raw[y*(w+1)+1:(y+1)*(w+1)] for y in range(h))


@pytest.mark.parametrize('x,y', [(0,0),(123,56),(502,496)])
def test_crop_padding_small_geometry_at_grid_edges(x,y):
    source = raster(512,x,y,10,16)
    w,h,pixels = _display_raster(source,512)
    assert (w,h) == (96,144)  # 10x16 visible + 1 cell each side, scale 8.
    assert sum(bool(p) for p in pixels) == 10*16*64
    assert not any(pixels[:w*8]) and not any(pixels[-w*8:])
    assert all(not any(pixels[y*w:y*w+8] + pixels[(y+1)*w-8:(y+1)*w]) for y in range(h))
    assert len(source) == 512*512 and sum(source) == 160


def test_translation_does_not_change_visual():
    assert _encode_png(raster(256,0,0,12,10),256) == _encode_png(raster(256,200,180,12,10),256)


@pytest.mark.parametrize('side', [1,2,16,40,80,160,320,512,1024])
def test_scale_and_output_are_bounded(side):
    w,h,pixels = _display_raster(bytes([1]) * side**2, side)
    assert w == h <= MAX_DISPLAY_SIDE
    visible_count = sum(bool(p) for p in pixels)
    scale = round((visible_count / side**2)**.5)
    assert 1 <= scale <= MAX_DISPLAY_SCALE
    assert visible_count == side**2 * scale**2
    if side >= 320:
        assert scale == 1  # No unnecessary inflation or lossy downsampling.
    elif side >= 40:
        assert side*scale >= 320


@pytest.mark.parametrize('width,height', [(1,1024),(1024,1),(200,400)])
def test_aspect_ratio_and_thin_geometry_preserved(width,height):
    w,h,pixels = _display_raster(raster(1024,0,0,width,height,2),1024)
    assert max(w,h) <= MAX_DISPLAY_SIDE
    assert sum(p == 2 for p in pixels) == width*height


@pytest.mark.parametrize('color', [1,2,3,4,5])
def test_each_renderable_color_survives_nearest_neighbor(color):
    source = raster(64,30,30,3,2,color)
    w,h,pixels = png_pixels(_encode_png(source,64))
    assert (w,h) == (40,32)
    assert set(pixels) == {0,color}
    assert sum(p == color for p in pixels) == 3*2*64


@pytest.mark.parametrize('side,data', [(0,b''), (2,b'\1'), (True,b'\1'), (1025,b''),
                                     (2,b'\0'*4), (2,[1]*4)])
def test_empty_or_invalid_display_rejected(side,data):
    with pytest.raises(MapFormatError):
        _display_raster(data,side)


@pytest.mark.parametrize('robot,dock', [(None,None), (RobotPosition(0,0),None),
    (None,DockPosition(100,100)), (RobotPosition(-100,20,45),DockPosition(10,80))])
async def test_raw_image_without_polygons_preserves_png_under_overlay(coordinator,robot,dock):
    state = await install_raw(coordinator)
    state.robot_position, state.dock_position = robot,dock
    assert not any(room.polygon for room in state.rooms)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image.available
    output = await image.async_image()
    if image.content_type == 'image/svg+xml':
        embedded = ET.fromstring(output).find('{http://www.w3.org/2000/svg}image')
        output = base64.b64decode(embedded.attrib['href'].split(',',1)[1])
    assert output == state.raw_map.png
    w,h,pixels = png_pixels(output)
    assert (w,h) == (48,48) and set(pixels) <= {0,1,2,3,4,5}
    assert image.unique_id == 'vac_map'
    assert not coordinator.client.mock_calls


async def test_reload_restores_image_from_fresh_valid_map(coordinator):
    state = await install_raw(coordinator)
    before = await YeediMapImage(coordinator,coordinator.robots[0]).async_image()
    coordinator.spatial['vac'] = SpatialState()
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert not image.available  # No invented persistent cache after restart.
    fresh = await client().load_raw_map(ROBOT,MID,None,safe_status())
    coordinator.client.maps.return_value = (YeediMap(MID,None,True),)
    coordinator.client.rooms.return_value = ()
    coordinator.client.load_raw_map.return_value = fresh
    await coordinator._spatial_refresh(coordinator.robots[0], force=True)
    image._sync_image()
    assert image.available and await image.async_image() == before


async def test_temporary_error_keeps_same_map_with_existing_grace(coordinator):
    state = await install_raw(coordinator)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    before = await image.async_image()
    coordinator.client.load_raw_map.side_effect = RuntimeError('PRIVATE')
    await coordinator._raw_refresh(coordinator.robots[0])
    image._sync_image()
    assert image.available and await image.async_image() == before
    assert time.monotonic() < state.raw_valid_until <= time.monotonic()+180
    state.active_map = YeediMap('different',None,True)
    assert await image.async_image() is None


async def test_visual_privacy_no_new_sensitive_fields(coordinator,caplog):
    state = await install_raw(coordinator)
    result = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    text = json.dumps(result) + caplog.text
    for value in ('PRIVATE', 'crop_bounds', 'output_width', 'output_height', 'pixel_values'):
        assert value not in text
    assert MID.encode() not in state.raw_map.png
    assert 'raw_map_visual' not in result  # No extra diagnostic payload needed.
