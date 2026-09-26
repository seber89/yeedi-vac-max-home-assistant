"""Synthetic private storage, image lifetime and narrowly scoped status regression."""
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import Platform

from tests.test_coordinator import coordinator
from tests.test_rc4 import raw_fixture
from custom_components.yeedi_vac_max.client import CloudError, activity
from custom_components.yeedi_vac_max.coordinator import SpatialState
from custom_components.yeedi_vac_max.map_data import YeediMap, RobotPosition, DockPosition
from custom_components.yeedi_vac_max.map_storage import MapStorage, SavedMap, valid_png
from custom_components.yeedi_vac_max.image import YeediMapImage
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics


async def build(coordinator):
    state = coordinator.spatial['vac']
    raw = raw_fixture()
    state.active_map = YeediMap(raw.major.map_id, None, True)
    state.metadata_valid = state.rooms_valid = True
    coordinator.client.load_raw_map.return_value = raw
    await coordinator._raw_refresh(coordinator.robots[0])
    return state, raw


async def restart(coordinator):
    coordinator.spatial['vac'] = SpatialState()
    coordinator.map_storage = MapStorage(coordinator.hass, coordinator.config_entry.entry_id)
    assert await coordinator.async_load_saved_maps()
    return coordinator.spatial['vac']


async def test_success_persists_only_png_and_identity(coordinator, caplog):
    state, raw = await build(coordinator)
    assert state.has_persisted_map
    data = await coordinator.map_storage.store.async_load()
    assert set(data) == {'vac'}  # Exact identity; no cross-device heuristic.
    assert set(data['vac']) == {'map_id', 'png'}
    assert base64.b64decode(data['vac']['png']) == raw.png
    assert coordinator.map_storage.store._private
    assert coordinator.map_storage.store._atomic_writes
    for forbidden in ('pieces', 'crcs', 'token', 'password', 'robot_position', 'dock_position', 'rooms'):
        assert forbidden not in data['vac']
    assert raw.major.map_id not in caplog.text


async def test_restart_image_before_cloud_or_metadata(coordinator):
    _, raw = await build(coordinator)
    state = await restart(coordinator)
    assert state.raw_map is None and state.using_persisted_fallback
    image = YeediMapImage(coordinator, coordinator.robots[0])
    assert image.available and image.content_type == 'image/png'
    assert await image.async_image() == raw.png


@pytest.mark.parametrize('failure', ['no_visible_pixels', 'timeout', 'cloud', 'generation'])
async def test_restart_failed_build_preserves_disk_and_image(coordinator, failure):
    _, raw = await build(coordinator)
    old_disk = await coordinator.map_storage.store.async_load()
    state = await restart(coordinator)
    state.active_map = YeediMap(raw.major.map_id, None, True)
    state.metadata_valid = True
    async def load(*args):
        if failure == 'timeout':
            raise TimeoutError('PRIVATE')
        if failure == 'cloud':
            raise CloudError('PRIVATE')
        if failure == 'generation':
            from custom_components.yeedi_vac_max.raw_map import MapChanged
            raise MapChanged('PRIVATE')
        args[3]['failure_stage'] = 'no_visible_pixels'
        return None
    coordinator.client.load_raw_map.side_effect = load
    await coordinator._raw_refresh(coordinator.robots[0], fresh=True)
    assert await YeediMapImage(coordinator,coordinator.robots[0]).async_image() == raw.png
    assert await coordinator.map_storage.store.async_load() == old_disk


@pytest.mark.parametrize('loaded', [False, True])
@pytest.mark.parametrize('invalid', ['metadata_valid', 'rooms_valid', 'raw_valid_until'])
async def test_image_lifetime_independent_of_metadata_and_age(coordinator, loaded, invalid):
    state, raw = await build(coordinator)
    if loaded:
        state = await restart(coordinator)
    setattr(state, invalid, False if invalid.endswith('valid') else 0)
    image = YeediMapImage(coordinator, coordinator.robots[0])
    assert image.available and await image.async_image() == raw.png
    assert coordinator.rooms['vac'] == ()


@pytest.mark.parametrize('failure', [False, True])
async def test_dock_edge_atomic_persistence(coordinator, failure):
    state, old = await build(coordinator)
    new = raw_fixture({(3,4),(4,4)}, generation=2)
    before = await coordinator.map_storage.store.async_load()
    coordinator._map_activity['vac'] = 'returning'
    state.next_map_refresh = float('inf')
    coordinator.client.snapshot.return_value = {'online':True,'activity':'docked'}
    async def load(*args):
        assert state.raw_map is old
        assert await coordinator.map_storage.store.async_load() == before
        assert args[2] is None
        if failure:
            return None
        return new
    coordinator.client.load_raw_map.reset_mock()
    coordinator.client.load_raw_map.side_effect = load
    await coordinator._poll_robot(coordinator.robots[0])
    await coordinator._poll_robot(coordinator.robots[0])
    coordinator.client.load_raw_map.assert_awaited_once()
    assert state.raw_map is (old if failure else new)
    state = await restart(coordinator)
    assert state.saved_map.png == (old if failure else new).png


@pytest.mark.parametrize('maps', ['error', 'none', 'same', 'different'])
async def test_only_positive_other_identity_invalidates(coordinator, maps):
    state, raw = await build(coordinator)
    if maps == 'error':
        coordinator.client.maps.side_effect = CloudError('PRIVATE')
    else:
        coordinator.client.maps.return_value = () if maps == 'none' else (
            YeediMap('OTHER' if maps == 'different' else raw.major.map_id, 'changed name', True),)
    coordinator.client.rooms.return_value = ()
    coordinator.client.load_raw_map.return_value = None
    await coordinator._spatial_refresh(coordinator.robots[0], force=True)
    if maps == 'different':
        assert state.image_map is None
        assert await coordinator.map_storage.store.async_load() == {}
    else:
        assert state.image_map is raw
        assert (await coordinator.map_storage.store.async_load())['vac']['map_id'] == raw.major.map_id


@pytest.mark.parametrize('charging', [1, '1'])
async def test_charging_alert_priority(charging):
    assert activity({'trigger':'alert'}, {'isCharging':charging}) == 'docked'


@pytest.mark.parametrize('charging', [None, 0, '0', True, 1.0, 'yes', 2, [], {}])
def test_alert_without_explicit_charging_remains_error(charging):
    assert activity({'trigger':'alert'}, {'isCharging':charging}) == 'error'


async def test_diagnostic_privacy_allowlisted_activity(coordinator, caplog):
    state, raw = await build(coordinator)
    state.robot_position = RobotPosition(987654,876543)
    state.dock_position = DockPosition(765432,654321)
    coordinator.data = {'vac': {'activity': 'PRIVATE_SECRET', 'online':True}}
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    assert output['robots'][0]['activity'] == 'unknown'
    assert output['robots'][0]['has_persisted_map']
    exported = json.dumps(output) + caplog.text
    for secret in ('PRIVATE', raw.major.map_id, '987654', '876543', '765432', '654321',
                   base64.b64encode(raw.png).decode('ascii')):
        assert secret not in exported


@pytest.mark.parametrize('value', [None, [], {'vac':{}}, {'vac':{'map_id':'0','png':'AA=='}},
    {'vac':{'map_id':'x','png':'@@@'}}, {'vac':{'map_id':'x','png':'AA=='}},
    {'vac':{'map_id':'x','png':'x' * 2800000}}])
async def test_bad_storage_is_optional(coordinator, value):
    coordinator.map_storage.store.async_load = AsyncMock(return_value=value)
    assert not await coordinator.async_load_saved_maps()


async def test_storage_failures_isolated_and_device_identity_exact(coordinator):
    _, raw = await build(coordinator)
    other = MapStorage(coordinator.hass,coordinator.config_entry.entry_id)
    assert await other.load(['different-device']) == {}
    assert 'vac' in other.records  # No identity migration or incidental deletion.
    other.store.async_save = AsyncMock(side_effect=OSError('PRIVATE'))
    assert not await other.save('vac',SavedMap('OTHER',raw.png))
    other.store.async_load = AsyncMock(side_effect=OSError('PRIVATE'))
    assert await other.load(['vac']) == {}
    assert not valid_png(raw.png[:-1])
    assert not valid_png(raw.png[:30] + b'!' + raw.png[31:])


@pytest.mark.parametrize('activity', ['cleaning','paused','returning'])
async def test_loaded_background_preserved_during_active_states(coordinator, activity):
    _, raw = await build(coordinator)
    state = await restart(coordinator)
    state.active_map = YeediMap(raw.major.map_id,None,True)
    state.metadata_valid = True
    coordinator._map_activity['vac'] = activity
    coordinator.client.load_raw_map.reset_mock()
    await coordinator._raw_refresh(coordinator.robots[0])
    coordinator.client.load_raw_map.assert_not_awaited()
    assert state.image_map.png == raw.png


async def test_disk_failure_keeps_successful_memory_image(coordinator, caplog):
    coordinator.map_storage.store.async_save = AsyncMock(side_effect=OSError('PRIVATE'))
    state, raw = await build(coordinator)
    assert not state.has_persisted_map
    assert state.image_map is raw
    assert 'PRIVATE' not in caplog.text


async def test_silent_write_failure_not_reported_as_persisted(coordinator):
    coordinator.map_storage.store.async_save = AsyncMock()
    coordinator.map_storage.store.async_load = AsyncMock(return_value=None)
    state, raw = await build(coordinator)
    assert not state.has_persisted_map and state.raw_map is raw


async def test_success_same_png_does_not_rewrite_storage(coordinator):
    state, raw = await build(coordinator)
    coordinator.map_storage.store.async_save = AsyncMock()
    await coordinator._raw_refresh(coordinator.robots[0])
    coordinator.map_storage.store.async_save.assert_not_awaited()
    assert state.raw_map is raw


async def test_setup_publishes_cached_image_before_cloud_refresh(coordinator):
    from custom_components.yeedi_vac_max import async_setup_entry, async_unload_entry
    await build(coordinator)
    await restart(coordinator)
    client = MagicMock()
    client.devices = AsyncMock(return_value=coordinator.robots)
    coordinator.client = client
    entry_data = {'username':'a','password':'b','country':'DE','device_id':'local'}
    entry = SimpleNamespace(data=entry_data)
    events = []
    async def forward(entry, platforms):
        events.append(tuple(platforms))
        if Platform.IMAGE in platforms:
            assert YeediMapImage(coordinator,coordinator.robots[0]).available
    async def refresh():
        assert events == [(Platform.IMAGE,)]
        events.append('cloud')
    coordinator.async_config_entry_first_refresh = AsyncMock(side_effect=refresh)
    with patch('custom_components.yeedi_vac_max.YeediClient',return_value=client), \
         patch('custom_components.yeedi_vac_max.YeediCoordinator',return_value=coordinator), \
         patch('custom_components.yeedi_vac_max.async_get_clientsession'), \
         patch.object(coordinator.hass.config_entries,'async_forward_entry_setups',side_effect=forward), \
         patch.object(coordinator.hass.config_entries,'async_unload_platforms',new=AsyncMock(return_value=True)):
        assert await async_setup_entry(coordinator.hass,entry)
        assert events[1] == 'cloud' and Platform.IMAGE not in events[2]
        assert await async_unload_entry(coordinator.hass,entry)
    assert (await coordinator.map_storage.store.async_load())['vac']
