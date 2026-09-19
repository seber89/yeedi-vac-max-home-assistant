"""Synthetic final-stage regressions; no hardware pixels or foreign fixtures."""
import json
from types import SimpleNamespace

import pytest

from tests.test_beta6 import client, major, minor, encoded, ROBOT, MID, install_raw
from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max import raw_map as raw
from custom_components.yeedi_vac_max.client import CommandTimeout
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics


def pixel_client(value):
    c = client()
    original = c.command.side_effect
    async def response(*args, **kwargs):
        if args[1] == 'getMinorMap':
            return {'data':minor(args[2]['pieceIndex'],pieceValue=encoded(bytes([value])*4))}
        return await original(*args,**kwargs)
    c.command.side_effect = response
    return c


@pytest.mark.parametrize('value',[1,2,3,4,5,6,7,8,9,10,11,20,21,30,31,40,41,50,51,255])
async def test_nonzero_visible_and_final_flags(value):
    status = raw.safe_status()
    result = await pixel_client(value).load_raw_map(ROBOT,MID,None,status)
    assert result and result.png.startswith(b'\x89PNG')
    assert status['failure_stage'] == 'none'
    assert all(status[k] for k in ('generation_verified','render_attempted','raster_assembled','image_generated'))
    assert status['total_nonzero_pixels_bucket'] == '9-32'
    assert status['known_renderable_pixels_bucket'] == ('0' if 5 <= value <= 10 else '9-32')
    assert status['unhandled_nonzero_pixels_bucket'] == ('9-32' if 5 <= value <= 10 else '0')
    raster = raw.assemble(result.major,result.pieces)
    assert sum(bool(p) for p in raster) == 12
    if value <= 3:
        assert set(raster) == {0,value}


async def test_all_zero_precise_failure():
    status = raw.safe_status()
    assert await pixel_client(0).load_raw_map(ROBOT,MID,None,status) is None
    assert status['failure_stage'] == 'no_visible_pixels'
    assert status['generation_verified'] and status['render_attempted'] and status['raster_assembled']
    assert not status['image_generated'] and status['total_nonzero_pixels_bucket'] == '0'


@pytest.mark.parametrize('change',[{'mid':'OTHER'},{'value':'1,2,3,4'},
                                 {'pieceWidth':3,'pieceHeight':3}])
async def test_generation_change_preserves_guard(change):
    c = client()
    original = c.command.side_effect
    calls = 0
    async def response(*args,**kwargs):
        nonlocal calls
        if args[1] == 'getMajorMap':
            calls += 1
            if calls == 2:
                return {'data':major(**change)}
        return await original(*args,**kwargs)
    c.command.side_effect = response
    status = raw.safe_status()
    with pytest.raises(raw.MapChanged):
        await c.load_raw_map(ROBOT,MID,None,status)
    assert status['failure_stage'] == 'generation_changed'
    assert not any(status[k] for k in ('generation_verified','render_attempted','raster_assembled','image_generated'))


@pytest.mark.parametrize('function,stage,assembled',[
    ('assemble','raster_assembly',False),('_encode_png','png_generation',True)])
async def test_render_failure_differentiation(monkeypatch,function,stage,assembled):
    def fail(*args):
        raise RuntimeError('PRIVATE_PIXEL_CRC_ID')
    monkeypatch.setattr(raw,function,fail)
    status = raw.safe_status()
    assert await client().load_raw_map(ROBOT,MID,None,status) is None
    assert status['failure_stage'] == stage and status['raster_assembled'] is assembled
    assert status['generation_verified'] and status['render_attempted'] and not status['image_generated']
    assert 'PRIVATE' not in json.dumps(status)


@pytest.mark.parametrize('stage',['major_initial','piece_download','piece_decode','unexpected'])
async def test_early_stage_outcomes(stage):
    c = client()
    original = c.command.side_effect
    async def response(*args,**kwargs):
        name = args[1]
        if stage == 'major_initial' and name == 'getMajorMap':
            raise CommandTimeout('PRIVATE')
        if name == 'getMinorMap':
            if stage == 'piece_download':
                raise CommandTimeout('PRIVATE')
            if stage == 'piece_decode':
                return {'data':minor(args[2]['pieceIndex'],pieceValue='@@@')}
            if stage == 'unexpected':
                raise RuntimeError('PRIVATE')
        return await original(*args,**kwargs)
    c.command.side_effect = response
    status = raw.safe_status()
    assert await c.load_raw_map(ROBOT,MID,None,status) is None
    assert status['failure_stage'] == stage and not status['render_attempted']


@pytest.mark.parametrize('count,bucket',[(0,'0'),(1,'1'),(8,'2-8'),(9,'9-32'),
    (64,'33-64'),(65,'65-256'),(256,'65-256'),(257,'257-1024'),(1024,'257-1024'),(1025,'>1024')])
def test_pixel_buckets(count,bucket):
    result = raw.pixel_buckets((bytes([4])*count,None))
    assert result['total_nonzero_pixels_bucket'] == result['known_renderable_pixels_bucket'] == bucket
    assert result['unhandled_nonzero_pixels_bucket'] == '0'


async def test_export_preserves_latest_failure_during_cache_grace(coordinator,caplog):
    state = await install_raw(coordinator)
    status = raw.safe_status()
    await pixel_client(0).load_raw_map(ROBOT,MID,None,status)
    state.raw_status = status
    exported = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    report = exported['raw_map'][0]
    assert report['available'] and report['complete']  # Previous image, not new render.
    assert report['failure_stage'] == 'no_visible_pixels' and not report['image_generated']
    text = json.dumps(exported)+caplog.text
    for secret in (MID,'PRIVATE','1295764014','pieceIndex','crcs','png','pixel_values','histogram'):
        assert secret not in text
