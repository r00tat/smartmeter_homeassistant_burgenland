"""Build telegrams for the Steiermark, Salzburg, Tirol and H1 profiles.

The layouts follow the operators' specifications exactly.

No real decryptable telegram with its key is public for these operators
yet, so the frames are synthetic: real layouts, a test key. Where real
bytes are published they are used as-is (``SALZBURG_SPEC_FRAME``, the
HDLC header of ``STEIERMARK_FORUM_HEADER``).
"""

from __future__ import annotations

import struct

from Cryptodome.Cipher import AES

from meter.obis.dsmr import crc16
from meter.obis.framing import hdlc_fcs

TEST_KEY = bytes.fromhex("000102030405060708090A0B0C0D0E0F")
TEST_KEY_HEX = TEST_KEY.hex().upper()
SYSTEM_TITLE = bytes.fromhex("4B464D675468AFC3")  # "KFM" = Kaifa
FRAME_COUNTER = 0x0001A2B3
# 2026-11-16 10:20:30, deviation -60 min (= UTC+1), clock status 0x00
TIMESTAMP = bytes.fromhex("07EA0B10010A141E00FFC400")
TIMESTAMP_ISO = "2026-11-16T10:20:30+01:00"
METER_NUMBER = b"KFM1200200012345"

# Example M-Bus frame from Salzburg Netz' "Technische Beschreibung
# Kundenschnittstelle" (chapter 7.7). Key unknown, so only framing and
# envelope parsing can be checked against it.
SALZBURG_SPEC_FRAME = bytes.fromhex(
    "685D5D6853FF100167DB08454C5365700000014D200000541FE2A330AD29E0D68C09365BA2"
    "86DBF3A7DF14B7790E14D1556AB974B27EC5847D11936DB5191DD0F489BA768C2DBB68F6"
    "B001E304C21FEA147E0B2E2CA1B91D574DF4F7F582CEBE928316"
)
# First bytes of a real Energienetze Steiermark E450 frame (gurux.fi
# forum, node 25250): flag, format/length, addresses, control, HCS, LLC,
# general-block-transfer header.
STEIERMARK_FORUM_HEADER = bytes.fromhex("7EA08BCEFF0313EEE1E6E700E0400001")


def obis(code: str) -> bytes:
    """``1-0:1.8.0`` → 6-byte OBIS octets (F = 255)."""
    ab, cde = code.split(":")
    a, b = ab.split("-")
    c, d, e = cde.split(".")
    return bytes([int(a), int(b), int(c), int(d), int(e), 255])


def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    if n < 0x100:
        return bytes([0x81, n])
    return bytes([0x82]) + struct.pack(">H", n)


def octets(raw: bytes) -> bytes:
    return b"\x09" + _len(len(raw)) + raw


def uint32(value: int) -> bytes:
    return b"\x06" + struct.pack(">I", value)


def uint16(value: int) -> bytes:
    return b"\x12" + struct.pack(">H", value)


def scaler_unit(scaler: int, unit: int) -> bytes:
    return b"\x02\x02\x0f" + struct.pack(">b", scaler) + b"\x16" + bytes([unit])


def structure(elements: list[bytes]) -> bytes:
    return b"\x02" + _len(len(elements)) + b"".join(elements)


def data_notification(body: bytes, timestamp: bytes | None = TIMESTAMP) -> bytes:
    ts = b"\x0c" + timestamp if timestamp else b"\x00"
    return b"\x0f" + struct.pack(">I", 0x0000016E) + ts + body


# --- Kaifa / Honeywell (Salzburg Netz, TINETZ) -------------------------------

KAIFA_REGISTERS: list[tuple[str, bytes, tuple[int, int]]] = [
    # OBIS, encoded value, (scaler, unit)
    ("1-0:32.7.0", uint16(2301), (-1, 35)),  # 230.1 V
    ("1-0:52.7.0", uint16(2312), (-1, 35)),
    ("1-0:72.7.0", uint16(2325), (-1, 35)),
    ("1-0:31.7.0", uint16(512), (-2, 33)),  # 5.12 A
    ("1-0:51.7.0", uint16(48), (-2, 33)),
    ("1-0:71.7.0", uint16(1999), (-2, 33)),
    ("1-0:1.7.0", uint32(1734), (0, 27)),  # W
    ("1-0:2.7.0", uint32(0), (0, 27)),
    ("1-0:1.8.0", uint32(12345678), (0, 30)),  # Wh
    ("1-0:2.8.0", uint32(4321), (0, 30)),
    ("1-0:3.8.0", uint32(6588), (0, 32)),  # varh
    ("1-0:4.8.0", uint32(13622858), (0, 32)),
]
KAIFA_EXPECTED = {
    "u1": 230.1,
    "u2": 231.2,
    "u3": 232.5,
    "i1": 5.12,
    "i2": 0.48,
    "i3": 19.99,
    "w_con": 1734,
    "w_prov": 0,
    "total_con": 12345678,
    "total_prov": 4321,
    "reactive_total_con": 6588,
    "reactive_total_prov": 13622858,
}


def kaifa_apdu() -> bytes:
    """Data-notification with the TINETZ / Salzburg Netz object list."""
    elements = [
        octets(obis("0-0:1.0.0")),
        octets(TIMESTAMP),
        octets(obis("0-0:96.1.0")),
        octets(METER_NUMBER),
        octets(obis("0-0:42.0.0")),
        octets(b"KFM6700000012345"),
    ]
    for code, value, (scaler, unit) in KAIFA_REGISTERS:
        elements += [octets(obis(code)), value, scaler_unit(scaler, unit)]
    return data_notification(structure(elements))


def envelope(
    plain: bytes,
    key: bytes = TEST_KEY,
    security_control: int = 0x21,
    frame_counter: int = FRAME_COUNTER,
) -> bytes:
    """general-glo-ciphering APDU; appends a GCM tag if SC has bit 0x10."""
    fc = struct.pack(">I", frame_counter)
    cipher = AES.new(key, AES.MODE_GCM, nonce=SYSTEM_TITLE + fc)
    if security_control & 0x10:
        cipher.update(bytes([security_control]) + key)  # AAD = SC || AK
        ciphertext, tag = cipher.encrypt_and_digest(plain)
        ciphertext += tag[:12]
    else:
        ciphertext = cipher.encrypt(plain)
    secured = bytes([security_control]) + fc + ciphertext
    return b"\xdb\x08" + SYSTEM_TITLE + _len(len(secured)) + secured


def mbus_frames(unit: bytes, segment_size: int = 250) -> bytes:
    """Split ``unit`` into DLMS M-Bus transport segments (CI 00, 01 … 1n)."""
    parts = [unit[i : i + segment_size] for i in range(0, len(unit), segment_size)]
    frames = b""
    for index, part in enumerate(parts):
        ci = index | (0x10 if index == len(parts) - 1 else 0)
        user = bytes([0x53, 0xFF, ci, 0x01, 0x67]) + part
        frames += (
            bytes([0x68, len(user), len(user), 0x68])
            + user
            + bytes([sum(user) & 0xFF, 0x16])
        )
    return frames


def kaifa_mbus_stream(key: bytes = TEST_KEY) -> bytes:
    return mbus_frames(envelope(kaifa_apdu(), key))


# --- Landis+Gyr E450 (Energienetze Steiermark) -------------------------------

E450_REGISTERS: list[tuple[str, int]] = [
    ("1-0:1.8.0", 5562),
    ("1-0:1.8.1", 2094),
    ("1-0:1.8.2", 3468),
    ("1-0:1.7.0", 412),
    ("1-0:2.8.0", 100),
    ("1-0:2.8.1", 0),
    ("1-0:2.8.2", 100),
    ("1-0:2.7.0", 0),
    ("1-0:3.8.0", 4419),
    ("1-0:3.8.1", 1918),
    ("1-0:3.8.2", 2501),
    ("1-0:3.7.0", 8),
    ("1-0:4.8.0", 78814),
    ("1-0:4.8.1", 52546),
    ("1-0:4.8.2", 26268),
    ("1-0:4.7.0", 0),
]
E450_EXPECTED = {
    "total_con": 5562,
    "total_con_t1": 2094,
    "total_con_t2": 3468,
    "w_con": 412,
    "total_prov": 100,
    "total_prov_t1": 0,
    "total_prov_t2": 100,
    "w_prov": 0,
    "reactive_total_con": 4419,
    "var_con": 8,
    "reactive_total_prov": 78814,
    "var_prov": 0,
}


def e450_apdu() -> bytes:
    """Clock followed by 16 OBIS/uint32 pairs, without scalers."""
    elements = [octets(TIMESTAMP)]
    for code, value in E450_REGISTERS:
        elements += [octets(obis(code)), uint32(value)]
    return data_notification(structure(elements), timestamp=None)


def hdlc_ui_frame(information: bytes, segmented: bool = False) -> bytes:
    address_control = b"\xce\xff\x03\x13"
    length = 2 + len(address_control) + 2 + len(information) + 2
    fmt = 0xA000 | (0x0800 if segmented else 0) | length
    header = struct.pack(">H", fmt) + address_control
    body = header + struct.pack("<H", hdlc_fcs(header)) + information
    return b"\x7e" + body + struct.pack("<H", hdlc_fcs(body)) + b"\x7e"


def gbt_hdlc_frames(unit: bytes, block_size: int = 120) -> bytes:
    """One general-block-transfer block per HDLC frame, as the E450 sends."""
    blocks = [unit[i : i + block_size] for i in range(0, len(unit), block_size)]
    frames = b""
    for number, block in enumerate(blocks, start=1):
        control = 0x40 | (0x80 if number == len(blocks) else 0)
        gbt = (
            bytes([0xE0, control])
            + struct.pack(">HH", number, 0)
            + _len(len(block))
            + block
        )
        frames += hdlc_ui_frame(b"\xe6\xe7\x00" + gbt)
    return frames


def e450_hdlc_stream(key: bytes = TEST_KEY) -> bytes:
    # SC 0x30: suite 0, authenticated and encrypted (GAK + GUEK).
    return gbt_hdlc_frames(envelope(e450_apdu(), key, security_control=0x30))


# --- DSMR P1 (Smart Meter 2.0 H1, Sagemcom Steiermark) ------------------------

DSMR_BODY = (
    "/EST5\\253740976_A\r\n"
    "\r\n"
    "1-3:0.2.8(50)\r\n"
    "0-0:1.0.0(261116102030W)\r\n"
    "0-0:96.1.1(4B464D31323030323030303132333435)\r\n"
    "1-0:1.8.0(000005562*Wh)\r\n"
    "1-0:1.8.1(000002094*Wh)\r\n"
    "1-0:1.8.2(000003468*Wh)\r\n"
    "1-0:1.7.0(00.412*kW)\r\n"
    "1-0:2.8.0(00000.100*kWh)\r\n"
    "1-0:2.7.0(000000000*W)\r\n"
    "1-0:3.8.0(000004419*varh)\r\n"
    "1-0:3.7.0(000000008*var)\r\n"
    "1-0:4.8.0(000078814*varh)\r\n"
    "1-0:4.7.0(000000000*var)\r\n"
    "1-0:32.7.0(230.1*V)\r\n"
    "1-0:31.7.0(005.12*A)\r\n"
    "!"
)
DSMR_EXPECTED = {
    "total_con": 5562,
    "total_con_t1": 2094,
    "total_con_t2": 3468,
    "w_con": 412,
    "total_prov": 100,
    "w_prov": 0,
    "reactive_total_con": 4419,
    "var_con": 8,
    "reactive_total_prov": 78814,
    "var_prov": 0,
    "u1": 230.1,
    "i1": 5.12,
}
DSMR_METER_ID = "KFM1200200012345"
DSMR_TIME_ISO = "2026-11-16T10:20:30+01:00"


def dsmr_telegram() -> bytes:
    body = DSMR_BODY.encode("ascii")
    return body + f"{crc16(body):04X}\r\n".encode("ascii")


def encrypted_dsmr(key: bytes = TEST_KEY) -> bytes:
    """Ciphered DSMR telegram as Sagemcom P1 ports send it (SC 0x30)."""
    return envelope(dsmr_telegram(), key, security_control=0x30)
