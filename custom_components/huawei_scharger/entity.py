"""Shared base entity for the Huawei SCharger integration."""

from __future__ import annotations

from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_NAME, DOMAIN, MANUFACTURER
from .coordinator import SChargerCoordinator


class SChargerEntity(CoordinatorEntity[SChargerCoordinator]):
    """Entity that belongs to the "Huawei SCharger" device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SChargerCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        reading = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=DEVICE_NAME,
            manufacturer=MANUFACTURER,
            model=(reading.model if reading else None) or "SCharger",
            sw_version=reading.firmware if reading else None,
            serial_number=reading.serial if reading else None,
        )


class SChargerSettingEntity(SChargerEntity):
    """Base for entities that show and change one wallbox setting (config signal)."""

    _attr_entity_category = EntityCategory.CONFIG
    signal_id: int

    def __init__(self, coordinator: SChargerCoordinator, key: str, signal_id: int) -> None:
        super().__init__(coordinator, key)
        self.signal_id = signal_id

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and data is not None and self.signal_id in data.settings

    @property
    def raw_setting(self) -> str | None:
        data = self.coordinator.data
        return data.setting(self.signal_id) if data else None

    async def async_write(self, value: str) -> None:
        await self.coordinator.async_write_setting(self.signal_id, value)
