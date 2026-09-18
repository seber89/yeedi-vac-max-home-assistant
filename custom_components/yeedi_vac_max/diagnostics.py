"""Allowlisted diagnostics: no credentials, identifiers or raw responses."""
import time

from .raw_map import safe_status


def raw_diagnostics(state):
    result = {key: state.raw_status.get(key, default) for key, default in safe_status().items()}
    available = bool(state.metadata_valid and state.active_map and state.raw_map
                     and state.active_map.map_id == state.raw_map.major.map_id
                     and time.monotonic() < state.raw_valid_until)
    result.update(available=available, complete=available, image_generated=available)
    return result


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "integration_version": "0.2.0-beta.6",
        "raw_map": [raw_diagnostics(coordinator.spatial[robot.did]) for robot in coordinator.robots],
        "target_class": "04z443",
        "region": "DE",
        "last_update_success": coordinator.last_update_success,
        "structure_probe": [coordinator.client.structure_diagnostics(robot)
                            for robot in coordinator.robots],
        "room_geometry_probe": [coordinator.client.geometry_diagnostics(robot)
                                for robot in coordinator.robots],
        **{section: [coordinator.client.transport_diagnostics(robot)[section]
                     for robot in coordinator.robots] for section in (
                         "direct_major_map_probe", "direct_minor_map_probe",
                         "mqtt_map_probe", "map_transport_probe")},
        "robots": [
            {
                "online": bool((coordinator.data or {}).get(robot.did, {}).get("online")),
                "has_active_map": coordinator.spatial[robot.did].active_map is not None,
                "metadata_valid": coordinator.spatial[robot.did].metadata_valid,
                "rooms_valid": coordinator.spatial[robot.did].rooms_valid,
                "has_rooms": bool(coordinator.spatial[robot.did].rooms),
                "has_room_polygons": coordinator.spatial[robot.did].rooms_valid and any(
                    room.polygon for room in coordinator.spatial[robot.did].rooms),
                "has_robot_position": coordinator.spatial[robot.did].robot_position is not None,
                "has_dock_position": coordinator.spatial[robot.did].dock_position is not None,
                "command_pending": coordinator.commands[robot.did].pending > 0,
            }
            for robot in coordinator.robots
        ],
    }
