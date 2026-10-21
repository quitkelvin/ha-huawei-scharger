"""Polling coordinator for the Huawei SCharger integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, MIN_SCAN_INTERVAL
from .portal import (
    BadCredentials,
    CaptchaRequired,
    ChargerNotFound,
    ChargerReading,
    PortalError,
    SChargerClient,
)

_LOGGER = logging.getLogger(__name__)


class SChargerCoordinator(DataUpdateCoordinator[ChargerReading]):
    """Fetches one ``ChargerReading`` per interval."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: SChargerClient) -> None:
        seconds = max(MIN_SCAN_INTERVAL, int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=seconds),
        )
        self.client = client

    async def _async_update_data(self) -> ChargerReading:
        try:
            return await self.hass.async_add_executor_job(self.client.read)
        except CaptchaRequired as err:
            raise ConfigEntryAuthFailed(
                "FusionSolar asks for a captcha. Log in once in a browser, wait some "
                "minutes and re-authenticate the integration."
            ) from err
        except BadCredentials as err:
            raise ConfigEntryAuthFailed("FusionSolar rejected username or password") from err
        except ChargerNotFound as err:
            raise UpdateFailed("No SCharger found in the selected plant") from err
        except PortalError as err:
            raise UpdateFailed(f"FusionSolar request failed: {err}") from err

    async def async_write_setting(self, signal_id: int, value: str) -> None:
        """Write a setting, then poll so the value is read back from the portal."""
        try:
            accepted = await self.hass.async_add_executor_job(self.client.write_setting, signal_id, value)
        except (BadCredentials, CaptchaRequired) as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"FusionSolar login failed: {err}") from err
        except (PortalError, ValueError) as err:
            raise HomeAssistantError(f"Changing the wallbox setting failed: {err}") from err
        if not accepted:
            raise HomeAssistantError("FusionSolar did not accept the change")
        await self.async_refresh()
