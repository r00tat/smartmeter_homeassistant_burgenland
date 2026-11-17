"""Tests for the Wiener Netze profile: data mapping and full decode pipeline."""

from __future__ import annotations

import json

import pytest

from smartmeter_austria.dlms.read import parse_dlms_data, parse_pyhiscal_dlms_data, parse_xml
from smartmeter_austria.profile import get_profile
from smartmeter_austria.serial import read as serial_read
from smartmeter_austria.serial.read import MeterReader
from tests.fake_port import EOF, FakePort, run_until
from smartmeter_austria.wien.data import MeterData, parse_dlms_datetime
from tests.fixtures.wien_sample_frame import (
    COUNTERS,
    SERIAL_NUMBER,
    TIMESTAMP,
    build_apdu,
    build_telegram,
)

EXPECTED_DICT = {
    "w_con": 143,
    "w_prov": 0,
    "total_con": 21763058,
    "total_prov": 6,
    "var_con": 0,
    "var_prov": 276,
    "reactive_total_con": 6588,
    "reactive_total_prov": 13622858,
    "meter_time": "2026-08-22T17:11:36+02:00",
}


def decode_optical(frame: bytes, key: str) -> list:
    return parse_dlms_data(frame, key).value


def decode_physical(frame: bytes, key: str) -> list:
    return parse_xml(parse_pyhiscal_dlms_data(frame, key))


DECODERS = [
    pytest.param(decode_optical, id="optical"),
    pytest.param(decode_physical, id="physical"),
]


# --- MeterData ----------------------------------------------------------------


def test_maps_values_without_serial_number() -> None:
    data = MeterData([bytearray(TIMESTAMP), *COUNTERS])
    assert data.to_dict() == EXPECTED_DICT
    assert data.meter_id is None


def test_maps_values_with_serial_number() -> None:
    data = MeterData([bytearray(SERIAL_NUMBER), bytearray(TIMESTAMP), *COUNTERS])
    assert data.to_dict() == EXPECTED_DICT
    assert data.meter_id == SERIAL_NUMBER.decode()


def test_to_json_round_trips() -> None:
    data = MeterData([bytearray(TIMESTAMP), *COUNTERS])
    assert json.loads(data.to_json()) == EXPECTED_DICT


@pytest.mark.parametrize(
    "values",
    [
        pytest.param([bytearray(TIMESTAMP), *COUNTERS[:-1]], id="too-few"),
        pytest.param([bytearray(TIMESTAMP), *COUNTERS, 1], id="too-many"),
        pytest.param([236, 235, 237, 512, 48, 1999, 3314, 0, 1, 2, 17, 195, 304,
                      bytearray(b"1LGZ")], id="burgenland-layout"),
    ],
)
def test_rejects_unexpected_layout(values: list) -> None:
    with pytest.raises(ValueError, match="Wiener Netze"):
        MeterData(values)


def test_datetime_without_deviation_is_naive() -> None:
    raw = bytes.fromhex("07EA081606110B2400800000")
    assert parse_dlms_datetime(raw) == "2026-08-22T17:11:36"


def test_datetime_with_unspecified_fields_is_dropped() -> None:
    assert parse_dlms_datetime(bytes.fromhex("FFFFFFFFFFFFFFFFFF800000")) is None
    assert parse_dlms_datetime(b"\x07\xea") is None


# --- through gurux ----------------------------------------------------------


@pytest.mark.parametrize("decode", DECODERS)
def test_real_layout_decodes_through_gurux(decode) -> None:
    telegram = build_telegram()
    assert len(telegram.frame) == 105  # same size as the real AM550 frame

    data = MeterData(decode(telegram.frame, telegram.key_hex))

    assert data.to_dict() == EXPECTED_DICT


@pytest.mark.parametrize("decode", DECODERS)
def test_layout_with_serial_number_decodes_through_gurux(decode) -> None:
    telegram = build_telegram(build_apdu(with_serial=True))

    data = MeterData(decode(telegram.frame, telegram.key_hex))

    assert data.to_dict() == EXPECTED_DICT
    assert data.meter_id == SERIAL_NUMBER.decode()


def test_wrong_key_is_not_decoded() -> None:
    telegram = build_telegram()
    with pytest.raises(ValueError):
        MeterData(decode_optical(telegram.frame, "00" * 16))


# --- through the reader built by the profile ----------------------------------


@pytest.mark.parametrize("interface_type", ["OPTICAL", "PHYSICAL"])
async def test_profile_reader_publishes_wien_data(
    interface_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serial_read, "OPTICAL_IDLE_GAP_SECONDS", 0.02)
    telegram = build_telegram()
    received: list = []
    cfg = {
        "interface_type": interface_type,
        "dlms": {
            "key": telegram.key_hex,
            "port": "/dev/ttyUSB0",
            "hdlc_frame_size": len(telegram.frame),
        },
    }
    reader = get_profile("wien").create_reader(cfg, received.append)
    assert isinstance(reader, MeterReader)
    assert reader.settings.port == "/dev/ttyUSB0"

    corrupted = bytearray(telegram.frame)
    corrupted[40] ^= 0xFF
    reader._open_stream = FakePort(
        [bytes(corrupted), 0.1, telegram.frame, 0.1, telegram.frame, 0.1, EOF]
    )
    await run_until(reader.run, lambda: False)

    assert [type(d) for d in received] == [MeterData, MeterData]
    assert [d.to_dict() for d in received] == [EXPECTED_DICT, EXPECTED_DICT]
