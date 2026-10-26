"""Binary sensor platform for the Met Office Warnings integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import WARNING_LEVEL_NONE
from .coordinator import MetOfficeWarningsCoordinator
from .entity import MetOfficeWarningsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the warning-active binary sensor for this config entry."""
    coordinator: MetOfficeWarningsCoordinator = entry.runtime_data
    async_add_entities([MetOfficeWarningActiveBinarySensor(coordinator, entry)])


class MetOfficeWarningActiveBinarySensor(MetOfficeWarningsEntity, BinarySensorEntity):
    """On when at least one warning matches the configured area filter."""

    _attr_name = "Warning active"
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(
        self, coordinator: MetOfficeWarningsCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_warning_active"

    @property
    def is_on(self) -> bool:
        return self._data.level != WARNING_LEVEL_NONE

    @property
    def extra_state_attributes(self) -> dict | None:
        top = self._data.top
        if top is None:
            return None
        return {
            "headline": top.headline,
            "level": top.level,
            "weather_types": top.weather_types,
            "areas": top.region_names,
        }
