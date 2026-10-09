"""Synthetic MapSet-scoped msid forwarding and privacy regression tests."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max.client import YeediClient, Robot
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

ROBOT = Robot('PRIVATE_DEVICE', 'PRIVATE_RESOURCE', 'PRIVATE_DEVICE_NAME')


def make_client(msid_fields, value=''):
    client = YeediClient(None, 'PRIVATE_ACCOUNT', 'PRIVATE_PASSWORD', 'DE', 'PRIVATE_CLIENT')
    client.authenticate = AsyncMock()
    bodies = [dict(mid='PRIVATE_MAP', subsets=[{'mssid':'PRIVATE_A'}, {'mssid':'PRIVATE_B'}], **msid_fields)]
    bodies += [dict(mid='PRIVATE_MAP', mssid=rid, name='PRIVATE_NAME', value=value)
               for rid in ('PRIVATE_A','PRIVATE_B')]
    client._request = AsyncMock(side_effect=[{'ret':'ok','resp':{'body':{'data':data}}} for data in bodies])
    return client


@pytest.mark.parametrize('msid,expected', [('PRIVATE_SET','PRIVATE_SET'), (' padded ','padded'), (17,'17'), ('0','0')])
async def test_validated_msid_shared_by_all_detail_requests(msid,expected):
    client = make_client({'msid':msid})
    await client.rooms(ROBOT,'PRIVATE_MAP')
    calls = client._request.call_args_list
    assert calls[0].kwargs['json']['payload']['body']['data'] == {'mid':'PRIVATE_MAP','type':'ar'}
    for call,rid in zip(calls[1:],('PRIVATE_A','PRIVATE_B'),strict=True):
        assert call.kwargs['json']['cmdName'] == 'getMapSubSet'
        assert call.kwargs['json']['payload']['body']['data'] == {
            'mid':'PRIVATE_MAP','type':'ar','mssid':rid,'msid':expected}


@pytest.mark.parametrize('fields', [{}, {'msid':None}, {'msid':''}, {'msid':'  '},
    {'msid':True}, {'msid':{}}, {'msid':[]}, {'msid':1.5}, {'msid':'x'*129}])
async def test_missing_invalid_msid_omitted(fields):
    client = make_client(fields)
    await client.rooms(ROBOT,'PRIVATE_MAP')
    for call in client._request.call_args_list[1:]:
        data = call.kwargs['json']['payload']['body']['data']
        assert set(data) == {'mid','type','mssid'}


@pytest.mark.parametrize('value,has_polygon', [('',False), ('987654,123456;987655,123456;987655,123457',True),
    ('[[987654,123456],[987655,123456],[987655,123457]]',True), ('unknown-format',False)])
async def test_existing_parser_and_private_diagnostics(coordinator,caplog,value,has_polygon):
    client = make_client({'msid':'PRIVATE_SET'},value)
    coordinator.client = client
    rooms = await client.rooms(coordinator.robots[0],'PRIVATE_MAP')
    assert len(rooms) == 2 and all((r.polygon is not None) == has_polygon for r in rooms)
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    text = json.dumps(output)+caplog.text
    for private in ('PRIVATE','987654','123456','unknown-format'):
        assert private not in text


async def test_msid_is_local_to_each_mapset():
    client = make_client({'msid':'FIRST_SET'})
    await client.rooms(ROBOT,'PRIVATE_MAP')
    next_client = make_client({})
    client._request = next_client._request
    await client.rooms(ROBOT,'PRIVATE_MAP')
    assert all('msid' not in call.kwargs['json']['payload']['body']['data']
               for call in client._request.call_args_list[1:])
