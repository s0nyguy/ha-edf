"""Data coordinator for EDF Kraken."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AccountData,
    EdfKrakenApiClient,
    EdfKrakenAuthError,
    EdfKrakenError,
    EdfKrakenRateLimitError,
)
from .const import CONF_ACCOUNT_NUMBER, DEFAULT_SCAN_INTERVAL, DOMAIN

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
            return await self.api.get_account_data(self.entry.data.get(CONF_ACCOUNT_NUMBER))
        except EdfKrakenAuthError as err:
            raise ConfigEntryAuthFailed("EDF Kraken authentication failed") from err
        except EdfKrakenRateLimitError as err:
            raise UpdateFailed(f"EDF Kraken rate limit or point allowance exceeded: {err}") from err
        except EdfKrakenError as err:
            raise UpdateFailed(f"EDF Kraken update failed: {err}") from err
