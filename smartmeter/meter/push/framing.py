"""Cut a serial byte stream into application units.

A *unit* is what the decoder works on: a ciphered APDU (``DB …``), a
plain APDU (``0F …``) or a DSMR telegram (``/ … !CRC``). ``PushFramer``
scans for the start bytes of the transports a profile enables:

- ``mbus``  — wired M-Bus long frames (``68 L L 68 … CS 16``) with the
  DLMS/COSEM M-Bus transport layer (EN 13757-3, Green Book 10.5.4.6):
  ``CI STSAP DTSAP`` followed by up to 250 bytes of DLMS data. Bit 4 of
  CI marks the last segment, bits 0–3 count the segments (TINETZ,
  Salzburg Netz: ``CI=00`` then ``CI=11`` for a two-part message).
- ``hdlc``  — HDLC frames (``7E A0 LL … FCS 7E``), optionally segmented
  (S bit) and carrying DLMS general-block-transfer blocks (``E0 …``) as
  sent by the Landis+Gyr E450 at Energienetze Steiermark.
- ``p1``    — raw ciphered APDUs and plain DSMR text telegrams on a P1
  port (Smart Meter 2.0 H1, Sagemcom at Energienetze Steiermark).

Frames with a bad checksum are dropped and the scan resynchronises on
the next start byte, so a reader can attach mid-telegram.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .axdr import AxdrError, decode_length
from .cipher import GLO_CIPHERING_TAGS, CipherError, envelope_size
from .dsmr import telegram_end

log = logging.getLogger("meter.push.framing")

_MBUS_START = 0x68
_MBUS_STOP = 0x16
_MBUS_MIN_LENGTH = 5  # C, A, CI, STSAP, DTSAP
_CI_FIN = 0x10
_CI_SEGMENT_MASK = 0x0F
_CI_DATA_HEADER_MASK = 0xE0

_HDLC_FLAG = 0x7E
_HDLC_FORMAT_MASK = 0xF0
_HDLC_FORMAT_TYPE3 = 0xA0
_HDLC_SEGMENTED = 0x08
_LLC_PREFIXES = (b"\xe6\xe7\x00", b"\xe6\xe6\x00")
_GBT_TAG = 0xE0
_GBT_LAST_BLOCK = 0x80

_DSMR_START = ord("/")
_MAX_UNIT_SIZE = 8192
_MAX_BUFFER = 4 * _MAX_UNIT_SIZE


def hdlc_fcs(data: bytes) -> int:
    """HDLC FCS-16 (CRC-16/X-25)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


class _NeedMore(Exception):
    """Not enough bytes buffered to decide."""


class _Invalid(Exception):
    """The candidate at the buffer start is not a valid frame."""


@dataclass
class PushFramer:
    """Stateful framer; feed it bytes, get complete units back."""

    mbus: bool = False
    hdlc: bool = False
    p1: bool = False
    _buffer: bytearray = field(default_factory=bytearray)
    _segments: list[bytes] = field(default_factory=list)
    _next_segment: int = 0
    _hdlc_pending: bytearray = field(default_factory=bytearray)
    _gbt_pending: bytearray = field(default_factory=bytearray)
    _gbt_next_block: int = 0
    dropped_bytes: int = 0
    frames: int = 0

    def __post_init__(self) -> None:
        starts: set[int] = set()
        if self.mbus:
            starts.add(_MBUS_START)
        if self.hdlc:
            starts.add(_HDLC_FLAG)
        if self.p1:
            starts.update(GLO_CIPHERING_TAGS)
            starts.add(_DSMR_START)
        if not starts:
            raise ValueError("enable at least one transport")
        self._starts = frozenset(starts)

    def feed(self, data: bytes) -> list[bytes]:
        self._buffer += data
        units: list[bytes] = []
        while self._buffer:
            if self._buffer[0] not in self._starts:
                self._drop(1)
                continue
            try:
                consumed, unit = self._try_frame()
            except _NeedMore:
                if len(self._buffer) > _MAX_BUFFER:
                    self._drop(1)
                    continue
                break
            except _Invalid:
                self._drop(1)
                continue
            del self._buffer[:consumed]
            self.frames += 1
            if unit is not None:
                units.append(unit)
        return units

    def _drop(self, count: int) -> None:
        del self._buffer[:count]
        self.dropped_bytes += count

    def _try_frame(self) -> tuple[int, bytes | None]:
        first = self._buffer[0]
        if first == _MBUS_START and self.mbus:
            return self._mbus_frame()
        if first == _HDLC_FLAG and self.hdlc:
            return self._hdlc_frame()
        if first in GLO_CIPHERING_TAGS and self.p1:
            return self._envelope()
        if first == _DSMR_START and self.p1:
            return self._dsmr()
        raise _Invalid

    # --- M-Bus -----------------------------------------------------------

    def _mbus_frame(self) -> tuple[int, bytes | None]:
        buf = self._buffer
        if len(buf) < 4:
            raise _NeedMore
        length = buf[1]
        if buf[3] != _MBUS_START or buf[2] != length or length < _MBUS_MIN_LENGTH:
            raise _Invalid
        total = length + 6
        if len(buf) < total:
            raise _NeedMore
        user = bytes(buf[4 : 4 + length])
        if buf[total - 1] != _MBUS_STOP or sum(user) & 0xFF != buf[total - 2]:
            raise _Invalid
        ci = user[2]
        if ci & _CI_DATA_HEADER_MASK:
            log.debug("skipping M-Bus frame with CI %#04x (no DLMS transport)", ci)
            return total, None
        payload = user[5:]
        segment = ci & _CI_SEGMENT_MASK
        if segment == 0:
            if self._segments:
                log.debug("discarding %d incomplete M-Bus segments", len(self._segments))
            self._segments = []
        elif segment != self._next_segment:
            log.debug("M-Bus segment %d out of order, discarding message", segment)
            self._segments = []
            self._next_segment = 0
            return total, None
        self._segments.append(payload)
        self._next_segment = segment + 1
        if not ci & _CI_FIN:
            return total, None
        unit = b"".join(self._segments)
        self._segments = []
        self._next_segment = 0
        return total, unit

    # --- HDLC ------------------------------------------------------------

    def _hdlc_frame(self) -> tuple[int, bytes | None]:
        buf = self._buffer
        if len(buf) < 3:
            raise _NeedMore
        if buf[1] == _HDLC_FLAG:
            # Two flags back to back (end of one frame, start of the next).
            return 1, None
        if buf[1] & _HDLC_FORMAT_MASK != _HDLC_FORMAT_TYPE3:
            raise _Invalid
        length = ((buf[1] & 0x07) << 8) | buf[2]
        total = length + 2
        if length < 7:
            raise _Invalid
        if len(buf) < total:
            raise _NeedMore
        frame = bytes(buf[1 : total - 1])
        if buf[total - 1] != _HDLC_FLAG:
            raise _Invalid
        fcs = int.from_bytes(frame[-2:], "little")
        if hdlc_fcs(frame[:-2]) != fcs:
            raise _Invalid
        info = self._hdlc_information(frame)
        segmented = bool(frame[0] & _HDLC_SEGMENTED)
        # A segmented frame leaves the closing flag for the next frame.
        consumed = total - 1 if segmented else total
        self._hdlc_pending += info
        if segmented:
            return consumed, None
        information = bytes(self._hdlc_pending)
        self._hdlc_pending.clear()
        for prefix in _LLC_PREFIXES:
            if information.startswith(prefix):
                information = information[len(prefix) :]
                break
        return consumed, self._block_transfer(information)

    @staticmethod
    def _hdlc_information(frame: bytes) -> bytes:
        """Information field of a frame without flags (format … FCS)."""
        pos = 2
        for _ in range(2):  # destination, then source address
            while pos < len(frame) - 2 and not frame[pos] & 0x01:
                pos += 1
            pos += 1
        pos += 1  # control
        if pos >= len(frame) - 2:
            return b""  # no information field, no HCS
        pos += 2  # HCS
        return frame[pos:-2]

    def _block_transfer(self, apdu: bytes) -> bytes | None:
        """Reassemble general-block-transfer blocks; pass other APDUs on."""
        if not apdu or apdu[0] != _GBT_TAG:
            return apdu or None
        try:
            length, offset = decode_length(apdu, 6)
        except AxdrError:
            log.debug("malformed general-block-transfer block, discarding")
            self._gbt_pending.clear()
            return None
        block_number = int.from_bytes(apdu[2:4], "big")
        if block_number == 1:
            self._gbt_pending.clear()
        elif block_number != self._gbt_next_block:
            # A block went missing: the message cannot be completed.
            if self._gbt_pending:
                log.debug("general-block-transfer block %d out of order", block_number)
            self._gbt_pending.clear()
            self._gbt_next_block = 0
            return None
        self._gbt_next_block = block_number + 1
        self._gbt_pending += apdu[offset : offset + length]
        if not apdu[1] & _GBT_LAST_BLOCK:
            return None
        unit = bytes(self._gbt_pending)
        self._gbt_pending.clear()
        self._gbt_next_block = 0
        return unit

    # --- P1 --------------------------------------------------------------

    def _envelope(self) -> tuple[int, bytes | None]:
        try:
            size = envelope_size(bytes(self._buffer[:16]))
        except CipherError:
            raise _Invalid from None
        if size is None:
            raise _NeedMore
        if size > _MAX_UNIT_SIZE:
            raise _Invalid
        if len(self._buffer) < size:
            raise _NeedMore
        return size, bytes(self._buffer[:size])

    def _dsmr(self) -> tuple[int, bytes | None]:
        end = telegram_end(bytes(self._buffer))
        if end is None:
            if len(self._buffer) > _MAX_UNIT_SIZE:
                raise _Invalid
            raise _NeedMore
        return end, bytes(self._buffer[:end])
