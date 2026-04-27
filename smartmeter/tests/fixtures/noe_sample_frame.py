"""Build a deterministic Sagemcom T210-D M-Bus frame for tests.

The fixture takes known plaintext OBIS values, encodes them into a
synthetic DLMS APDU, AES-GCM-encrypts it with a known test key, and
wraps the ciphertext in a valid M-Bus long frame. Tests can round-trip
the whole decode pipeline against it.

Running this module directly writes ``noe_sample_frame.hex`` next to
it – useful for human inspection and for replaying the fixture through
external tools.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from Cryptodome.Cipher import AES

# 128-bit AES key used only by tests.
TEST_KEY = bytes.fromhex("000102030405060708090A0B0C0D0E0F")
SYSTEM_TITLE = bytes.fromhex("4B464D1020200412")  # 8 bytes
FRAME_COUNTER = bytes.fromhex("00000001")  # 4 bytes

EXPECTED_OBIS_VALUES: dict[str, int] = {
    "energy_consumed": 12345678,  # Wh
    "energy_provided": 1000,
    "power_consumed": 1500,
    "power_provided": 0,
    "voltage_l1": 2301,  # will render as 230.1 V
    "voltage_l2": 2302,
    "voltage_l3": 2303,
    "current_l1": 500,  # will render as 5.00 A
    "current_l2": 200,
    "current_l3": 100,
    "power_factor": 980,  # will render as 0.980
}

# Map field → OBIS code (reverse of meter.noe.obis.OBIS_TO_FIELD).
_FIELD_TO_OBIS: dict[str, str] = {
    "energy_consumed": "0100010800FF",
    "energy_provided": "0100020800FF",
    "power_consumed": "0100010700FF",
    "power_provided": "0100020700FF",
    "voltage_l1": "0100200700FF",
    "voltage_l2": "0100340700FF",
    "voltage_l3": "0100480700FF",
    "current_l1": "01001F0700FF",
    "current_l2": "0100330700FF",
    "current_l3": "0100470700FF",
    "power_factor": "01000D0700FF",
}


def _encode_apdu(obis_values: dict[str, int]) -> bytes:
    """Synthesise a DLMS APDU that the gurux translator can parse.

    The gurux ``GXDLMSTranslator.pduToXml`` accepts a data-notification
    APDU. We build one that contains a structure of pairs
    ``(OctetString OBIS code, UInt32 value)``. The real meter uses a
    slightly different structure but gurux's output XML contains
    OctetString and UInt nodes in the same order, which is what
    ``parse_obis_xml`` relies on.
    """
    # DLMS tag 0x0F = data-notification; long invoke-id-and-priority
    # (4 bytes) + date-time (0x00 = not-specified) + body.
    body = bytearray()
    body.append(0x0F)  # data-notification
    body += bytes.fromhex("00000001")  # long invoke id and priority
    body.append(0x00)  # date-time: not-specified

    # Body = structure with 2*N elements (OBIS code, value).
    n_items = len(obis_values) * 2
    body.append(0x02)  # type: structure
    body.append(n_items)  # element count (fits in one byte for our test)

    for field, value in obis_values.items():
        obis_hex = _FIELD_TO_OBIS[field]
        obis_bytes = bytes.fromhex(obis_hex)
        # OctetString tag 0x09 + length + bytes
        body.append(0x09)
        body.append(len(obis_bytes))
        body += obis_bytes
        # UInt32 tag 0x06 + 4 bytes big-endian
        body.append(0x06)
        body += struct.pack(">I", value)
    return bytes(body)


def _encrypt(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.encrypt(plaintext)


def _wrap_mbus(
    ciphertext: bytes, system_title: bytes, frame_counter: bytes
) -> bytes:
    """Place the ciphertext at the byte offsets the parser expects."""
    pre = bytes(7)  # bytes 4..10
    mid = bytes(3)  # bytes 19..21
    user_data = pre + system_title + mid + frame_counter + ciphertext
    length = len(user_data)
    assert length <= 0xFF, "synthetic frame larger than an M-Bus long frame"
    checksum = sum(user_data) & 0xFF
    return (
        bytes([0x68, length, length, 0x68])
        + user_data
        + bytes([checksum, 0x16])
    )


@dataclass(frozen=True)
class SampleFrame:
    frame_hex: str
    key: bytes
    system_title: bytes
    frame_counter: bytes
    apdu_plaintext: bytes
    obis_values: dict[str, int]


def build_sample_frame() -> SampleFrame:
    apdu = _encode_apdu(EXPECTED_OBIS_VALUES)
    ciphertext = _encrypt(apdu, TEST_KEY, SYSTEM_TITLE + FRAME_COUNTER)
    frame = _wrap_mbus(ciphertext, SYSTEM_TITLE, FRAME_COUNTER)
    return SampleFrame(
        frame_hex=frame.hex(),
        key=TEST_KEY,
        system_title=SYSTEM_TITLE,
        frame_counter=FRAME_COUNTER,
        apdu_plaintext=apdu,
        obis_values=dict(EXPECTED_OBIS_VALUES),
    )


if __name__ == "__main__":  # pragma: no cover - utility only
    sample = build_sample_frame()
    Path(__file__).with_name("noe_sample_frame.hex").write_text(
        sample.frame_hex + "\n", encoding="utf-8"
    )
    print(sample.frame_hex)
