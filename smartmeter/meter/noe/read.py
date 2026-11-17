"""Serial reader for the Sagemcom T210-D (Netz NÖ / EVN) M-Bus interface.

The reader is a thin shell around the pure parsing logic in this
package:

    bytes → sync on ``68 LL LL 68`` → parse MBusFrame → AES-GCM decrypt
          → GXDLMSTranslator.pduToXml → OBIS dict → MeterData → callback

Only the byte-sync loop and error handling live here. Everything else is
unit-tested directly. Reconnecting after a fault is the supervisor's job.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic

from gurux_dlms import GXDLMSTranslator

from ..serial.transport import (
    ByteStream,
    SerialSettings,
    StreamOpener,
    open_serial,
    periodically,
    read_exactly,
)
from .data import MeterData
from .decrypt import DecryptionError, aes_gcm_decrypt
from .mbus import MBusFrame, MBusFrameError
from .obis import parse_obis_xml

log = logging.getLogger("meter.noe.read")

_START_BYTE = 0x68
_STOP_BYTE = 0x16
_MIN_FRAME_LENGTH = 27  # must fit system title and frame counter
MAX_CONSECUTIVE_FAILURES = 10
_DATA_NOTIFICATION_TAG = 0x0F
HEARTBEAT_SECONDS = 30.0  # how often to emit a reader stats line


class NoeMeterReader:
    """Read and decode M-Bus frames emitted by the Sagemcom T210-D."""

    def __init__(
        self,
        key_hex: str,
        settings: SerialSettings,
        callback: Callable[[MeterData], None] | None = None,
        open_stream: StreamOpener = open_serial,
        monotonic: Callable[[], float] = monotonic,
    ) -> None:
        self.key = bytes.fromhex(key_hex)
        self.settings = settings
        self.callback = callback
        self._open_stream = open_stream
        self._translator = GXDLMSTranslator()

        # Diagnostic counters surfaced in the periodic heartbeat so a failed
        # run produces actionable logs (no bytes vs. no sync vs. no decode).
        self._monotonic = monotonic
        self._bytes_read = 0
        self._sync_hits = 0
        self._frames_parsed = 0
        self._frames_decoded = 0
        self._frame_failures = 0
        self._last_frame_at: float | None = None

    async def run(self) -> None:
        """Read until cancelled; raise on a port error or repeated failures."""
        async with (
            self._open_stream(self.settings) as stream,
            periodically(HEARTBEAT_SECONDS, self.log_heartbeat),
        ):
            await self._read_loop(stream)

    async def _read_loop(self, stream: ByteStream) -> None:
        failures = 0
        while True:
            try:
                self._handle_frame(await self._read_frame(stream))
                failures = 0
            except (MBusFrameError, DecryptionError, ValueError) as exc:
                failures += 1
                self._frame_failures += 1
                log.exception("failed to handle frame: %s", exc)
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    log.error(
                        "exceeded %d consecutive failures, reconnecting",
                        MAX_CONSECUTIVE_FAILURES,
                    )
                    raise

    async def _read_frame(self, stream: ByteStream) -> bytes:
        """Synchronise on the next M-Bus long frame and return its bytes."""
        # Scan byte-by-byte until we see ``68 LL LL 68`` so we recover from
        # mid-frame re-connects and the occasional sync byte on the wire.
        header = bytearray()
        while not (
            len(header) == 4
            and header[0] == _START_BYTE
            and header[3] == _START_BYTE
            and header[1] == header[2]
            and header[1] >= _MIN_FRAME_LENGTH
        ):
            header += await read_exactly(stream, 1)
            self._bytes_read += 1
            if len(header) > 4:
                header.pop(0)

        self._sync_hits += 1
        length = header[1]
        log.debug("synced on M-Bus long frame, user-data length %d", length)
        body = await read_exactly(stream, length + 2)  # user data + CS + stop byte
        self._bytes_read += len(body)
        if body[-1] != _STOP_BYTE:
            raise MBusFrameError(f"missing trailer byte 0x16, got {body[-1]:#04x}")
        return bytes(header) + body

    def _handle_frame(self, raw_frame: bytes) -> None:
        log.debug("raw frame (%d bytes): %s", len(raw_frame), raw_frame.hex())
        parsed = MBusFrame.parse(raw_frame.hex())
        self._frames_parsed += 1
        nonce = parsed.system_title + parsed.frame_counter
        apdu = aes_gcm_decrypt(parsed.ciphertext, self.key, nonce)
        if not apdu or apdu[0] != _DATA_NOTIFICATION_TAG:
            # Wrong key produces garbage here (the on-wire layout omits the
            # GCM tag, so decryption itself cannot fail) — the heartbeat's
            # "frames but no decodes" hint points at the key.
            log.debug(
                "apdu does not start with data-notification tag 0x0F "
                "(got %s), skipping — check the decryption key",
                f"{apdu[0]:#04x}" if apdu else "empty",
            )
            return
        xml = self._translator.pduToXml(apdu.hex())
        obis_values = parse_obis_xml(xml)
        data = MeterData(obis_values)
        self._frames_decoded += 1
        self._last_frame_at = self._monotonic()
        log.debug("decoded meter data: %s", data)
        if self.callback is not None:
            self.callback(data)

    def log_heartbeat(self) -> None:
        """Emit a stats line so a stalled run is diagnosable."""
        now = self._monotonic()
        if self._last_frame_at is not None:
            age = f"{now - self._last_frame_at:.0f}s ago"
        else:
            age = "never"
        log.info(
            "reader heartbeat — bytes:%d syncs:%d frames:%d decoded:%d "
            "failures:%d (last frame: %s)",
            self._bytes_read,
            self._sync_hits,
            self._frames_parsed,
            self._frames_decoded,
            self._frame_failures,
            age,
        )
        hint = self.diagnostic_hint()
        if hint:
            log.warning("reader diagnostic: %s", hint)

    def diagnostic_hint(self) -> str | None:
        """Map the current counters to a likely root cause, or ``None``."""
        if self._frames_decoded > 0:
            return None
        if self._bytes_read == 0:
            return (
                "no bytes received — check wiring, serial port, baudrate "
                "and parity"
            )
        if self._sync_hits == 0:
            return (
                "bytes received but no M-Bus frame sync (68 LL LL 68) — "
                "check baudrate/parity and that this is a Sagemcom T210-D"
            )
        return (
            "frames received but none decoded — check the decryption key"
        )
