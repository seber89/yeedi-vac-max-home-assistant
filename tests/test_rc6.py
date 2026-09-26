"""Original synthetic same-map bootstrap tests; no hardware fixtures."""
import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from tests.test_rc4 import raw_fixture
from tests.test_client import Session
from custom_components.yeedi_vac_max.client import (
    YeediClient, Robot, CommandTimeout, CommandRejected, CommandUncertain, RateLimited)
from custom_components.yeedi_vac_max.map_data import YeediMap
from custom_components.yeedi_vac_max.map_storage import SavedMap
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

ROBOT = Robot('PRIVATE_DEVICE', 'PRIVATE_RESOURCE', 'PRIVATE_NAME')
MID = 'PRIVATE_MAP'


def setup(coordinator):
    state = coordinator.spatial['vac']
    state.active_map = YeediMap(MID, None, True)
    state.metadata_valid = state.rooms_valid = True
    coordinator.client.confirms_cached_map.return_value = True
    return state


def zero(*args):
    args[3].update(major_valid=True, generation_verified=True, raster_assembled=True,
                   decode_failures_bucket='0', failure_stage='no_visible_pixels')
    return None


async def acquire(coordinator):
    async with coordinator.commands['vac'].lock:
        await coordinator._raw_refresh(coordinator.robots[0])


async def test_direct_success_never_reactivates(coordinator):
    state = setup(coordinator)
    coordinator.client.load_raw_map.return_value = raw_fixture()
    await acquire(coordinator)
    assert state.raw_map and state.has_persisted_map
    coordinator.client.reactivate_map.assert_not_awaited()
    coordinator.client.confirms_cached_map.assert_not_awaited()


@pytest.mark.parametrize('second_success',[False,True])
async def test_one_bootstrap_second_build_and_persistence(coordinator,second_success):
    state = setup(coordinator)
    calls = 0
    async def load(*args):
        nonlocal calls
        calls += 1
        return raw_fixture() if calls == 2 and second_success else zero(*args)
    coordinator.client.load_raw_map.side_effect = load
    await acquire(coordinator)
    coordinator.client.reactivate_map.assert_awaited_once_with(coordinator.robots[0],MID)
    assert coordinator.client.confirms_cached_map.await_count == 2
    assert coordinator.client.prepare_raw_map.await_count == 2
    assert state.map_reactivation_confirmed and state.post_reactivation_build_attempted
    assert state.post_reactivation_result == ('success' if second_success else 'no_visible_pixels')
    assert state.has_persisted_map is second_success
    if second_success:
        assert (await coordinator.map_storage.store.async_load())['vac']
    else:
        assert state.raw_map is None and state.next_raw_refresh > time.monotonic()+170
    # Even later failed refreshes cannot automatically repeat this bootstrap write.
    for _ in range(2):
        await acquire(coordinator)
    assert coordinator.client.reactivate_map.await_count == 1


@pytest.mark.parametrize('pre,post',[(False,True),(True,False)])
async def test_context_confirmation_required_both_sides(coordinator,pre,post):
    state = setup(coordinator)
    coordinator.client.confirms_cached_map.side_effect = [pre,post]
    coordinator.client.load_raw_map.side_effect = zero
    await acquire(coordinator)
    assert coordinator.client.reactivate_map.await_count == int(pre)
    assert coordinator.client.load_raw_map.await_count == 1
    assert state.post_reactivation_result == 'map_changed'


@pytest.mark.parametrize('error,result',[(CommandRejected,'rejected'),(CommandTimeout,'timeout'),
    (CommandUncertain,'uncertain'),(TimeoutError,'timeout'),(RateLimited,'rate_limited')])
async def test_write_errors_isolated_no_repeat(coordinator,error,result):
    state = setup(coordinator)
    coordinator.client.load_raw_map.side_effect = zero
    coordinator.client.reactivate_map.side_effect = error('PRIVATE')
    await acquire(coordinator)
    await acquire(coordinator)
    coordinator.client.reactivate_map.assert_awaited_once()
    assert state.post_reactivation_result == result
    assert not state.post_reactivation_build_attempted
    assert state.metadata_valid and state.rooms_valid


async def test_cached_info_timeout_never_uses_legacy_authority(coordinator):
    state = setup(coordinator)
    coordinator.client.load_raw_map.side_effect = zero
    coordinator.client.confirms_cached_map.side_effect = CommandTimeout('PRIVATE')
    await acquire(coordinator)
    await acquire(coordinator)
    assert state.post_reactivation_result == 'timeout'
    coordinator.client.confirms_cached_map.assert_awaited_once()
    coordinator.client.reactivate_map.assert_not_awaited()
    coordinator.client.maps.assert_not_awaited()


@pytest.mark.parametrize('cache',['raw','saved'])
async def test_existing_good_cache_never_reactivated(coordinator,cache):
    state = setup(coordinator)
    raw = raw_fixture()
    if cache == 'raw':
        state.raw_map = raw
    else:
        state.saved_map = SavedMap(MID,raw.png)
        state.has_persisted_map = True
    coordinator.client.load_raw_map.side_effect = zero
    await acquire(coordinator)
    assert state.image_map.png == raw.png
    coordinator.client.reactivate_map.assert_not_awaited()


@pytest.mark.parametrize('field,value', [('major_valid',False),('generation_verified',False),
    ('raster_assembled',False),('decode_failures_bucket','1'),('failure_stage','piece_download')])
async def test_only_verified_all_zero_build_qualifies(coordinator,field,value):
    setup(coordinator)
    async def load(*args):
        zero(*args)
        args[3][field] = value
    coordinator.client.load_raw_map.side_effect = load
    await acquire(coordinator)
    coordinator.client.reactivate_map.assert_not_awaited()


@pytest.mark.parametrize('info',[
    [], [{'mid':'OTHER','using':1}], [{'mid':MID,'using':0}],
    [{'mid':MID,'using':1},{'mid':'OTHER','using':1}],
    [{'mid':MID,'using':1},{'mid':MID,'using':1}],
    [{'mid':'0','using':1}], [{'mid':'','using':1}], [{'mid':None,'using':1}],
    [{'mid':' '+MID,'using':1}], [{'mid':MID,'using':True}], {}, None])
async def test_cached_evidence_rejects_invalid_or_ambiguous(info):
    client = YeediClient(None,'a','b','DE','c')
    client.command = AsyncMock(return_value={'data':{'info':info}})
    assert not await client.confirms_cached_map(ROBOT,MID)
    client.command.assert_awaited_once_with(ROBOT,'getCachedMapInfo')


@pytest.mark.parametrize('using',[1,'1'])
async def test_strict_cached_evidence_success(using):
    client = YeediClient(None,'a','b','DE','c')
    client.command = AsyncMock(return_value={'data':{'info':[{'mid':MID,'using':using}]}})
    assert await client.confirms_cached_map(ROBOT,MID)


@pytest.mark.parametrize('mid',[None,'0','', ' padded ', True])
async def test_bad_target_cannot_write_or_verify(mid):
    from custom_components.yeedi_vac_max.client import CloudError
    client = YeediClient(None,'a','b','DE','c')
    client.command = AsyncMock()
    assert not await client.confirms_cached_map(ROBOT,mid)
    with pytest.raises(CloudError):
        await client.reactivate_map(ROBOT,mid)
    client.command.assert_not_awaited()


async def test_transport_exact_payload_no_write_retry():
    client = YeediClient(None,'a','b','DE','c')
    client.authenticate = AsyncMock()
    client._request = AsyncMock(return_value={'ret':'ok','resp':{'body':{'code':0}}})
    await client.reactivate_map(ROBOT,MID)
    kwargs = client._request.call_args.kwargs
    assert kwargs['retry'] is False
    assert kwargs['json']['cmdName'] == 'setMajorMap'
    assert kwargs['json']['payload']['body']['data'] == {'mid':MID}
    with pytest.raises(ValueError):
        await client.command(ROBOT,'setMajorMap',{'mid':MID})


async def test_real_timeout_transport_sends_once():
    client = YeediClient(Session(100),'a','b','DE','c')
    client.authenticate = AsyncMock()
    with pytest.raises(CommandTimeout):
        await client.reactivate_map(ROBOT,MID)
    assert client.session.calls == 1


@pytest.mark.parametrize('body,error', [({},CommandUncertain),
    ({'code':20003},CommandRejected), ({'code':'not-supported'},CommandRejected)])
async def test_map_write_needs_explicit_ack(body,error):
    client = YeediClient(None,'a','b','DE','c')
    client.authenticate = AsyncMock()
    client._request = AsyncMock(return_value={'ret':'ok','resp':{'body':body}})
    with pytest.raises(error):
        await client.reactivate_map(ROBOT,MID)
    client._request.assert_awaited_once()
    assert client._request.call_args.kwargs['retry'] is False


async def test_cancellation_consumes_bootstrap_permission(coordinator):
    state = setup(coordinator)
    coordinator.client.load_raw_map.side_effect = zero
    coordinator.client.reactivate_map.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await acquire(coordinator)
    assert state.reactivation_checked and state.map_reactivation_attempted
    coordinator.client.reactivate_map.side_effect = None
    await acquire(coordinator)
    coordinator.client.reactivate_map.assert_awaited_once()


async def test_local_context_changes_during_permission_read_no_write(coordinator):
    state = setup(coordinator)
    coordinator.client.load_raw_map.side_effect = zero
    async def confirm(*args):
        state.active_map = YeediMap('OTHER',None,True)
        return True
    coordinator.client.confirms_cached_map.side_effect = confirm
    await acquire(coordinator)
    coordinator.client.reactivate_map.assert_not_awaited()
    assert state.post_reactivation_result == 'map_changed'


async def test_same_existing_lock_serializes_with_vacuum_write(coordinator):
    setup(coordinator)
    coordinator.client.load_raw_map.side_effect = zero
    entered, release = asyncio.Event(), asyncio.Event()
    async def write(*args):
        entered.set()
        await release.wait()
    coordinator.client.reactivate_map.side_effect = write
    task = asyncio.create_task(acquire(coordinator))
    await entered.wait()
    control = asyncio.create_task(coordinator.execute(coordinator.robots[0],'charge',{'act':'go'}))
    await asyncio.sleep(0)
    coordinator.client.command.assert_not_awaited()
    release.set()
    await asyncio.gather(task,control)
    coordinator.client.reactivate_map.assert_awaited_once()
    coordinator.client.command.assert_awaited_once()


async def test_no_unlocked_private_write_and_private_diagnostics(coordinator,caplog):
    state = setup(coordinator)
    coordinator.client.load_raw_map.side_effect = zero
    await coordinator._raw_refresh(coordinator.robots[0])
    coordinator.client.reactivate_map.assert_not_awaited()
    state.post_reactivation_result = 'PRIVATE_MAP_TOKEN_COORDINATES'
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    probe = output['map_reactivation'][0]
    assert probe == {'map_reactivation_attempted':False,'map_reactivation_confirmed':False,
                     'post_reactivation_build_attempted':False,'post_reactivation_result':'unexpected'}
    assert 'PRIVATE' not in json.dumps(output)+caplog.text
