"""Synthetic source-identity observations, never authorization for a write."""
from unittest.mock import AsyncMock
import pytest
from tests.test_coordinator import coordinator
from tests.test_beta6 import install_raw, client, MID, ROBOT
from custom_components.yeedi_vac_max.client import CloudError
from custom_components.yeedi_vac_max.map_data import YeediMap
from custom_components.yeedi_vac_max.diagnostics import identity_diagnostics
from custom_components.yeedi_vac_max.map_storage import SavedMap


@pytest.mark.parametrize('using,expected', [(1,True),('1',True),(0,False),('0',False)])
async def test_cached_presence_is_not_using(using,expected):
    c = client()
    c.command = AsyncMock(return_value={'data':{'info':[{'mid':MID,'using':using}]}})
    assert await c.cached_map_identity(ROBOT,MID) == (True,expected)
    c.command.assert_awaited_once_with(ROBOT,'getCachedMapInfo')


@pytest.mark.parametrize('info', [None,{},[{'mid':MID,'using':True}],
    [{'mid':MID,'using':1},{'mid':MID,'using':0}], [None], [{'mid':'0','using':1}], [{}]])
async def test_cached_invalid_not_identity_evidence(info):
    c = client()
    c.command = AsyncMock(return_value={'data':{'info':info}})
    with pytest.raises(CloudError):
        await c.cached_map_identity(ROBOT,MID)


@pytest.mark.parametrize('current', [MID,'other-map'])
@pytest.mark.parametrize('persisted', [False,True])
async def test_two_verified_zero_builds_check_once_even_with_last_good(coordinator,current,persisted):
    state = await install_raw(coordinator)
    old = state.raw_map
    if persisted:
        state.saved_map = SavedMap(MID,old.png)
        state.has_persisted_map = True
        state.raw_map = None
    retained = state.image_map
    coordinator.client.current_yeedi_map_id.return_value = current
    coordinator.client.cached_map_identity.return_value = (True,True)
    def zero(*args):
        args[3].update(major_valid=True,generation_verified=True,raster_assembled=True,
            decode_failures_bucket='0',failure_stage='no_visible_pixels')
        return None
    coordinator.client.load_raw_map.side_effect = zero
    async with coordinator.commands['vac'].lock:
        for _ in range(4):
            await coordinator._raw_refresh(coordinator.robots[0],fresh=True)
    assert state.image_map is retained
    assert state.map_identity_probe['current_map_matches_selected'] == (current == MID)
    coordinator.client.current_yeedi_map_id.assert_awaited_once()
    coordinator.client.cached_map_identity.assert_awaited_once()
    coordinator.client.reactivate_map.assert_not_awaited()
    coordinator.client.command.assert_not_awaited()


@pytest.mark.parametrize('error', [TimeoutError(),CloudError('private'),RuntimeError('private')])
async def test_optional_errors_isolated_and_consumed(coordinator,error):
    state = await install_raw(coordinator)
    coordinator.client.current_yeedi_map_id.side_effect = error
    coordinator.client.cached_map_identity.return_value = (True,False)
    async with coordinator.commands['vac'].lock:
        await coordinator._check_raw_map_identity(coordinator.robots[0],state.active_map)
        await coordinator._check_raw_map_identity(coordinator.robots[0],state.active_map)
    coordinator.client.current_yeedi_map_id.assert_awaited_once()
    assert state.map_identity_probe['cached_map_valid']
    assert 'private' not in str(state.map_identity_probe)
    assert coordinator.last_update_success


async def test_changed_context_discards_read_and_skips_cached(coordinator):
    state = await install_raw(coordinator)
    selected = state.active_map
    async def changed(*args):
        state.active_map = YeediMap('different',None,True)
        return MID
    coordinator.client.current_yeedi_map_id.side_effect = changed
    async with coordinator.commands['vac'].lock:
        await coordinator._check_raw_map_identity(coordinator.robots[0],selected)
    assert not state.map_identity_probe['current_map_valid']
    assert state.map_identity_probe['current_result'] == 'map_changed'
    coordinator.client.cached_map_identity.assert_not_awaited()


async def test_successful_build_has_no_identity_reads(coordinator):
    state = await install_raw(coordinator)
    coordinator.client.load_raw_map.return_value = state.raw_map
    async with coordinator.commands['vac'].lock:
        await coordinator._raw_refresh(coordinator.robots[0],fresh=True)
    coordinator.client.current_yeedi_map_id.assert_not_awaited()
    coordinator.client.cached_map_identity.assert_not_awaited()


async def test_privacy_no_diagnostic_io_and_unload_reset(coordinator):
    state = await install_raw(coordinator)
    state.map_identity_probe.update(current_result='private-url-token',private='secret')
    result = identity_diagnostics(state)
    assert result['current_result'] == 'unexpected'
    assert 'private' not in str(result) and MID not in str(result)
    assert all(type(value) in (bool,str) for value in result.values())
    coordinator.client.current_yeedi_map_id.assert_not_awaited()
    await coordinator.async_shutdown()
    assert identity_diagnostics(state)['current_result'] == 'never'
    assert not state.identity_checked


async def test_no_cache_still_checks_without_any_write(coordinator):
    state = await install_raw(coordinator)
    state.raw_map = state.saved_map = None
    state.has_persisted_map = False
    coordinator.client.current_yeedi_map_id.return_value = MID
    coordinator.client.cached_map_identity.return_value = (True,False)
    async with coordinator.commands['vac'].lock:
        await coordinator._check_raw_map_identity(coordinator.robots[0],state.active_map)
    assert state.map_identity_probe['current_map_matches_selected']
    assert not state.map_identity_probe['cached_selected_using']
    coordinator.client.reactivate_map.assert_not_awaited()


async def test_unlocked_check_does_not_create_io(coordinator):
    state = await install_raw(coordinator)
    await coordinator._check_raw_map_identity(coordinator.robots[0],state.active_map)
    assert not state.identity_checked
    coordinator.client.current_yeedi_map_id.assert_not_awaited()
