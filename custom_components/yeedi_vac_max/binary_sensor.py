"""Connectivity requires a successful response from the robot."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass

from .entity import YeediEntity


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    async_add_entities(YeediOnline(c, robot, "online") for robot in c.robots)


class YeediOnline(YeediEntity, BinarySensorEntity):
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def available(self):
        return self.coordinator.last_update_success

    @property
    def is_on(self):
        return self.values.get("online", False)
