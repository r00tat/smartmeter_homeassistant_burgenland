"""Tests for the config and options flow."""

from unittest.mock import patch

import pytest
import serial
from homeassistant.exceptions import HomeAssistantError
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at import config_flow as cf
from custom_components.smartmeter_at.const import CONF_PORT, CONF_UPDATE_INTERVAL, DOMAIN
from custom_components.smartmeter_at.core import async_load_core

from .conftest import ENTRY_DATA, METER_ID, sample_reading

FLOW = "custom_components.smartmeter_at.config_flow"
# The fixture below replaces these module attributes, keep the real ones.
REAL_LIST_PORTS = cf.async_list_ports
REAL_CHECK_PORT = cf.async_check_port


@pytest.fixture(autouse=True)
def no_real_ports_or_setup():
    with (
        patch(f"{FLOW}.async_list_ports", return_value=["/dev/ttyUSB0"]),
        patch(f"{FLOW}.async_check_port", return_value=None),
        patch("custom_components.smartmeter_at.async_setup_entry", return_value=True),
        patch("custom_components.smartmeter_at.async_unload_entry", return_value=True),
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
        result["flow_id"], {CONF_UPDATE_INTERVAL: 30.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_UPDATE_INTERVAL: 30}
    assert isinstance(entry.options[CONF_UPDATE_INTERVAL], int)


async def test_unreachable_port_is_cannot_connect_without_probe(hass: HomeAssistant) -> None:
    result = await _start(hass)
    with (
        patch(f"{FLOW}.async_check_port", REAL_CHECK_PORT),
        patch(f"{FLOW}.serial.Serial", side_effect=serial.SerialException("nope")),
        patch(f"{FLOW}.async_probe") as probe,
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    probe.assert_not_called()
    assert result["errors"] == {"base": "cannot_connect"}


async def test_port_check_opens_and_closes_the_port(hass: HomeAssistant) -> None:
    with patch(f"{FLOW}.serial.Serial") as port:
        await REAL_CHECK_PORT(hass, "/dev/ttyUSB0")
    port.assert_called_once_with("/dev/ttyUSB0")
    port.return_value.close.assert_called_once()


async def test_port_of_existing_entry_is_aborted_before_probe(
    hass: HomeAssistant, tmp_path
) -> None:
    device = tmp_path / "ttyUSB0"
    device.touch()
    link = tmp_path / "by-id-link"
    link.symlink_to(device)
    MockConfigEntry(
        domain=DOMAIN, data={**ENTRY_DATA, CONF_PORT: str(device)}, unique_id=METER_ID
    ).add_to_hass(hass)
    result = await _start(hass)
    with patch(f"{FLOW}.async_probe") as probe:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**ENTRY_DATA, CONF_PORT: str(link)}
        )
    probe.assert_not_called()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_known_meter_on_new_port_updates_the_entry(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=METER_ID)
    entry.add_to_hass(hass)
    result = await _start(hass)
    with patch(f"{FLOW}.async_probe", return_value=sample_reading()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**ENTRY_DATA, CONF_PORT: "/dev/ttyUSB1"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_PORT] == "/dev/ttyUSB1"


async def test_unique_id_falls_back_to_port(hass: HomeAssistant) -> None:
    reading = sample_reading()
    reading.meter_id = None
    result = await _start(hass)
    with patch(f"{FLOW}.async_probe", return_value=reading):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == ENTRY_DATA[CONF_PORT]


async def test_key_with_spaces_is_normalised(hass: HomeAssistant) -> None:
    key = ENTRY_DATA["key"]
    grouped = " ".join(key[i : i + 4] for i in range(0, 32, 4))
    result = await _start(hass)
    with patch(f"{FLOW}.async_probe", return_value=sample_reading()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**ENTRY_DATA, "key": grouped}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["key"] == key


async def test_core_unavailable_aborts(hass: HomeAssistant) -> None:
    with patch(f"{FLOW}.async_load_core", side_effect=HomeAssistantError("no gurux")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "core_unavailable"


async def test_port_listing_failure_falls_back_to_empty(hass: HomeAssistant) -> None:
    with patch(f"{FLOW}._list_ports", side_effect=OSError("boom")):
        assert await REAL_LIST_PORTS(hass) == []


def test_list_ports_prefers_by_id_link(tmp_path, monkeypatch) -> None:
    device = tmp_path / "ttyUSB0"
    device.touch()
    by_id = tmp_path / "by-id"
    by_id.mkdir()
    (by_id / "usb-FTDI-if00").symlink_to(device)
    monkeypatch.setattr(cf, "SERIAL_BY_ID", by_id)
    port = type("Port", (), {"device": str(device.resolve())})()
    with patch(f"{FLOW}.serial.tools.list_ports.comports", return_value=[port]):
        assert cf._list_ports() == [str(by_id / "usb-FTDI-if00")]


@pytest.mark.parametrize(
    ("meter_type", "timeout"),
    [("burgenland", 15.0), ("wien", 10.0), ("h1", 10.0), ("steiermark", 30.0)],
)
async def test_probe_timeout_per_profile(hass: HomeAssistant, meter_type, timeout) -> None:
    core = await async_load_core(hass)
    with patch.object(core.supervisor, "probe", return_value=None) as probe:
        await cf.async_probe(hass, core, {**ENTRY_DATA, "meter_type": meter_type})
    assert probe.call_args.args[1] == timeout
