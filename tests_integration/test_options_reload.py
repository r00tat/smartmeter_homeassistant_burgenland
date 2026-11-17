"""Changing the options of a running entry reloads it."""

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at.const import CONF_UPDATE_INTERVAL, DOMAIN

from .conftest import ENTRY_DATA, METER_ID, wait_for_data


async def test_options_change_reloads_running_entry(hass: HomeAssistant, fake_readers) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=METER_ID)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for_data(entry.runtime_data)
    assert len(fake_readers) == 1
    first = fake_readers[0]
    try:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_UPDATE_INTERVAL: 30}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        assert first.cancelled
        assert len(fake_readers) == 2
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)
