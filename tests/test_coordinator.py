"""Exercise the real coordinator with an isolated Home Assistant instance."""
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.yeedi_vac_max.client import Robot, CloudError, InvalidAuth
from custom_components.yeedi_vac_max.coordinator import YeediCoordinator


@pytest.fixture
async def coordinator(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    entry = ConfigEntry(domain="yeedi_vac_max", title="Yeedi", data={}, options={},
                        version=1, minor_version=1, source="user", unique_id="DE:user",
                        discovery_keys=MappingProxyType({}), subentries_data=[])
    client = AsyncMock()
    client.positions.return_value = (None, None)
    client.maps.return_value = ()
    client.snapshot.return_value = {"online": True, "activity": "idle"}
    robot = Robot("vac", "res", "Vac")
    instance = YeediCoordinator(hass, entry, client, [robot])
    yield instance
    await instance.async_shutdown()
    await hass.async_stop()


async def test_update_and_auth_error(coordinator):
    coordinator.client.snapshot.return_value = {"online": True, "battery": 90}
    assert await coordinator._async_update_data() == {"vac": {"online": True, "battery": 90}}
    coordinator.client.snapshot.side_effect = InvalidAuth("invalid")
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_cloud_failure(coordinator):
    coordinator.client.snapshot.side_effect = CloudError("bad response")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_rejected_command_does_not_refresh_or_change_state(coordinator):
    coordinator.data = {"vac": {"activity": "docked"}}
    coordinator.client.command.side_effect = CloudError("rejected")
    coordinator.async_request_refresh = AsyncMock()
    with pytest.raises(HomeAssistantError):
        await coordinator.execute(coordinator.robots[0], "clean", {"act": "start"})
    assert coordinator.data["vac"]["activity"] == "docked"
    coordinator.async_request_refresh.assert_not_awaited()


async def test_acknowledged_command_refreshes(coordinator):
    coordinator.async_request_refresh = AsyncMock()
    await coordinator.execute(coordinator.robots[0], "charge", {"act": "go"})
    coordinator.client.command.assert_awaited_once_with(coordinator.robots[0], "charge", {"act": "go"}, writing=True)
    coordinator.client.snapshot.assert_awaited_once()
