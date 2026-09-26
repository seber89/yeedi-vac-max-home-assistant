"""Yeedi Vac Max direct-cloud integration."""
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_COUNTRY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import YeediClient, CloudError, InvalidAuth, VerificationRequired
from .coordinator import YeediCoordinator

PLATFORMS = [Platform.VACUUM, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.IMAGE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = YeediClient(async_get_clientsession(hass), entry.data[CONF_USERNAME],
                         entry.data[CONF_PASSWORD], entry.data[CONF_COUNTRY],
                         entry.data["device_id"])
    image_forwarded = False
    try:
        async with asyncio.timeout(60):
            robots = await client.devices()
        if not robots:
            raise ConfigEntryNotReady("No Vac Max 04z443 found in this Yeedi account")
        coordinator = YeediCoordinator(hass, entry, client, robots)
        cached = await coordinator.async_load_saved_maps()
        entry.runtime_data = coordinator
        if cached:
            # Publish the private fallback before waiting for spatial cloud reads.
            # No extra task or polling loop; other platforms retain normal setup.
            await hass.config_entries.async_forward_entry_setups(entry, [Platform.IMAGE])
            image_forwarded = True
        await coordinator.async_config_entry_first_refresh()
        await hass.config_entries.async_forward_entry_setups(
            entry, [platform for platform in PLATFORMS if not image_forwarded or platform != Platform.IMAGE])
    except (InvalidAuth, VerificationRequired):
        if image_forwarded:
            await hass.config_entries.async_unload_platforms(entry, [Platform.IMAGE])
        client.close()
        raise ConfigEntryAuthFailed("Please check your Yeedi account in the integration setup") from None
    except (CloudError, TimeoutError):
        if image_forwarded:
            await hass.config_entries.async_unload_platforms(entry, [Platform.IMAGE])
        client.close()
        raise ConfigEntryNotReady("Cannot connect to Yeedi cloud") from None
    except BaseException:
        if image_forwarded:
            await hass.config_entries.async_unload_platforms(entry, [Platform.IMAGE])
        client.close()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry.runtime_data.client.close()
        return True
    return False
