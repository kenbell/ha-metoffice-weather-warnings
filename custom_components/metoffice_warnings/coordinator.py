"""Data update coordinator for the Met Office Warnings integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NSWWSApiClient, NSWWSAuthError, NSWWSConnectionError
from .const import (
    AREA_ALL,
    DEFAULT_DISTANCE_MILES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    WARNING_LEVEL_NONE,
    WARNING_LEVELS,
)
from .geo import distance_to_polygons_miles
from .models import Warning

_LOGGER = logging.getLogger(__name__)

_SEVERITY_RANK = {level: index for index, level in enumerate(WARNING_LEVELS)}


def highest_level(warnings: list[Warning]) -> str:
    """Return the most severe level present, or 'none' if the list is empty."""
    if not warnings:
        return WARNING_LEVEL_NONE
    return max((w.level for w in warnings), key=lambda level: _SEVERITY_RANK[level])


def top_warning(warnings: list[Warning]) -> Warning | None:
    """Return the most prominent active warning, or None if there isn't one.

    The API already sorts `/objects/issued` by severity (RED > AMBER > YELLOW),
    then impact/likelihood, then chronologically - so the first entry in an
    already-filtered list is the one worth surfacing on its own.
    """
    return warnings[0] if warnings else None


def _matches_area(warning: Warning, areas: list[str]) -> bool:
    if AREA_ALL in areas:
        return True
    return any(region in areas for region in warning.region_names)


@dataclass(frozen=True, slots=True)
class WarningsData:
    """Coordinator payload: the filtered warnings plus the derived overall level."""

    warnings: list[Warning]
    level: str
    top: Warning | None = None
    top_distance_miles: float | None = None


class MetOfficeWarningsCoordinator(DataUpdateCoordinator[WarningsData]):
    """Polls NSWWS `/issued` and filters the result to the configured areas."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: NSWWSApiClient,
        areas: list[str],
        update_interval=DEFAULT_SCAN_INTERVAL,
        latitude: float | None = None,
        longitude: float | None = None,
        distance_miles: float = DEFAULT_DISTANCE_MILES,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self._client = client
        self._areas = areas
        self._latitude = latitude
        self._longitude = longitude
        self._distance_miles = distance_miles

    async def _async_update_data(self) -> WarningsData:
        try:
            all_warnings = await self._client.async_get_active_warnings()
        except NSWWSAuthError as err:
            raise ConfigEntryAuthFailed(
                "Met Office rejected the configured API key"
            ) from err
        except NSWWSConnectionError as err:
            raise UpdateFailed(f"Error fetching NSWWS warnings: {err}") from err

        matched = [w for w in all_warnings if _matches_area(w, self._areas)]
        if self._latitude is None or self._longitude is None:
            return WarningsData(
                warnings=matched,
                level=highest_level(matched),
                top=top_warning(matched),
            )

        # Keep only warnings whose region is within the configured distance.
        # The API order (most prominent first) is preserved.
        nearby: list[tuple[Warning, float]] = []
        for warning in matched:
            distance = distance_to_polygons_miles(
                warning.polygons, self._latitude, self._longitude
            )
            if distance is not None and distance <= self._distance_miles:
                nearby.append((warning, distance))

        warnings = [w for w, _ in nearby]
        return WarningsData(
            warnings=warnings,
            level=highest_level(warnings),
            top=warnings[0] if warnings else None,
            top_distance_miles=round(nearby[0][1], 1) if nearby else None,
        )
