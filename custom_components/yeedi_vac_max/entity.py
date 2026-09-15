"""Shared device identity."""
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class YeediEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, robot, key):
        super().__init__(coordinator)
        self.robot = robot
        self._attr_unique_id = f"{robot.did}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, robot.did)}, manufacturer="yeedi",
            model="Yeedi Vac Max DVX34", name=robot.name)

    @property
    def values(self):
        return (self.coordinator.data or {}).get(self.robot.did, {})

    @property
    def available(self):
        return super().available and self.values.get("online", False)
