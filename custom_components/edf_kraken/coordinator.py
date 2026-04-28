"""Data coordinator for EDF Kraken."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AccountData,
    EdfKrakenApiClient,
    EdfKrakenAuthError,
    EdfKrakenError,
    EdfKrakenRateLimitError,
)
from .const import (
    CONF_ACCOUNT_NUMBER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ISSUE_AUTH_FAILED,
    ISSUE_DAILY_USAGE_UNAVAILABLE,
    ISSUE_METADATA_UNAVAILABLE,
    ISSUE_NO_METERS,
    ISSUE_RATE_LIMITED,
    OPT_ENABLE_ACCOUNT_METADATA,
    OPT_ENABLE_DAILY_USAGE,
)

LOGGER = logging.getLogger(__name__)


class EdfKrakenDataUpdateCoordinator(DataUpdateCoordinator[AccountData]):
    """Coordinate EDF Kraken updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: EdfKrakenApiClient,
        *,
        update_interval: timedelta = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.entry = entry
        self.api = api

    async def _async_update_data(self) -> AccountData:
        """Fetch the latest account data."""
        try:
            data = await self.api.get_account_data(
                self.entry.data.get(CONF_ACCOUNT_NUMBER),
                include_daily_usage=bool(self.entry.options.get(OPT_ENABLE_DAILY_USAGE, False)),
                include_metadata=bool(self.entry.options.get(OPT_ENABLE_ACCOUNT_METADATA, False)),
                timezone=self.hass.config.time_zone,
            )
            self._async_update_repair_issues(data)
            return data
        except EdfKrakenAuthError as err:
            self._async_create_issue(
                ISSUE_AUTH_FAILED,
                ir.IssueSeverity.ERROR,
                {"account_number": self._account_number_placeholder},
            )
            raise ConfigEntryAuthFailed("EDF Kraken authentication failed") from err
        except EdfKrakenRateLimitError as err:
            self._async_create_issue(
                ISSUE_RATE_LIMITED,
                ir.IssueSeverity.WARNING,
                {"account_number": self._account_number_placeholder},
            )
            raise UpdateFailed(f"EDF Kraken rate limit or point allowance exceeded: {err}") from err
        except EdfKrakenError as err:
            raise UpdateFailed(f"EDF Kraken update failed: {err}") from err

    def _async_update_repair_issues(self, data: AccountData) -> None:
        """Create or clear repair issues based on the latest successful update."""
        self._async_delete_issue(ISSUE_AUTH_FAILED)
        self._async_delete_issue(ISSUE_RATE_LIMITED)

        if data.readings:
            self._async_delete_issue(ISSUE_NO_METERS)
        else:
            self._async_create_issue(
                ISSUE_NO_METERS,
                ir.IssueSeverity.ERROR,
                {"account_number": data.account_number},
            )

        if self.entry.options.get(OPT_ENABLE_DAILY_USAGE, False):
            if data.daily_usages:
                self._async_delete_issue(ISSUE_DAILY_USAGE_UNAVAILABLE)
            else:
                self._async_create_issue(
                    ISSUE_DAILY_USAGE_UNAVAILABLE,
                    ir.IssueSeverity.WARNING,
                    {"account_number": data.account_number},
                )
        else:
            self._async_delete_issue(ISSUE_DAILY_USAGE_UNAVAILABLE)

        if self.entry.options.get(OPT_ENABLE_ACCOUNT_METADATA, False):
            if data.metadata:
                self._async_delete_issue(ISSUE_METADATA_UNAVAILABLE)
            else:
                self._async_create_issue(
                    ISSUE_METADATA_UNAVAILABLE,
                    ir.IssueSeverity.WARNING,
                    {"account_number": data.account_number},
                )
        else:
            self._async_delete_issue(ISSUE_METADATA_UNAVAILABLE)

    def _async_create_issue(
        self,
        issue_key: str,
        severity: ir.IssueSeverity,
        placeholders: dict[str, str],
    ) -> None:
        """Create a repair issue for this config entry."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id(issue_key),
            is_fixable=False,
            is_persistent=False,
            issue_domain=DOMAIN,
            severity=severity,
            translation_key=issue_key,
            translation_placeholders=placeholders,
        )

    def _async_delete_issue(self, issue_key: str) -> None:
        """Delete a repair issue for this config entry."""
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(issue_key))

    def _issue_id(self, issue_key: str) -> str:
        """Return a config-entry scoped issue id."""
        return f"{self.entry.entry_id}_{issue_key}"

    @property
    def _account_number_placeholder(self) -> str:
        """Return a repair-safe account number placeholder."""
        return str(self.entry.data.get(CONF_ACCOUNT_NUMBER) or "unknown")
