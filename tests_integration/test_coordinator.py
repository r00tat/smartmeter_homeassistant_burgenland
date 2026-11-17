"""Tests for the push coordinator."""

import asyncio
import os

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at.const import CONF_PORT, CONF_UPDATE_INTERVAL, DOMAIN
from custom_components.smartmeter_at.coordinator import (
    RESTART_AFTER_SECONDS,
    SmartMeterCoordinator,
    build_reader_factory,
)
from custom_components.smartmeter_at.core import async_load_core

from .conftest import (
    ENTRY_DATA,
    KEY,
    METER_ID,
    METER_VALUES,
    sample_reading,
    sample_telegram,
    wait_for_data,
)


async def test_coordinator_receives_readings(hass: HomeAssistant, fake_readers) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, options={CONF_UPDATE_INTERVAL: 10})
    entry.add_to_hass(hass)
    coordinator = SmartMeterCoordinator(hass, entry, await async_load_core(hass))
    coordinator.async_start()
    try:
        await wait_for_data(coordinator)
    finally:
        await coordinator.async_stop()

    assert coordinator.data["u1"] == 236
    assert coordinator.data["total_con"] == 49244276
    assert coordinator.meter_id == METER_ID
    assert coordinator.last_update_success
    assert fake_readers[0].cancelled


async def test_stop_is_idempotent(hass: HomeAssistant, fake_readers) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    coordinator = SmartMeterCoordinator(hass, entry, await async_load_core(hass))
    await coordinator.async_stop()  # never started
    coordinator.async_start()
    await wait_for_data(coordinator)
    await coordinator.async_stop()
    await coordinator.async_stop()
    assert fake_readers[0].cancelled


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
    assert reader.settings.port == "/dev/ttyUSB0"
    assert reader.key == ENTRY_DATA["key"]
    assert reader.is_optical_interface is True


async def test_supervisor_watches_for_a_silent_meter(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={**ENTRY_DATA, "meter_type": "wien"})
    entry.add_to_hass(hass)
    coordinator = SmartMeterCoordinator(hass, entry, await async_load_core(hass))

    assert coordinator.stale_after == 60.0  # Wien pushes every second
    assert coordinator._supervisor._stale_after == 60.0
    assert coordinator._supervisor._restart_after == RESTART_AFTER_SECONDS


async def test_silent_meter_goes_unavailable_and_recovers(hass: HomeAssistant) -> None:
    """The supervisor's silence report reaches the entities through on_error."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    core = await async_load_core(hass)
    coordinator = SmartMeterCoordinator(hass, entry, core)

    coordinator._supervisor._on_error(core.supervisor.ReaderSilentError("no telegram for 60 s"))
    assert not coordinator.last_update_success

    coordinator._supervisor._on_data(sample_reading())
    assert coordinator.last_update_success


async def test_meter_on_a_pseudo_terminal_end_to_end(hass: HomeAssistant) -> None:
    """Config entry → real reader → real serial transport on a pty → state."""
    sample = sample_telegram()
    assert sample.key_hex == KEY
    master, slave = os.openpty()
    name = os.ttyname(slave)
    os.close(slave)
    entry = MockConfigEntry(domain=DOMAIN, data={**ENTRY_DATA, CONF_PORT: name})
    entry.add_to_hass(hass)
    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await asyncio.sleep(0.1)
        os.write(master, sample.frame)
        coordinator = entry.runtime_data
        await wait_for_data(coordinator)
        await hass.async_block_till_done()
        assert coordinator.data["u1"] == METER_VALUES[0]
        assert coordinator.meter_id == METER_ID
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert coordinator._task is None
    finally:
        os.close(master)
