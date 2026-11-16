"""Tests for the push coordinator."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at.const import CONF_UPDATE_INTERVAL, DOMAIN
from custom_components.smartmeter_at.coordinator import (
    SmartMeterCoordinator,
    build_reader_factory,
)
from custom_components.smartmeter_at.core import async_load_core

from .conftest import ENTRY_DATA, METER_ID, wait_for_data


async def test_coordinator_receives_readings(hass: HomeAssistant, fake_readers) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, options={CONF_UPDATE_INTERVAL: 10})
    entry.add_to_hass(hass)
    coordinator = SmartMeterCoordinator(hass, entry, await async_load_core(hass))
    coordinator.start()
    try:
        await wait_for_data(coordinator)
    finally:
        await coordinator.async_stop()

    assert coordinator.data["u1"] == 236
    assert coordinator.data["total_con"] == 49244276
    assert coordinator.meter_id == METER_ID
    assert coordinator.last_update_success


async def test_reader_error_marks_update_failed(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    coordinator = SmartMeterCoordinator(hass, entry, await async_load_core(hass))
    coordinator.async_set_update_error(OSError("port gone"))
    assert not coordinator.last_update_success


async def test_build_reader_factory_maps_entry_data(hass: HomeAssistant) -> None:
    core = await async_load_core(hass)
    profile = core.profile.get_profile("burgenland")
    reader = build_reader_factory(profile, ENTRY_DATA)(lambda data: None)
    assert reader.port == "/dev/ttyUSB0"
    assert reader.key == ENTRY_DATA["key"]
    assert reader.is_optical_interface is True
