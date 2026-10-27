"""Tests for the Met Office Warnings data update coordinator."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.metoffice_warnings.api import (
    NSWWSAuthError,
    NSWWSConnectionError,
)
from custom_components.metoffice_warnings.const import AREA_ALL, WARNING_LEVEL_AMBER
from custom_components.metoffice_warnings.coordinator import (
    MetOfficeWarningsCoordinator,
    highest_level,
    top_warning,
)
from custom_components.metoffice_warnings.models import warnings_from_geojson


async def test_update_success_no_filter(hass, issued_active) -> None:
    client = AsyncMock()
    client.async_get_active_warnings.return_value = warnings_from_geojson(issued_active)
    coordinator = MetOfficeWarningsCoordinator(hass, client=client, areas=[AREA_ALL])

    data = await coordinator._async_update_data()

    assert len(data.warnings) == 2
    assert data.level == WARNING_LEVEL_AMBER


async def test_update_filters_by_area(hass, issued_active) -> None:
    client = AsyncMock()
    client.async_get_active_warnings.return_value = warnings_from_geojson(issued_active)
    coordinator = MetOfficeWarningsCoordinator(
        hass, client=client, areas=["West Midlands"]
    )

    data = await coordinator._async_update_data()

    assert len(data.warnings) == 1
    assert data.warnings[0].region_names == ["West Midlands"]
    assert data.level == "yellow"


async def test_update_no_matches_gives_none_level(hass, issued_active) -> None:
    client = AsyncMock()
    client.async_get_active_warnings.return_value = warnings_from_geojson(issued_active)
    coordinator = MetOfficeWarningsCoordinator(
        hass, client=client, areas=["Scotland"]
    )

    data = await coordinator._async_update_data()

    assert data.warnings == []
    assert data.level == "none"


async def test_auth_error_raises_config_entry_auth_failed(hass) -> None:
    client = AsyncMock()
    client.async_get_active_warnings.side_effect = NSWWSAuthError("nope")
    coordinator = MetOfficeWarningsCoordinator(hass, client=client, areas=[AREA_ALL])

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_connection_error_raises_update_failed(hass) -> None:
    client = AsyncMock()
    client.async_get_active_warnings.side_effect = NSWWSConnectionError("down")
    coordinator = MetOfficeWarningsCoordinator(hass, client=client, areas=[AREA_ALL])

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


def test_highest_level_orders_by_severity(issued_active) -> None:
    warnings = warnings_from_geojson(issued_active)
    assert highest_level(warnings) == WARNING_LEVEL_AMBER
    assert highest_level([]) == "none"


def test_top_warning_returns_first_or_none(issued_active) -> None:
    warnings = warnings_from_geojson(issued_active)
    assert top_warning(warnings) is warnings[0]
    assert top_warning([]) is None


async def test_top_warning_respects_location(hass, issued_active) -> None:
    client = AsyncMock()
    client.async_get_active_warnings.return_value = warnings_from_geojson(issued_active)

    inside = MetOfficeWarningsCoordinator(
        hass, client=client, areas=[AREA_ALL], latitude=51.5, longitude=-0.1
    )
    data = await inside._async_update_data()
    assert data.top is not None
    assert data.top_distance_miles == 0.0

    far = MetOfficeWarningsCoordinator(
        hass, client=client, areas=[AREA_ALL], latitude=57.0, longitude=-4.0
    )
    data = await far._async_update_data()
    assert data.top is None
    assert data.top_distance_miles is None


async def test_location_filters_level_and_warnings(hass, issued_active) -> None:
    client = AsyncMock()
    client.async_get_active_warnings.return_value = warnings_from_geojson(issued_active)

    far = MetOfficeWarningsCoordinator(
        hass, client=client, areas=[AREA_ALL], latitude=57.0, longitude=-4.0
    )
    data = await far._async_update_data()
    assert data.warnings == []
    assert data.level == "none"

    near = MetOfficeWarningsCoordinator(
        hass, client=client, areas=[AREA_ALL], latitude=51.5, longitude=-0.1
    )
    data = await near._async_update_data()
    assert data.warnings
    assert data.level != "none"


async def test_top_warning_is_nearest_of_equal_severity(hass, issued_active) -> None:
    from dataclasses import replace

    base = warnings_from_geojson(issued_active)[0]
    square = lambda lon: (  # noqa: E731
        [[[lon, 51.0], [lon, 52.0], [lon + 1, 52.0], [lon + 1, 51.0], [lon, 51.0]]],
    )
    far = replace(base, warning_id="far", polygons=square(5.0))
    near = replace(base, warning_id="near", polygons=square(1.0))
    client = AsyncMock()
    client.async_get_active_warnings.return_value = [far, near]

    coordinator = MetOfficeWarningsCoordinator(
        hass,
        client=client,
        areas=[AREA_ALL],
        latitude=51.5,
        longitude=0.0,
        distance_miles=500,
    )
    data = await coordinator._async_update_data()
    assert data.top.warning_id == "near"
    assert data.top_distance_miles < 100


async def test_weather_type_filter(hass, issued_active) -> None:
    client = AsyncMock()
    client.async_get_active_warnings.return_value = warnings_from_geojson(issued_active)

    wind = MetOfficeWarningsCoordinator(
        hass, client=client, areas=[AREA_ALL], weather_types=["WIND"]
    )
    data = await wind._async_update_data()
    assert [w.weather_types for w in data.warnings] == [["WIND"]]

    snow = MetOfficeWarningsCoordinator(
        hass, client=client, areas=[AREA_ALL], weather_types=["SNOW"]
    )
    data = await snow._async_update_data()
    assert data.warnings == []
    assert data.level == "none"

    everything = MetOfficeWarningsCoordinator(hass, client=client, areas=[AREA_ALL])
    assert len((await everything._async_update_data()).warnings) == 2
