"""Config flow for EDF Kraken."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import suggested_title
from .api import EdfKrakenApiClient, EdfKrakenAuthError, EdfKrakenError
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_REFRESH_TOKEN,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    OPT_ENABLE_ACCOUNT_METADATA,
    OPT_ENABLE_DAILY_USAGE,
    OPT_SCAN_INTERVAL,
)


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class EdfKrakenConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle EDF Kraken config flow."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = EdfKrakenApiClient(session)
            try:
                token = await api.authenticate(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
                account_number = await api.get_first_account_number()
            except EdfKrakenAuthError:
                errors["base"] = "invalid_auth"
            except EdfKrakenError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(account_number)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=suggested_title(user_input[CONF_EMAIL], account_number),
                    data={
                        CONF_ACCOUNT_NUMBER: account_number,
                        CONF_REFRESH_TOKEN: token.refresh_token,
                    },
                    options={
                        OPT_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MINUTES,
                        OPT_ENABLE_DAILY_USAGE: False,
                        OPT_ENABLE_ACCOUNT_METADATA: False,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """Handle reauth."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Confirm reauth with fresh credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = EdfKrakenApiClient(session)
            try:
                token = await api.authenticate(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
                account_number = await api.get_first_account_number()
            except EdfKrakenAuthError:
                errors["base"] = "invalid_auth"
            except EdfKrakenError:
                errors["base"] = "cannot_connect"
            else:
                entry = self._reauth_entry
                if entry is None:
                    return self.async_abort(reason="reauth_failed")
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_ACCOUNT_NUMBER: account_number,
                        CONF_REFRESH_TOKEN: token.refresh_token,
                    },
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> EdfKrakenOptionsFlow:
        """Create the options flow."""
        return EdfKrakenOptionsFlow()


class EdfKrakenOptionsFlow(config_entries.OptionsFlow):
    """Handle EDF Kraken options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    OPT_SCAN_INTERVAL,
                    default=options.get(OPT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=MAX_SCAN_INTERVAL_MINUTES),
                ),
                vol.Required(
                    OPT_ENABLE_DAILY_USAGE,
                    default=options.get(OPT_ENABLE_DAILY_USAGE, False),
                ): bool,
                vol.Required(
                    OPT_ENABLE_ACCOUNT_METADATA,
                    default=options.get(OPT_ENABLE_ACCOUNT_METADATA, False),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
