"""Number entities: power limits, charging current and PV thresholds."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SChargerConfigEntry
from .coordinator import SChargerCoordinator
from .entity import SChargerSettingEntity
from .portal import endpoints as ep
from .portal.readings import to_float


@dataclass(frozen=True, kw_only=True)
class SChargerNumberDescription(NumberEntityDescription):
    """Number description bound to a portal setting.

    ``native_min_value``/``native_max_value`` are fallbacks; the range the
    portal reports for the setting takes precedence.
    """

    signal_id: int


NUMBERS: tuple[SChargerNumberDescription, ...] = (
    SChargerNumberDescription(
        key="dynamic_power_limit",
        signal_id=ep.SETTING_DYNAMIC_POWER,
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        native_min_value=4.1, native_max_value=11.0, native_step=0.1,
        mode=NumberMode.BOX,
    ),
    SChargerNumberDescription(
        key="max_charge_current",
        signal_id=ep.SETTING_MAX_CURRENT,
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_min_value=6, native_max_value=32, native_step=1,
        mode=NumberMode.BOX,
    ),
    SChargerNumberDescription(
        key="grid_share_pv_mode",
        signal_id=ep.SETTING_GRID_SHARE_PV,
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        native_min_value=0.0, native_max_value=11.0, native_step=0.1,
        mode=NumberMode.BOX,
    ),
    SChargerNumberDescription(
        key="surplus_start_threshold",
        signal_id=ep.SETTING_SURPLUS_START,
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        native_min_value=0.5, native_max_value=22.0, native_step=0.1,
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SChargerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if coordinator.client.connector is None:
        return
    async_add_entities(SChargerNumber(coordinator, desc) for desc in NUMBERS)


class SChargerNumber(SChargerSettingEntity, NumberEntity):
    """A numeric wallbox setting."""

    entity_description: SChargerNumberDescription

    def __init__(self, coordinator: SChargerCoordinator, description: SChargerNumberDescription) -> None:
        super().__init__(coordinator, description.key, description.signal_id)
        self.entity_description = description

    def _portal_range(self) -> tuple[float | None, float | None]:
        data = self.coordinator.data
        item = data.settings.get(self.signal_id) if data else None
        return (item.minimum, item.maximum) if item else (None, None)

    @property
    def native_min_value(self) -> float:
        low, _ = self._portal_range()
        return low if low is not None else self.entity_description.native_min_value

    @property
    def native_max_value(self) -> float:
        _, high = self._portal_range()
        return high if high is not None else self.entity_description.native_max_value

    @property
    def native_value(self) -> float | None:
        return to_float(self.raw_setting)

    async def async_set_native_value(self, value: float) -> None:
        value = min(max(value, self.native_min_value), self.native_max_value)
        step = self.entity_description.native_step or 1
        await self.async_write(f"{value:.0f}" if step >= 1 else f"{value:.1f}")
