"""Unit tests for meter.noe.data.MeterData."""

import json

from meter.noe.data import MeterData


BASE = {
    "energy_consumed": 12345678,  # Wh
    "energy_provided": 1000,  # Wh
    "power_consumed": 1500,  # W
    "power_provided": 0,
    "voltage_l1": 2301,  # raw; scaled ·0.1 → 230.1 V
    "voltage_l2": 2302,
    "voltage_l3": 2303,
    "current_l1": 500,  # raw; scaled ·0.01 → 5.00 A
    "current_l2": 200,
    "current_l3": 100,
    "power_factor": 980,  # raw; scaled ·0.001 → 0.980
}


def test_empty_input_keeps_defaults() -> None:
    md = MeterData({})
    assert md.voltage_l1 == 0
    assert md.current_l1 == 0
    assert md.power_factor == 0
    assert md.meter_id is None


def test_scaling_applied_to_voltage_current_pf() -> None:
    md = MeterData(dict(BASE))
    assert md.voltage_l1 == 230.1
    assert md.voltage_l2 == 230.2
    assert md.voltage_l3 == 230.3
    assert md.current_l1 == 5.0
    assert md.current_l2 == 2.0
    assert md.current_l3 == 1.0
    assert md.power_factor == 0.98


def test_power_and_energy_not_scaled() -> None:
    md = MeterData(dict(BASE))
    assert md.power_consumed == 1500
    assert md.power_provided == 0
    assert md.total_consumed == 12345678
    assert md.total_provided == 1000


def test_to_dict_uses_bgld_compatible_keys_plus_power_factor() -> None:
    md = MeterData(dict(BASE))
    d = md.to_dict()
    # Reuse the same sensor keys as the BGLD profile so existing HA
    # sensor templates keep working, with power_factor added.
    assert d == {
        "u1": 230.1,
        "u2": 230.2,
        "u3": 230.3,
        "i1": 5.0,
        "i2": 2.0,
        "i3": 1.0,
        "w_con": 1500,
        "w_prov": 0,
        "total_con": 12345678,
        "total_prov": 1000,
        "power_factor": 0.98,
    }


def test_to_json_roundtrips_to_to_dict() -> None:
    md = MeterData(dict(BASE))
    assert json.loads(md.to_json()) == md.to_dict()
