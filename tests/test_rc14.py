"""Original synthetic pixel, generation and composition evidence; no cloud fixtures."""
import json
import zlib
from types import SimpleNamespace

import pytest
from tests.test_beta6 import client, major, minor, encoded, MID, ROBOT
from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max.raw_map import (
    parse_major, decode_piece, assemble, render_png, safe_status, safe_visibility,
    MapRenderError, MapFormatError, visibility_bucket, _display_raster)
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics


def cloud(pixels, metadata=None):
    c = client(metadata)
    original = c.command.side_effect
    async def response(robot, name, data=None, **kwargs):
        if name == 'getMinorMap':
            return {'data': minor(data['pieceIndex'], pieceValue=encoded(pixels[data['pieceIndex']]))}
        return await original(robot, name, data, **kwargs)
    c.command.side_effect = response
    return c


@pytest.mark.parametrize('value', [1,2,3,4,5,10,11,50,51,255])
async def test_visible_bytes_survive_decode_assembly_crop_png(value):
    pixels = {0: bytes([value,0,0,0]), 2: bytes(4), 3: bytes(4)}
    c = cloud(pixels)
    status = safe_status()
    result = await c.load_raw_map(ROBOT, MID, None, status)
    assert result and result.pieces[0] == pixels[0]
    raster = assemble(result.major, result.pieces)
    assert sum(bool(x) for x in raster) == 1
    width, height, display = _display_raster(raster, result.major.side)
    assert any(display) and len(display) == width * height
    # Validate the actually generated indexed PNG scanlines, not just a flag.
    offset = 8
    compressed = b''
    while offset < len(result.png):
        length = int.from_bytes(result.png[offset:offset+4], 'big')
        if result.png[offset+4:offset+8] == b'IDAT':
            compressed += result.png[offset+8:offset+8+length]
        offset += 12 + length
    scanlines = zlib.decompress(compressed)
    assert b''.join(scanlines[y*(width+1)+1:(y+1)*(width+1)] for y in range(height)) == display
    probe = status['raw_visibility']
    assert probe['pieces_with_visible_pixels_bucket'] == probe['decoded_piece_visible_bucket'] == '1'
    assert probe['decoded_piece_empty_bucket'] == '2-3'
    assert probe['composition_has_visible_pixels_before_crop']
    assert probe['composition_has_visible_pixels_after_crop']
    assert probe['composition_result'] == 'success'


async def test_nonempty_encoded_zero_pieces_are_valid_but_not_visible():
    c = cloud({i: bytes(4) for i in (0,2,3)})
    status = safe_status()
    assert await c.load_raw_map(ROBOT, MID, None, status) is None
    assert status['generation_verified'] and status['raster_assembled']
    assert not status['complete'] and status['failure_stage'] == 'no_visible_pixels'
    probe = status['raw_visibility']
    assert probe['source_piece_nonempty_bucket'] == probe['decoded_piece_empty_bucket'] == '2-3'
    assert probe['pieces_with_visible_pixels_bucket'] == '0'
    assert probe['pieces_without_visible_pixels_bucket'] == '2-3'
    assert probe['composition_canvas_valid'] and probe['composition_attempted']
    assert not probe['composition_has_visible_pixels_before_crop']
    assert not probe['composition_has_visible_pixels_after_crop']
    assert probe['composition_result'] == 'no_visible_pixels'
    assert c.command.await_count == 5  # Two Major reads, exactly three required pieces.


def test_every_nonzero_palette_byte_survives_without_alpha_conversion():
    m = parse_major(major(pieceWidth=16,pieceHeight=16,cellWidth=1,cellHeight=1,value='11'), MID)
    pixels = bytes(range(256))
    decoded = decode_piece(minor(0,pieceValue=encoded(pixels)), m, 0)
    assert decoded == pixels
    raster = assemble(m, (decoded,))
    assert sum(bool(p) for p in raster) == 255
    assert any(_display_raster(raster,m.side)[2])


@pytest.mark.parametrize('index', [0,2,3])
def test_piece_at_each_grid_edge_is_not_lost(index):
    m = parse_major(major(), MID)
    pieces = [bytes(4),None,bytes(4),bytes(4)]
    pieces[index] = b'\x00\x00\x00\xff'
    probe = safe_visibility()
    assert render_png(m,tuple(pieces),probe)
    assert probe['composition_has_visible_pixels_after_crop']


@pytest.mark.parametrize('changes', [{'pieceWidth':-1}, {'cellHeight':-1}, {'pieceHeight':3}])
def test_negative_or_non_square_bounds_not_guessed(changes):
    with pytest.raises(MapFormatError):
        parse_major(major(**changes), MID)


async def test_changed_crc_downloads_only_changed_slot():
    pixels = {0:b'\x01'*4,2:bytes(4),3:bytes(4)}
    previous = await cloud(pixels).load_raw_map(ROBOT,MID,None,safe_status())
    c = cloud({0:b'\x02'*4}, major(value='99,1295764014,33,44'))
    status = safe_status()
    result = await c.load_raw_map(ROBOT,MID,previous,status)
    assert result.pieces[0] == b'\x02'*4 and result.pieces[2:] == previous.pieces[2:]
    assert [call.args[2]['pieceIndex'] for call in c.command.call_args_list if call.args[1]=='getMinorMap'] == [0]
    assert status['raw_visibility']['reused_piece_bucket'] == '2-3'
    assert status['raw_visibility']['freshly_loaded_piece_bucket'] == '1'


async def test_same_generation_normal_reuses_but_fresh_reads_cloud():
    pixels = {i:b'\x01'*4 for i in (0,2,3)}
    previous = await cloud(pixels).load_raw_map(ROBOT,MID,None,safe_status())
    c = cloud({i:bytes(4) for i in (0,2,3)})
    normal = safe_status()
    assert await c.load_raw_map(ROBOT,MID,previous,normal) is previous
    assert c.command.await_count == 2
    assert normal['raw_visibility']['composition_result'] == 'reused_image'
    assert not normal['raw_visibility']['composition_attempted']
    c.command.reset_mock()
    fresh = safe_status()
    assert await c.load_raw_map(ROBOT,MID,None,fresh) is None
    assert c.command.await_count == 5
    assert fresh['failure_stage'] == 'no_visible_pixels'
    # Same declared CRC does not prove remote payload consistency; do not invent CRC validation.


async def test_identical_piece_set_fresh_and_normal_images_match():
    c = cloud({i:b'\x04'*4 for i in (0,2,3)})
    first = await c.load_raw_map(ROBOT,MID,None,safe_status())
    normal = await c.load_raw_map(ROBOT,MID,first,safe_status())
    fresh = await c.load_raw_map(ROBOT,MID,None,safe_status())
    assert first.png == normal.png == fresh.png


async def test_diagnostics_do_not_confuse_old_complete_image_with_new_zero_build(coordinator, caplog):
    state = coordinator.spatial['vac']
    state.raw_map = await cloud({i:b'\x01'*4 for i in (0,2,3)}).load_raw_map(ROBOT,MID,None,safe_status())
    status = safe_status()
    await cloud({i:bytes(4) for i in (0,2,3)}).load_raw_map(ROBOT,MID,None,status)
    state.raw_status = status
    before = list(coordinator.client.mock_calls)
    output = await async_get_config_entry_diagnostics(None, SimpleNamespace(runtime_data=coordinator))
    assert output['raw_map'][0]['complete'] and output['raw_map'][0]['available']
    assert not output['raw_map'][0]['image_generated']
    assert output['raw_composition'][0]['composition_result'] == 'no_visible_pixels'
    assert coordinator.client.mock_calls == before
    assert not any(x in json.dumps(output)+caplog.text for x in [MID,'PRIVATE_DEVICE','pieceValue','1295764014'])


async def test_visibility_diagnostics_sanitize_arbitrary_values(coordinator):
    state = coordinator.spatial['vac']
    state.raw_status['raw_visibility'] = {key:'PRIVATE_URL_COORDINATES_TOKEN' for key in safe_visibility()}
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    assert 'PRIVATE' not in json.dumps(output)


@pytest.mark.parametrize('count,bucket',[(0,'0'),(1,'1'),(2,'2-3'),(4,'4-8'),(9,'9-32'),(33,'33-64'),(65,'>64')])
def test_visibility_buckets(count,bucket):
    assert visibility_bucket(count) == bucket
