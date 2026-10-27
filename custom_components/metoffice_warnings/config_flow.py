"""Config flow for the Met Office Warnings integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .api import NSWWSApiClient, NSWWSAuthError, NSWWSConnectionError
from .const import (
    AREA_ALL,
    CONF_API_KEY,
    CONF_AREAS,
    CONF_BASE_URL,
    CONF_DISTANCE_MILES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_WEATHER_TYPES,
    DEFAULT_DISTANCE_MILES,
    CONF_MONITOR_ALL,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MIN_SCAN_INTERVAL_MINUTES,
    WEATHER_TYPES,
)
from .models import Warning

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
    }
)

STEP_LOCATION_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Required(CONF_DISTANCE_MILES, default=DEFAULT_DISTANCE_MILES): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
    }
)

WEATHER_TYPE_CHOICES = {t: t.capitalize() for t in WEATHER_TYPES}

STEP_WEATHER_TYPES_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_WEATHER_TYPES, default=[]): cv.multi_select(
            WEATHER_TYPE_CHOICES
        ),
    }
)


async def _async_fetch_warnings(hass, api_key: str, base_url: str) -> list[Warning]:
    """Validate credentials and return the currently active warnings.

    Raises NSWWSAuthError / NSWWSConnectionError on failure.
    """
    client = NSWWSApiClient(hass, base_url=base_url, api_key=api_key)
    return await client.async_get_active_warnings()


def _region_choices(warnings: list[Warning]) -> dict[str, str]:
    names = sorted({name for w in warnings for name in w.region_names if name})
    return {name: name for name in names}


def _areas_schema(region_choices: dict[str, str]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_MONITOR_ALL, default=True): bool,
            vol.Optional(CONF_AREAS, default=[]): cv.multi_select(region_choices),
        }
    )


class MetOfficeWarningsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Met Office Warnings."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._region_choices: dict[str, str] = {}
        self._areas: list[str] = [AREA_ALL]
        self._options: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY]
            self._base_url = user_input[CONF_BASE_URL]

            await self.async_set_unique_id(self._api_key)
            self._abort_if_unique_id_configured()

            try:
                warnings = await _async_fetch_warnings(
                    self.hass, self._api_key, self._base_url
                )
            except NSWWSAuthError:
                errors["base"] = "invalid_auth"
            except NSWWSConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - guard config flow against any bug
                _LOGGER.exception("Unexpected error validating NSWWS credentials")
                errors["base"] = "unknown"
            else:
                self._region_choices = _region_choices(warnings)
                if not self._region_choices:
                    # No warnings currently active anywhere - nothing to build an
                    # area picker from, so default to monitoring the whole UK.
                    return await self.async_step_location()
                return await self.async_step_areas()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_areas(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            self._areas = (
                [AREA_ALL]
                if user_input[CONF_MONITOR_ALL]
                else user_input[CONF_AREAS] or [AREA_ALL]
            )
            return await self.async_step_location()

        return self.async_show_form(
            step_id="areas", data_schema=_areas_schema(self._region_choices)
        )

    async def async_step_location(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Optionally restrict warnings to those near a latitude/longitude."""
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = user_input.get(CONF_LATITUDE)
            lon = user_input.get(CONF_LONGITUDE)
            if (lat is None) != (lon is None):
                errors["base"] = "location_incomplete"
            else:
                self._options = {CONF_DISTANCE_MILES: user_input[CONF_DISTANCE_MILES]}
                if lat is not None:
                    self._options[CONF_LATITUDE] = lat
                    self._options[CONF_LONGITUDE] = lon
                return await self.async_step_weather_types()

        schema = STEP_LOCATION_DATA_SCHEMA
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(
            step_id="location", data_schema=schema, errors=errors
        )

    async def async_step_weather_types(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Optionally restrict warnings to selected weather types."""
        if user_input is not None:
            weather_types = user_input.get(CONF_WEATHER_TYPES, [])
            if weather_types:
                self._options[CONF_WEATHER_TYPES] = weather_types
            return self.async_create_entry(
                title="Met Office Warnings",
                data={
                    CONF_API_KEY: self._api_key,
                    CONF_BASE_URL: self._base_url,
                    CONF_AREAS: self._areas,
                },
                options=self._options,
            )

        return self.async_show_form(
            step_id="weather_types", data_schema=STEP_WEATHER_TYPES_DATA_SCHEMA
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> Any:
        """Handle a reauth triggered by ConfigEntryAuthFailed (e.g. a rejected key)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            try:
                await _async_fetch_warnings(
                    self.hass, api_key, reauth_entry.data[CONF_BASE_URL]
                )
            except NSWWSAuthError:
                errors["base"] = "invalid_auth"
            except NSWWSConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - guard config flow against any bug
                _LOGGER.exception("Unexpected error validating NSWWS credentials")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_API_KEY: api_key},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MetOfficeWarningsOptionsFlow()


class MetOfficeWarningsOptionsFlow(OptionsFlow):
    """Handle options: scan interval and area filter."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        errors: dict[str, str] = {}

        if user_input is not None:
            interval = user_input[CONF_SCAN_INTERVAL_MINUTES]
            if interval < MIN_SCAN_INTERVAL_MINUTES:
                errors["base"] = "interval_too_short"
            else:
                areas = (
                    [AREA_ALL]
                    if user_input[CONF_MONITOR_ALL]
                    else user_input[CONF_AREAS] or [AREA_ALL]
                )
                lat = user_input.get(CONF_LATITUDE)
                lon = user_input.get(CONF_LONGITUDE)
                if (lat is None) != (lon is None):
                    errors["base"] = "location_incomplete"
                else:
                    data = {
                        CONF_SCAN_INTERVAL_MINUTES: interval,
                        CONF_AREAS: areas,
                        CONF_DISTANCE_MILES: user_input[CONF_DISTANCE_MILES],
                    }
                    if lat is not None:
                        data[CONF_LATITUDE] = lat
                        data[CONF_LONGITUDE] = lon
                    if user_input.get(CONF_WEATHER_TYPES):
                        data[CONF_WEATHER_TYPES] = user_input[CONF_WEATHER_TYPES]
                    return self.async_create_entry(data=data)

        try:
            warnings = await _async_fetch_warnings(
                self.hass,
                self.config_entry.data[CONF_API_KEY],
                self.config_entry.data[CONF_BASE_URL],
            )
            region_choices = _region_choices(warnings)
        except (NSWWSAuthError, NSWWSConnectionError):
            region_choices = {}

        current_areas = self.config_entry.data.get(CONF_AREAS, [AREA_ALL])
        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
        )

        opts = self.config_entry.options
        location_fields: dict = {}
        for key, validator in (
            (CONF_LATITUDE, cv.latitude),
            (CONF_LONGITUDE, cv.longitude),
        ):
            # suggested_value (not default) so the user can clear the field.
            location_fields[
                vol.Optional(key, description={"suggested_value": opts.get(key)})
            ] = validator

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_MINUTES, default=current_interval
                ): vol.Coerce(int),
                vol.Required(
                    CONF_MONITOR_ALL, default=AREA_ALL in current_areas
                ): bool,
                vol.Optional(
                    CONF_AREAS,
                    default=[a for a in current_areas if a != AREA_ALL],
                ): cv.multi_select(region_choices),
                **location_fields,
                vol.Required(
                    CONF_DISTANCE_MILES,
                    default=opts.get(CONF_DISTANCE_MILES, DEFAULT_DISTANCE_MILES),
                ): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Optional(
                    CONF_WEATHER_TYPES,
                    default=opts.get(CONF_WEATHER_TYPES, []),
                ): cv.multi_select(WEATHER_TYPE_CHOICES),
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
