"""Tests for the config and options flow."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at.const import CONF_UPDATE_INTERVAL, DOMAIN

from .conftest import ENTRY_DATA, METER_ID, sample_reading

FLOW = "custom_components.smartmeter_at.config_flow"


@pytest.fixture(autouse=True)
def no_real_ports_or_setup():
    with (
        patch(f"{FLOW}.async_list_ports", return_value=["/dev/ttyUSB0"]),
        patch("custom_components.smartmeter_at.async_setup_entry", return_value=True),
    ):
        yield


async def _start(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await _start(hass)
    with patch(f"{FLOW}.async_probe", return_value=sample_reading()):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Smart Meter Landis+Gyr E450"
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == METER_ID


async def test_invalid_key_is_rejected_without_probe(hass: HomeAssistant) -> None:
    result = await _start(hass)
    with patch(f"{FLOW}.async_probe") as probe:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**ENTRY_DATA, "key": "not-hex"}
        )
    probe.assert_not_called()
    assert result["errors"] == {"key": "invalid_key"}


@pytest.mark.parametrize(
    ("probe_result", "error"),
    [
        (OSError("no such port"), "cannot_connect"),
        (None, "no_data"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_probe_errors(hass: HomeAssistant, probe_result, error: str) -> None:
    result = await _start(hass)
    kwargs = (
        {"side_effect": probe_result}
        if isinstance(probe_result, Exception)
        else {"return_value": probe_result}
    )
    with patch(f"{FLOW}.async_probe", **kwargs):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_same_meter_cannot_be_added_twice(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=METER_ID).add_to_hass(hass)
    result = await _start(hass)
    with patch(f"{FLOW}.async_probe", return_value=sample_reading()):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_sets_update_interval(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=METER_ID)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_UPDATE_INTERVAL: 30}
