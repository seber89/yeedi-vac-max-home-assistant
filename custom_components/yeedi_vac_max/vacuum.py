"""Vac Max controls using the current activity-based vacuum API."""
from homeassistant.components.vacuum import StateVacuumEntity, VacuumActivity, VacuumEntityFeature

from .client import FAN_SPEEDS
from .entity import YeediEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(YeediVacuum(coordinator, robot) for robot in coordinator.robots)


class YeediVacuum(YeediEntity, StateVacuumEntity):
    _attr_name = None

    def __init__(self, coordinator, robot):
        super().__init__(coordinator, robot, "vacuum")

    @property
    def supported_features(self):
        features = (VacuumEntityFeature.STATE | VacuumEntityFeature.START |
                    VacuumEntityFeature.PAUSE | VacuumEntityFeature.STOP |
                    VacuumEntityFeature.RETURN_HOME)
        if self.fan_speed is not None:
            features |= VacuumEntityFeature.FAN_SPEED
        return features

    @property
    def activity(self):
        value = self.values.get("activity")
        return VacuumActivity(value) if value else None

    @property
    def fan_speed(self):
        return self.values.get("fan_speed")

    @property
    def fan_speed_list(self):
        return list(FAN_SPEEDS) if self.fan_speed else []

    async def async_start(self):
        action = "resume" if self.activity == VacuumActivity.PAUSED else "start"
        data = {"act": action}
        if action == "start":
            data.update(type="auto", count=1, donotClean=0, router="plan")
        await self.coordinator.execute(self.robot, "clean", data)

    async def async_pause(self):
        await self.coordinator.execute(self.robot, "clean", {"act": "pause"})

    async def async_stop(self, **kwargs):
        await self.coordinator.execute(self.robot, "clean", {"act": "stop"})

    async def async_return_to_base(self, **kwargs):
        await self.coordinator.execute(self.robot, "charge", {"act": "go"})

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        if fan_speed not in self.fan_speed_list:
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError("Unsupported fan speed")
        await self.coordinator.execute(self.robot, "setSpeed", {"speed": FAN_SPEEDS[fan_speed]})
