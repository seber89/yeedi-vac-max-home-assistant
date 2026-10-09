"""Original synthetic regressions for the externally reported DVX34 levels."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.yeedi_vac_max.client import Robot, YeediClient
from custom_components.yeedi_vac_max.vacuum import YeediVacuum


@pytest.mark.parametrize("speed,label", [(0, "Quiet"), (1, "Strong"), (2, "Max"), (999, None)])
async def test_canonical_readback(speed, label):
    client = YeediClient(None, "synthetic@example.invalid", "synthetic", "DE", "synthetic")
    client.command = AsyncMock(side_effect=[
        {"data": {"value": 70}}, {"data": {"state": "idle"}},
        {"data": {"isCharging": 1}}, {"data": {"speed": speed}},
    ])
    assert (await client.snapshot(Robot("synthetic", "resource", "Vac")))["fan_speed"] == label


@pytest.mark.parametrize("label,speed", [("Quiet", 0), ("Strong", 1), ("Max", 2), ("Normal", 1)])
async def test_canonical_write_and_input_only_alias(label, speed):
    robot = Robot("synthetic", "resource", "Vac")
    coordinator = SimpleNamespace(hass=None, last_update_success=True, rooms={},
        data={robot.did: {"online": True, "fan_speed": "Strong"}},
        execute=AsyncMock(), async_contexts=lambda: [])
    entity = YeediVacuum(coordinator, robot)
    assert entity.fan_speed_list == ["Quiet", "Strong", "Max"]
    await entity.async_set_fan_speed(label)
    coordinator.execute.assert_awaited_once_with(robot, "setSpeed", {"speed": speed})
    assert entity.fan_speed == "Strong"


async def test_invalid_speed_still_rejected():
    robot = Robot("synthetic", "resource", "Vac")
    coordinator = SimpleNamespace(hass=None, last_update_success=True, rooms={},
        data={robot.did: {"online": True, "fan_speed": "Quiet"}},
        execute=AsyncMock(), async_contexts=lambda: [])
    with pytest.raises(HomeAssistantError, match="Unsupported fan speed"):
        await YeediVacuum(coordinator, robot).async_set_fan_speed("Max+")
    coordinator.execute.assert_not_awaited()
