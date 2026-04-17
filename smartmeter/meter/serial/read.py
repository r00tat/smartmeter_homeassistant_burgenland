#!/usr/bin/env python3
import serial
import logging
import struct
from time import sleep
from collections.abc import Callable

from gurux_dlms import GXDLMSException

from ..dlms.read import parse_dlms_data, parse_pyhiscal_dlms_data, parse_xml
from ..bgld.data import MeterData

MAX_CONSECUTIVE_FAILURES = 10
DEFAULT_SERIAL_TIMEOUT = 1.0

PARSE_ERRORS = (
    serial.SerialException,
    ValueError,
    struct.error,
    UnicodeDecodeError,
    IndexError,
    GXDLMSException,
)

log = logging.getLogger("meter.serial.read")

PARITY_VALUES = serial.PARITY_NAMES.keys()
PARITY_NAME_VALUES = {v.upper(): k for k, v in serial.PARITY_NAMES.items()}


class MeterReader:
    """Read smart meter data and parse it."""

    def __init__(
        self,
        key: str,
        port: str = "/dev/ttyUSB0",
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        interface_type="OPTICAL",
        hdlc_frame_size=120,
        timeout: float = DEFAULT_SERIAL_TIMEOUT,
        callback: Callable[[MeterData], None] = None,
    ):
        """Create a meter reader"""
        log.debug("parity values: %s", ",".join(PARITY_VALUES))
        log.debug("parity name values: %s", PARITY_NAME_VALUES)
        self.key = key

        self.ser: serial.Serial = None
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        if self.parity not in PARITY_VALUES:
            self.parity = PARITY_NAME_VALUES.get(parity.upper(), serial.PARITY_NONE)
        self.stopbits = stopbits
        self.timeout = timeout
        log.info(
            "serial port config: %s %s%s%s",
            self.port,
            self.baudrate,
            self.parity,
            self.stopbits,
        )
        self.is_optical_interface = interface_type == "OPTICAL"

        self.should_run = True
        self.is_running = False
        self.hdlc_frame_size = hdlc_frame_size
        self.callback = callback

    def connect(self):
        """Connect serial port"""
        log.info(
            "connecting to serial port %s with %s%s%s",
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

    def disconnect(self):
        """Disconnect from serial port"""
        if self.ser and not self.ser.closed:
            self.ser.close()

    def _read_frame(self, min_size: int) -> bytes:
        """Read at least ``min_size`` bytes (or a single byte for optical)."""
        received_data = self.ser.read()
        if min_size <= 1:
            sleep(0.5)
            data_left = self.ser.inWaiting()
            received_data += self.ser.read(data_left)
        else:
            while len(received_data) < min_size:
                sleep(0.5)
                data_left = self.ser.inWaiting()
                received_data += self.ser.read(data_left)
        return received_data

    def _handle_optical_frame(self, received_data: bytes) -> None:
        decrypted_data = parse_dlms_data(received_data, self.key)
        log.debug("values: %s", decrypted_data.value)
        if decrypted_data.value:
            data = MeterData(decrypted_data.value)
            log.debug("received meter data: %s", data)
            if self.callback:
                self.callback(data)

    def _handle_physical_frame(self, received_data: bytes) -> None:
        parsed_xml = parse_pyhiscal_dlms_data(received_data, self.key)
        log.debug("XML Result:\n%s", parsed_xml)
        if parsed_xml and len(parsed_xml) > 0:
            values = parse_xml(parsed_xml)
            if values and len(values) > 0:
                data = MeterData(values)
                log.debug("received meter data: %s", data)
                if self.callback:
                    self.callback(data)

    def _read_loop(self, handler: Callable[[bytes], None], frame_size: int) -> None:
        failures = 0
        while self.should_run:
            received_data = self._read_frame(frame_size)
            log.debug("received: %s", received_data)
            try:
                handler(received_data)
                failures = 0
            except KeyboardInterrupt:
                raise
            except PARSE_ERRORS as e:
                failures += 1
                log.exception("failed to parse data from serial port: %s", e)
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    log.error(
                        "exceeded %d consecutive parse failures, aborting",
                        MAX_CONSECUTIVE_FAILURES,
                    )
                    raise

    def optical_loop(self):
        """Read data from the optical interface and parse it."""
        self._read_loop(self._handle_optical_frame, 1)

    def physical_loop(self):
        """Read data from the physical serial port and parse it."""
        self._read_loop(self._handle_physical_frame, self.hdlc_frame_size)

    def start(self):
        """Start the read process"""
        self.is_running = True
        self.connect()

        if self.is_optical_interface:
            self.optical_loop()
        else:
            self.physical_loop()

        self.is_running = False
        self.disconnect()

    def stop(self):
        """Stop the read process"""
        self.should_run = False
