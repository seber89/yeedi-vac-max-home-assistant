"""Synthetic discovery provenance, no duplicated cloud read or write."""
from unittest.mock import AsyncMock
import asyncio
import pytest
from tests.test_coordinator import coordinator
from tests.test_beta6 import client, ROBOT, MID, install_raw
from custom_components.yeedi_vac_max.client import CommandTimeout, CloudError
from custom_components.yeedi_vac_max.map_data import YeediMap
from custom_components.yeedi_vac_max.diagnostics import identity_diagnostics


@pytest.mark.parametrize('using,source',[(1,'cached_using'),(0,'cached_present')])
async def test_discovery_evidence_no_second_read(coordinator,using,source):
    c = client()
    c.command = AsyncMock(return_value={'data':{'info':[{'mid':MID,'using':using}]}})
    selected, = await c.maps(ROBOT)
    state = await install_raw(coordinator)
    state.active_map = selected
    coordinator.client.current_yeedi_map_id.return_value = MID
    async with coordinator.commands['vac'].lock:
        await coordinator._check_raw_map_identity(coordinator.robots[0],selected)
    coordinator.client.cached_map_identity.assert_not_awaited()
    output = identity_diagnostics(state)
    assert output['cached_map_valid'] and output['cached_selected_present']
    assert output['cached_selected_using'] == bool(using)
    assert output['selected_map_source'] == source
    assert output['cached_evidence_source'] == 'discovery'
    c.command.assert_awaited_once_with(ROBOT,'getCachedMapInfo')


async def test_major_fallback_does_not_prove_using(coordinator):
    c = client()
    c.command = AsyncMock(side_effect=CommandTimeout('private'))
    c.probe_legacy_maps = AsyncMock(return_value=YeediMap(MID,None,True))
    selected, = await c.maps(ROBOT)
    state = await install_raw(coordinator)
    state.active_map = selected
    coordinator.client.current_yeedi_map_id.return_value = MID
    async with coordinator.commands['vac'].lock:
        await coordinator._check_raw_map_identity(coordinator.robots[0],selected)
    output = identity_diagnostics(state)
    assert output['selected_map_source'] == 'major_fallback'
    assert output['cached_result'] == 'timeout'
    assert not output['cached_map_valid'] and not output['cached_selected_using']
    coordinator.client.cached_map_identity.assert_not_awaited()
    coordinator.client.reactivate_map.assert_not_awaited()


@pytest.mark.parametrize('info',[
    [{'mid':MID,'using':True}], [{'mid':MID,'using':1},{'mid':'other','using':1}],
])
async def test_tolerated_discovery_is_not_strict_using_evidence(info):
    c = client()
    c.command = AsyncMock(return_value={'data':{'info':info}})
    maps = await c.maps(ROBOT)
    assert all(not m.cached_evidence_valid for m in maps)


async def test_other_map_using_does_not_make_selected_using(coordinator):
    c = client()
    c.command = AsyncMock(return_value={'data':{'info':[
        {'mid':MID,'using':0},{'mid':'other','using':1}]}})
    selected, other = await c.maps(ROBOT)
    assert not selected.active and other.active
    state = await install_raw(coordinator)
    state.active_map = selected
    coordinator.client.current_yeedi_map_id.return_value = MID
    async with coordinator.commands['vac'].lock:
        await coordinator._check_raw_map_identity(coordinator.robots[0],selected)
    assert not identity_diagnostics(state)['cached_selected_using']
    assert state.active_map is selected


async def test_duplicate_discovery_rejected_without_using_claim():
    c = client()
    c.command = AsyncMock(return_value={'data':{'info':[
        {'mid':MID,'using':1},{'mid':MID,'using':0}]}})
    with pytest.raises(CloudError):
        await c.maps(ROBOT)
    assert c.discovery_result(ROBOT) == 'invalid_response'


async def test_new_metadata_error_hides_old_using_evidence(coordinator):
    state = await install_raw(coordinator)
    state.active_map = YeediMap(MID,None,True,'cached_using','success',True)
    assert identity_diagnostics(state)['cached_selected_using']
    state.metadata_valid = False
    state.normal_cached_result = 'timeout'
    result = identity_diagnostics(state)
    assert not result['cached_selected_using'] and not result['cached_map_valid']
    assert result['cached_discovery_result'] == 'timeout'


async def test_real_normal_discovery_outcome_captured_without_extra_read(coordinator):
    c = client()
    c.positions = AsyncMock(return_value=(None,None))
    c.command = AsyncMock(return_value={'data':{'info':[{'mid':MID,'using':1}]}})
    c.rooms = AsyncMock(return_value=())
    c.prepare_raw_map = AsyncMock()
    c.load_raw_map = AsyncMock(return_value=None)
    coordinator.client = c
    async with coordinator.commands['vac'].lock:
        await coordinator._spatial_refresh(coordinator.robots[0])
    state = coordinator.spatial['vac']
    assert identity_diagnostics(state)['cached_discovery_result'] == 'success'
    assert identity_diagnostics(state)['cached_selected_using']
    c.command.assert_awaited_once_with(coordinator.robots[0],'getCachedMapInfo')


async def test_waiting_lock_does_not_start_identity_timeout(coordinator):
    state = await install_raw(coordinator)
    selected = YeediMap(MID,None,True,'cached_using','success',True)
    state.active_map = selected
    coordinator.client.current_yeedi_map_id.return_value = MID
    async def locked_check():
        async with coordinator.commands['vac'].lock:
            await coordinator._check_raw_map_identity(coordinator.robots[0],selected)
    async with coordinator.commands['vac'].lock:
        task = asyncio.create_task(locked_check())
        await asyncio.sleep(0)
        assert not state.identity_checked
        coordinator.client.current_yeedi_map_id.assert_not_awaited()
    await task
    assert identity_diagnostics(state)['current_map_matches_selected']
    coordinator.client.cached_map_identity.assert_not_awaited()


async def test_existing_outer_budget_cancels_current_read(coordinator,monkeypatch):
    state = await install_raw(coordinator)
    coordinator.client.current_yeedi_map_id.side_effect = lambda *args: None
    async def slow(*args):
        await asyncio.sleep(.05)
        return MID
    coordinator.client.current_yeedi_map_id.side_effect = slow
    coordinator.client.cached_map_identity.return_value = (True,True)
    actual_timeout = asyncio.timeout
    budgets = []
    def short_budget(seconds):
        budgets.append(seconds)
        return actual_timeout(.01)
    monkeypatch.setattr('custom_components.yeedi_vac_max.coordinator.asyncio.timeout',short_budget)
    async with coordinator.commands['vac'].lock:
        await coordinator._check_raw_map_identity(coordinator.robots[0],state.active_map)
    assert budgets == [8,8]
    assert state.map_identity_probe['current_result'] == 'timeout'
    assert state.map_identity_probe['cached_result'] == 'success'
    assert state.raw_map is not None
    coordinator.client.reactivate_map.assert_not_awaited()


async def test_empty_cached_list_valid_no_using(coordinator):
    c = client()
    c.command = AsyncMock(return_value={'data':{'info':[]}})
    assert await c.maps(ROBOT) == ()
    state = coordinator.spatial['vac']
    state.metadata_valid = True
    state.normal_cached_result = c.discovery_result(ROBOT)
    result = identity_diagnostics(state)
    assert result['cached_map_valid'] and not result['cached_selected_using']
    assert not result['direct_cached_probe_required']


def test_evidence_does_not_change_map_identity():
    assert YeediMap(MID,None,True) == YeediMap(MID,None,True,'cached_using','success',True)


async def test_unload_discards_provenance_and_diagnostics_do_no_io(coordinator):
    state = await install_raw(coordinator)
    state.active_map = YeediMap(MID,None,True,'cached_using','success',True)
    state.maps = (state.active_map,)
    state.normal_cached_result = 'success'
    result = identity_diagnostics(state)
    assert result['cached_selected_using'] and MID not in str(result)
    coordinator.client.command.assert_not_awaited()
    await coordinator.async_shutdown()
    result = identity_diagnostics(state)
    assert result['cached_evidence_source'] == 'none'
    assert result['selected_map_source'] == 'unknown'
    assert result['cached_discovery_result'] == 'never'
    assert all(not item.cached_evidence_valid for item in state.maps)


async def test_direct_probe_retains_rc19_timeout_no_write_or_repeat(coordinator):
    state = await install_raw(coordinator)
    old = state.raw_map
    coordinator.client.current_yeedi_map_id.return_value = MID
    coordinator.client.cached_map_identity.side_effect = TimeoutError()
    async with coordinator.commands['vac'].lock:
        await coordinator._check_raw_map_identity(coordinator.robots[0],state.active_map)
        await coordinator._check_raw_map_identity(coordinator.robots[0],state.active_map)
    assert state.raw_map is old
    result = identity_diagnostics(state)
    assert result['cached_result'] == 'timeout'
    assert result['cached_evidence_source'] == 'direct_probe'
    coordinator.client.cached_map_identity.assert_awaited_once()
    coordinator.client.reactivate_map.assert_not_awaited()
