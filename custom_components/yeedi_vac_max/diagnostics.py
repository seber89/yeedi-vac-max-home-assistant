"""Compact allowlisted support diagnostics; no private cloud or map contents."""
import time

from .clean_log_map import safe_probe
from .raw_map import safe_visibility

_BUCKETS = frozenset(("0", "1", "2-8", "9-32", "33-64", ">64"))
_FAILURES = frozenset(("none", "major_initial", "piece_download", "piece_decode",
                      "generation_changed", "raster_assembly", "no_visible_pixels",
                      "png_generation", "unexpected"))
_REFRESH_RESULTS = (_FAILURES - {'none'}) | {
    'never', 'success', 'map_changed', 'timeout', 'cloud_error'}
_DECISIONS = {'never', 'attempted', 'skipped_invalid_metadata',
              'skipped_no_active_map', 'skipped_not_due', 'skipped_activity_hold'}


def refresh_bucket(value):
    if type(value) is not int or value < 0:
        return '0'
    return '0' if value == 0 else '1' if value == 1 else '2-3' if value <= 3 else '4-8' if value <= 8 else '>8'


def raw_refresh_diagnostics(state, activity):
    """Read RAM observations and deadlines only; no I/O or exported clock values."""
    probe = state.raw_refresh_probe
    def result(value):
        return value if type(value) is str and value in _REFRESH_RESULTS else 'unexpected'
    due = time.monotonic() >= state.next_raw_refresh
    last = result(probe.last_result)
    backoff = not due and probe.error_backoff is True
    same_map = bool(state.active_map and (
        (state.raw_map and state.raw_map.major.map_id == state.active_map.map_id) or
        (state.saved_map and state.saved_map.map_id == state.active_map.map_id)))
    hold = ('invalid_metadata' if not state.metadata_valid else
            'no_active_map' if state.active_map is None else
            'activity_hold' if same_map and activity in {'cleaning', 'paused', 'returning'} else
            'backoff' if backoff else 'cache_interval' if not due else 'none')
    return {
        'raw_refresh_attempt_bucket': refresh_bucket(probe.attempts),
        'raw_refresh_success_bucket': refresh_bucket(probe.successes),
        'raw_refresh_failure_bucket': refresh_bucket(probe.failures),
        'raw_refresh_normal_attempt_bucket': refresh_bucket(probe.normal_attempts),
        'raw_refresh_fresh_attempt_bucket': refresh_bucket(probe.fresh_attempts),
        'raw_refresh_last_result': last,
        'raw_refresh_last_fresh_result': result(probe.last_fresh_result),
        'raw_refresh_last_mode': probe.last_mode if type(probe.last_mode) is str and probe.last_mode in {'never', 'normal', 'fresh'} else 'never',
        'raw_refresh_last_decision': probe.decision if type(probe.decision) is str and probe.decision in _DECISIONS else 'never',
        'raw_refresh_backoff_active': backoff,
        'raw_refresh_due': due,
        'raw_refresh_current_hold': hold,
    }


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


def visibility_diagnostics(state):
    defaults = safe_visibility()
    source = state.raw_status.get('raw_visibility')
    if not isinstance(source, dict):
        return defaults
    for key, default in defaults.items():
        value = source.get(key)
        if type(default) is bool:
            defaults[key] = value is True
        elif key.endswith('_bucket'):
            defaults[key] = value if type(value) is str and value in {'0', '1', '2-3', '4-8', '9-32', '33-64', '>64'} else '0'
        else:
            defaults[key] = value if type(value) is str and value in {
                'not_attempted', 'reused_image', 'success', 'generation_changed',
                'raster_assembly', 'no_visible_pixels', 'png_generation'} else 'not_attempted'
    return defaults


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "integration_version": "0.2.0-rc.16",
        "last_update_success": bool(coordinator.last_update_success),
        "fast_position": [coordinator.fast_positions[robot.did].diagnostics() for robot in coordinator.robots],
        "raw_map": [raw_diagnostics(coordinator.spatial[robot.did]) for robot in coordinator.robots],
        "raw_composition": [visibility_diagnostics(coordinator.spatial[robot.did]) for robot in coordinator.robots],
        "raw_refresh": [raw_refresh_diagnostics(coordinator.spatial[robot.did],
                        safe_activity(getattr(coordinator, '_map_activity', {}).get(robot.did))) for robot in coordinator.robots],
        "map_reactivation": [reactivation_diagnostics(coordinator.spatial[robot.did]) for robot in coordinator.robots],
        "clean_log_map": [clean_log_diagnostics(coordinator.spatial[robot.did]) for robot in coordinator.robots],
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


def clean_log_diagnostics(state):
    result = safe_probe(state.clean_log_probe)
    result['clean_log_fallback_active'] = state.image_map is None and state.historical_image is not None
    return result


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
