"""Tests for entry setup and the sensor entities."""

import asyncio
import logging
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.components.sensor import DEVICE_CLASS_UNITS
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at.const import DOMAIN
from custom_components.smartmeter_at.coordinator import SmartMeterCoordinator
from custom_components.smartmeter_at.core import async_load_core
from custom_components.smartmeter_at.sensor import description_from_spec

from .conftest import ENTRY_DATA, METER_ID, FakeReader, sample_reading, wait_for_data


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
    assert all(reader.cancelled for reader in fake_readers)


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
            description = description_from_spec(spec)  # raises on unknown classes
            if description.device_class is not None:
                assert (
                    description.native_unit_of_measurement
                    in DEVICE_CLASS_UNITS[description.device_class]
                ), spec.name


async def test_stop_event_then_unload_is_clean(
    hass: HomeAssistant, fake_readers, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await _setup(hass)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert all(reader.cancelled for reader in fake_readers)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert all(reader.cancelled for reader in fake_readers)


class _FailingReader:
    """Raises on start, like a serial port that cannot be opened."""

    async def run(self) -> None:
        raise OSError("port gone")


async def test_error_then_recovery_through_the_supervisor(hass: HomeAssistant) -> None:
    readers: list[Any] = []

    def factory(callback: Any) -> Any:
        reader = _FailingReader() if not readers else FakeReader(callback)
        readers.append(reader)
        return reader

    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Smart Meter")
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.smartmeter_at.coordinator.build_reader_factory",
            return_value=factory,
        ),
        patch("custom_components.smartmeter_at.coordinator.RETRY_SECONDS", 0.01),
        patch.object(
            SmartMeterCoordinator,
            "async_set_update_error",
            autospec=True,
            side_effect=SmartMeterCoordinator.async_set_update_error,
        ) as set_error,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        try:
            await wait_for_data(entry.runtime_data)
            await hass.async_block_till_done()
            assert len(readers) >= 2
            set_error.assert_called()  # the failure was reported
            assert isinstance(set_error.call_args.args[1], OSError)
            assert entry.runtime_data.last_update_success
            assert _state(hass, entry, "_voltage_l1").state == "236"
        finally:
            assert await hass.config_entries.async_unload(entry.entry_id)


class _PausingReader:
    """One reading, ``pause`` seconds of silence, another reading, silence."""

    def __init__(self, callback: Any, pause: float) -> None:
        self.callback = callback
        self.pause = pause

    async def run(self) -> None:
        self.callback(sample_reading())
        await asyncio.sleep(self.pause)
        self.callback(sample_reading())
        await asyncio.Event().wait()


async def test_silent_meter_makes_entities_unavailable_until_data_returns(
    hass: HomeAssistant,
) -> None:
    core = await async_load_core(hass)
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Smart Meter")
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.smartmeter_at.coordinator.build_reader_factory",
            return_value=lambda callback: _PausingReader(callback, pause=0.4),
        ),
        patch.object(core.profile.MeterProfile, "stale_after_seconds", 0.1),
        patch.object(
            SmartMeterCoordinator,
            "async_set_update_error",
            autospec=True,
            side_effect=SmartMeterCoordinator.async_set_update_error,
        ) as set_error,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        coordinator = entry.runtime_data
        try:
            await wait_for_data(coordinator)
            await hass.async_block_till_done()
            assert _state(hass, entry, "_voltage_l1").state == "236"

            await _wait(lambda: not coordinator.last_update_success)
            await hass.async_block_till_done()
            assert _state(hass, entry, "_voltage_l1").state == "unavailable"

            await _wait(lambda: coordinator.last_update_success)
            await hass.async_block_till_done()
            assert _state(hass, entry, "_voltage_l1").state == "236"
            # reported once per silence, not on every watchdog wake-up
            assert set_error.call_count == 1
        finally:
            assert await hass.config_entries.async_unload(entry.entry_id)


async def _wait(predicate: Any, timeout: float = 3.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


async def test_unload_cancels_the_reader(hass: HomeAssistant, fake_readers) -> None:
    entry = await _setup(hass)
    await wait_for_data(entry.runtime_data)
    assert not fake_readers[0].cancelled
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert fake_readers[0].cancelled
    assert entry.state is ConfigEntryState.NOT_LOADED
