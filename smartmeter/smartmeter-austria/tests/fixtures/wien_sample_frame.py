"""Build Wiener Netze telegrams for tests.

The decrypted notification below is the real example documented in
tofuSCHNITZEL/wiener-netze-smartmeter-serial (Iskraemeco AM550, MIT
licensed). It is re-encrypted with a test key and wrapped in the HDLC
header of the same real frame (``7E A0 67 CF 02 23 13 FB F1 E6 E7 00 DB 08
49 53 4B ...``), so the frame matches what the meter puts on the wire
except for the key.

Built without gurux, like ``bgld_sample_frame``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from Cryptodome.Cipher import AES

from tests.fixtures.bgld_sample_frame import hdlc_fcs

TEST_KEY = bytes.fromhex("000102030405060708090A0B0C0D0E0F")
SYSTEM_TITLE = bytes.fromhex("49534B697456F2C3")  # "ISK" = Iskraemeco
INVOCATION_COUNTER = 0x0D398FA4
# 2026-08-22 17:11:36, deviation -120 min (= UTC+2), clock status 0x80
TIMESTAMP = bytes.fromhex("07EA081606110B2400FF8880")

# +A, -A, +R, -R, +P, -P, +Q, -Q
COUNTERS = [21763058, 6, 6588, 13622858, 143, 0, 0, 276]
SERIAL_NUMBER = b"1SIE0012345678AB"  # 16 ASCII chars, sent by some meters

# Real decrypted notification from the reference README (without serial).
REAL_PLAIN_APDU = bytes.fromhex(
    "0F00398F9A0C07EA081606110B2400FF888002090"
    "90C07EA081606110B2400FF888006014C13F2060000000606000019BC"
    "0600CFDE4A060000008F06000000000600000000060000 0114".replace(" ", "")
)


def build_apdu(with_serial: bool = False, counters: list[int] = COUNTERS) -> bytes:
    """Data-notification with the Wiener Netze structure layout."""
    elements = b""
    if with_serial:
        elements += b"\x09" + bytes([len(SERIAL_NUMBER)]) + SERIAL_NUMBER
    elements += b"\x09\x0c" + TIMESTAMP
    for value in counters:
        elements += b"\x06" + struct.pack(">I", value)
    count = 2 + len(counters) - (0 if with_serial else 1)
    return (
        b"\x0f"
        + struct.pack(">I", 0x00398F9A)
        + b"\x0c"
        + TIMESTAMP
        + b"\x02"
        + bytes([count])
        + elements
    )


def hdlc_frame(apdu: bytes, key: bytes = TEST_KEY) -> bytes:
    """Encrypt ``apdu`` and wrap it like the meter does."""
    ic = struct.pack(">I", INVOCATION_COUNTER)
    ciphertext = AES.new(key, AES.MODE_GCM, nonce=SYSTEM_TITLE + ic).encrypt(apdu)
    secured = b"\x20" + ic + ciphertext  # encryption only, suite 0
    assert len(secured) < 0x80, "short length form only"
    information = (
        b"\xe6\xe7\x00\xdb\x08" + SYSTEM_TITLE + bytes([len(secured)]) + secured
    )
    address_control = b"\xcf\x02\x23\x13"
    length = 2 + len(address_control) + 2 + len(information) + 2
    header = struct.pack(">H", 0xA000 | length) + address_control
    body = header + hdlc_fcs(header) + information
    return b"\x7e" + body + hdlc_fcs(body) + b"\x7e"


@dataclass(frozen=True)
class WienTelegram:
    frame: bytes
    key_hex: str


def build_telegram(apdu: bytes = REAL_PLAIN_APDU, key: bytes = TEST_KEY) -> WienTelegram:
    return WienTelegram(frame=hdlc_frame(apdu, key), key_hex=key.hex().upper())
