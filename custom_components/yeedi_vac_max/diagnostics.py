"""Allowlisted diagnostics: no credentials, identifiers or raw responses."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "integration_version": "0.1.0",
        "target_class": "04z443",
        "region": "DE",
        "last_update_success": coordinator.last_update_success,
        "robots": [
            {key: state.get(key) for key in ("online", "activity", "battery", "fan_speed")}
            for state in (coordinator.data or {}).values()
        ],
    }
