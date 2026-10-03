"""Original synthetic HTTPS historical-image tests; no captured cloud fixtures."""
import asyncio
import json
import struct
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import zlib

import pytest

from tests.test_coordinator import coordinator
from tests.test_rc6 import setup, zero, acquire, ROBOT, MID
from tests.test_rc4 import raw_fixture
from custom_components.yeedi_vac_max import clean_log_map as module
from custom_components.yeedi_vac_max.clean_log_map import (
    CleanLogError, HistoricalMap, latest_image_url, supported_url, validate_png,
    download_png, safe_probe, FLAGS, MAX_BYTES, MAX_RECORDS)
from custom_components.yeedi_vac_max.client import YeediClient, CommandTimeout, CloudError
from custom_components.yeedi_vac_max.map_data import YeediMap, RobotPosition
from custom_components.yeedi_vac_max.map_storage import SavedMap
from custom_components.yeedi_vac_max.image import YeediMapImage
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

URL = 'https://portal-eu.ecouser.net/api/lg/image/SYNTHETIC_PRIVATE'


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def png(color=2, width=2, height=2):
    channels = {2:3, 6:4, 0:1, 4:2}[color]
    rows = (b'\0' + b'\x80' * (width * channels)) * height
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width,height,8,color,0,0,0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


@pytest.mark.parametrize('color', [0,2,4,6])
def test_external_png_types(color):
    validate_png(png(color))


def test_indexed_own_png_also_accepted():
    validate_png(raw_fixture().png)


@pytest.mark.parametrize('blob,category', [
    (b'{}', 'not_png'), (b'<html>private</html>', 'not_png'),
    (b'\x89PNG\r\n\x1a\n', 'invalid_png'),
    (png()[:-1], 'invalid_png'), (png() + b'extra', 'invalid_png'),
    (png()[:29] + b'BAD!' + png()[33:], 'invalid_png'),
    (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB',4097,1,8,2,0,0,0)), 'invalid_png'),
    (b'\x89PNG\r\n\x1a\n' + b'x'*MAX_BYTES, 'too_large'),
    (png()[:8] + chunk(b'IHDR', struct.pack('>IIBBBBB',0,1,8,2,0,0,0)), 'invalid_png'),
], ids=['json','html','empty','truncated','trailing','crc','dimensions','oversized','zero-dimension'])
def test_invalid_images(blob,category):
    with pytest.raises(CleanLogError, match=category):
        validate_png(blob)


@pytest.mark.parametrize('url', [URL, URL.replace('net/', 'net:443/')])
def test_allowed_url(url):
    assert supported_url(url)


@pytest.mark.parametrize('url', [
    URL.replace('https:', 'http:'), URL.replace('portal-eu.ecouser.net','elsewhere.invalid'),
    URL.replace('portal-eu.ecouser.net','127.0.0.1'), URL.replace('portal-eu.ecouser.net','localhost'),
    URL.replace('portal-eu.ecouser.net','user:pass@portal-eu.ecouser.net'),
    URL.replace('net/', 'net:444/'), URL.replace('/api/lg/image/','/api/other/'),
    URL+'#fragment', URL+'?token=private', '\n'+URL, URL+'\n',
    URL.replace('/image/','/image/../'), URL.replace('/image/','/image/%2e%2e/'),
    URL.replace('net/','net./'), URL.replace('net/','net.evil.invalid/'), None, 1,
])
def test_rejected_urls(url):
    assert not supported_url(url)


@pytest.mark.parametrize('response,error', [
    ({'ret':'fail','logs':[]},'portal_rejected'), ({'ret':'ok'},'invalid_response'),
    ({'ret':'ok','logs':{}},'invalid_response'), ({'ret':'ok','logs':[{}]*(MAX_RECORDS+1)},'invalid_response'),
    ({'ret':'ok','logs':[]},'no_records'), ({'ret':'ok','logs':[{'ts':True,'imageUrl':URL}]},'no_image_url'),
    ({'ret':'ok','logs':[{'ts':'200','imageUrl':URL}]},'no_image_url'),
    ({'ret':'ok','logs':[{'ts':2,'imageUrl':''}]},'no_image_url'),
    ({'ret':'ok','logs':[{'ts':0,'imageUrl':URL}]},'no_image_url'), (None,'invalid_response'),
])
def test_strict_log_response(response,error):
    with pytest.raises(CleanLogError, match=error):
        latest_image_url(response,safe_probe())


def test_unsorted_latest_valid_no_recursive_search():
    response = {'ret':'ok','logs':[
        {'ts':200,'imageUrl':URL+'latest'}, {'ts':99,'imageUrl':URL},
        {'ts':300,'imageUrl':None}, {'nested':{'ts':500,'imageUrl':URL}},
        {'ts':200,'imageUrl':URL+'tie'}]}
    probe = safe_probe()
    assert latest_image_url(response,probe) == URL+'latest'
    assert probe['clean_log_records_present'] and probe['clean_log_image_url_present']
    assert URL not in json.dumps(probe)


async def test_exact_client_request_reuses_auth():
    client = YeediClient(None,'private','secret','DE','resource')
    client.authenticate = AsyncMock()
    client._request = AsyncMock(return_value={'ret':'ok','logs':[{'ts':42,'imageUrl':URL}]})
    assert await client.clean_logs(ROBOT,safe_probe()) == URL
    client._request.assert_awaited_once_with('POST','https://portal-eu.ecouser.net/api/lg/log.do?cv=1.94.76&t=a&av=1.3.0',
        retry=True,json={'auth':client._auth(),'td':'GetCleanLogs','did':ROBOT.did,'country':'DE','resource':ROBOT.resource})


@pytest.mark.parametrize('error,result', [(CommandTimeout,'portal_timeout'),(TimeoutError,'portal_timeout'),
                                         (CloudError,'portal_rejected')])
async def test_client_portal_errors_safe(error,result):
    client = YeediClient(None,'private','secret','DE','resource')
    client.authenticate = AsyncMock()
    client._request = AsyncMock(side_effect=error('PRIVATE'))
    with pytest.raises(CleanLogError,match=result) as caught:
        await client.clean_logs(ROBOT,safe_probe())
    assert 'PRIVATE' not in str(caught.value)


class Download:
    def __init__(self, payload=None, status=200, length=None, error=None):
        self.payload = png() if payload is None else payload
        self.status, self.content_length, self.error = status, length, error
        self.content = self
        self.calls = []
        self.closed = False
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return self
    async def __aenter__(self):
        return self
    async def __aexit__(self,*args):
        self.closed = True
    async def iter_chunked(self,size):
        if self.error:
            raise self.error
        for start in range(0,len(self.payload),size):
            yield self.payload[start:start+size]


async def test_download_no_redirect_no_credentials_normal_tls():
    session = Download()
    probe = safe_probe()
    assert await download_png(session,URL,probe) == png()
    kwargs = session.calls[0][1]
    assert kwargs['allow_redirects'] is False and kwargs['timeout'].total == 15
    assert kwargs['auto_decompress'] is False
    assert not {'ssl','verify_ssl','headers','auth'} & kwargs.keys()
    assert session.closed and probe['clean_log_png_valid']


@pytest.mark.parametrize('session,error', [
    (Download(status=302),'download_rejected'), (Download(status=403),'download_rejected'),
    (Download(length=MAX_BYTES+1),'too_large'), (Download(payload=b'x'*(MAX_BYTES+1)),'too_large'),
    (Download(payload=b'{}'),'not_png'), (Download(error=TimeoutError('PRIVATE')),'download_timeout'),
])
async def test_download_failures(session,error):
    with pytest.raises(CleanLogError,match=error):
        await download_png(session,URL,safe_probe())
    assert session.closed and len(session.calls) == 1


async def test_unsupported_url_never_requests():
    session = Download()
    with pytest.raises(CleanLogError,match='unsupported_image_url'):
        await download_png(session,'http://localhost/private',safe_probe())
    assert not session.calls


def fallback_setup(coordinator):
    state = setup(coordinator)
    coordinator.client.load_raw_map.side_effect = zero
    coordinator.client.clean_logs.return_value = URL
    coordinator.client.clean_log_image.return_value = png()
    return state


async def test_zero_build_one_readonly_fallback_no_store(coordinator):
    state = fallback_setup(coordinator)
    coordinator.map_storage.save = AsyncMock()
    await acquire(coordinator)
    await acquire(coordinator)
    assert state.historical_image and not state.raw_map and not state.saved_map
    coordinator.client.clean_logs.assert_awaited_once()
    coordinator.client.clean_log_image.assert_awaited_once()
    coordinator.client.reactivate_map.assert_not_awaited()
    coordinator.client.current_yeedi_map_id.assert_not_awaited()
    coordinator.map_storage.save.assert_not_awaited()
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image.available and image.content_type == 'image/png'
    assert await image.async_image() == png()
    key = image._render_key
    state.robot_position = RobotPosition(100,200)
    image._sync_image()
    assert image._render_key == key and image._raw_overlay is None


@pytest.mark.parametrize('cache',['raw','saved','persisted'])
async def test_good_cache_never_falls_back(coordinator,cache):
    state = fallback_setup(coordinator)
    if cache == 'raw':
        state.raw_map = raw_fixture()
    elif cache == 'saved':
        state.saved_map = SavedMap(MID,raw_fixture().png)
    else:
        state.has_persisted_map = True
    await acquire(coordinator)
    coordinator.client.clean_logs.assert_not_awaited()
    coordinator.client.reactivate_map.assert_not_awaited()


async def test_direct_success_never_calls_fallback(coordinator):
    fallback_setup(coordinator)
    coordinator.client.load_raw_map.side_effect = None
    coordinator.client.load_raw_map.return_value = raw_fixture()
    await acquire(coordinator)
    coordinator.client.clean_logs.assert_not_awaited()


@pytest.mark.parametrize('field,value',[('major_valid',False),('generation_verified',False),
    ('raster_assembled',False),('decode_failures_bucket','1'),('failure_stage','piece_decode')])
async def test_only_verified_zero_qualifies(coordinator,field,value):
    fallback_setup(coordinator)
    async def fail(*args):
        zero(*args)
        args[3][field] = value
    coordinator.client.load_raw_map.side_effect = fail
    await acquire(coordinator)
    coordinator.client.clean_logs.assert_not_awaited()


@pytest.mark.parametrize('phase',['log','image'])
async def test_map_change_discards_result(coordinator,phase):
    state = fallback_setup(coordinator)
    async def change(*args):
        state.active_map = YeediMap('OTHER',None,True)
        return URL if phase == 'log' else png()
    getattr(coordinator.client,'clean_logs' if phase == 'log' else 'clean_log_image').side_effect = change
    await acquire(coordinator)
    assert state.clean_log_map is None and state.clean_log_probe['error'] == 'map_changed'
    if phase == 'log':
        coordinator.client.clean_log_image.assert_not_awaited()


async def test_confirmed_map_change_clears_ram_image(coordinator):
    state = fallback_setup(coordinator)
    await acquire(coordinator)
    await coordinator._confirm_image_map(state,coordinator.robots[0],YeediMap('OTHER',None,True))
    assert state.clean_log_map is None


@pytest.mark.parametrize('phase',['log','image'])
async def test_failure_isolated_backoff_and_privacy(coordinator,phase,caplog):
    state = fallback_setup(coordinator)
    coordinator.client.maps.return_value = (state.active_map,)
    coordinator.client.rooms.return_value = ()
    getattr(coordinator.client,'clean_logs' if phase == 'log' else 'clean_log_image').side_effect = CleanLogError('portal_timeout')
    await coordinator.async_refresh()
    await acquire(coordinator)
    assert coordinator.last_update_success and state.metadata_valid and state.rooms_valid
    assert state.next_clean_log_attempt > time.monotonic()+170
    coordinator.client.clean_logs.assert_awaited_once()
    assert state.historical_image is None
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    assert 'PRIVATE' not in json.dumps(output)+caplog.text


@pytest.mark.parametrize('cache',['raw','saved'])
async def test_image_priority(coordinator,cache):
    state = fallback_setup(coordinator)
    state.clean_log_map = HistoricalMap(MID,png())
    raw = raw_fixture()
    if cache == 'raw':
        state.raw_map = raw
    else:
        state.saved_map = SavedMap(MID,raw.png)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert image._render_key[0] == cache and await image.async_image() == raw.png


async def test_all_diagnostics_allowlisted(coordinator,caplog):
    state = fallback_setup(coordinator)
    await acquire(coordinator)
    state.clean_log_probe.update({key:'PRIVATE' for key in FLAGS})
    state.clean_log_probe.update(url=URL,ts=123456789,raw=png(),error=URL)
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    probe = output['clean_log_map'][0]
    assert set(probe) == set(FLAGS) | {'error'}
    assert probe['error'] == 'unexpected'
    assert all(type(value) is bool for key,value in probe.items() if key != 'error')
    text = json.dumps(output)+caplog.text
    for private in (URL,MID,ROBOT.did,'PRIVATE','123456789','imageUrl'):
        assert private not in text


async def test_cancellation_propagates_and_no_partial_image(coordinator):
    state = fallback_setup(coordinator)
    coordinator.client.clean_log_image.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await acquire(coordinator)
    assert state.clean_log_map is None


async def test_metadata_invalidated_during_download(coordinator):
    state = fallback_setup(coordinator)
    async def change(*args):
        state.metadata_valid = False
        return png()
    coordinator.client.clean_log_image.side_effect = change
    await acquire(coordinator)
    assert state.clean_log_map is None and state.clean_log_probe['error'] == 'map_changed'


async def test_portal_total_budget(monkeypatch):
    from custom_components.yeedi_vac_max import client as client_module
    monkeypatch.setattr(client_module,'READ_RETRY_BUDGET',-3.99)
    client = YeediClient(None,'private','secret','DE','resource')
    async def blocked():
        await asyncio.Event().wait()
    client.authenticate = AsyncMock(side_effect=blocked)
    with pytest.raises(CleanLogError,match='portal_timeout'):
        await client.clean_logs(ROBOT,safe_probe())


async def test_download_total_budget(monkeypatch):
    monkeypatch.setattr(module,'DOWNLOAD_TIMEOUT',0.01)
    class Blocked(Download):
        async def iter_chunked(self,size):
            await asyncio.Event().wait()
            yield b''
    session = Blocked()
    with pytest.raises(CleanLogError,match='download_timeout'):
        await download_png(session,URL,safe_probe())
    assert session.closed


async def test_retry_only_after_full_backoff(coordinator):
    state = fallback_setup(coordinator)
    coordinator.client.clean_logs.side_effect = CleanLogError('portal_timeout')
    await acquire(coordinator)
    await acquire(coordinator)
    coordinator.client.clean_logs.assert_awaited_once()
    state.next_clean_log_attempt = time.monotonic()-1
    await acquire(coordinator)
    assert coordinator.client.clean_logs.await_count == 2
    coordinator.client.reactivate_map.assert_not_awaited()
