"""Yeedi Vac Max direct-cloud integration."""
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_COUNTRY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import YeediClient, CloudError, InvalidAuth, VerificationRequired
from .coordinator import YeediCoordinator
from .mqtt_diagnostics import MqttProbe

PLATFORMS = [Platform.VACUUM, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.IMAGE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    mqtt_probe = None
    client = YeediClient(async_get_clientsession(hass), entry.data[CONF_USERNAME],
                         entry.data[CONF_PASSWORD], entry.data[CONF_COUNTRY],
                         entry.data["device_id"])
    try:
        async with asyncio.timeout(60):
            robots = await client.devices()
        if not robots:
            raise ConfigEntryNotReady("No Vac Max 04z443 found in this Yeedi account")
        coordinator = YeediCoordinator(hass, entry, client, robots)
        mqtt_probe = MqttProbe(robots)
        coordinator.mqtt_probe = mqtt_probe
        mqtt_probe.start(hass, entry, client)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except (InvalidAuth, VerificationRequired):
        if mqtt_probe is not None:
            await mqtt_probe.stop()
        client.close()
        raise ConfigEntryAuthFailed("Please check your Yeedi account in the integration setup") from None
    except (CloudError, TimeoutError):
        if mqtt_probe is not None:
            await mqtt_probe.stop()
        client.close()
        raise ConfigEntryNotReady("Cannot connect to Yeedi cloud") from None
    except BaseException:
        if mqtt_probe is not None:
            await mqtt_probe.stop()
        client.close()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        if getattr(entry.runtime_data, 'mqtt_probe', None) is not None:
            await entry.runtime_data.mqtt_probe.stop()
        entry.runtime_data.client.close()
        return True
    return False
