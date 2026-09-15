"""Bounded polling with per-device availability and no optimistic states."""
import asyncio
from datetime import timedelta
import logging

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import CloudError, InvalidAuth, VerificationRequired

_LOGGER = logging.getLogger(__name__)


class YeediCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client, robots):
        super().__init__(hass, _LOGGER, name="Yeedi Vac Max",
                         config_entry=entry, update_interval=timedelta(seconds=60))
        self.client = client
        self.robots = robots
        self._io_lock = asyncio.Lock()

    async def _async_update_data(self):
        try:
            async with self._io_lock:
                async with asyncio.timeout(60):
                    states = await asyncio.gather(*(self.client.snapshot(r) for r in self.robots))
            return {r.did: state for r, state in zip(self.robots, states, strict=True)}
        except (InvalidAuth, VerificationRequired):
            raise ConfigEntryAuthFailed("Yeedi authentication requires attention") from None
        except (CloudError, TimeoutError) as err:
            _LOGGER.debug("Yeedi refresh failed: %s", err)
            raise UpdateFailed("Could not refresh Yeedi devices") from None

    async def execute(self, robot, command, data):
        try:
            async with self._io_lock:
                async with asyncio.timeout(60):
                    await self.client.command(robot, command, data, writing=True)
        except (InvalidAuth, VerificationRequired):
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Yeedi login expired; please reauthenticate") from None
        except (CloudError, TimeoutError) as err:
            _LOGGER.debug("Yeedi command %s failed: %s", command, err)
            raise HomeAssistantError("Yeedi command was not confirmed; check robot and connection") from None
        await self.async_request_refresh()
