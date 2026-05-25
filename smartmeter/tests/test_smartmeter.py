"""Tests for ``SmartMqttMeter.setup`` profile wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from meter import smartmeter as smartmeter_mod
from meter.profile import get_profile


VALID_KEY = "000102030405060708090A0B0C0D0E0F"

_BASE_CFG = {
    "mqtt": {"host": "mqtt.local"},
    "dlms": {"key": VALID_KEY, "port": "/dev/ttyUSB0"},
}


def _make_meter(cfg: dict) -> tuple[object, MagicMock, MagicMock]:
    """Instantiate SmartMqttMeter with build_reader + SmartMeterDevice patched."""
    with (
        patch.object(smartmeter_mod, "build_reader") as build_reader,
        patch.object(smartmeter_mod, "SmartMeterDevice") as device_cls,
    ):
        build_reader.return_value = MagicMock()
        device_cls.return_value = MagicMock()
        meter = smartmeter_mod.SmartMqttMeter(cfg)
        return meter, build_reader, device_cls


def test_setup_uses_burgenland_profile_by_default() -> None:
    _, build_reader, device_cls = _make_meter(dict(_BASE_CFG))
    assert build_reader.call_count == 1
    _, kwargs = build_reader.call_args
    profile = kwargs.get("profile") or build_reader.call_args.args[1]
    assert profile.name == "burgenland"
    # device also receives the profile
    assert device_cls.call_args.kwargs.get("profile") is profile


def test_setup_uses_noe_profile_when_configured() -> None:
    cfg = dict(_BASE_CFG, meter_type="noe_evn")
    _, build_reader, device_cls = _make_meter(cfg)
    profile = build_reader.call_args.args[1]
    assert profile.name == "noe_evn"
    assert device_cls.call_args.kwargs.get("profile").name == "noe_evn"


def test_setup_passes_got_meter_data_callback() -> None:
    meter, build_reader, _ = _make_meter(dict(_BASE_CFG))
    callback = build_reader.call_args.kwargs.get("callback")
    assert callback == meter.got_meter_data


def test_setup_connects_reader() -> None:
    _, build_reader, _ = _make_meter(dict(_BASE_CFG))
    build_reader.return_value.connect.assert_called_once()


def test_profile_lookup_matches_registry() -> None:
    # Sanity: noe_evn profile is known.
    assert get_profile("noe_evn").name == "noe_evn"
