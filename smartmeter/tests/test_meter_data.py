"""Unit tests for meter.bgld.data.MeterData."""

import json

from meter.bgld.data import MeterData


BASE_DLMS = [
    230,  # voltage_l1
    231,  # voltage_l2
    232,  # voltage_l3
    100,  # current_l1 (raw, 10mA units -> 1.0A)
    200,  # current_l2
    300,  # current_l3
    1500,  # power_consumed (W)
    0,  # power_provided (W)
    1234567,  # total_consumed (Wh)
    89,  # total_provided (Wh)
]


def test_empty_data_keeps_defaults() -> None:
    md = MeterData([])
    assert md.voltage_l1 == 0
    assert md.current_l1 == 0
    assert md.meter_id is None


def test_parse_currents_are_scaled_by_100() -> None:
    md = MeterData(list(BASE_DLMS))
    assert md.current_l1 == 1.0
    assert md.current_l2 == 2.0
    assert md.current_l3 == 3.0


def test_angles_parsed_when_present() -> None:
    data = list(BASE_DLMS) + [10, 20, 30]
    md = MeterData(data)
    assert md.angle_1 == 10
    assert md.angle_2 == 20
    assert md.angle_3 == 30
    assert md.meter_id is None


def test_meter_id_decoded_from_bytes() -> None:
    data = list(BASE_DLMS) + [10, 20, 30, b"ABC123"]
    md = MeterData(data)
    assert md.meter_id == "ABC123"


def test_to_dict_uses_expected_keys() -> None:
    md = MeterData(list(BASE_DLMS))
    d = md.to_dict()
    assert d == {
        "u1": 230,
        "u2": 231,
        "u3": 232,
        "i1": 1.0,
        "i2": 2.0,
        "i3": 3.0,
        "w_con": 1500,
        "w_prov": 0,
        "total_con": 1234567,
        "total_prov": 89,
        "angle1": 0,
        "angle2": 0,
        "angle3": 0,
    }


def test_to_json_roundtrips_to_to_dict() -> None:
    md = MeterData(list(BASE_DLMS))
    assert json.loads(md.to_json()) == md.to_dict()
