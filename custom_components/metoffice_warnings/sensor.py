"""Sensor platform for the Met Office Warnings integration."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LATITUDE, CONF_LONGITUDE, WARNING_LEVELS
from .coordinator import MetOfficeWarningsCoordinator
from .entity import MetOfficeWarningsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the warning sensors for this config entry."""
    coordinator: MetOfficeWarningsCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
            MetOfficeWarningLevelSensor(coordinator, entry),
            MetOfficeWarningHeadlineSensor(coordinator, entry),
            MetOfficeWarningAreasSensor(coordinator, entry),
            MetOfficeWarningValidFromSensor(coordinator, entry),
            MetOfficeWarningValidToSensor(coordinator, entry),
    ]
    latitude = entry.options.get(CONF_LATITUDE)
    longitude = entry.options.get(CONF_LONGITUDE)
    if latitude is not None and longitude is not None:
        entities.append(MetOfficeWarningDistanceSensor(coordinator, entry))
    async_add_entities(entities)


class MetOfficeWarningLevelSensor(MetOfficeWarningsEntity, SensorEntity):
    """Highest active warning level among the configured areas."""

    _attr_name = "Warning level"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(WARNING_LEVELS)

    def __init__(
        self, coordinator: MetOfficeWarningsCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_warning_level"

    @property
    def native_value(self) -> str:
        return self._data.level

    @property
    def extra_state_attributes(self) -> dict:
        warnings = self._data.warnings
        return {
            "warning_count": len(warnings),
            "warnings": [w.as_dict() for w in warnings],
        }


class MetOfficeWarningHeadlineSensor(MetOfficeWarningsEntity, SensorEntity):
    """Headline of the single most prominent active warning, if any."""

    _attr_name = "Warning headline"

    def __init__(
        self, coordinator: MetOfficeWarningsCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_warning_headline"

    @property
    def native_value(self) -> str | None:
        top = self._data.top
        return top.headline if top else None

    @property
    def extra_state_attributes(self) -> dict | None:
        top = self._data.top
        if top is None:
            return None
        return {
            "level": top.level,
            "weather_types": top.weather_types,
            "what_to_expect": top.what_to_expect,
            "what_should_i_do": top.what_should_i_do,
            "further_details": top.further_details,
            "likelihood": top.likelihood,
            "impact": top.impact,
        }


class MetOfficeWarningAreasSensor(MetOfficeWarningsEntity, SensorEntity):
    """Comma-separated regions affected by the most prominent active warning."""

    _attr_name = "Warning areas"

    def __init__(
        self, coordinator: MetOfficeWarningsCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_warning_areas"

    @property
    def native_value(self) -> str | None:
        top = self._data.top
        return ", ".join(top.region_names) if top else None


class MetOfficeWarningValidFromSensor(MetOfficeWarningsEntity, SensorEntity):
    """Start time of the most prominent active warning."""

    _attr_name = "Warning valid from"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: MetOfficeWarningsCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_warning_valid_from"

    @property
    def native_value(self) -> datetime | None:
        top = self._data.top
        return top.valid_from if top else None


class MetOfficeWarningValidToSensor(MetOfficeWarningsEntity, SensorEntity):
    """End time of the most prominent active warning."""

    _attr_name = "Warning valid to"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: MetOfficeWarningsCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_warning_valid_to"

    @property
    def native_value(self) -> datetime | None:
        top = self._data.top
        return top.valid_to if top else None


class MetOfficeWarningDistanceSensor(MetOfficeWarningsEntity, SensorEntity):
    """Distance from the configured location to the top warning's region."""

    _attr_name = "Warning distance"
    # No DISTANCE device class: HA would convert the miles value to the user's
    # unit system (e.g. km) and the distance filter is configured in miles.
    _attr_native_unit_of_measurement = UnitOfLength.MILES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: MetOfficeWarningsCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_warning_distance"

    @property
    def native_value(self) -> float | None:
        return self._data.top_distance_miles
