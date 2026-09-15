"""Explain the backend limitation before requesting account secrets."""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class YeediVacMaxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Stop setup until a working direct Yeedi backend is available."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Never persist or transmit user input for an absent backend."""
        return self.async_abort(reason="backend_not_verified")
