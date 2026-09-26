"""Compact allowlisted support diagnostics; no private cloud or map contents."""

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
    available = state.image_map is not None
    result.update(available=available, complete=available)
    return result


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "integration_version": "0.2.0-rc.7",
        "last_update_success": bool(coordinator.last_update_success),
        "raw_map": [raw_diagnostics(coordinator.spatial[robot.did]) for robot in coordinator.robots],
        "map_reactivation": [reactivation_diagnostics(coordinator.spatial[robot.did]) for robot in coordinator.robots],
        "robots": [
            {
                "online": bool((coordinator.data or {}).get(robot.did, {}).get("online")),
                "activity": safe_activity((coordinator.data or {}).get(robot.did, {}).get("activity")),
                "has_persisted_map": bool(coordinator.spatial[robot.did].has_persisted_map),
                "using_persisted_fallback": coordinator.spatial[robot.did].using_persisted_fallback,
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


def safe_activity(value):
    return value if type(value) is str and value in {
        'docked', 'returning', 'cleaning', 'paused', 'idle', 'error', 'unknown'} else 'unknown'


def reactivation_diagnostics(state):
    value = state.post_reactivation_result
    return {
        'yeedi_map_info_attempted': state.yeedi_map_info_attempted is True,
        'yeedi_map_info_valid': state.yeedi_map_info_valid is True,
        'yeedi_map_identity_match': state.yeedi_map_identity_match is True,
        'map_reactivation_attempted': state.map_reactivation_attempted is True,
        'map_reactivation_confirmed': state.map_reactivation_confirmed is True,
        'post_reactivation_build_attempted': state.post_reactivation_build_attempted is True,
        'post_reactivation_result': value if type(value) is str and value in {
            'not_needed', 'success', 'no_visible_pixels', 'rejected', 'uncertain',
            'map_changed', 'yeedi_map_info_timeout', 'yeedi_map_info_invalid',
            'map_identity_mismatch', 'unexpected', 'rate_limited'} else 'unexpected',
    }
