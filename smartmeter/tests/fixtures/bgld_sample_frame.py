"""Build deterministic Netz Burgenland (Landis+Gyr E450) telegrams for tests.

The meter pushes a DLMS ``data-notification`` every 5 seconds, encrypted with
``general-glo-ciphering`` (security control 0x20 = encryption only, AES-GCM
without authentication tag) and wrapped in a single HDLC frame:

    7E A0 LL  CE FF  03  13  HCS HCS  E6 E7 00  <ciphered APDU>  FCS FCS  7E

The layout matches the frame headers seen in real debug logs (#128), e.g.
``7e a0 76 ce ff 03 13 3c 02 e6 e7 00 db 08 4c 47 5a ...``.

Everything here is built **without gurux** (HDLC CRC, AES via pycryptodomex),
so the tests that feed these frames to gurux check gurux against an
independent reference instead of against itself.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from Cryptodome.Cipher import AES

TEST_KEY = bytes.fromhex("36C66639E48A8CA4D6BC8B282A793BBB")
SYSTEM_TITLE = b"LGZgr\x00\x01\x02"  # 8 bytes, "LGZ" = Landis+Gyr
FRAME_COUNTER = 0x0001E240

# Value order as decoded by meter.bgld.data.MeterData.
EXPECTED_VALUES: list[int | bytes] = [
    236,  # voltage L1 [V]
    235,  # voltage L2 [V]
    237,  # voltage L3 [V]
    512,  # current L1 [10 mA]
    48,  # current L2 [10 mA]
    1999,  # current L3 [10 mA]
    3314,  # active power +P [W]
    0,  # active power -P [W]
    49244276,  # energy +A [Wh]
    1234567,  # energy -A [Wh]
    17,  # angle U1/I1
    195,  # angle U2/I2
    304,  # angle U3/I3
    b"1LGZ0012345678",  # meter id
]


def _dlms_value(value: int | bytes, kind: str) -> bytes:
    if kind == "u16":
        return b"\x12" + struct.pack(">H", value)
    if kind == "u32":
        return b"\x06" + struct.pack(">I", value)
    assert isinstance(value, bytes)
    return b"\x09" + bytes([len(value)]) + value


_KINDS = ["u16"] * 6 + ["u32"] * 4 + ["u16"] * 3 + ["octets"]


def build_apdu(values: list[int | bytes] = EXPECTED_VALUES) -> bytes:
    """Plain DLMS data-notification carrying ``values`` as a structure."""
    apdu = bytearray(b"\x0f")  # data-notification
    apdu += struct.pack(">I", 0x00000001)  # long-invoke-id-and-priority
    # date-time as octet-string(12): 2026-11-14 12:00:00, deviation/status unset
    apdu += b"\x0c\x07\xea\x0b\x0e\x06\x0c\x00\x00\x00\x80\x00\x00"
    apdu += b"\x02" + bytes([len(values)])  # structure
    for value, kind in zip(values, _KINDS, strict=True):
        apdu += _dlms_value(value, kind)
    return bytes(apdu)


def cipher_apdu(
    apdu: bytes,
    key: bytes = TEST_KEY,
    system_title: bytes = SYSTEM_TITLE,
    frame_counter: int = FRAME_COUNTER,
) -> bytes:
    """Wrap ``apdu`` in general-glo-ciphering (encryption only, suite 0)."""
    fc = struct.pack(">I", frame_counter)
    ciphertext = AES.new(key, AES.MODE_GCM, nonce=system_title + fc).encrypt(apdu)
    payload = b"\x20" + fc + ciphertext  # security control: encryption only
    assert len(payload) < 0x80, "short BER length only"
    return (
        b"\xdb"
        + bytes([len(system_title)])
        + system_title
        + bytes([len(payload)])
        + payload
    )


def hdlc_fcs(data: bytes) -> bytes:
    """HDLC FCS-16 (CRC-16/X-25), little endian."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return struct.pack("<H", crc ^ 0xFFFF)


def hdlc_frame(information: bytes) -> bytes:
    """Single, unsegmented HDLC UI frame as pushed by the meter."""
    address_control = b"\xce\xff\x03\x13"  # dest 0x67FF, src 0x01, UI + P/F
    llc = b"\xe6\xe7\x00"
    length = 2 + len(address_control) + 2 + len(llc) + len(information) + 2
    assert length <= 0x7FF
    header = struct.pack(">H", 0xA000 | length) + address_control
    body = header + hdlc_fcs(header) + llc + information
    return b"\x7e" + body + hdlc_fcs(body) + b"\x7e"


@dataclass(frozen=True)
class SampleTelegram:
    frame: bytes
    key_hex: str
    values: list[int | bytes]


def build_sample_telegram(
    values: list[int | bytes] = EXPECTED_VALUES,
    key: bytes = TEST_KEY,
    frame_counter: int = FRAME_COUNTER,
) -> SampleTelegram:
    frame = hdlc_frame(
        cipher_apdu(build_apdu(values), key=key, frame_counter=frame_counter)
    )
    return SampleTelegram(frame=frame, key_hex=key.hex().upper(), values=list(values))
