"""Synthetic room response and privacy regressions."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock


from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max.client import YeediClient, Robot
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics


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
    exported = json.dumps(output)+caplog.text
    for token in ('PRIVATE_MAP','PRIVATE_ROOM','PRIVATE_NAME','987654','123456','987664','123466'):
        assert token not in exported


async def test_missing_wrong_value_and_no_major_map_inspection():
    client = YeediClient(None,'a','b','DE','c')
    robot = Robot('d','r','n')
    client.command = AsyncMock(side_effect=[{'data':{'subsets':[{'mssid':'a'},{'mssid':'b'}]}},
        {'data':{'mssid':'a'}}, {'data':{'mssid':'b','value':{'SECRET':'123456'}}}])
    assert len(await client.rooms(robot,'map')) == 2
    client.command.side_effect = [{'data':{'state':'x'}}, {'data':{'mid':'map','value':'PRIVATE_MAJOR'}}]
    assert await client.probe_legacy_maps(robot)
