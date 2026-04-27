"""Unit tests for the meter profile registry."""

import pytest

from meter.profile import MeterProfile, get_profile


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
