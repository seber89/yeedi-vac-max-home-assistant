"""Allowlisted diagnostics: no credentials, identifiers or raw responses."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "integration_version": "0.2.0-alpha.1",
        "target_class": "04z443",
        "region": "DE",
        "last_update_success": coordinator.last_update_success,
        "robots": [
            {
                "online": bool((coordinator.data or {}).get(robot.did, {}).get("online")),
                "has_active_map": coordinator.spatial[robot.did].active_map is not None,
                "metadata_valid": coordinator.spatial[robot.did].metadata_valid,
                "rooms_valid": coordinator.spatial[robot.did].rooms_valid,
                "has_rooms": bool(coordinator.spatial[robot.did].rooms),
                "has_robot_position": coordinator.spatial[robot.did].robot_position is not None,
                "has_dock_position": coordinator.spatial[robot.did].dock_position is not None,
                "command_pending": coordinator.commands[robot.did].pending > 0,
            }
            for robot in coordinator.robots
        ],
    }
