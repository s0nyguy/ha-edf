"""Sensors for EDF Kraken."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import MeterReading
from .const import DOMAIN, MANUFACTURER
from .coordinator import EdfKrakenDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class EdfKrakenSensorEntityDescription(SensorEntityDescription):
    """EDF Kraken sensor description."""

    reading_unique_id: str


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EDF Kraken sensors."""
    coordinator: EdfKrakenDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [
        EdfKrakenReadingSensor(coordinator, entry, reading)
        for reading in coordinator.data.readings
    ]
    async_add_entities(entities)


class EdfKrakenReadingSensor(
    CoordinatorEntity[EdfKrakenDataUpdateCoordinator],
    SensorEntity,
):
    """Cumulative EDF meter reading sensor."""

    entity_description: EdfKrakenSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EdfKrakenDataUpdateCoordinator,
        entry: ConfigEntry,
        reading: MeterReading,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = EdfKrakenSensorEntityDescription(
            key=reading.unique_id,
            reading_unique_id=reading.unique_id,
            name=reading.name,
            device_class=_device_class(reading),
            native_unit_of_measurement=_unit(reading),
            state_class=SensorStateClass.TOTAL_INCREASING,
        )
        self._attr_unique_id = reading.unique_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, _device_identifier(reading))},
            "manufacturer": MANUFACTURER,
            "name": _device_name(reading),
        }

    @property
    def native_value(self) -> float | None:
        """Return the latest normalized reading value."""
        reading = self._current_reading
        return reading.value if reading else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return useful reading metadata."""
        reading = self._current_reading
        if reading is None:
            return {}
        return {
            "account_number": reading.account_number,
            "fuel": reading.fuel,
            "read_at": reading.read_at,
            "meter_point_id": reading.meter_point_id,
            "meter_id": reading.meter_id,
            "register_id": reading.register_id,
            "serial_number": reading.serial_number,
        }

    @property
    def _current_reading(self) -> MeterReading | None:
        for reading in self.coordinator.data.readings:
            if reading.unique_id == self.entity_description.reading_unique_id:
                return reading
        return None


def _device_class(reading: MeterReading) -> SensorDeviceClass:
    if reading.fuel == "electricity":
        return SensorDeviceClass.ENERGY
    if reading.unit == "kWh":
        return SensorDeviceClass.ENERGY
    return SensorDeviceClass.GAS


def _unit(reading: MeterReading) -> str:
    if reading.unit == "kWh":
        return UnitOfEnergy.KILO_WATT_HOUR
    if reading.unit == "m3":
        return UnitOfVolume.CUBIC_METERS
    return reading.unit


def _device_identifier(reading: MeterReading) -> str:
    parts = [
        reading.account_number,
        reading.fuel,
        reading.meter_point_id,
        reading.meter_id,
        reading.serial_number,
    ]
    return "_".join(part for part in parts if part)


def _device_name(reading: MeterReading) -> str:
    if reading.serial_number:
        return f"EDF {reading.fuel.title()} Meter {reading.serial_number}"
    return f"EDF {reading.fuel.title()} Meter"
