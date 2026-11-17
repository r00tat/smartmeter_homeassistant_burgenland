"""Serial reader for the OBIS profiles.

Thin shell around ``TelegramFramer`` and ``decode_unit``: open the port, feed
bytes to the framer, decode each unit, hand the result to the callback.
Reconnecting after a fault is the supervisor's job; a periodic heartbeat
says which layer is failing (no bytes, no frames, no decodes).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic

from ..serial.transport import (
    ByteStream,
    SerialSettings,
    StreamOpener,
    open_serial,
    periodically,
    read_some,
)
from .decode import decode_unit
from .framing import TelegramFramer
from .registers import ObisMeterData

log = logging.getLogger("meter.obis.reader")

MAX_CONSECUTIVE_FAILURES = 10
HEARTBEAT_SECONDS = 30.0


class ObisMeterReader:
    """Read framed, optionally encrypted push telegrams from a serial port."""

    def __init__(
        self,
        key_hex: str,
        framer_factory: Callable[[], TelegramFramer],
        settings: SerialSettings,
        callback: Callable[[ObisMeterData], None] | None = None,
        open_stream: StreamOpener = open_serial,
        monotonic: Callable[[], float] = monotonic,
    ) -> None:
        self.key = bytes.fromhex(key_hex) if key_hex else b""
        self.framer_factory = framer_factory
        self.settings = settings
        self.callback = callback
        self._open_stream = open_stream

        self._monotonic = monotonic
        self._bytes_read = 0
        self._units = 0
        self._decoded = 0
        self._failures = 0
        self._last_decoded_at: float | None = None

    async def run(self) -> None:
        """Read until cancelled; raise on a port error or repeated failures."""
        async with (
            self._open_stream(self.settings) as stream,
            periodically(HEARTBEAT_SECONDS, self.log_heartbeat),
        ):
            await self._read_loop(stream)

    async def _read_loop(self, stream: ByteStream) -> None:
        framer = self.framer_factory()
        failures = 0
        while True:
            chunk = await read_some(stream)
            self._bytes_read += len(chunk)
            # Raw capture for reports of untested meters (see README).
            log.debug("raw bytes: %s", chunk.hex())
            for unit in framer.feed(chunk):
                self._units += 1
                if self._handle_unit(unit):
                    failures = 0
                    continue
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    raise ValueError(
                        f"exceeded {MAX_CONSECUTIVE_FAILURES} consecutive "
                        "decode failures, reconnecting"
                    )

    def _handle_unit(self, unit: bytes) -> bool:
        log.debug("telegram (%d bytes): %s", len(unit), unit.hex())
        try:
            data = decode_unit(unit, self.key)
        except ValueError as exc:
            self._failures += 1
            log.warning("failed to decode telegram: %s", exc)
            return False
        self._decoded += 1
        self._last_decoded_at = self._monotonic()
        log.debug("decoded meter data: %s", data)
        if self.callback is not None:
            self.callback(data)
        return True

    def log_heartbeat(self) -> None:
        """Emit a stats line so a stalled run is diagnosable."""
        now = self._monotonic()
        age = (
            f"{now - self._last_decoded_at:.0f}s ago"
            if self._last_decoded_at is not None
            else "never"
        )
        log.info(
            "reader heartbeat — bytes:%d telegrams:%d decoded:%d failures:%d "
            "(last decoded: %s)",
            self._bytes_read,
            self._units,
            self._decoded,
            self._failures,
            age,
        )
        hint = self.diagnostic_hint()
        if hint:
            log.warning("reader diagnostic: %s", hint)

    def diagnostic_hint(self) -> str | None:
        """Map the counters to a likely root cause, or ``None``."""
        if self._decoded > 0:
            return None
        if self._bytes_read == 0:
            return "no bytes received — check wiring, serial port, baudrate and parity"
        if self._units == 0:
            return (
                "bytes received but no complete telegram — check baudrate/parity "
                "and the selected meter_type"
            )
        return "telegrams received but none decoded — check the decryption key"
