"""Sensors of the Huawei SCharger integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfMass,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SChargerConfigEntry
from .const import DOMAIN, MANUFACTURER, PLANT_DEVICE_NAME
from .entity import SChargerEntity
from .portal import ChargerReading


@dataclass(frozen=True, kw_only=True)
class SChargerSensorDescription(SensorEntityDescription):
    """Sensor description with a value getter."""

    value: Callable[[ChargerReading], Any]


def _phase(name: str) -> SChargerSensorDescription:
    return SChargerSensorDescription(
        key=f"current_{name}",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value=lambda r: r.currents_a.get(name),
    )


SENSORS: tuple[SChargerSensorDescription, ...] = (
    SChargerSensorDescription(
        key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        value=lambda r: r.power_kw,
    ),
    SChargerSensorDescription(
        key="status",
        device_class=SensorDeviceClass.ENUM,
        options=["charging", "idle"],
        value=lambda r: r.status,
    ),
    SChargerSensorDescription(
        key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value=lambda r: r.energy_total_kwh,
    ),
    SChargerSensorDescription(
        key="working_status",
        value=lambda r: r.working_status,
    ),
    SChargerSensorDescription(
        key="working_mode",
        value=lambda r: r.working_mode,
    ),
    SChargerSensorDescription(
        key="lock_state",
        value=lambda r: r.lock_state,
    ),
    SChargerSensorDescription(
        key="reported_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda r: r.reported_status,
    ),
    SChargerSensorDescription(
        key="data_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda r: r.data_time,
    ),
    _phase("l1"),
    _phase("l2"),
    _phase("l3"),
    SChargerSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda r: r.temperature_c,
    ),
    SChargerSensorDescription(
        key="dynamic_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda r: r.dynamic_power_kw,
    ),
    SChargerSensorDescription(
        key="max_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda r: r.max_power_kw,
    ),
)


PLANT_SENSORS: tuple[SChargerSensorDescription, ...] = (
    SChargerSensorDescription(
        key="co2_avoided",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        value=lambda r: r.plant.co2_avoided_kg if r.plant else None,
    ),
    SChargerSensorDescription(
        key="standard_coal_saved",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        value=lambda r: r.plant.standard_coal_saved_kg if r.plant else None,
    ),
    SChargerSensorDescription(
        key="equivalent_trees",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value=lambda r: r.plant.equivalent_trees if r.plant else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SChargerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [SChargerSensor(coordinator, desc) for desc in SENSORS]
    entities += [SChargerPlantSensor(coordinator, desc) for desc in PLANT_SENSORS]
    async_add_entities(entities)


class SChargerSensor(SChargerEntity, SensorEntity):
    """A single wallbox value."""

    entity_description: SChargerSensorDescription

    def __init__(self, coordinator, description: SChargerSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value(self.coordinator.data)


class SChargerPlantSensor(SChargerSensor):
    """Environmental figure of the whole plant, shown on its own device."""

    def __init__(self, coordinator, description: SChargerSensorDescription) -> None:
        super().__init__(coordinator, description)
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_plant")},
            name=PLANT_DEVICE_NAME,
            manufacturer=MANUFACTURER,
            model="FusionSolar plant",
            entry_type=DeviceEntryType.SERVICE,
        )
