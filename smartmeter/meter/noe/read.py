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
from time import sleep
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
    ) -> None:
        self.key = bytes.fromhex(key_hex)
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.callback = callback
        self._serial_factory = serial_factory
        self._translator = GXDLMSTranslator()
        self.ser: _SerialLike | None = None
        self.should_run = True
        self.is_running = False

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
        self.is_running = True
        self.connect()
        try:
            self._read_loop()
        finally:
            self.is_running = False
            self.disconnect()

    def stop(self) -> None:
        self.should_run = False

    def _read_loop(self) -> None:
        assert self.ser is not None
        failures = 0
        while self.should_run:
            frame = self._read_frame()
            if frame is None:
                # EOF or stopped
                return
            try:
                self._handle_frame(frame)
                failures = 0
            except (MBusFrameError, DecryptionError, ValueError) as exc:
                failures += 1
                log.exception("failed to handle frame: %s", exc)
                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    log.error(
                        "exceeded %d consecutive failures, aborting",
                        _MAX_CONSECUTIVE_FAILURES,
                    )
                    raise

    def _read_frame(self) -> bytes | None:
        """Synchronise on the next M-Bus long frame and return its bytes."""
        assert self.ser is not None
        # Scan byte-by-byte until we see ``68 LL LL 68`` so we recover from
        # mid-frame re-connects and the occasional sync byte on the wire.
        header = bytearray()
        while self.should_run:
            byte = self.ser.read(1)
            if not byte:
                return None
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

        length = header[1]
        remaining = length + 2  # user data + CS + stop byte
        body = bytearray()
        while self.should_run and len(body) < remaining:
            chunk = self.ser.read(remaining - len(body))
            if not chunk:
                return None
            body += chunk
        if len(body) < remaining:
            return None
        if body[-1] != _STOP_BYTE:
            raise MBusFrameError(f"missing trailer byte 0x16, got {body[-1]:#04x}")
        return bytes(header) + bytes(body)

    def _handle_frame(self, raw_frame: bytes) -> None:
        parsed = MBusFrame.parse(raw_frame.hex())
        nonce = parsed.system_title + parsed.frame_counter
        apdu = aes_gcm_decrypt(parsed.ciphertext, self.key, nonce)
        if not apdu or apdu[0] != _DATA_NOTIFICATION_TAG:
            log.debug(
                "apdu does not start with data-notification tag 0x0F, skipping"
            )
            return
        xml = self._translator.pduToXml(apdu.hex())
        obis_values = parse_obis_xml(xml)
        data = MeterData(obis_values)
        log.debug("decoded meter data: %s", data)
        if self.callback is not None:
            self.callback(data)

    SHUTDOWN_GRACE_SECONDS = 2.5

    def recover(self) -> None:
        """Match the reference script's sleep-and-reopen recovery."""
        log.warning("recovering serial port after failure")
        self.disconnect()
        sleep(self.SHUTDOWN_GRACE_SECONDS)
        self.connect()
