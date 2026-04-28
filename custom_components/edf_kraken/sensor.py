"""Sensors for EDF Kraken."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
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

from .api import AccountMetadata, DailyUsage, MeterReading
from .const import DOMAIN, MANUFACTURER
from .coordinator import EdfKrakenDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class EdfKrakenSensorEntityDescription(SensorEntityDescription):
    """EDF Kraken sensor description."""

    source_unique_id: str


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EDF Kraken sensors."""
    coordinator: EdfKrakenDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = [
        EdfKrakenReadingSensor(coordinator, entry, reading)
        for reading in coordinator.data.readings
    ]
    entities.extend(
        EdfKrakenReadingTimestampSensor(coordinator, entry, reading)
        for reading in coordinator.data.readings
    )
    entities.extend(
        EdfKrakenDailyUsageSensor(coordinator, entry, usage)
        for usage in coordinator.data.daily_usages
    )
    entities.extend(
        EdfKrakenMetadataSensor(coordinator, entry, item)
        for item in coordinator.data.metadata
    )
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
            source_unique_id=reading.unique_id,
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
            if reading.unique_id == self.entity_description.source_unique_id:
                return reading
        return None


class EdfKrakenReadingTimestampSensor(
    CoordinatorEntity[EdfKrakenDataUpdateCoordinator],
    SensorEntity,
):
    """Latest EDF meter reading timestamp sensor."""

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
        unique_id = f"{reading.unique_id}_latest_reading"
        self.entity_description = EdfKrakenSensorEntityDescription(
            key=unique_id,
            source_unique_id=reading.unique_id,
            name=f"{reading.name} Latest Reading",
            device_class=SensorDeviceClass.TIMESTAMP,
        )
        self._attr_unique_id = unique_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, _device_identifier(reading))},
            "manufacturer": MANUFACTURER,
            "name": _device_name(reading),
        }

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the latest reading."""
        reading = self._current_reading
        return _parse_datetime(reading.read_at) if reading else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return useful reading metadata."""
        reading = self._current_reading
        if reading is None:
            return {}
        return {
            "account_number": reading.account_number,
            "fuel": reading.fuel,
            "meter_point_id": reading.meter_point_id,
            "meter_id": reading.meter_id,
            "register_id": reading.register_id,
            "serial_number": reading.serial_number,
        }

    @property
    def _current_reading(self) -> MeterReading | None:
        for reading in self.coordinator.data.readings:
            if reading.unique_id == self.entity_description.source_unique_id:
                return reading
        return None


class EdfKrakenDailyUsageSensor(
    CoordinatorEntity[EdfKrakenDataUpdateCoordinator],
    SensorEntity,
):
    """Optional grouped daily usage sensor."""

    entity_description: EdfKrakenSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EdfKrakenDataUpdateCoordinator,
        entry: ConfigEntry,
        usage: DailyUsage,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = EdfKrakenSensorEntityDescription(
            key=usage.unique_id,
            source_unique_id=usage.unique_id,
            name=usage.name,
            device_class=_usage_device_class(usage),
            native_unit_of_measurement=_usage_unit(usage),
            state_class=SensorStateClass.TOTAL,
        )
        self._attr_unique_id = usage.unique_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, _usage_device_identifier(usage))},
            "manufacturer": MANUFACTURER,
            "name": _usage_device_name(usage),
        }

    @property
    def native_value(self) -> float | None:
        """Return the latest grouped daily usage value."""
        usage = self._current_usage
        return usage.value if usage else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return usage metadata."""
        usage = self._current_usage
        if usage is None:
            return {}
        return {
            "account_number": usage.account_number,
            "fuel": usage.fuel,
            "start_at": usage.start_at,
            "end_at": usage.end_at,
            "is_estimate": usage.is_estimate,
            "meter_point_id": usage.meter_point_id,
            "meter_id": usage.meter_id,
            "serial_number": usage.serial_number,
        }

    @property
    def _current_usage(self) -> DailyUsage | None:
        for usage in self.coordinator.data.daily_usages:
            if usage.unique_id == self.entity_description.source_unique_id:
                return usage
        return None


class EdfKrakenMetadataSensor(
    CoordinatorEntity[EdfKrakenDataUpdateCoordinator],
    SensorEntity,
):
    """Optional account metadata sensor."""

    entity_description: EdfKrakenSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EdfKrakenDataUpdateCoordinator,
        entry: ConfigEntry,
        item: AccountMetadata,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = EdfKrakenSensorEntityDescription(
            key=item.unique_id,
            source_unique_id=item.unique_id,
            name=item.name,
            device_class=_metadata_device_class(item),
            native_unit_of_measurement=item.unit,
        )
        self._attr_unique_id = item.unique_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, item.account_number)},
            "manufacturer": MANUFACTURER,
            "name": f"EDF Account {item.account_number}",
        }

    @property
    def native_value(self) -> str | float | None:
        """Return metadata value."""
        item = self._current_item
        return item.value if item else None

    @property
    def _current_item(self) -> AccountMetadata | None:
        for item in self.coordinator.data.metadata:
            if item.unique_id == self.entity_description.source_unique_id:
                return item
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


def _usage_device_class(usage: DailyUsage) -> SensorDeviceClass:
    if usage.fuel == "electricity":
        return SensorDeviceClass.ENERGY
    if usage.unit == "kWh":
        return SensorDeviceClass.ENERGY
    return SensorDeviceClass.GAS


def _usage_unit(usage: DailyUsage) -> str:
    if usage.unit == "kWh":
        return UnitOfEnergy.KILO_WATT_HOUR
    if usage.unit == "m3":
        return UnitOfVolume.CUBIC_METERS
    return usage.unit


def _usage_device_identifier(usage: DailyUsage) -> str:
    parts = [
        usage.account_number,
        usage.fuel,
        usage.meter_point_id,
        usage.meter_id,
        usage.serial_number,
    ]
    return "_".join(part for part in parts if part)


def _usage_device_name(usage: DailyUsage) -> str:
    if usage.serial_number:
        return f"EDF {usage.fuel.title()} Meter {usage.serial_number}"
    return f"EDF {usage.fuel.title()} Meter"


def _metadata_device_class(item: AccountMetadata) -> SensorDeviceClass | None:
    if item.device_class == "monetary":
        return SensorDeviceClass.MONETARY
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
