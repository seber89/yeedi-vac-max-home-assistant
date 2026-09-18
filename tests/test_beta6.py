"""Original tiny synthetic rasters; no vendor/fork fixtures or hardware contents."""
import asyncio
import base64
import json
import lzma
import struct
import time
import zlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max import client as module
from custom_components.yeedi_vac_max.client import YeediClient, Robot, CommandTimeout, CommandRejected
from custom_components.yeedi_vac_max.raw_map import (
    MapFormatError, MapChanged, RawMap, EMPTY_PIECE, parse_major, decode_piece,
    assemble, render_png, safe_status, MAX_ENCODED)
from custom_components.yeedi_vac_max.map_data import YeediMap
from custom_components.yeedi_vac_max.image import YeediMapImage
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

MID = 'PRIVATE_MAP'
ROBOT = Robot('PRIVATE_DEVICE','PRIVATE_RESOURCE','PRIVATE_NAME')


def major(**changes):
    return dict(mid=MID,pieceWidth=2,pieceHeight=2,cellWidth=2,cellHeight=2,
                pixel=50,value=f'11,{EMPTY_PIECE},33,44') | changes


def encoded(pixels=b'\x01\x02\x03\x00', size=None):
    # Construct our own legacy wire header from a stdlib-created synthetic stream.
    stream = lzma.compress(pixels, format=lzma.FORMAT_ALONE, preset=0)
    wire = stream[:5] + struct.pack('<I',len(pixels) if size is None else size) + stream[13:]
    return base64.b64encode(wire).decode('ascii')


def minor(index, **changes):
    return dict(mid=MID,type='ol',pieceIndex=index,pieceValue=encoded()) | changes


def client(data=None):
    c = YeediClient(None,'PRIVATE_ACCOUNT','PRIVATE_PASSWORD','DE','PRIVATE_CLIENT')
    c.authenticate = AsyncMock()
    async def response(robot, name, payload=None, **kwargs):
        if name == 'getMajorMap':
            return {'data':data if data is not None else major()}
        assert name == 'getMinorMap' and kwargs == {}
        assert payload['mid'] == MID and payload['type'] == 'ol'
        return {'data':minor(payload['pieceIndex'])}
    c.command = AsyncMock(side_effect=response)
    return c


@pytest.mark.parametrize('changes',[
    {'mid':'different'}, {'pieceWidth':0}, {'pieceWidth':True}, {'pieceWidth':257},
    {'pieceWidth':float('nan')}, {'pieceHeight':3}, {'cellWidth':17}, {'cellHeight':3},
    {'pieceWidth':256,'pieceHeight':256,'cellWidth':16,'cellHeight':16},
    {'pixel':0}, {'pixel':float('inf')}, {'pixel':False}, {'pixel':1001},
    {'value':''}, {'value':'1,2'}, {'value':'-1,2,3,4'}, {'value':'1,2,3,4294967296'},
    {'value':[]}, {'value':'x'*8193}, {'cellHeight':None}, {'pieceHeight':1.5},
])
def test_reject_malformed_oversized_major(changes):
    with pytest.raises(MapFormatError):
        parse_major(major(**changes), MID)


def test_major_and_empty_piece_validation():
    m = parse_major(major(),MID)
    assert m.required == (0,2,3) and m.side == 4
    assert parse_major(major(value=','.join([str(EMPTY_PIECE)]*4)),MID).required == ()
    assert MID not in repr(m)


@pytest.mark.parametrize('changes',[
    {'pieceIndex':-1}, {'pieceIndex':True}, {'pieceIndex':1}, {'pieceIndex':4},
    {'mid':'other'}, {'type':'ar'}, {'pieceValue':''}, {'pieceValue':'@@@'},
    {'pieceValue':'x'*(MAX_ENCODED+1)}, {'pieceValue':None},
    {'pieceValue':base64.b64encode(b'not lzma bytes').decode()},
    {'pieceValue':encoded(b'\x01'*3)}, {'pieceValue':encoded(b'\x01'*5,size=4)},
    {'pieceValue':encoded()+'\n'},
])
def test_strict_piece_identity_and_codec(changes):
    with pytest.raises(MapFormatError):
        decode_piece(minor(0,**changes),parse_major(major(),MID),0)


def test_decompression_bounds_truncation_trailing_data_dictionary():
    m = parse_major(major(),MID)
    packed = base64.b64decode(encoded())
    bad = [packed[:-2], packed+b'extra', packed[:1]+struct.pack('<I',1<<30)+packed[5:]]
    for wire in bad:
        with pytest.raises(MapFormatError):
            decode_piece(minor(0,pieceValue=base64.b64encode(wire).decode()),m,0)
    with pytest.raises(MapFormatError):
        decode_piece(minor(1),m,1)  # Unused index is never accepted.


def test_column_major_assembly_and_original_png():
    m = parse_major(major(),MID)
    p = (b'\x01\x02\x03\x00',None,b'\x02'*4,b'\x01'*4)
    raster = assemble(m,p)
    # Tile 0 bottom-left; tile 1 unused top-left; local bytes are x-major.
    assert list(raster) == [0,0,1,1, 0,0,1,1, 2,0,2,2, 1,3,2,2]
    png = render_png(m,p)
    assert png.startswith(b'\x89PNG\r\n\x1a\n') and MID.encode() not in png
    offset, chunks = 8, {}
    while offset < len(png):
        n = struct.unpack('>I',png[offset:offset+4])[0]
        kind, data = png[offset+4:offset+8],png[offset+8:offset+8+n]
        assert zlib.crc32(kind+data) == struct.unpack('>I',png[offset+8+n:offset+12+n])[0]
        chunks[kind] = data
        offset += n+12
    assert set(chunks) == {b'IHDR',b'PLTE',b'IDAT',b'IEND'}
    assert struct.unpack('>II',chunks[b'IHDR'][:8]) == (4,4)
    assert zlib.decompress(chunks[b'IDAT']) == b''.join(b'\0'+raster[i:i+4] for i in range(0,16,4))


def test_incomplete_and_all_empty_no_image():
    m = parse_major(major(),MID)
    with pytest.raises(MapFormatError):
        render_png(m,(b'\x01'*4,None,None,b'\x01'*4))
    with pytest.raises(MapFormatError):
        render_png(parse_major(major(value=','.join([str(EMPTY_PIECE)]*4)),MID),(None,)*4)


async def test_all_required_requests_concurrency_two_and_cached_generation():
    c = client()
    original = c.command.side_effect
    active = peak = 0
    async def response(*args,**kwargs):
        nonlocal active,peak
        if args[1] == 'getMinorMap':
            active += 1
            peak = max(peak,active)
            try:
                await asyncio.sleep(.01)
                return await original(*args,**kwargs)
            finally:
                active -= 1
        return await original(*args,**kwargs)
    c.command.side_effect = response
    status = safe_status()
    result = await c.load_raw_map(ROBOT,MID,None,status)
    assert isinstance(result,RawMap) and status['complete'] and peak == 2 and active == 0
    calls = [x.args[2] for x in c.command.call_args_list if x.args[1] == 'getMinorMap']
    assert sorted(x['pieceIndex'] for x in calls) == [0,2,3]
    c.command.reset_mock()
    assert await c.load_raw_map(ROBOT,MID,result,safe_status()) is result
    assert [x.args[1] for x in c.command.call_args_list] == ['getMajorMap','getMajorMap']


async def test_changed_piece_only_and_map_id_no_reuse():
    c = client()
    previous = await c.load_raw_map(ROBOT,MID,None,safe_status())
    c = client(major(value=f'11,{EMPTY_PIECE},99,44'))
    changed = await c.load_raw_map(ROBOT,MID,previous,safe_status())
    assert changed.major != previous.major
    assert [x.args[2]['pieceIndex'] for x in c.command.call_args_list if x.args[1]=='getMinorMap'] == [2]
    other = RawMap(parse_major(major(mid='OTHER'), 'OTHER'),previous.pieces,previous.png)
    c = client()
    assert await c.load_raw_map(ROBOT,MID,other,safe_status())
    assert len([x for x in c.command.call_args_list if x.args[1]=='getMinorMap']) == 3


@pytest.mark.parametrize('change',[{'mid':'NEW_MAP'},{'value':f'77,{EMPTY_PIECE},33,44'}])
async def test_generation_change_during_build_discarded(change):
    c = client()
    original = c.command.side_effect
    count = 0
    async def response(*args,**kwargs):
        nonlocal count
        if args[1]=='getMajorMap':
            count += 1
            if count == 2:
                return {'data':major(**change)}
        return await original(*args,**kwargs)
    c.command.side_effect = response
    with pytest.raises(MapChanged):
        await c.load_raw_map(ROBOT,MID,None,safe_status())


@pytest.mark.parametrize('error',[CommandTimeout,CommandRejected])
async def test_piece_error_no_incomplete_image_no_retry(error):
    c = client()
    original = c.command.side_effect
    async def response(*args,**kwargs):
        if args[1]=='getMinorMap':
            raise error('PRIVATE')
        return await original(*args,**kwargs)
    c.command.side_effect = response
    assert await c.load_raw_map(ROBOT,MID,None,safe_status()) is None
    assert len([x for x in c.command.call_args_list if x.args[1]=='getMinorMap']) <= 2


async def test_deadline_and_cancellation_cleanup(monkeypatch):
    c = client()
    original = c.command.side_effect
    pending = 0
    async def response(*args,**kwargs):
        nonlocal pending
        if args[1]=='getMinorMap':
            pending += 1
            try:
                await asyncio.sleep(5)
            finally:
                pending -= 1
        return await original(*args,**kwargs)
    c.command.side_effect = response
    monkeypatch.setattr(module,'RAW_MAP_TIMEOUT',.03)
    assert await c.load_raw_map(ROBOT,MID,None,safe_status()) is None
    assert pending == 0
    task = asyncio.create_task(c.load_raw_map(ROBOT,MID,None,safe_status()))
    await asyncio.sleep(.005)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pending == 0


async def install_raw(coordinator):
    c = client()
    raw = await c.load_raw_map(ROBOT,MID,None,safe_status())
    state = coordinator.spatial['vac']
    state.active_map = YeediMap(MID,None,True)
    state.metadata_valid = True
    state.raw_map = raw
    state.raw_valid_until = time.monotonic()+3600
    state.next_map_refresh = state.next_raw_refresh = time.monotonic()+3600
    coordinator.data = {'vac':{'online':True}}
    return state


async def test_raw_image_without_rooms_positions_and_privacy(coordinator,caplog):
    state = await install_raw(coordinator)
    assert not state.rooms_valid and not state.rooms and state.robot_position is None
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image.available and image.content_type == 'image/png'
    assert await image.async_image() == state.raw_map.png
    coordinator.client.assert_not_awaited()
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    text = json.dumps(output)+caplog.text
    for secret in ('PRIVATE','pieceIndex','crcs','png','base64','1295764014'):
        assert secret not in text
    assert output['raw_map'][0]['complete'] and not output['robots'][0]['has_room_polygons']
    state.active_map = YeediMap('NEW',None,True)
    assert await image.async_image() is None
    image._sync_image()
    assert not image.available


async def test_raw_cache_refresh_and_failure_grace(coordinator):
    state = await install_raw(coordinator)
    robot = coordinator.robots[0]
    await coordinator._spatial_refresh(robot)
    coordinator.client.load_raw_map.assert_not_awaited()
    state.next_raw_refresh = 0
    coordinator.client.load_raw_map.side_effect = RuntimeError('PRIVATE')
    await coordinator._spatial_refresh(robot)
    assert state.metadata_valid and state.raw_map and state.raw_valid_until <= time.monotonic()+180
    deadline = state.raw_valid_until
    state.next_raw_refresh = 0
    await coordinator._spatial_refresh(robot)
    assert state.raw_valid_until == deadline
    state.raw_valid_until = 0
    assert not YeediMapImage(coordinator,robot).available


async def test_map_switch_clears_before_loading_and_stale_inflight(coordinator):
    state = await install_raw(coordinator)
    raw = state.raw_map
    coordinator.client.maps.return_value = (YeediMap('NEW',None,True),)
    coordinator.client.rooms.return_value = ()
    async def load(*args):
        assert state.raw_map is None and args[1]=='NEW'
        state.active_map = YeediMap('NEWER',None,True)
        return raw
    coordinator.client.load_raw_map.side_effect = load
    await coordinator._spatial_refresh(coordinator.robots[0],force=True)
    assert state.raw_map is None


async def test_functional_refresh_never_calls_beta5_probe(coordinator):
    c = client()
    original = c.command.side_effect
    async def response(*args,**kwargs):
        if args[1]=='getMapInfo':
            return {'data':{}}
        return await original(*args,**kwargs)
    c.command.side_effect = response
    c.positions = AsyncMock(return_value=(None,None))
    c.maps = AsyncMock(return_value=(YeediMap(MID,None,True),))
    c.rooms = AsyncMock(return_value=())
    c.probe_map_transport = AsyncMock()
    coordinator.client = c
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert coordinator.spatial['vac'].raw_map
    c.probe_map_transport.assert_not_awaited()
    assert len([x for x in c.command.call_args_list if x.args[1]=='getMinorMap']) == 3


async def test_decode_failure_bucket_and_no_cache():
    c = client()
    original = c.command.side_effect
    async def response(*args,**kwargs):
        if args[1]=='getMinorMap':
            return {'data':minor(args[2]['pieceIndex'],pieceValue='@@@')}
        return await original(*args,**kwargs)
    c.command.side_effect = response
    status = safe_status()
    assert await c.load_raw_map(ROBOT,MID,None,status) is None
    assert status['decode_failures_bucket'] != '0' and not status['complete']


async def test_changed_generation_clears_previous_image(coordinator):
    state = await install_raw(coordinator)
    coordinator.client.load_raw_map.side_effect = MapChanged('changed')
    await coordinator._raw_refresh(coordinator.robots[0])
    assert state.raw_map is None and state.raw_valid_until == 0
    assert state.metadata_valid


async def test_raw_refresh_success_and_reload(coordinator):
    state = await install_raw(coordinator)
    coordinator.client.load_raw_map.return_value = state.raw_map
    state.raw_valid_until = 0
    await coordinator._raw_refresh(coordinator.robots[0])
    assert state.raw_valid_until > time.monotonic()+3600
    image = YeediMapImage(coordinator,coordinator.robots[0])
    previous = await image.async_image()
    c = client(major(value=f'11,{EMPTY_PIECE},99,44'))
    state.raw_map = await c.load_raw_map(ROBOT,MID,state.raw_map,safe_status())
    assert await image.async_image() is None  # Until the update callback synchronizes.
    image._sync_image()
    assert await image.async_image() == previous  # Same synthetic pixels, new generation.
    from custom_components.yeedi_vac_max.coordinator import SpatialState
    coordinator.spatial['vac'] = SpatialState()
    assert await image.async_image() is None


async def test_raw_failure_does_not_break_online_or_control(coordinator):
    state = await install_raw(coordinator)
    state.next_raw_refresh = 0
    coordinator.client.load_raw_map.side_effect = RuntimeError('PRIVATE')
    snapshot = await coordinator._async_update_data()
    assert snapshot['vac']['online']
    await coordinator.execute(coordinator.robots[0],'setSuctionPower',{'power':1})
    coordinator.client.command.assert_awaited_once_with(coordinator.robots[0],
        'setSuctionPower',{'power':1},writing=True)


async def test_real_command_path_readonly_and_no_extra_probes():
    c = YeediClient(None,'PRIVATE_ACCOUNT','PRIVATE_PASSWORD','DE','PRIVATE_CLIENT')
    c.authenticate = AsyncMock()
    async def request(*args,**kwargs):
        name = kwargs['json']['cmdName']
        payload = kwargs['json']['payload']['body']['data']
        if name == 'getMajorMap':
            assert not kwargs['retry']
            data = major()
        else:
            assert name == 'getMinorMap' and kwargs['retry']
            assert set(payload) == {'mid','type','pieceIndex'}
            data = minor(payload['pieceIndex'])
        return {'ret':'ok','resp':{'body':{'data':data}}}
    c._request = AsyncMock(side_effect=request)
    assert await c.load_raw_map(ROBOT,MID,None,safe_status())
    assert c._request.await_count == 5  # Two Major generations, three required pieces.


@pytest.mark.parametrize('mid',[None,'0',' padded '])
async def test_invalid_id_no_raw_requests(mid):
    c = client()
    assert await c.load_raw_map(ROBOT,mid,None,safe_status()) is None
    c.command.assert_not_awaited()
