"""Unit tests for the meter profile registry and the profile base class."""

import json
import os

import pytest
import serial
import yaml

from meter.bgld.data import MeterData as BgldMeterData
from meter.config_validation import VALID_METER_TYPES
from meter.noe.read import NoeMeterReader
from meter.profile import HdlcDlmsProfile, MeterProfile, get_profile, known_meter_types
from meter.serial.read import MeterReader as HdlcMeterReader
from meter.wien.data import MeterData as WienMeterData


def test_burgenland_profile_uses_landis_gyr_metadata() -> None:
    profile = get_profile("burgenland")
    assert isinstance(profile, MeterProfile)
    assert profile.name == "burgenland"
    assert profile.manufacturer == "Landis+Gyr"
    assert profile.model == "E450"
    assert profile.default_baudrate == 9600


def test_noe_evn_profile_uses_sagemcom_metadata() -> None:
    profile = get_profile("noe_evn")
    assert profile.name == "noe_evn"
    assert profile.manufacturer == "Sagemcom"
    assert profile.model == "T210-D"
    assert profile.default_baudrate == 2400


def test_sensor_catalogs_differ_between_profiles() -> None:
    bgld = get_profile("burgenland")
    noe = get_profile("noe_evn")

    bgld_suffixes = {s.suffix for s in bgld.sensor_specs}
    noe_suffixes = {s.suffix for s in noe.sensor_specs}

    assert "_angle_l1" in bgld_suffixes
    assert "_angle_l1" not in noe_suffixes
    assert "_power_factor" in noe_suffixes
    assert "_power_factor" not in bgld_suffixes


def test_unknown_profile_raises() -> None:
    with pytest.raises(ValueError, match="meter_type"):
        get_profile("wien_netze")


# --- base class: every interface decision lives on the profile ---------------

_ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
VALID_KEY = "000102030405060708090A0B0C0D0E0F"


def test_base_profile_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        MeterProfile(  # type: ignore[abstract]
            name="x", manufacturer="x", model="x", sensor_specs=(), default_baudrate=1
        )


def test_wien_profile_metadata() -> None:
    profile = get_profile("wien")
    assert isinstance(profile, HdlcDlmsProfile)
    assert profile.data_factory is WienMeterData
    assert profile.default_baudrate == 9600
    assert profile.push_interval_seconds == 1.0
    suffixes = {s.suffix for s in profile.sensor_specs}
    assert "_reactive_power_consumed" in suffixes
    assert "_voltage_l1" not in suffixes


def test_burgenland_profile_decodes_into_bgld_meter_data() -> None:
    profile = get_profile("burgenland")
    assert isinstance(profile, HdlcDlmsProfile)
    assert profile.data_factory is BgldMeterData


@pytest.mark.parametrize(
    ("meter_type", "expected"),
    [
        ("burgenland", (9600, 8, serial.PARITY_NONE, 1)),
        ("wien", (9600, 8, serial.PARITY_NONE, 1)),
        ("noe_evn", (2400, 8, serial.PARITY_EVEN, 1)),
    ],
)
def test_serial_defaults_come_from_profile(meter_type: str, expected: tuple) -> None:
    settings = get_profile(meter_type).serial_settings({"dlms": {"key": VALID_KEY}})
    assert (
        settings.baudrate,
        settings.bytesize,
        settings.parity,
        settings.stopbits,
    ) == expected
    assert settings.port == "/dev/ttyUSB0"


def test_serial_overrides_win_and_empty_values_fall_back() -> None:
    profile = get_profile("noe_evn")
    settings = profile.serial_settings(
        {"dlms": {"baudrate": 9600, "parity": "", "stopbits": None, "port": "/dev/x"}}
    )
    assert settings.baudrate == 9600
    assert settings.parity == serial.PARITY_EVEN
    assert settings.stopbits == 1
    assert settings.port == "/dev/x"


@pytest.mark.parametrize("parity", ["NONE", "none", "N"])
def test_parity_names_are_normalised(parity: str) -> None:
    settings = get_profile("noe_evn").serial_settings({"dlms": {"parity": parity}})
    assert settings.parity == serial.PARITY_NONE


@pytest.mark.parametrize(
    ("meter_type", "publish_seconds", "expected"),
    [
        ("burgenland", 30, 6),
        ("noe_evn", 30, 6),
        ("wien", 30, 30),
        ("burgenland", 1, 1),
        ("burgenland", 7, 2),
    ],
)
def test_readings_per_publish(meter_type: str, publish_seconds: int, expected: int) -> None:
    assert get_profile(meter_type).readings_per_publish(publish_seconds) == expected


@pytest.mark.parametrize(
    ("meter_type", "reader_type"),
    [
        ("burgenland", HdlcMeterReader),
        ("wien", HdlcMeterReader),
        ("noe_evn", NoeMeterReader),
    ],
)
def test_create_reader_uses_profile_interface(meter_type: str, reader_type: type) -> None:
    reader = get_profile(meter_type).create_reader(
        {"dlms": {"key": VALID_KEY}}, lambda _d: None
    )
    assert isinstance(reader, reader_type)
    assert reader.parity == get_profile(meter_type).default_parity


def test_meter_types_are_consistent_across_config_files() -> None:
    known = set(known_meter_types())
    assert set(VALID_METER_TYPES) == known

    with open(os.path.join(_ADDON_DIR, "config.schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    assert set(schema["properties"]["meter_type"]["enum"]) == known

    with open(os.path.join(_ADDON_DIR, "config.yaml"), encoding="utf-8") as fh:
        addon = yaml.safe_load(fh)
    listed = addon["schema"]["meter_type"]
    assert listed.startswith("list(") and listed.endswith(")?")
    assert set(listed[len("list(") : -len(")?")].split("|")) == known


def test_addon_options_leave_serial_defaults_to_the_profile() -> None:
    # If the add-on options pinned baudrate/parity, Home Assistant would always
    # send them and the profile defaults (e.g. 2400 8E1 for noe_evn) never apply.
    with open(os.path.join(_ADDON_DIR, "config.yaml"), encoding="utf-8") as fh:
        addon = yaml.safe_load(fh)
    dlms_options = addon["options"]["dlms"]
    for key in ("baudrate", "bytesize", "parity", "stopbits"):
        assert key not in dlms_options
        assert key in addon["schema"]["dlms"]
