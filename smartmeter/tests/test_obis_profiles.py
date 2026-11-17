"""End-to-end tests: serial bytes → profile reader → ObisMeterData.

Covers the Steiermark, Salzburg, Tirol and H1 profiles. The telegrams
follow the operators' specifications but are synthetic (see
tests/fixtures/obis_frames.py); real telegrams are still wanted.
"""

from __future__ import annotations

import logging

import pytest
import serial

from meter.profile import ObisProfile, get_profile
from meter.obis import reader as obis_reader
from meter.obis.reader import ObisMeterReader
from meter.serial.transport import PortClosedError
from tests.fake_port import EOF, FakePort, chunks, run_until
from meter.obis.registers import FIELDS, ObisMeterData
from tests.fixtures.obis_frames import (
    DSMR_EXPECTED,
    DSMR_TIME_ISO,
    E450_EXPECTED,
    KAIFA_EXPECTED,
    TEST_KEY,
    TEST_KEY_HEX,
    TIMESTAMP_ISO,
    dsmr_telegram,
    e450_hdlc_stream,
    encrypted_dsmr,
    envelope,
    gbt_hdlc_frames,
    hdlc_ui_frame,
    kaifa_apdu,
    kaifa_mbus_stream,
)

OBIS_PROFILES = ["steiermark", "steiermark_sagemcom", "salzburg", "tirol", "h1"]


async def run_reader(meter_type: str, payload: bytes, key_hex: str = TEST_KEY_HEX) -> list:
    """Feed ``payload`` in small chunks through the profile's reader."""
    received: list = []
    reader = get_profile(meter_type).create_reader({"dlms": {"key": key_hex}}, received.append)
    assert isinstance(reader, ObisMeterReader)
    reader._open_stream = FakePort([*chunks(payload, 9), EOF])
    task = await run_until(reader.run, lambda: False)
    assert isinstance(task.exception(), PortClosedError)
    return received


def expected_dict(values: dict, meter_time: str | None) -> dict:
    result = {field: values.get(field) for field in FIELDS}
    result["meter_time"] = meter_time
    return result


@pytest.mark.parametrize("meter_type", ["salzburg", "tirol"])
async def test_kaifa_profiles_decode_segmented_mbus(meter_type: str) -> None:
    received = await run_reader(meter_type, kaifa_mbus_stream() * 2)
    assert len(received) == 2
    assert all(isinstance(d, ObisMeterData) for d in received)
    assert received[0].to_dict() == expected_dict(KAIFA_EXPECTED, TIMESTAMP_ISO)
    assert received[0].meter_id == "KFM1200200012345"


async def test_steiermark_e450_decodes_hdlc_block_transfer() -> None:
    received = await run_reader("steiermark", b"\x00\x01" + e450_hdlc_stream())
    assert [d.to_dict() for d in received] == [expected_dict(E450_EXPECTED, TIMESTAMP_ISO)]


@pytest.mark.parametrize("meter_type", ["h1", "steiermark_sagemcom"])
async def test_p1_profiles_decode_encrypted_dsmr(meter_type: str) -> None:
    received = await run_reader(meter_type, encrypted_dsmr() + encrypted_dsmr())
    assert len(received) == 2
    assert received[0].to_dict() == expected_dict(DSMR_EXPECTED, DSMR_TIME_ISO)


async def test_h1_accepts_plain_dsmr_and_hdlc_wrapped_dlms() -> None:
    hdlc = hdlc_ui_frame(b"\xe6\xe7\x00" + envelope(kaifa_apdu(), security_control=0x30))
    raw_dlms = envelope(kaifa_apdu(), security_control=0x30)
    received = await run_reader("h1", dsmr_telegram() + hdlc + raw_dlms)
    assert len(received) == 3
    assert received[1].to_dict() == expected_dict(KAIFA_EXPECTED, TIMESTAMP_ISO)
    assert received[2].to_dict() == received[1].to_dict()


async def test_wrong_key_decodes_nothing_and_hints_at_key() -> None:
    received: list = []
    reader = get_profile("tirol").create_reader(
        {"dlms": {"key": "00" * 16}}, received.append
    )
    assert isinstance(reader, ObisMeterReader)
    reader._open_stream = FakePort([*chunks(kaifa_mbus_stream(), 9), EOF])
    await run_until(reader.run, lambda: False)
    assert received == []
    assert reader.diagnostic_hint() is not None
    assert "key" in (reader.diagnostic_hint() or "")


async def test_repeated_decode_failures_end_the_reader() -> None:
    bad = gbt_hdlc_frames(envelope(kaifa_apdu(), bytes(16), security_control=0x30))
    reader = get_profile("steiermark").create_reader(
        {"dlms": {"key": TEST_KEY_HEX}}, lambda data: None
    )
    assert isinstance(reader, ObisMeterReader)
    reader._open_stream = FakePort([bad] * obis_reader.MAX_CONSECUTIVE_FAILURES)
    task = await run_until(reader.run, lambda: False)
    assert isinstance(task.exception(), ValueError)


async def test_heartbeat_reports_the_failing_layer(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(obis_reader, "HEARTBEAT_SECONDS", 0.02)
    reader = get_profile("h1").create_reader({"dlms": {"key": ""}}, lambda data: None)
    reader._open_stream = FakePort([b"\x00\x01\x02"])
    with caplog.at_level(logging.INFO, logger="meter.obis.reader"):
        await run_until(reader.run, lambda: "reader diagnostic" in caplog.text)
    assert "no complete telegram" in caplog.text


async def test_garbled_telegram_does_not_stop_the_reader() -> None:
    good = gbt_hdlc_frames(envelope(kaifa_apdu(), TEST_KEY, security_control=0x30))
    bad = gbt_hdlc_frames(envelope(kaifa_apdu(), bytes(16), security_control=0x30))
    received = await run_reader("steiermark", bad + good)
    assert len(received) == 1


# --- profile metadata ----------------------------------------------------------


@pytest.mark.parametrize(
    ("meter_type", "serial_defaults", "push_seconds"),
    [
        ("steiermark", (2400, 8, serial.PARITY_EVEN, 1), 10.0),
        ("steiermark_sagemcom", (115200, 8, serial.PARITY_NONE, 1), 10.0),
        ("salzburg", (2400, 8, serial.PARITY_EVEN, 1), 5.0),
        ("tirol", (2400, 8, serial.PARITY_EVEN, 1), 5.0),
        ("h1", (115200, 8, serial.PARITY_NONE, 1), 1.0),
    ],
)
def test_obis_profile_defaults(
    meter_type: str, serial_defaults: tuple, push_seconds: float
) -> None:
    profile = get_profile(meter_type)
    assert isinstance(profile, ObisProfile)
    settings = profile.serial_settings({"dlms": {}})
    assert (
        settings.baudrate,
        settings.bytesize,
        settings.parity,
        settings.stopbits,
    ) == serial_defaults
    assert profile.push_interval_seconds == push_seconds


@pytest.mark.parametrize("meter_type", OBIS_PROFILES)
def test_obis_profile_sensors_read_published_keys(meter_type: str) -> None:
    profile = get_profile(meter_type)
    specs = profile.sensor_specs
    assert specs[0].raw
    suffixes = [s.suffix for s in specs[1:]]
    assert len(suffixes) == len(set(suffixes))
    for spec in specs[1:]:
        key = (spec.value_template or "").strip("{} ").removeprefix("value_json.")
        assert key in FIELDS, spec


def test_sensor_names_match_existing_profiles() -> None:
    """Shared fields keep the unique-id suffix of the NÖ/Wien profiles."""
    reference = {
        s.value_template: s.suffix
        for name in ("noe_evn", "wien")
        for s in get_profile(name).sensor_specs
        if not s.raw
    }
    for spec in get_profile("h1").sensor_specs[1:]:
        if spec.value_template in reference:
            assert reference[spec.value_template] == spec.suffix
