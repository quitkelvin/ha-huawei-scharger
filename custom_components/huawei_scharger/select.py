"""Select entities: working mode and connector locking mode."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SChargerConfigEntry
from .coordinator import SChargerCoordinator
from .entity import SChargerSettingEntity
from .portal import endpoints as ep
from .portal.readings import code_to_name


async def async_setup_entry(
    hass: HomeAssistant, entry: SChargerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    # both settings belong to the charging connector; without one there is nothing to switch
    if coordinator.client.connector is None:
        return
    async_add_entities([
        SChargerOptionSelect(coordinator, "working_mode_setting", ep.SETTING_MODE, ep.MODE_CODES),
        SChargerOptionSelect(coordinator, "lock_mode", ep.SETTING_LOCK_MODE, ep.LOCK_MODE_CODES),
    ])


class SChargerOptionSelect(SChargerSettingEntity, SelectEntity):
    """A setting with a fixed set of options (option name -> portal code)."""

    def __init__(
        self, coordinator: SChargerCoordinator, key: str, signal_id: int, codes: dict[str, str]
    ) -> None:
        super().__init__(coordinator, key, signal_id)
        self._codes = codes
        self._names = {code: name for name, code in codes.items()}
        self._attr_options = list(codes)

    @property
    def current_option(self) -> str | None:
        return code_to_name(self.raw_setting, self._names)

    async def async_select_option(self, option: str) -> None:
        await self.async_write(self._codes[option])
