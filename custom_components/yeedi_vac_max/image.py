"""Coordinator-only map image; no independent cloud requests or disk cache."""
import time

from homeassistant.components.image import ImageEntity
from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from .entity import YeediEntity
from .svg_map import render_map


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(YeediMapImage(coordinator, robot) for robot in coordinator.robots)


class YeediMapImage(YeediEntity, ImageEntity):
    _attr_name = "Map"
    _attr_content_type = "image/svg+xml"

    def __init__(self, coordinator, robot):
        ImageEntity.__init__(self, coordinator.hass)
        YeediEntity.__init__(self, coordinator, robot, "map")
        self._render_key = None
        self._svg = None
        self._sync_image()

    def _current_key(self):
        state = self.coordinator.spatial[self.robot.did]
        valid = (super().available and state.active_map is not None
                 and state.metadata_valid and state.rooms_valid
                 and time.monotonic() < state.next_map_refresh)
        return (state.active_map.map_id, state.room_generation, state.rooms,
               state.robot_position, state.dock_position) if valid else None

    def _sync_image(self):
        state = self.coordinator.spatial[self.robot.did]
        key = self._current_key()
        if key != self._render_key:
            self._render_key = key
            self._svg = render_map(state.rooms, state.robot_position, state.dock_position) if key else None
            self._attr_image_last_updated = dt_util.utcnow()

    @property
    def available(self):
        return self._current_key() == self._render_key and self._svg is not None

    @callback
    def _handle_coordinator_update(self):
        self._sync_image()
        super()._handle_coordinator_update()

    async def async_image(self):
        # The image endpoint may be accessed even while the entity is unavailable.
        return self._svg if self.available else None
