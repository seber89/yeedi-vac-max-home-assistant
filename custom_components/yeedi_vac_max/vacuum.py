"""Vac Max controls using the current activity-based vacuum API."""
from homeassistant.components.vacuum import Segment, StateVacuumEntity, VacuumActivity, VacuumEntityFeature
from homeassistant.exceptions import HomeAssistantError

from .client import FAN_SPEEDS
from .entity import YeediEntity
from .map_data import identifier


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
        if self.coordinator.rooms.get(self.robot.did):
            features |= VacuumEntityFeature.CLEAN_AREA
        return features

    async def async_get_segments(self) -> list[Segment]:
        """Expose the coordinator cache only; no second cloud room query."""
        active = self.coordinator.spatial[self.robot.did].active_map
        return [Segment(id=room.room_id, name=room.name, group=active.map_id)
                for room in self.coordinator.rooms.get(self.robot.did, ())]

    async def async_clean_segments(self, segment_ids: list[str], **kwargs) -> None:
        if not isinstance(segment_ids, (list, tuple)) or not segment_ids:
            raise HomeAssistantError("Select at least one known room")
        if self.registry_entry is not None and self.last_seen_segments is not None:
            if self.last_seen_segments != await self.async_get_segments():
                self.async_create_segments_issue()
                raise HomeAssistantError("Room mapping changed; configure area mapping again")
        known = {room.room_id for room in self.coordinator.rooms.get(self.robot.did, ())}
        selected = []
        for value in segment_ids:
            room_id = identifier(value)
            if room_id is None or room_id not in known or "," in room_id:
                raise HomeAssistantError("Unknown or invalid room selection")
            if room_id not in selected:
                selected.append(room_id)
        active = self.coordinator.spatial[self.robot.did].active_map
        if active is None:
            raise HomeAssistantError("No active map available")
        await self.coordinator.execute(self.robot, "clean", {
            "act": "start", "type": "spotArea", "content": ",".join(selected),
            "count": 1, "donotClean": 0, "router": "plan",
        }, expected_map_id=active.map_id)

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
