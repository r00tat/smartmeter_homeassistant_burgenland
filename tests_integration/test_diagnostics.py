"""Diagnostics never leak the meter key."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at.const import DOMAIN
from custom_components.smartmeter_at.diagnostics import async_get_config_entry_diagnostics

from .conftest import ENTRY_DATA, KEY, wait_for_data


async def test_diagnostics_redact_key(hass: HomeAssistant, fake_readers) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for_data(entry.runtime_data)
    try:
        result = await async_get_config_entry_diagnostics(hass, entry)
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)

    assert KEY not in str(result)
    assert result["entry_data"]["key"] == "**REDACTED**"
    assert result["meter_id_known"] is True
    assert result["data"]["u1"] == 236
