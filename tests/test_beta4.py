"""Synthetic outline-probe contracts, failure isolation and privacy."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from tests.test_stage2 import setup_rooms
from custom_components.yeedi_vac_max.client import (
    YeediClient, Robot, CommandTimeout, CommandRejected, CloudError, MAP_REQUEST_TIMEOUT,
    READ_RETRY_BUDGET)
from custom_components.yeedi_vac_max.map_data import YeediMap, YeediRoom
from custom_components.yeedi_vac_max.structure_diagnostics import OUTLINE_FIELDS, outline_shape
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

ROBOT = Robot('PRIVATE_DEVICE','PRIVATE_RESOURCE','PRIVATE_NAME')


def client():
    c = YeediClient(None,'PRIVATE_ACCOUNT','PRIVATE_PASSWORD','DE','PRIVATE_CLIENT')
    c.authenticate = AsyncMock()
    c.probe_map_transport = AsyncMock()  # New comparison is tested separately.
    c.load_raw_map = AsyncMock(return_value=None)  # Functional loader tested in Beta 6.
    c._request = AsyncMock(return_value={'ret':'ok','resp':{'body':{'data':{}}}})
    return c


async def test_exact_payload_read_only_no_minor_map():
    c = client()
    await c.probe_map_info(ROBOT,'PRIVATE_MAP')
    c._request.assert_awaited_once()
    call = c._request.call_args.kwargs
    assert call['json']['cmdName'] == 'getMapInfo'
    assert call['json']['payload']['body']['data'] == {'mid':'PRIVATE_MAP','type':'ol'}
    assert call['retry'] is True  # Existing read strategy, no probe-level loop.
    assert READ_RETRY_BUDGET < MAP_REQUEST_TIMEOUT <= 40
    assert c.structure_diagnostics(ROBOT)['getMapInfo']['outcome'] == 'accepted_read'
    c._request.reset_mock()
    with pytest.raises(ValueError):
        await c.command(ROBOT,'getMapInfo',writing=True)
    c._request.assert_not_awaited()


@pytest.mark.parametrize('mid',[None,0,False,'0','','  ',' padded ',{},'x'*129])
async def test_invalid_id_never_requests(mid):
    c = client()
    await c.probe_map_info(ROBOT,mid)
    c._request.assert_not_awaited()


@pytest.mark.parametrize('maps',[(),(YeediMap('a',None,False),),
    (YeediMap('a',None,True),YeediMap('b',None,True))])
async def test_no_unambiguous_active_map_no_probe(coordinator,maps):
    coordinator.client.maps.return_value = maps
    await coordinator._spatial_refresh(coordinator.robots[0])
    coordinator.client.probe_map_info.assert_not_awaited()


@pytest.mark.parametrize('error,outcome',[(CommandTimeout,'timeout'),(CommandRejected,'rejected')])
async def test_probe_failure_preserves_rooms_and_cache(coordinator,error,outcome):
    c = client()
    c._request.side_effect = error('PRIVATE_ERROR')
    c.positions = AsyncMock(return_value=(None,None))
    c.maps = AsyncMock(return_value=(YeediMap('PRIVATE_MAP',None,True),))
    c.rooms = AsyncMock(return_value=(YeediRoom('PRIVATE_ROOM','PRIVATE_NAME'),))
    coordinator.client = c
    await coordinator._spatial_refresh(coordinator.robots[0])
    state = coordinator.spatial['vac']
    assert state.metadata_valid and state.rooms_valid and len(coordinator.rooms['vac']) == 1
    assert c.structure_diagnostics(coordinator.robots[0])['getMapInfo']['outcome'] == outcome
    assert c._request.await_count == 1
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert c._request.await_count == 1  # No minute-by-minute or immediate retry.


async def test_probe_after_rooms_including_room_failure(coordinator):
    robot = coordinator.robots[0]
    coordinator.client.maps.return_value = (YeediMap('current',None,True),)
    coordinator.client.rooms.side_effect = CloudError('synthetic')
    await coordinator._spatial_refresh(robot)
    coordinator.client.probe_map_info.assert_awaited_once_with(robot,'current')
    assert coordinator.spatial['vac'].metadata_valid
    assert not coordinator.spatial['vac'].rooms_valid


async def test_room_cleaning_does_not_add_outline_read(coordinator):
    vacuum = setup_rooms(coordinator)
    await vacuum.async_clean_segments(['3'])
    coordinator.client.probe_map_info.assert_not_awaited()
    assert coordinator.client.command.call_args.args[1] == 'clean'


@pytest.mark.parametrize('encoded',[False,True])
async def test_structure_and_export_only_allowed_information(coordinator,caplog,encoded):
    c = client()
    data = {name:87654321 for name in OUTLINE_FIELDS}
    data.update(mid='PRIVATE_MAP',crc='PRIVATE_CRC',value='PRIVATE_PIXEL_CONTENT',
                pieceValue='PRIVATE_PIECE_CONTENT',UNKNOWN_SECRET='PRIVATE_UNKNOWN')
    payload = {'body':{'data':data}}
    c._request.return_value = {'ret':'ok','resp':json.dumps(payload) if encoded else payload}
    coordinator.client = c
    await c.probe_map_info(coordinator.robots[0],'PRIVATE_MAP')
    exported = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    text = json.dumps(exported)+caplog.text
    assert 'PRIVATE' not in text and '87654321' not in text and 'UNKNOWN_SECRET' not in text
    probe = exported['structure_probe'][0]['getMapInfo']
    assert probe['response_received'] and probe['command_success']
    shape = probe['levels']['resp.body.data']
    assert shape['type'] == 'object' and shape['keys'] == sorted(OUTLINE_FIELDS)
    assert shape['fields']['width'] == {'present':True,'type':'number'}
    for name in ('value','pieceValue'):
        assert shape['fields'][name] == {'present':True,'type':'string','empty':False,'length_bucket':'1-64'}


@pytest.mark.parametrize('value,bucket',[('', '0'),('x'*65,'65-256'),('x'*257,'257-1024'),
    ('x'*1025,'1025-4096'),('x'*4097,'>4096')])
def test_value_buckets_no_content(value,bucket):
    result = outline_shape({'value':value,'pieceValue':value})['fields']
    assert result['value'] == result['pieceValue'] == {
        'present':True,'type':'string','empty':not value,'length_bucket':bucket}
    assert set(result['value']) == {'present','type','empty','length_bucket'}


@pytest.mark.parametrize('value',[None,[],{},3,True])
def test_unexpected_value_type_safe(value):
    shape = outline_shape({'value':value})['fields']
    assert set(shape['value']) == {'present','type'}
    assert shape['pieceValue'] == {'present':False,'type':'null'}


async def test_cancel_propagates_and_is_structurally_recorded():
    c = client()
    c._request.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await c.probe_map_info(ROBOT,'map')
    assert c.structure_diagnostics(ROBOT)['getMapInfo']['outcome'] == 'cancelled_or_budget_expired'
