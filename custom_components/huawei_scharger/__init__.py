"""Huawei SCharger wallbox via the FusionSolar web portal."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CONF_HOST, CONF_STATION_DN, DEFAULT_PORTAL_HOST, PLATFORMS
from .coordinator import SChargerCoordinator
from .portal import (
    BadCredentials,
    CaptchaRequired,
    PortalError,
    PortalSession,
    SChargerClient,
)

type SChargerConfigEntry = ConfigEntry[SChargerCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SChargerConfigEntry) -> bool:
    """Log in, locate the wallbox and start polling."""
    session = PortalSession(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_HOST, DEFAULT_PORTAL_HOST),
    )
    client = SChargerClient(session, entry.data[CONF_STATION_DN])
    try:
        await hass.async_add_executor_job(client.locate)
    except (BadCredentials, CaptchaRequired) as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except PortalError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = SChargerCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_options_changed))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SChargerConfigEntry) -> bool:
    """Unload platforms and drop the HTTP session."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await hass.async_add_executor_job(entry.runtime_data.client.session.close)
    return unloaded


async def _async_options_changed(hass: HomeAssistant, entry: SChargerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
