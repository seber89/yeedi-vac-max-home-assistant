"""Yeedi account setup and reauthentication, restricted to DE."""
import asyncio
import logging
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_COUNTRY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .client import YeediClient, CloudError, CannotConnect, InvalidAuth, VerificationRequired
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class YeediVacMaxConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            data = dict(user_input)
            data[CONF_USERNAME] = data[CONF_USERNAME].strip()
            data[CONF_COUNTRY] = data[CONF_COUNTRY].strip().upper()
            if data[CONF_COUNTRY] != "DE":
                errors["base"] = "unsupported_country"
            elif not data[CONF_USERNAME] or not data[CONF_PASSWORD]:
                errors["base"] = "invalid_auth"
            else:
                reauth = self.source == "reauth"
                old = self._get_reauth_entry() if reauth else None
                data["device_id"] = old.data["device_id"] if old else uuid4().hex
                client = YeediClient(async_get_clientsession(self.hass),
                                     data[CONF_USERNAME], data[CONF_PASSWORD], "DE",
                                     data["device_id"])
                try:
                    async with asyncio.timeout(60):
                        robots = await client.devices()
                    if not robots:
                        errors["base"] = "no_devices"
                    else:
                        await self.async_set_unique_id("DE:" + client.user_id)
                        if reauth:
                            self._abort_if_unique_id_mismatch()
                            return self.async_update_reload_and_abort(old, data_updates=data)
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(title="Yeedi Vac Max", data=data)
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except VerificationRequired:
                    errors["base"] = "verification_required"
                except (CannotConnect, TimeoutError):
                    errors["base"] = "cannot_connect"
                except CloudError as err:
                    _LOGGER.debug("Yeedi setup failed: %s", err)
                    errors["base"] = "unknown"
                finally:
                    client.close()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Required(CONF_COUNTRY, default="DE"): str,
        }), errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_user()
