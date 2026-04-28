"""EDF Kraken Home Assistant integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EdfKrakenApiClient
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_REFRESH_TOKEN,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    OPT_SCAN_INTERVAL,
    PLATFORMS,
)
from .coordinator import EdfKrakenDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EDF Kraken from a config entry."""
    session = async_get_clientsession(hass)
    api = EdfKrakenApiClient(session)
    api.set_refresh_token(entry.data[CONF_REFRESH_TOKEN])

    scan_interval = int(entry.options.get(OPT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES))
    scan_interval = max(MIN_SCAN_INTERVAL_MINUTES, min(MAX_SCAN_INTERVAL_MINUTES, scan_interval))

    coordinator = EdfKrakenDataUpdateCoordinator(
        hass,
        entry,
        api,
        update_interval=timedelta(minutes=scan_interval),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    if api.refresh_token and api.refresh_token != entry.data[CONF_REFRESH_TOKEN]:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_REFRESH_TOKEN: api.refresh_token},
        )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload EDF Kraken."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate older config entries."""
    if entry.version == 1:
        return True

    hass.config_entries.async_update_entry(entry, version=1)
    return True


def suggested_title(email: str | None, account_number: str | None) -> str:
    """Build a stable entry title."""
    if account_number:
        return f"EDF {account_number}"
    if email:
        return f"EDF {email}"
    return "EDF Kraken"
