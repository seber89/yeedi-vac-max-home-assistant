"""Independently generated transport fixtures, no real map/credential values."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max.client import YeediClient, Robot, CommandTimeout, CommandRejected, RateLimited
from custom_components.yeedi_vac_max import client as module
from custom_components.yeedi_vac_max.transport_diagnostics import (
    EMPTY_PIECE, piece_indices, major_shape, minor_shape)
from custom_components.yeedi_vac_max.map_data import YeediMap, YeediRoom
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

ROBOT = Robot('PRIVATE_DEVICE','PRIVATE_RESOURCE','PRIVATE_NAME')


def envelope(data):
    return {'ret':'ok','resp':{'body':{'data':data}}}


def client(value='101,202,303', mid='PRIVATE_MAP'):
    c = YeediClient(None,'PRIVATE_ACCOUNT','PRIVATE_PASSWORD','DE','PRIVATE_CLIENT')
    c.authenticate = AsyncMock()
    c._request = AsyncMock(side_effect=[envelope({'mid':mid,'value':value}),
        envelope({'mid':mid,'pieceIndex':1,'pieceValue':'PRIVATE_BINARY'}),
        envelope({'mid':mid,'pieceIndex':2,'pieceValue':'PRIVATE_BINARY'})])
    return c


@pytest.mark.parametrize('value', [None,'',[],{},123,'123','1,,2','1,','-1,2',
    '1.0,2','x,y','١,٢','4294967296,1','x'*8193,','.join(['1']*257)])
async def test_bad_piece_list_never_invents_requests(value):
    c = client(value)
    await c.probe_map_transport(ROBOT,'PRIVATE_MAP')
    assert c._request.await_count == 1
    assert piece_indices(value) is None
    assert not c.transport_diagnostics(ROBOT)['map_transport_probe']['direct_major_map']['piece_list_detected']


def test_indices_are_positions_excluding_only_evidenced_empty_crc():
    assert piece_indices(f'{EMPTY_PIECE},101,{EMPTY_PIECE},202,303') == (1,3)
    assert piece_indices(f'{EMPTY_PIECE},{EMPTY_PIECE}') == ()
    assert piece_indices(f'{EMPTY_PIECE},101') == (1,)
    assert piece_indices(' 101 , 202 ') == (0,1)


async def test_two_distinct_pieces_and_exact_requests():
    c = client(f'{EMPTY_PIECE},101,{EMPTY_PIECE},202,303')
    await c.probe_map_transport(ROBOT,'PRIVATE_MAP')
    calls = c._request.call_args_list
    assert len(calls) == 3
    assert calls[0].kwargs['json']['cmdName'] == 'getMajorMap'
    assert calls[0].kwargs['retry'] is False  # Preserve existing legacy strategy.
    for call,index in zip(calls[1:],(1,3),strict=True):
        assert call.kwargs['json']['cmdName'] == 'getMinorMap'
        assert call.kwargs['json']['payload']['body']['data'] == {
            'mid':'PRIVATE_MAP','pieceIndex':index,'type':'ol'}
        assert call.kwargs['retry'] is True
    result = c.transport_diagnostics(ROBOT)
    minor = result['direct_minor_map_probe']
    assert minor['attempted_count'] == minor['response_count'] == minor['accepted_count'] == 2
    assert len(minor['formats']) == 1 and minor['formats'][0]['count'] == 2
    assert result['map_transport_probe']['direct_minor_map']['nonempty_payload_seen']
    assert not result['mqtt_map_probe']['connection_attempted']
    assert not result['mqtt_map_probe']['protocol_verified']


@pytest.mark.parametrize('mid',[None,'','0',' padded ',1,True])
async def test_invalid_current_id_no_probe(mid):
    c = client()
    await c.probe_map_transport(ROBOT,mid)
    c._request.assert_not_awaited()


async def test_changed_or_missing_map_cannot_select_pieces():
    for mid in ('OTHER_MAP',None):
        c = client(mid=mid)
        await c.probe_map_transport(ROBOT,'PRIVATE_MAP')
        assert c._request.await_count == 1
        assert not c.transport_diagnostics(ROBOT)['map_transport_probe']['direct_major_map']['usable_structure']


@pytest.mark.parametrize('error,key',[(CommandTimeout,'timeout_count'),(CommandRejected,'rejected_count')])
async def test_failures_isolated_two_attempts_max(error,key):
    c = client()
    c._request.side_effect = [envelope({'mid':'PRIVATE_MAP','value':'101,202'}),error('PRIVATE'),error('PRIVATE')]
    await c.probe_map_transport(ROBOT,'PRIVATE_MAP')
    minor = c.transport_diagnostics(ROBOT)['direct_minor_map_probe']
    assert minor[key] == minor['attempted_count'] == 2 and minor['accepted_count'] == 0
    assert c._request.await_count == 3


async def test_real_rejection_counts_received_response():
    c = client()
    c._request.side_effect = [envelope({'mid':'PRIVATE_MAP','value':f'{EMPTY_PIECE},101'}),
        {'ret':'fail','errno':1}]
    await c.probe_map_transport(ROBOT,'PRIVATE_MAP')
    minor = c.transport_diagnostics(ROBOT)['direct_minor_map_probe']
    assert minor['attempted_count'] == minor['response_count'] == minor['rejected_count'] == 1


async def test_busy_stops_second_piece():
    c = client()
    c._request.side_effect = [envelope({'mid':'PRIVATE_MAP','value':'101,202'}),RateLimited('PRIVATE')]
    await c.probe_map_transport(ROBOT,'PRIVATE_MAP')
    assert c._request.await_count == 2


@pytest.mark.parametrize('value,seen',[('',False),('PRIVATE_DATA',True),(None,False),({},False)])
async def test_nonempty_only_means_payload_not_decoder(value,seen):
    c = client()
    c._request.side_effect = [envelope({'mid':'PRIVATE_MAP','value':f'101,{EMPTY_PIECE}'}),
        envelope({'mid':'PRIVATE_MAP','value':value})]
    await c.probe_map_transport(ROBOT,'PRIVATE_MAP')
    assert c.transport_diagnostics(ROBOT)['map_transport_probe']['direct_minor_map']['nonempty_payload_seen'] == seen


async def test_privacy_complete_export_and_reset(coordinator,caplog):
    c = client('456789012,345678901')
    coordinator.client = c
    await c.probe_map_transport(coordinator.robots[0],'PRIVATE_MAP')
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    text = json.dumps(output)+caplog.text
    for secret in ('PRIVATE','456789012','345678901','iot/','@ecouser'):
        assert secret not in text
    shape = output['direct_minor_map_probe'][0]['formats'][0]['format']
    assert shape['fields']['pieceIndex'] == {'present':True,'type':'number'}
    assert shape['fields']['pieceValue']['length_bucket'] == '1-64'
    copy = c.transport_diagnostics(coordinator.robots[0])
    copy['direct_minor_map_probe']['formats'].clear()
    assert c.transport_diagnostics(coordinator.robots[0])['direct_minor_map_probe']['formats']
    c.close()
    assert not c._transport


def test_major_flags_only_and_no_tokens():
    shape = major_shape({'mid':'PRIVATE','pieceWidth':87654321,'value':'123456789,987654321'})
    value = shape['fields']['value']
    assert value['all_tokens_decimal'] and value['has_multiple_tokens'] and value['contains_comma']
    assert value['token_count_bucket'] == '2-8' and value['length_bucket'] == '1-64'
    assert shape['fields']['pieceWidth'] == {'present':True,'type':'number'}
    assert all(s not in json.dumps(shape) for s in ('PRIVATE','87654321','123456789','987654321'))
    assert major_shape({'value':''})['fields']['value']['token_count_bucket'] == '0'
    assert minor_shape({'pieceValue':'AAAA=='})['fields']['pieceValue']['base64_charset_only']
    assert minor_shape({'value':'aaff'})['fields']['value']['hex_charset_only']


async def test_total_budget_and_external_cancel(monkeypatch):
    c = client()
    async def request(*args,**kwargs):
        if kwargs['json']['cmdName'] == 'getMajorMap':
            return envelope({'mid':'PRIVATE_MAP','value':'101,202'})
        await asyncio.sleep(10)
    c._request.side_effect = request
    monkeypatch.setattr(module,'TRANSPORT_PROBE_TIMEOUT',.02)
    await c.probe_map_transport(ROBOT,'PRIVATE_MAP')
    minor = c.transport_diagnostics(ROBOT)['direct_minor_map_probe']
    assert minor['attempted_count'] == minor['timeout_count'] == 1
    c._request.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await c.probe_map_transport(ROBOT,'PRIVATE_MAP')


async def test_optional_path_does_not_break_coordinator(coordinator):
    c = client()
    c._request.side_effect = CommandTimeout('PRIVATE')
    c.snapshot = AsyncMock(return_value={'online':True,'activity':'docked'})
    c.maps = AsyncMock(return_value=(YeediMap('PRIVATE_MAP',None,True),))
    c.rooms = AsyncMock(return_value=(YeediRoom('room','Synthetic'),))
    c.positions = AsyncMock(return_value=(None,None))
    coordinator.client = c
    assert (await coordinator._async_update_data())['vac']['online']
    assert coordinator.spatial['vac'].rooms_valid and coordinator.rooms['vac']
    assert [call.kwargs['json']['cmdName'] for call in c._request.call_args_list] == ['getMapInfo','getMajorMap']


async def test_no_minor_writes():
    c = client()
    with pytest.raises(ValueError):
        await c.command(ROBOT,'getMinorMap',writing=True)
    c.authenticate.assert_not_awaited()
    c._request.assert_not_awaited()
