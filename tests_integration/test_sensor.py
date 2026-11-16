"""Tests for entry setup and the sensor entities."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at.const import DOMAIN
from custom_components.smartmeter_at.core import async_load_core
from custom_components.smartmeter_at.sensor import description_from_spec

from .conftest import ENTRY_DATA, METER_ID, wait_for_data


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Smart Meter")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for_data(entry.runtime_data)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, entry: MockConfigEntry, suffix: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}{suffix}"
    )
    assert entity_id is not None, suffix
    return hass.states.get(entity_id)


async def test_sensors_show_meter_values(hass: HomeAssistant, fake_readers) -> None:
    entry = await _setup(hass)
    try:
        assert _state(hass, entry, "_voltage_l1").state == "236"
        assert float(_state(hass, entry, "_current_l1").state) == pytest.approx(5.12)
        assert _state(hass, entry, "_power_consumed").state == "3314"
        energy = _state(hass, entry, "_total_energy_consumed")
        assert float(energy.state) == pytest.approx(49244.276)
        assert energy.attributes["unit_of_measurement"] == "kWh"
        assert energy.attributes["state_class"] == "total_increasing"
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_angle_sensors_are_disabled_by_default(hass: HomeAssistant, fake_readers) -> None:
    entry = await _setup(hass)
    try:
        entity_id = er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_angle_l1"
        )
        assert er.async_get(hass).async_get(entity_id).disabled_by is not None
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_device_gets_meter_serial(hass: HomeAssistant, fake_readers) -> None:
    entry = await _setup(hass)
    try:
        device = dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, entry.entry_id), entry.entry_id
        )
        assert device.manufacturer == "Landis+Gyr"
        assert device.model == "E450"
        assert device.serial_number == METER_ID
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_stops_reader(hass: HomeAssistant, fake_readers) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert all(reader.stopped.is_set() for reader in fake_readers)


@pytest.mark.parametrize(
    "meter_type",
    ["burgenland", "noe_evn", "wien", "steiermark", "steiermark_sagemcom", "salzburg", "tirol", "h1"],
)
async def test_every_catalog_maps_to_valid_descriptions(
    hass: HomeAssistant, meter_type: str
) -> None:
    core = await async_load_core(hass)
    for spec in core.profile.get_profile(meter_type).sensor_specs:
        if not spec.raw:
            description_from_spec(spec)  # raises on unknown device/state class
