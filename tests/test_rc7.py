"""Synthetic Yeedi current-map confirmation; no third-party fixtures."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from tests.test_rc6 import setup, zero, acquire, ROBOT, MID
from tests.test_rc4 import raw_fixture
from custom_components.yeedi_vac_max import client as client_module
from custom_components.yeedi_vac_max.client import YeediClient, CloudError
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics


async def test_current_map_exact_read_transport():
    client = YeediClient(None, 'private', 'secret', 'DE', 'resource')
    client.authenticate = AsyncMock()
    client._request = AsyncMock(return_value={'ret':'ok','resp':{'body':{'data':{'mid':MID}}}})
    assert await client.current_yeedi_map_id(ROBOT) == MID
    request = client._request.call_args.kwargs
    assert request['retry'] is True
    assert request['json']['cmdName'] == 'getMapInfo_V2'
    assert request['json']['payload']['body']['data'] == {'type':'0'}
    with pytest.raises(ValueError):
        await client.command(ROBOT, 'getMapInfo_V2', {'type':'0'}, writing=True)
    client._request.assert_awaited_once()


@pytest.mark.parametrize('data', [{}, None, [], {'mid':None}, {'mid':''}, {'mid':'0'},
    {'mid':1}, {'mid':True}, {'mid':' padded '}, {'mid':{}},
    {'nested':{'mid':MID}}, {'id':MID}])
async def test_current_map_strict_identifier_only(data):
    client = YeediClient(None, 'private', 'secret', 'DE', 'resource')
    client.command = AsyncMock(return_value={'data':data})
    with pytest.raises(CloudError, match='identifier unavailable'):
        await client.current_yeedi_map_id(ROBOT)
    client.command.assert_awaited_once_with(ROBOT, 'getMapInfo_V2', {'type':'0'})


async def test_current_map_timeout_bounded(monkeypatch):
    client = YeediClient(None, 'a', 'b', 'DE', 'c')
    async def blocked(*args):
        await asyncio.Event().wait()
    client.command = AsyncMock(side_effect=blocked)
    assert client_module.READ_RETRY_BUDGET < client_module.YEEDI_MAP_INFO_TIMEOUT <= 40
    monkeypatch.setattr(client_module, 'YEEDI_MAP_INFO_TIMEOUT', 0.01)
    with pytest.raises(TimeoutError):
        await client.current_yeedi_map_id(ROBOT)
    client.command.assert_awaited_once()


@pytest.mark.parametrize('mid,result', [('OTHER','map_identity_mismatch'),
    (None,'yeedi_map_info_invalid'), ('0','yeedi_map_info_invalid'),
    (' padded ','yeedi_map_info_invalid')])
async def test_no_write_without_exact_valid_identity(coordinator,mid,result):
    state = setup(coordinator)
    coordinator.client.current_yeedi_map_id.return_value = mid
    coordinator.client.load_raw_map.side_effect = zero
    await acquire(coordinator)
    await acquire(coordinator)
    assert state.post_reactivation_result == result
    coordinator.client.current_yeedi_map_id.assert_awaited_once()
    coordinator.client.reactivate_map.assert_not_awaited()
    coordinator.client.confirms_cached_map.assert_not_awaited()


async def test_optional_read_timeout_preserves_coordinator_success(coordinator,caplog):
    state = setup(coordinator)
    coordinator.client.maps.return_value = (state.active_map,)
    coordinator.client.rooms.return_value = ()
    coordinator.client.current_yeedi_map_id.side_effect = TimeoutError('PRIVATE_TOKEN')
    coordinator.client.load_raw_map.side_effect = zero
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert state.metadata_valid and state.rooms_valid
    assert state.post_reactivation_result == 'yeedi_map_info_timeout'
    coordinator.client.reactivate_map.assert_not_awaited()
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    assert 'PRIVATE' not in json.dumps(output) + caplog.text


async def test_read_cloud_error_is_invalid_not_write_failure(coordinator):
    state = setup(coordinator)
    coordinator.client.load_raw_map.side_effect = zero
    coordinator.client.current_yeedi_map_id.side_effect = CloudError('PRIVATE')
    await acquire(coordinator)
    assert state.yeedi_map_info_attempted and not state.yeedi_map_info_valid
    assert state.post_reactivation_result == 'yeedi_map_info_invalid'
    coordinator.client.reactivate_map.assert_not_awaited()


async def test_exact_sequence_gap_sync_and_no_cached_map_reads(coordinator,monkeypatch):
    from custom_components.yeedi_vac_max import coordinator as module
    state = setup(coordinator)
    events = []
    async def prepare(*args):
        events.append('prepare')
    async def load(*args):
        events.append('build')
        return raw_fixture() if state.map_reactivation_confirmed else zero(*args)
    async def identity(*args):
        events.append('identity')
        return MID
    async def write(*args):
        assert state.reactivation_checked
        assert coordinator.commands['vac'].lock.locked()
        events.append('write')
    async def sleep(delay):
        events.append(('sleep',delay))
    monkeypatch.setattr(module.asyncio, 'sleep', sleep)
    monkeypatch.setattr(module.time, 'monotonic', lambda: 100)
    coordinator.commands['vac'].last_end = 100
    coordinator.client.prepare_raw_map.side_effect = prepare
    coordinator.client.load_raw_map.side_effect = load
    coordinator.client.current_yeedi_map_id.side_effect = identity
    coordinator.client.reactivate_map.side_effect = write
    await acquire(coordinator)
    assert events == ['prepare','build','identity',('sleep',1.5),'write',
                      ('sleep',1),'prepare','build']
    assert state.has_persisted_map and state.post_reactivation_result == 'success'
    coordinator.client.confirms_cached_map.assert_not_awaited()
    coordinator.client.maps.assert_not_awaited()


async def test_diagnostic_allowlist_never_accepts_private_values(coordinator):
    state = setup(coordinator)
    for name in ('yeedi_map_info_attempted','yeedi_map_info_valid','yeedi_map_identity_match'):
        setattr(state,name,'PRIVATE_COORDINATE_ID')
    state.post_reactivation_result = 'timeout'  # Old RC6 result is no longer allowed.
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    probe = output['map_reactivation'][0]
    assert set(probe) == {'yeedi_map_info_attempted','yeedi_map_info_valid',
        'yeedi_map_identity_match','map_reactivation_attempted','map_reactivation_confirmed',
        'post_reactivation_build_attempted','post_reactivation_result'}
    assert probe['post_reactivation_result'] == 'unexpected'
    assert all(type(value) is bool for key,value in probe.items() if key != 'post_reactivation_result')
    assert 'PRIVATE' not in json.dumps(output)
