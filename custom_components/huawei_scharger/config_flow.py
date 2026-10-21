"""Config flow for the Huawei SCharger integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_HOST,
    CONF_SCAN_INTERVAL,
    CONF_STATION_DN,
    CONF_STATION_NAME,
    DEFAULT_PORTAL_HOST,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .portal import (
    BadCredentials,
    CaptchaRequired,
    ChargerNotFound,
    PortalError,
    PortalSession,
    SChargerClient,
    normalize_host,
)

_LOGGER = logging.getLogger(__name__)

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _user_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
        vol.Required(CONF_PASSWORD): _PASSWORD,
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, DEFAULT_PORTAL_HOST)): str,
    })


def _login_and_list(username: str, password: str, host: str) -> tuple[PortalSession, list[dict[str, str]]]:
    session = PortalSession(username, password, host)
    session.login()
    return session, session.list_stations()


def _has_charger(session: PortalSession, station_dn: str) -> None:
    SChargerClient(session, station_dn, plant_figures=False).locate()


def _error_key(err: Exception) -> str:
    if isinstance(err, CaptchaRequired):
        return "captcha_required"
    if isinstance(err, BadCredentials):
        return "invalid_auth"
    if isinstance(err, ChargerNotFound):
        return "no_charger"
    if isinstance(err, PortalError):
        return "cannot_connect"
    return "unknown"


class SChargerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a wallbox from FusionSolar credentials."""

    VERSION = 1

    def __init__(self) -> None:
        self._input: dict[str, Any] = {}
        self._session: PortalSession | None = None
        self._stations: list[dict[str, str]] = []

    async def _check_station(self, station: dict[str, str]) -> str | None:
        """Return an error key, or None if the plant has a wallbox."""
        assert self._session is not None
        try:
            await self.hass.async_add_executor_job(_has_charger, self._session, station["dn"])
        except Exception as err:  # noqa: BLE001
            if not isinstance(err, PortalError):
                _LOGGER.exception("Unexpected error while looking for the wallbox")
            return _error_key(err)
        return None

    async def _finish(self, station: dict[str, str]) -> ConfigFlowResult:
        await self.async_set_unique_id(station["dn"])
        self._abort_if_unique_id_configured()
        if self._session is not None:
            await self.hass.async_add_executor_job(self._session.close)
        return self.async_create_entry(
            title=f"SCharger ({station['name']})",
            data={**self._input, CONF_STATION_DN: station["dn"], CONF_STATION_NAME: station["name"]},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_HOST] = normalize_host(user_input.get(CONF_HOST))
            try:
                self._session, self._stations = await self.hass.async_add_executor_job(
                    _login_and_list, user_input[CONF_USERNAME], user_input[CONF_PASSWORD], user_input[CONF_HOST]
                )
            except Exception as err:  # noqa: BLE001
                if not isinstance(err, PortalError):
                    _LOGGER.exception("Unexpected error during login")
                errors["base"] = _error_key(err)
            else:
                self._input = user_input
                if not self._stations:
                    errors["base"] = "no_station"
                elif len(self._stations) > 1:
                    return await self.async_step_station()
                elif (error := await self._check_station(self._stations[0])) is not None:
                    errors["base"] = error
                else:
                    return await self._finish(self._stations[0])
        return self.async_show_form(
            step_id="user", data_schema=_user_schema(user_input or {}), errors=errors
        )

    async def async_step_station(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            station = next(s for s in self._stations if s["dn"] == user_input[CONF_STATION_DN])
            if (error := await self._check_station(station)) is not None:
                errors["base"] = error
            else:
                return await self._finish(station)
        options = [SelectOptionDict(value=s["dn"], label=s["name"]) for s in self._stations]
        return self.async_show_form(
            step_id="station",
            data_schema=vol.Schema({
                vol.Required(CONF_STATION_DN): SelectSelector(SelectSelectorConfig(options=options))
            }),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            data[CONF_HOST] = normalize_host(data.get(CONF_HOST))
            try:
                session, _ = await self.hass.async_add_executor_job(
                    _login_and_list, data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_HOST]
                )
                await self.hass.async_add_executor_job(session.close)
            except Exception as err:  # noqa: BLE001
                if not isinstance(err, PortalError):
                    _LOGGER.exception("Unexpected error during re-authentication")
                errors["base"] = _error_key(err)
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD): _PASSWORD,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SChargerOptionsFlow()


class SChargerOptionsFlow(OptionsFlow):
    """Polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=3600)
                ),
            }),
        )
