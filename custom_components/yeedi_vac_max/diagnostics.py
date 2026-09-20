"""Compact allowlisted support diagnostics; no private cloud or map contents."""
import time

_BUCKETS = frozenset(("0", "1", "2-8", "9-32", "33-64", ">64"))
_FAILURES = frozenset(("none", "major_initial", "piece_download", "piece_decode",
                      "generation_changed", "raster_assembly", "no_visible_pixels",
                      "png_generation", "unexpected"))


def raw_diagnostics(state):
    result = {}
    for key in ("major_valid", "image_generated", "generation_verified"):
        result[key] = state.raw_status.get(key) is True
    for key in ("loaded_piece_count_bucket", "decoded_piece_count_bucket", "decode_failures_bucket"):
        value = state.raw_status.get(key)
        result[key] = value if type(value) is str and value in _BUCKETS else "0"
    failure = state.raw_status.get("failure_stage")
    result["failure_stage"] = failure if type(failure) is str and failure in _FAILURES else "unexpected"
    available = bool(state.metadata_valid and state.active_map and state.raw_map
                     and state.active_map.map_id == state.raw_map.major.map_id
                     and time.monotonic() < state.raw_valid_until)
    result.update(available=available, complete=available)
    return result


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "integration_version": "0.2.0-rc.2",
        "last_update_success": bool(coordinator.last_update_success),
        "raw_map": [raw_diagnostics(coordinator.spatial[robot.did]) for robot in coordinator.robots],
        "robots": [
            {
                "online": bool((coordinator.data or {}).get(robot.did, {}).get("online")),
                "has_active_map": coordinator.spatial[robot.did].active_map is not None,
                "metadata_valid": bool(coordinator.spatial[robot.did].metadata_valid),
                "rooms_valid": bool(coordinator.spatial[robot.did].rooms_valid),
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
