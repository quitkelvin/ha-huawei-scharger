"""Switch entities: dynamic charge power and automatic phase switching."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SChargerConfigEntry
from .entity import SChargerSettingEntity
from .portal import endpoints as ep
from .portal.readings import to_float

SWITCHES = (
    ("dynamic_power_enabled", ep.SETTING_DYNAMIC_ENABLED),
    ("phase_switching", ep.SETTING_PHASE_SWITCHING),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SChargerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if coordinator.client.connector is None:
        return
    async_add_entities(SChargerSwitch(coordinator, key, sid) for key, sid in SWITCHES)


class SChargerSwitch(SChargerSettingEntity, SwitchEntity):
    """An on/off wallbox setting (portal values "1" / "0")."""

    @property
    def is_on(self) -> bool | None:
        value = to_float(self.raw_setting)
        return None if value is None else value == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_write("1")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_write("0")
