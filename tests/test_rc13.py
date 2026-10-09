"""Synthetic refresh observations; acquisition scheduling stays unchanged."""
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from tests.test_coordinator import coordinator
from tests.test_rc4 import raw_fixture
from custom_components.yeedi_vac_max.client import CloudError, CommandTimeout
from custom_components.yeedi_vac_max.coordinator import RawRefreshProbe, SpatialState
from custom_components.yeedi_vac_max.map_data import YeediMap
from custom_components.yeedi_vac_max.raw_map import MapChanged
from custom_components.yeedi_vac_max.diagnostics import (
    raw_refresh_diagnostics, refresh_bucket, async_get_config_entry_diagnostics)


def install(coordinator):
    state = coordinator.spatial['vac']
    state.active_map = YeediMap('PRIVATE_MAP', None, True)
    state.metadata_valid = state.rooms_valid = True
    state.raw_map = raw_fixture()
    state.next_map_refresh = time.monotonic() + 3600
    coordinator._map_activity['vac'] = 'docked'
    coordinator.map_storage.save = AsyncMock(return_value=True)
    coordinator.client.load_raw_map.return_value = state.raw_map
    return state


def diagnostic(state):
    return raw_refresh_diagnostics(state, 'docked')


def test_initial():
    d = diagnostic(SpatialState())
    assert d['raw_refresh_attempt_bucket'] == '0'
    assert d['raw_refresh_last_result'] == d['raw_refresh_last_fresh_result'] == 'never'
    assert d['raw_refresh_last_mode'] == 'never'
    assert not d['raw_refresh_backoff_active']


@pytest.mark.parametrize('fresh', [False, True])
async def test_success(coordinator, fresh):
    state = install(coordinator)
    await coordinator._raw_refresh(coordinator.robots[0], fresh=fresh)
    d = diagnostic(state)
    assert d['raw_refresh_attempt_bucket'] == d['raw_refresh_success_bucket'] == '1'
    assert d['raw_refresh_failure_bucket'] == '0'
    assert d['raw_refresh_last_result'] == 'success'
    assert d['raw_refresh_last_mode'] == ('fresh' if fresh else 'normal')
    assert not d['raw_refresh_backoff_active'] and not d['raw_refresh_due']
    assert d['raw_refresh_current_hold'] == 'cache_interval'
    assert d['raw_refresh_last_fresh_result'] == ('success' if fresh else 'never')


async def test_failed_docking_and_normal_retries_after_backoff(coordinator):
    state = install(coordinator)
    original = state.raw_map
    async def zero(robot, mid, previous, status):
        status.update(failure_stage='no_visible_pixels', major_valid=True,
                      generation_verified=True, raster_assembled=True, decode_failures_bucket='0')
        return None
    coordinator.client.load_raw_map.side_effect = zero
    await coordinator._spatial_refresh(coordinator.robots[0], docking_refresh=True)
    d = diagnostic(state)
    assert d['raw_refresh_last_fresh_result'] == 'no_visible_pixels'
    assert d['raw_refresh_fresh_attempt_bucket'] == '1'
    assert d['raw_refresh_backoff_active'] and d['raw_refresh_current_hold'] == 'backoff'
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert state.raw_refresh_probe.attempts == 1
    assert diagnostic(state)['raw_refresh_last_decision'] == 'skipped_not_due'
    assert diagnostic(state)['raw_refresh_last_result'] == 'no_visible_pixels'
    for _ in range(3):
        state.next_raw_refresh = time.monotonic() - 1
        assert diagnostic(state)['raw_refresh_due']
        assert not diagnostic(state)['raw_refresh_backoff_active']
        await coordinator._spatial_refresh(coordinator.robots[0])
    d = diagnostic(state)
    assert d['raw_refresh_attempt_bucket'] == d['raw_refresh_failure_bucket'] == '4-8'
    assert d['raw_refresh_normal_attempt_bucket'] == '2-3'
    assert d['raw_refresh_last_mode'] == 'normal'
    assert d['raw_refresh_last_result'] == d['raw_refresh_last_fresh_result'] == 'no_visible_pixels'
    assert state.raw_map is original
    assert coordinator.client.load_raw_map.await_count == 4
    coordinator.map_storage.save.assert_not_awaited()


@pytest.mark.parametrize('activity', ['cleaning', 'paused', 'returning'])
async def test_activity_hold_only_observed(coordinator, activity):
    state = install(coordinator)
    coordinator._map_activity['vac'] = activity
    await coordinator._spatial_refresh(coordinator.robots[0])
    d = raw_refresh_diagnostics(state, activity)
    assert d['raw_refresh_last_decision'] == 'skipped_activity_hold'
    assert d['raw_refresh_current_hold'] == 'activity_hold'
    assert d['raw_refresh_attempt_bucket'] == '0'
    coordinator.client.load_raw_map.assert_not_awaited()


@pytest.mark.parametrize('invalid', ['metadata', 'map'])
async def test_invalid_context_skips(coordinator, invalid):
    state = install(coordinator)
    if invalid == 'metadata':
        state.metadata_valid = False
    else:
        state.active_map = None
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert diagnostic(state)['raw_refresh_last_decision'] == (
        'skipped_invalid_metadata' if invalid == 'metadata' else 'skipped_no_active_map')
    assert state.raw_refresh_probe.attempts == 0


@pytest.mark.parametrize('error,expected', [
    (MapChanged('PRIVATE'), 'generation_changed'),
    (TimeoutError('PRIVATE'), 'timeout'),
    (CommandTimeout('PRIVATE'), 'timeout'),
    (CloudError('PRIVATE'), 'cloud_error'),
    (RuntimeError('PRIVATE'), 'unexpected')])
async def test_escape_errors_allowlisted_without_function_change(coordinator, error, expected, caplog):
    state = install(coordinator)
    coordinator.client.prepare_raw_map.side_effect = error
    await coordinator._raw_refresh(coordinator.robots[0])
    assert diagnostic(state)['raw_refresh_last_result'] == expected
    assert diagnostic(state)['raw_refresh_failure_bucket'] == '1'
    assert 'PRIVATE' not in json.dumps(diagnostic(state)) + caplog.text
    assert state.raw_status['failure_stage'] == ('none' if isinstance(error, MapChanged) else 'unexpected')


async def test_local_map_change(coordinator):
    state = install(coordinator)
    async def change(*args):
        state.active_map = YeediMap('NEW_PRIVATE_MAP', None, True)
        return None
    coordinator.client.load_raw_map.side_effect = change
    await coordinator._raw_refresh(coordinator.robots[0])
    assert diagnostic(state)['raw_refresh_last_result'] == 'map_changed'
    assert not diagnostic(state)['raw_refresh_backoff_active']


@pytest.mark.parametrize('stage', ['major_initial', 'piece_download', 'piece_decode',
                                 'generation_changed', 'raster_assembly', 'png_generation', 'unexpected'])
async def test_internal_loader_stage_not_invented_exception_category(coordinator, stage):
    state = install(coordinator)
    async def failed(robot, mid, previous, status):
        status['failure_stage'] = stage
        return None
    coordinator.client.load_raw_map.side_effect = failed
    await coordinator._raw_refresh(coordinator.robots[0])
    assert diagnostic(state)['raw_refresh_last_result'] == stage


@pytest.mark.parametrize('count,bucket', [(0,'0'),(1,'1'),(2,'2-3'),(3,'2-3'),(4,'4-8'),(8,'4-8'),(9,'>8')])
def test_buckets(count, bucket):
    assert refresh_bucket(count) == bucket


def test_bounded_ram_counters():
    probe = RawRefreshProbe()
    for _ in range(100):
        probe.begin(False)
        probe.finish('success', False)
        probe.begin(True)
        probe.finish('no_visible_pixels', True)
    assert probe.attempts == probe.successes == probe.failures == probe.normal_attempts == probe.fresh_attempts == 9
    assert 'no_visible_pixels' not in repr(probe)


async def test_unload_clears_probe(coordinator):
    state = install(coordinator)
    await coordinator._raw_refresh(coordinator.robots[0])
    await coordinator.async_shutdown()
    assert state.raw_refresh_probe.attempts == 0
    assert diagnostic(state)['raw_refresh_last_result'] == 'never'


async def test_privacy_no_requests_no_clock_export(coordinator, caplog):
    state = install(coordinator)
    probe = state.raw_refresh_probe
    probe.last_result = probe.last_fresh_result = probe.last_mode = probe.decision = 'SECRET_URL_COORDINATES'
    state.next_raw_refresh = 987654321.125
    before = list(coordinator.client.mock_calls)
    output = await async_get_config_entry_diagnostics(None, SimpleNamespace(runtime_data=coordinator))
    exported = json.dumps(output) + caplog.text
    assert all(private not in exported for private in ['PRIVATE_MAP', 'SECRET_URL_COORDINATES', '987654321', '"vac"', '"res"'])
    assert coordinator.client.mock_calls == before
    assert output['raw_refresh'][0]['raw_refresh_last_result'] == 'unexpected'


async def test_actual_docking_edge_once_and_followup_normal(coordinator):
    state = install(coordinator)
    coordinator._map_activity['vac'] = 'returning'
    coordinator.client.snapshot.return_value = {'online': True, 'activity': 'docked'}
    await coordinator._poll_robot(coordinator.robots[0])
    await coordinator._poll_robot(coordinator.robots[0])
    assert state.raw_refresh_probe.fresh_attempts == 1
    assert state.raw_refresh_probe.normal_attempts == 0
    state.next_raw_refresh = time.monotonic() - 1
    await coordinator._poll_robot(coordinator.robots[0])
    assert state.raw_refresh_probe.normal_attempts == 1
    assert state.raw_refresh_probe.last_fresh_result == 'success'
