"""Serial reader for the Sagemcom T210-D (Netz NÖ / EVN) M-Bus interface.

The reader is a thin shell around the pure parsing logic in this
package:

    bytes → sync on ``68 LL LL 68`` → parse MBusFrame → AES-GCM decrypt
          → GXDLMSTranslator.pduToXml → OBIS dict → MeterData → callback

Only the byte-sync loop and error-recovery handling live here. Everything
else is unit-tested directly.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic, sleep
from typing import Protocol

import serial
from gurux_dlms import GXDLMSTranslator

from .data import MeterData
from .decrypt import DecryptionError, aes_gcm_decrypt
from .mbus import MBusFrame, MBusFrameError
from .obis import parse_obis_xml

log = logging.getLogger("meter.noe.read")

_START_BYTE = 0x68
_STOP_BYTE = 0x16
_MIN_FRAME_LENGTH = 27  # must fit system title and frame counter
_MAX_CONSECUTIVE_FAILURES = 10
_DATA_NOTIFICATION_TAG = 0x0F
_HEARTBEAT_SECONDS = 30.0  # how often to emit a reader stats line
_RECONNECT_BACKOFF_SECONDS = 5.0  # wait before reopening the port after a fault

_PARITY_LETTERS = serial.PARITY_NAMES.keys()
_PARITY_NAME_TO_LETTER = {v.upper(): k for k, v in serial.PARITY_NAMES.items()}


class _SerialLike(Protocol):
    def read(self, size: int = 1) -> bytes: ...
    def close(self) -> None: ...


class NoeMeterReader:
    """Read and decode M-Bus frames emitted by the Sagemcom T210-D."""

    def __init__(
        self,
        key_hex: str,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 2400,
        bytesize: int = serial.EIGHTBITS,
        parity: str = serial.PARITY_NONE,
        stopbits: int = serial.STOPBITS_ONE,
        timeout: float = 1.0,
        callback: Callable[[MeterData], None] | None = None,
        serial_factory: Callable[[], _SerialLike] | None = None,
        monotonic: Callable[[], float] = monotonic,
    ) -> None:
        self.key = bytes.fromhex(key_hex)
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        # Config supplies human-readable names ("NONE"); pyserial wants the
        # single-letter codes ("N"). Normalise, falling back to no parity.
        self.parity = parity
        if self.parity not in _PARITY_LETTERS:
            self.parity = _PARITY_NAME_TO_LETTER.get(
                str(parity).upper(), serial.PARITY_NONE
            )
        self.stopbits = stopbits
        self.timeout = timeout
        self.callback = callback
        self._serial_factory = serial_factory
        self._translator = GXDLMSTranslator()
        self.ser: _SerialLike | None = None
        self.should_run = True
        self.is_running = False
        self.reconnect_backoff_seconds = _RECONNECT_BACKOFF_SECONDS

        # Diagnostic counters surfaced in the periodic heartbeat so a failed
        # run produces actionable logs (no bytes vs. no sync vs. no decode).
        self._monotonic = monotonic
        self._bytes_read = 0
        self._sync_hits = 0
        self._frames_parsed = 0
        self._frames_decoded = 0
        self._frame_failures = 0
        self._last_frame_at: float | None = None
        self._last_heartbeat = 0.0

    def connect(self) -> None:
        if self._serial_factory is not None:
            self.ser = self._serial_factory()
            return
        log.info(
            "connecting to serial port %s with %s %s%s",
            self.port,
            self.baudrate,
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
        """Supervise the read loop, reconnecting on faults until stopped.

        A serial fault or a burst of frame failures no longer kills the
        thread (and with it the whole add-on): the port is reopened after a
        short backoff and reading resumes. Only ``stop()`` ends the loop.
        """
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
        failures = 0
        while self.should_run:
            self._maybe_heartbeat()
            frame = self._read_frame()
            if frame is None:
                # Only reached on shutdown (``should_run`` cleared).
                return
            try:
                self._handle_frame(frame)
                failures = 0
            except (MBusFrameError, DecryptionError, ValueError) as exc:
                failures += 1
                self._frame_failures += 1
                log.exception("failed to handle frame: %s", exc)
                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    # Return (not raise) so ``start()`` reconnects instead of
                    # tearing the thread — and the whole app — down.
                    log.error(
                        "exceeded %d consecutive failures, reconnecting",
                        _MAX_CONSECUTIVE_FAILURES,
                    )
                    return

    def _read_frame(self) -> bytes | None:
        """Synchronise on the next M-Bus long frame and return its bytes."""
        assert self.ser is not None
        # Scan byte-by-byte until we see ``68 LL LL 68`` so we recover from
        # mid-frame re-connects and the occasional sync byte on the wire.
        header = bytearray()
        while self.should_run:
            byte = self.ser.read(1)
            if not byte:
                # Empty read is a serial *timeout* (no byte arrived within
                # ``self.timeout``), not end-of-stream. The meter pushes a
                # frame only every few seconds, so keep waiting instead of
                # tearing the reader down and shutting the whole app off.
                self._maybe_heartbeat()
                continue
            self._bytes_read += len(byte)
            header += byte
            if len(header) > 4:
                header.pop(0)
            if (
                len(header) == 4
                and header[0] == _START_BYTE
                and header[3] == _START_BYTE
                and header[1] == header[2]
                and header[1] >= _MIN_FRAME_LENGTH
            ):
                break
        else:
            return None

        self._sync_hits += 1
        length = header[1]
        log.debug("synced on M-Bus long frame, user-data length %d", length)
        remaining = length + 2  # user data + CS + stop byte
        body = bytearray()
        while self.should_run and len(body) < remaining:
            chunk = self.ser.read(remaining - len(body))
            if not chunk:
                # Timeout mid-frame; keep reading until the rest arrives.
                continue
            self._bytes_read += len(chunk)
            body += chunk
        if len(body) < remaining:
            # Loop only exits short when ``should_run`` flipped (shutdown).
            return None
        if body[-1] != _STOP_BYTE:
            raise MBusFrameError(f"missing trailer byte 0x16, got {body[-1]:#04x}")
        return bytes(header) + bytes(body)

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

    def _maybe_heartbeat(self) -> None:
        """Emit a periodic stats line so a stalled run is diagnosable."""
        now = self._monotonic()
        if now - self._last_heartbeat < _HEARTBEAT_SECONDS:
            return
        self._last_heartbeat = now
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
        hint = self._diagnostic_hint()
        if hint:
            log.warning("reader diagnostic: %s", hint)

    def _diagnostic_hint(self) -> str | None:
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
