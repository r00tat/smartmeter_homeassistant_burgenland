"""Sensor entities, one per sensor spec of the selected meter profile."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartMeterConfigEntry, SmartMeterCoordinator


def description_from_spec(spec: Any) -> SensorEntityDescription:
    """Translate a core ``SensorSpec`` into a Home Assistant description."""
    unit = spec.unit_of_measurement or None  # "" (power factor) means no unit
    return SensorEntityDescription(
        key=spec.value_key,
        name=spec.name,
        device_class=SensorDeviceClass(spec.device_class) if spec.device_class else None,
        state_class=SensorStateClass(spec.state_class) if spec.state_class else None,
        native_unit_of_measurement=unit,
        suggested_unit_of_measurement=(
            UnitOfEnergy.KILO_WATT_HOUR if unit == UnitOfEnergy.WATT_HOUR else None
        ),
        entity_registry_enabled_default=spec.enabled_by_default is not False,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartMeterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one sensor per spec of the entry's meter profile."""
    coordinator = entry.runtime_data
    async_add_entities(
        SmartMeterSensor(coordinator, description_from_spec(spec), spec.suffix)
        for spec in coordinator.profile.sensor_specs
        if not spec.raw
    )


class SmartMeterSensor(CoordinatorEntity[SmartMeterCoordinator], SensorEntity):
    """One value of the latest meter reading."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmartMeterCoordinator,
        description: SensorEntityDescription,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=coordinator.profile.manufacturer,
            model=coordinator.profile.model,
        )

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.key)
