"""Minimal A-XDR decoder for DLMS data-notification APDUs.

Only decoding is needed (the customer interfaces are push-only), and only
the data types that appear in push telegrams. Values map to plain Python:

    structure / array      → list
    octet-string, bcd      → bytes
    visible / utf8-string  → str
    integers, enum         → int
    boolean                → bool
    float32 / float64      → float
    null-data              → None
    date-time / date / time→ bytes (raw, 12 / 5 / 4 bytes)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

DATA_NOTIFICATION_TAG = 0x0F
_DATETIME_LENGTH = 12

# tag → (struct format, size) for fixed-size numeric types
_FIXED: dict[int, tuple[str, int]] = {
    0x05: (">i", 4),  # double-long
    0x06: (">I", 4),  # double-long-unsigned
    0x0F: (">b", 1),  # integer
    0x10: (">h", 2),  # long
    0x11: (">B", 1),  # unsigned
    0x12: (">H", 2),  # long-unsigned
    0x14: (">q", 8),  # long64
    0x15: (">Q", 8),  # long64-unsigned
    0x16: (">B", 1),  # enum
    0x17: (">f", 4),  # float32
    0x18: (">d", 8),  # float64
}
# tag → raw length for fixed-size byte types
_RAW: dict[int, int] = {
    0x19: 12,  # date-time
    0x1A: 5,  # date
    0x1B: 4,  # time
}


class AxdrError(ValueError):
    """Raised when an APDU cannot be decoded."""


@dataclass(frozen=True)
class DataNotification:
    """A decoded data-notification APDU."""

    invoke_id: int
    timestamp: bytes | None  # 12-byte DLMS date-time, if the meter sent one
    body: Any


class _Cursor:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def take(self, size: int) -> bytes:
        end = self.pos + size
        if size < 0 or end > len(self.data):
            raise AxdrError(
                f"truncated APDU: need {size} bytes at offset {self.pos}, "
                f"have {len(self.data) - self.pos}"
            )
        chunk = self.data[self.pos : end]
        self.pos = end
        return chunk

    def byte(self) -> int:
        return self.take(1)[0]

    def length(self) -> int:
        """A-XDR / BER length: one byte < 0x80, or 0x8N followed by N bytes."""
        first = self.byte()
        if first < 0x80:
            return first
        size = first & 0x7F
        if size == 0 or size > 4:
            raise AxdrError(f"unsupported length encoding {first:#04x}")
        return int.from_bytes(self.take(size), "big")


def decode_length(data: bytes, offset: int) -> tuple[int, int]:
    """Return ``(length, offset after the length field)``."""
    cursor = _Cursor(data)
    cursor.pos = offset
    value = cursor.length()
    return value, cursor.pos


def _decode_value(cursor: _Cursor) -> Any:
    tag = cursor.byte()
    if tag == 0x00:
        return None
    if tag in (0x01, 0x02):  # array, structure
        count = cursor.length()
        return [_decode_value(cursor) for _ in range(count)]
    if tag == 0x03:
        return cursor.byte() != 0
    if tag == 0x04:  # bit-string, length in bits
        bits = cursor.length()
        return cursor.take((bits + 7) // 8)
    if tag in (0x09, 0x0D):  # octet-string, bcd
        return cursor.take(cursor.length())
    if tag in (0x0A, 0x0C):  # visible-string, utf8-string
        return cursor.take(cursor.length()).decode("utf-8", errors="replace")
    if tag in _FIXED:
        fmt, size = _FIXED[tag]
        return struct.unpack(fmt, cursor.take(size))[0]
    if tag in _RAW:
        return cursor.take(_RAW[tag])
    raise AxdrError(f"unsupported A-XDR tag {tag:#04x} at offset {cursor.pos - 1}")


def decode_data(data: bytes) -> Any:
    """Decode one A-XDR ``Data`` value (tag + content)."""
    cursor = _Cursor(data)
    return _decode_value(cursor)


def decode_data_notification(apdu: bytes) -> DataNotification:
    """Decode a DLMS data-notification APDU (tag 0x0F)."""
    if not apdu or apdu[0] != DATA_NOTIFICATION_TAG:
        first = f"{apdu[0]:#04x}" if apdu else "empty"
        raise AxdrError(f"not a data-notification APDU (starts with {first})")
    cursor = _Cursor(apdu)
    cursor.pos = 1
    invoke_id = int.from_bytes(cursor.take(4), "big")
    # date-time is an OPTIONAL octet-string: 0x00 = absent, else its length.
    ts_length = cursor.byte()
    timestamp: bytes | None = None
    if ts_length:
        if ts_length != _DATETIME_LENGTH:
            raise AxdrError(f"unexpected date-time length {ts_length}")
        timestamp = cursor.take(ts_length)
    body = _decode_value(cursor)
    return DataNotification(invoke_id=invoke_id, timestamp=timestamp, body=body)
