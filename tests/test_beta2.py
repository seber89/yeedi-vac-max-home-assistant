"""Synthetic format-only diagnostics; never hardware response fixtures."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max.client import YeediClient, Robot
from custom_components.yeedi_vac_max.geometry_diagnostics import value_format, aggregate_formats
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.parametrize('value,kind', [('[987654,123456]', 'array'),
    ('{"PRIVATE_NAME":987654}', 'object'), ('"PRIVATE_STRING"','string'),
    ('123456','number'), ('true','boolean'), ('null','null')])
def test_json_type_only(value,kind):
    result = value_format(value)
    assert result['valid_json'] and result['json_top_level_type'] == kind
    exported = json.dumps(result)
    assert 'PRIVATE' not in exported and '987654' not in exported and '123456' not in exported
    assert value not in exported or value in ('true','null')


@pytest.mark.parametrize('size,bucket', [(0,'0'),(1,'1-64'),(64,'1-64'),
    (65,'65-256'),(256,'65-256'),(257,'257-1024'),(1024,'257-1024'),
    (1025,'1025-4096'),(4096,'1025-4096'),(4097,'>4096')])
def test_length_buckets_not_exact(size,bucket):
    result = value_format('x'*size)
    assert result['length_bucket'] == bucket
    assert 'length' not in result
    assert all(type(v) in (str,bool) for v in result.values())


def test_existing_xy_and_syntax_only_encodings():
    xy = value_format('-17,21;31,-43;57,69')
    assert xy['matches_existing_xy_semicolon_format']
    assert xy['contains_comma'] and xy['contains_semicolon'] and not xy['valid_json']
    base64 = value_format('U1lOVEhFVElDX1BSSVZBVEU=')
    assert base64['base64_charset_only'] and base64['length_multiple_of_4']
    assert not base64['hex_charset_only'] and not base64['valid_json']
    assert value_format('deadBEEF09')['hex_charset_only']
    # Charset-only means no claim of valid encoding/padding or compression.
    assert value_format('===A')['base64_charset_only']
    assert not value_format('é')['ascii_only']
    assert value_format(' \n[1,2]')['starts_with_array_marker']
    assert value_format('\t{"x":1}')['starts_with_object_marker']


@pytest.mark.parametrize('value', [None,{},[],False,123,object(),'{oops',
    '['*2000, 'NaN', 'Infinity'])
def test_unexpected_or_malformed_safe(value):
    result = value_format(value)
    json.dumps(result)
    if isinstance(value,str):
        assert not result['valid_json']
    else:
        assert set(result) == {'present','type'}
    assert value_format(present=False) == {'present':False,'type':'null'}


def test_deduplicate_shapes_not_values():
    a = value_format('PRIVATE_A')
    b = value_format('PRIVATE_B')
    result = aggregate_formats([a,b])
    assert result == {'value_count':2,'polygon_count':0,'all_same_shape':True,
                      'formats':[{'count':2,'format':a}]}
    assert 'PRIVATE' not in json.dumps(result)
    assert not aggregate_formats([])['all_same_shape']


async def test_real_room_path_aggregate_export_no_values(coordinator,caplog):
    client = YeediClient(None,'PRIVATE_ACCOUNT','PRIVATE_PASSWORD','DE','PRIVATE_CLIENT')
    coordinator.client = client
    robot = coordinator.robots[0]
    client.command = AsyncMock(side_effect=[
        {'data':{'mid':'PRIVATE_MAP','subsets':[{'mssid':'PRIVATE_ROOM_A'},{'mssid':'PRIVATE_ROOM_B'}]}},
        {'data':{'mid':'PRIVATE_MAP','mssid':'PRIVATE_ROOM_A','name':'PRIVATE_NAME_A',
                 'value':'[[987654,123456],[987655,123456],[987655,123457]]'}},
        {'data':{'mid':'PRIVATE_MAP','mssid':'PRIVATE_ROOM_B','name':'PRIVATE_NAME_B',
                 'value':'[[987664,123466],[987665,123466],[987665,123467]]'}}])
    rooms = await client.rooms(robot,'PRIVATE_MAP')
    assert len(rooms) == 2 and all(r.polygon for r in rooms)
    assert [call.args[1] for call in client.command.call_args_list] == ['getMapSet','getMapSubSet','getMapSubSet']
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    probe = output['room_geometry_probe'][0]
    assert probe['value_count'] == probe['polygon_count'] == 2
    assert probe['all_same_shape'] and len(probe['formats']) == 1
    assert probe['formats'][0]['count'] == 2
    exported = json.dumps(output)+json.dumps(client._geometry)+caplog.text
    for token in ('PRIVATE_MAP','PRIVATE_ROOM','PRIVATE_NAME','987654','123456','987664','123466'):
        assert token not in exported
    copy = client.geometry_diagnostics(robot)
    copy['formats'].clear()
    assert client.geometry_diagnostics(robot)['formats']
    client.command.side_effect = [{'data':{'subsets':[]}}]
    await client.rooms(robot,'PRIVATE_MAP')
    assert client.geometry_diagnostics(robot) == aggregate_formats([])
    client.close()
    assert client._geometry == {}


async def test_missing_wrong_value_and_no_major_map_inspection():
    client = YeediClient(None,'a','b','DE','c')
    robot = Robot('d','r','n')
    client.command = AsyncMock(side_effect=[{'data':{'subsets':[{'mssid':'a'},{'mssid':'b'}]}},
        {'data':{'mssid':'a'}}, {'data':{'mssid':'b','value':{'SECRET':'123456'}}}])
    assert len(await client.rooms(robot,'map')) == 2
    probe = client.geometry_diagnostics(robot)
    assert probe['value_count'] == 2 and probe['polygon_count'] == 0
    assert not probe['all_same_shape']
    assert probe['formats'][0]['format'] == {'present':False,'type':'null'}
    assert probe['formats'][1]['format'] == {'present':True,'type':'object'}
    before = client.geometry_diagnostics(robot)
    client.command.side_effect = [{'data':{'state':'x'}}, {'data':{'mid':'map','value':'PRIVATE_MAJOR'}}]
    assert await client.probe_legacy_maps(robot)
    assert client.geometry_diagnostics(robot) == before
