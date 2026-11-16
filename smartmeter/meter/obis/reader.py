"""Serial reader for the OBIS profiles.

Thin shell around ``TelegramFramer`` and ``decode_unit``: open the port, feed
bytes to the framer, decode each unit, hand the result to the callback.
Faults reopen the port after a backoff instead of ending the thread, and
a periodic heartbeat says which layer is failing (no bytes, no frames,
no decodes).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic, sleep
from typing import Protocol

import serial

from .decode import decode_unit
from .framing import TelegramFramer
from .registers import ObisMeterData

log = logging.getLogger("meter.obis.reader")

_MAX_CONSECUTIVE_FAILURES = 10
_HEARTBEAT_SECONDS = 30.0
_RECONNECT_BACKOFF_SECONDS = 5.0
_READ_CHUNK = 256


class _SerialLike(Protocol):
    def read(self, size: int = 1) -> bytes: ...
    def close(self) -> None: ...


class ObisMeterReader:
    """Read framed, optionally encrypted push telegrams from a serial port."""

    def __init__(
        self,
        key_hex: str,
        framer_factory: Callable[[], TelegramFramer],
        port: str = "/dev/ttyUSB0",
        baudrate: int = 2400,
        bytesize: int = serial.EIGHTBITS,
        parity: str = serial.PARITY_EVEN,
        stopbits: int = serial.STOPBITS_ONE,
        timeout: float = 1.0,
        callback: Callable[[ObisMeterData], None] | None = None,
        serial_factory: Callable[[], _SerialLike] | None = None,
        monotonic: Callable[[], float] = monotonic,
    ) -> None:
        self.key = bytes.fromhex(key_hex) if key_hex else b""
        self.framer_factory = framer_factory
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.callback = callback
        self._serial_factory = serial_factory
        self.ser: _SerialLike | None = None
        self.should_run = True
        self.is_running = False
        self.reconnect_backoff_seconds = _RECONNECT_BACKOFF_SECONDS

        self._monotonic = monotonic
        self._bytes_read = 0
        self._units = 0
        self._decoded = 0
        self._failures = 0
        self._last_decoded_at: float | None = None
        self._last_heartbeat = 0.0

    def connect(self) -> None:
        if self._serial_factory is not None:
            self.ser = self._serial_factory()
            return
        log.info(
            "connecting to serial port %s with %s %s%s%s",
            self.port,
            self.baudrate,
            self.bytesize,
            self.parity,
            self.stopbits,
        )
        self.ser = serial.Serial(
            self.port,
            self.baudrate,
            self.bytesize,
            self.parity,
            self.stopbits,
            timeout=self.timeout,
        )

    def disconnect(self) -> None:
        if self.ser is not None:
            self.ser.close()
            self.ser = None

    def start(self) -> None:
        """Supervise the read loop, reconnecting on faults until stopped."""
        self.is_running = True
        self._last_heartbeat = self._monotonic()
        try:
            while self.should_run:
                try:
                    self.connect()
                    self._read_loop()
                except (serial.SerialException, OSError) as exc:
                    log.exception("serial port error on %s: %s", self.port, exc)
                finally:
                    self.disconnect()
                if self.should_run:
                    log.warning(
                        "reader interrupted, reconnecting in %.1fs",
                        self.reconnect_backoff_seconds,
                    )
                    sleep(self.reconnect_backoff_seconds)
        finally:
            self.is_running = False
            self.disconnect()

    def stop(self) -> None:
        self.should_run = False

    def _read_loop(self) -> None:
        assert self.ser is not None
        framer = self.framer_factory()
        failures = 0
        while self.should_run:
            self._maybe_heartbeat()
            waiting = getattr(self.ser, "in_waiting", 0) or 0
            chunk = self.ser.read(min(max(1, waiting), _READ_CHUNK))
            if not chunk:
                continue  # read timeout; the meter pushes every few seconds
            self._bytes_read += len(chunk)
            # Raw capture for reports of untested meters (see README).
            log.debug("raw bytes: %s", chunk.hex())
            for unit in framer.feed(chunk):
                self._units += 1
                if self._handle_unit(unit):
                    failures = 0
                    continue
                failures += 1
                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    log.error(
                        "exceeded %d consecutive failures, reconnecting",
                        _MAX_CONSECUTIVE_FAILURES,
                    )
                    return

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

    def _maybe_heartbeat(self) -> None:
        now = self._monotonic()
        if now - self._last_heartbeat < _HEARTBEAT_SECONDS:
            return
        self._last_heartbeat = now
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
