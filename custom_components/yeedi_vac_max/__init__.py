"""Experimental integration with no verified cloud backend yet."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Reject injected entries without creating a nonfunctional device."""
    raise ConfigEntryError("Yeedi Vac Max 0.1.0 has no verified backend. See README.")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """No connections, platforms or background tasks exist in this version."""
    return True
