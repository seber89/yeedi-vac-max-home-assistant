"""Tests against real HA classes; cloud and platform I/O are mocked."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntries
from homeassistant.components.vacuum import VacuumActivity, VacuumEntityFeature
from homeassistant.exceptions import HomeAssistantError

from custom_components.yeedi_vac_max.client import Robot, InvalidAuth
from custom_components.yeedi_vac_max.config_flow import YeediVacMaxConfigFlow
from custom_components.yeedi_vac_max.vacuum import YeediVacuum
from custom_components.yeedi_vac_max.sensor import YeediBattery
from custom_components.yeedi_vac_max.binary_sensor import YeediOnline


@pytest.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    instance.config_entries = ConfigEntries(instance, {})
    yield instance
    await instance.async_stop()


async def test_config_flow_success(hass):
    flow = YeediVacMaxConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    fake = MagicMock(user_id="user-id")
    fake.devices = AsyncMock(return_value=[Robot("vac", "res", "Vac")])
    with patch("custom_components.yeedi_vac_max.config_flow.YeediClient", return_value=fake), patch("custom_components.yeedi_vac_max.config_flow.async_get_clientsession"):
        result = await flow.async_step_user({"username": "test@example.invalid", "password": "test", "country": "de"})
    assert result["type"] == "create_entry"
    assert result["data"]["country"] == "DE"
    assert result["data"]["device_id"]
    fake.close.assert_called_once()


async def test_config_flow_auth_failure(hass):
    flow = YeediVacMaxConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    fake = MagicMock()
    fake.devices = AsyncMock(side_effect=InvalidAuth("invalid"))
    with patch("custom_components.yeedi_vac_max.config_flow.YeediClient", return_value=fake), patch("custom_components.yeedi_vac_max.config_flow.async_get_clientsession"):
        result = await flow.async_step_user({"username": "a", "password": "b", "country": "DE"})
    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_auth"
    fake.close.assert_called_once()


async def test_entities_and_control_payloads(hass):
    coordinator = SimpleNamespace(hass=hass, last_update_success=True,
        data={"vac": {"online": True, "activity": "paused", "battery": 75, "fan_speed": "Normal"}},
        execute=AsyncMock(), rooms={}, async_contexts=lambda: [])
    robot = Robot("vac", "res", "Vac")
    vacuum = YeediVacuum(coordinator, robot)
    assert vacuum.activity == VacuumActivity.PAUSED
    assert vacuum.supported_features & VacuumEntityFeature.FAN_SPEED
    await vacuum.async_start()
    coordinator.execute.assert_awaited_with(robot, "clean", {"act": "resume"})
    await vacuum.async_return_to_base()
    coordinator.execute.assert_awaited_with(robot, "charge", {"act": "go"})
    await vacuum.async_pause()
    coordinator.execute.assert_awaited_with(robot, "clean", {"act": "pause"})
    await vacuum.async_stop()
    coordinator.execute.assert_awaited_with(robot, "clean", {"act": "stop"})
    coordinator.data["vac"]["activity"] = "idle"
    await vacuum.async_start()
    coordinator.execute.assert_awaited_with(robot, "clean", {
        "act": "start", "type": "auto", "count": 1, "donotClean": 0, "router": "plan"})
    await vacuum.async_set_fan_speed("Max")
    coordinator.execute.assert_awaited_with(robot, "setSpeed", {"speed": 1})
    with pytest.raises(HomeAssistantError):
        await vacuum.async_set_fan_speed("Max+")
    assert YeediBattery(coordinator, robot, "battery").native_value == 75
    online = YeediOnline(coordinator, robot, "online")
    coordinator.data["vac"]["online"] = False
    assert not vacuum.available
    assert online.available and not online.is_on


async def test_setup_unload(hass):
    from custom_components.yeedi_vac_max import async_setup_entry, async_unload_entry
    entry = SimpleNamespace(data={"username": "a", "password": "b", "country": "DE", "device_id": "local-id"})
    entry.async_create_background_task = lambda host, coro, name: host.async_create_background_task(coro, name)
    client = MagicMock()
    client.devices = AsyncMock(return_value=[Robot("vac", "res", "Vac")])
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.client = client
    with patch("custom_components.yeedi_vac_max.YeediClient", return_value=client), patch("custom_components.yeedi_vac_max.YeediCoordinator", return_value=coordinator), patch("custom_components.yeedi_vac_max.async_get_clientsession"), patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()), patch.object(hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=True)):
        assert await async_setup_entry(hass, entry)
        assert entry.runtime_data is coordinator
        assert await async_unload_entry(hass, entry)
    client.close.assert_called_once()
