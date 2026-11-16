"""Unit tests for the layers of the generic push pipeline (meter.push)."""

from __future__ import annotations

import pytest

from meter.push.axdr import AxdrError, decode_data, decode_data_notification
from meter.push.cipher import CipherError, decrypt_envelope, envelope_size, parse_envelope
from meter.push.decode import WrongKeyError, decode_unit
from meter.push.dsmr import DsmrError, crc16, parse_telegram
from meter.push.framing import PushFramer, hdlc_fcs
from meter.push.registers import (
    FIELDS,
    obis_to_str,
    parse_dsmr_timestamp,
    registers_from_notification,
)
from tests.fixtures.push_frames import (
    DSMR_EXPECTED,
    DSMR_METER_ID,
    DSMR_TIME_ISO,
    E450_EXPECTED,
    KAIFA_EXPECTED,
    METER_NUMBER,
    SALZBURG_SPEC_FRAME,
    STEIERMARK_FORUM_HEADER,
    SYSTEM_TITLE,
    TEST_KEY,
    TIMESTAMP,
    TIMESTAMP_ISO,
    dsmr_telegram,
    e450_apdu,
    e450_hdlc_stream,
    encrypted_dsmr,
    envelope,
    kaifa_apdu,
    kaifa_mbus_stream,
    mbus_frames,
)


def expected_dict(values: dict, meter_time: str | None) -> dict:
    result = {field: values.get(field) for field in FIELDS}
    result["meter_time"] = meter_time
    return result


# --- A-XDR ------------------------------------------------------------------


def test_decodes_nested_structures_and_types() -> None:
    # structure { octet-string OBIS, long-unsigned 255, integer -2, array [1, 2, 3] }
    raw = bytes.fromhex("0204 09060100010800FF 120 0FF 0FFE 0103110111021103".replace(" ", ""))
    assert decode_data(raw) == [bytes.fromhex("0100010800FF"), 255, -2, [1, 2, 3]]


def test_decodes_strings_signed_and_null() -> None:
    raw = bytes.fromhex("0205" "0A03414243" "05FFFFFFFE" "00" "0301" "1621")
    assert decode_data(raw) == ["ABC", -2, None, True, 0x21]


def test_long_form_length() -> None:
    payload = bytes(range(200))
    assert decode_data(b"\x09\x81\xc8" + payload) == payload


def test_truncated_apdu_raises() -> None:
    with pytest.raises(AxdrError, match="truncated"):
        decode_data(bytes.fromhex("0906010001"))


def test_unknown_tag_raises() -> None:
    with pytest.raises(AxdrError, match="tag"):
        decode_data(b"\x7f")


def test_data_notification_header() -> None:
    notification = decode_data_notification(kaifa_apdu())
    assert notification.invoke_id == 0x16E
    assert notification.timestamp == TIMESTAMP
    assert isinstance(notification.body, list)


def test_data_notification_without_timestamp() -> None:
    notification = decode_data_notification(e450_apdu())
    assert notification.timestamp is None


def test_rejects_non_notification() -> None:
    with pytest.raises(AxdrError, match="data-notification"):
        decode_data_notification(b"\xc4\x01")


# --- general-glo-ciphering ---------------------------------------------------


def test_salzburg_spec_example_envelope() -> None:
    """Real example frame from the Salzburg Netz specification."""
    units = PushFramer(mbus=True).feed(SALZBURG_SPEC_FRAME)
    assert len(units) == 1
    parsed = parse_envelope(units[0])
    assert parsed.system_title == bytes.fromhex("454C536570000001")  # "ELSep"
    assert parsed.security_control == 0x20
    assert parsed.frame_counter == bytes.fromhex("0000541F")
    assert len(parsed.payload) == 0x4D - 5


@pytest.mark.parametrize("security_control", [0x20, 0x21, 0x30, 0x31])
def test_envelope_round_trip(security_control: int) -> None:
    plain = kaifa_apdu()
    unit = envelope(plain, security_control=security_control)
    assert envelope_size(unit) == len(unit)
    assert decrypt_envelope(unit, TEST_KEY) == plain


def test_envelope_size_waits_for_header() -> None:
    unit = envelope(kaifa_apdu())
    assert unit[10] == 0x82  # two-byte length form
    assert envelope_size(unit[:5]) is None
    assert envelope_size(unit[:11]) is None
    assert envelope_size(unit[:13]) == len(unit)


def test_envelope_rejects_garbage() -> None:
    with pytest.raises(CipherError):
        envelope_size(b"\x0f\x00")
    with pytest.raises(CipherError):
        parse_envelope(envelope(kaifa_apdu())[:-3])


def test_wrong_key_is_reported() -> None:
    with pytest.raises(WrongKeyError, match="key"):
        decode_unit(envelope(kaifa_apdu()), bytes(16))


# --- DSMR ---------------------------------------------------------------------


def test_dsmr_crc_matches_reference() -> None:
    # CRC-16/ARC check value
    assert crc16(b"123456789") == 0xBB3D


def test_dsmr_telegram_values_are_normalised() -> None:
    values = {v.obis: (v.value, v.unit) for v in parse_telegram(dsmr_telegram())}
    assert values["1-0:1.7.0"] == (412, "W")
    assert values["1-0:2.8.0"] == (100, "Wh")
    assert values["1-0:32.7.0"] == (230.1, "V")
    assert values["0-0:1.0.0"] == ("261116102030W", None)


def test_dsmr_crc_mismatch_raises() -> None:
    telegram = dsmr_telegram().replace(b"5562", b"5563")
    with pytest.raises(DsmrError, match="CRC"):
        parse_telegram(telegram)


def test_dsmr_without_crc_is_accepted() -> None:
    telegram = dsmr_telegram()
    telegram = telegram[: telegram.index(b"!") + 1] + b"\r\n"
    assert parse_telegram(telegram)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("261116102030W", "2026-11-16T10:20:30+01:00"),
        ("260716102030S", "2026-07-16T10:20:30+02:00"),
        ("2607161020", None),
        ("261399102030S", None),
    ],
)
def test_dsmr_timestamp(text: str, expected: str | None) -> None:
    assert parse_dsmr_timestamp(text) == expected


# --- OBIS register mapping -----------------------------------------------------


def test_obis_to_str() -> None:
    assert obis_to_str(bytes.fromhex("0100200700FF")) == "1-0:32.7.0"


def test_kaifa_registers_apply_scalers() -> None:
    data = registers_from_notification(decode_data_notification(kaifa_apdu()))
    assert data.to_dict() == expected_dict(KAIFA_EXPECTED, TIMESTAMP_ISO)
    assert data.meter_id == METER_NUMBER.decode()
    assert data.u1 == 230.1


def test_e450_registers_without_scalers() -> None:
    data = registers_from_notification(decode_data_notification(e450_apdu()))
    assert data.to_dict() == expected_dict(E450_EXPECTED, TIMESTAMP_ISO)
    assert data.meter_id is None


def test_dsmr_registers() -> None:
    data = decode_unit(dsmr_telegram(), b"")
    assert data.to_dict() == expected_dict(DSMR_EXPECTED, DSMR_TIME_ISO)
    assert data.meter_id == DSMR_METER_ID


def test_telegram_without_known_registers_raises() -> None:
    from tests.fixtures.push_frames import data_notification, octets, structure, uint32

    apdu = data_notification(structure([octets(bytes.fromhex("0100630700FF")), uint32(1)]))
    with pytest.raises(ValueError, match="no known OBIS"):
        registers_from_notification(decode_data_notification(apdu))


# --- framing ------------------------------------------------------------------


def test_mbus_reassembles_two_segments() -> None:
    stream = kaifa_mbus_stream()
    assert stream[6] == 0x00  # first segment CI
    units = PushFramer(mbus=True).feed(stream)
    assert units == [envelope(kaifa_apdu())]


def test_mbus_single_segment_has_ci_0x10() -> None:
    unit = envelope(e450_apdu())
    stream = mbus_frames(unit, segment_size=250)
    assert stream[6] == 0x10
    assert PushFramer(mbus=True).feed(stream) == [unit]


def test_mbus_resyncs_after_garbage_and_split_reads() -> None:
    stream = b"\x00\x68\x01\xe5" + kaifa_mbus_stream() + kaifa_mbus_stream()
    framer = PushFramer(mbus=True)
    units: list[bytes] = []
    for i in range(0, len(stream), 7):
        units += framer.feed(stream[i : i + 7])
    assert len(units) == 2
    assert framer.dropped_bytes == 4


def test_mbus_bad_checksum_is_dropped() -> None:
    stream = bytearray(kaifa_mbus_stream())
    stream[20] ^= 0xFF
    assert PushFramer(mbus=True).feed(bytes(stream)) == []


def test_mbus_missing_first_segment_is_discarded() -> None:
    stream = kaifa_mbus_stream()
    first_len = stream[1] + 6
    assert PushFramer(mbus=True).feed(stream[first_len:]) == []


def test_hdlc_fcs_matches_real_steiermark_header() -> None:
    # HCS of "A0 8B CE FF 03 13" is "EE E1" (little endian) in the real frame.
    header = STEIERMARK_FORUM_HEADER[1:7]
    assert hdlc_fcs(header).to_bytes(2, "little") == STEIERMARK_FORUM_HEADER[7:9]


def test_hdlc_general_block_transfer_is_reassembled() -> None:
    stream = e450_hdlc_stream()
    assert stream.count(b"\xe6\xe7\x00\xe0") >= 2  # really split into blocks
    units = PushFramer(hdlc=True).feed(stream)
    assert len(units) == 1
    assert decrypt_envelope(units[0], TEST_KEY) == e450_apdu()


def test_hdlc_bad_fcs_drops_the_message() -> None:
    stream = bytearray(e450_hdlc_stream())
    stream[30] ^= 0x01
    assert PushFramer(hdlc=True).feed(bytes(stream)) == []


def test_p1_framer_splits_dsmr_and_envelopes() -> None:
    stream = b"garbage" + dsmr_telegram() + encrypted_dsmr() + dsmr_telegram()
    units = PushFramer(p1=True, hdlc=True).feed(stream)
    assert units == [dsmr_telegram(), encrypted_dsmr(), dsmr_telegram()]


def test_framer_needs_a_transport() -> None:
    with pytest.raises(ValueError):
        PushFramer()


def test_system_title_is_kaifa() -> None:
    assert SYSTEM_TITLE[:3] == b"KFM"
