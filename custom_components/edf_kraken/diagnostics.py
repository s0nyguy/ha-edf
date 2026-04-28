"""Diagnostics for EDF Kraken."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_REFRESH_TOKEN, DOMAIN

TO_REDACT = {CONF_REFRESH_TOKEN, "token", "access_token", "refreshToken", "refresh_token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    return {
        "entry": {
            "title": entry.title,
            "data": _redact(entry.data),
            "options": dict(entry.options),
        },
        "account": {
            "account_number": coordinator.data.account_number,
            "reading_count": len(coordinator.data.readings),
            "readings": [
                {
                    "unique_id": reading.unique_id,
                    "fuel": reading.fuel,
                    "unit": reading.unit,
                    "read_at": reading.read_at,
                    "meter_point_id": reading.meter_point_id,
                    "meter_id": reading.meter_id,
                    "serial_number": reading.serial_number,
                }
                for reading in coordinator.data.readings
            ],
        },
    }


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "**REDACTED**" if key in TO_REDACT else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
