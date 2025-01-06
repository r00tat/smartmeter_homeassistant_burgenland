#!/usr/bin/env python3
import serial
import logging
from time import sleep
from collections.abc import Callable
import json

from ..dlms.read import parse_dlms_data, parse_pyhiscal_dlms_data, parse_xml
from ..bgld.data import MeterData

log = logging.getLogger("meter.serial.read")

PARITY_VALUES = serial.PARITY_NAMES.keys()
PARITY_NAME_VALUES = {v.upper(): k for k, v in serial.PARITY_NAMES.items()}

log.info("parity values: %s", ",".join(PARITY_VALUES))
log.info("parity name values: %s", json.dumps(PARITY_NAME_VALUES))


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
        callback: Callable[[MeterData], None] = None,
    ):
        """Create a meter reader"""
        self.key = key

        self.ser: serial.Serial = None
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        if self.parity not in PARITY_VALUES:
            self.parity = PARITY_NAME_VALUES.get(parity.upper(), serial.PARITY_NONE)
        self.stopbits = stopbits
        log.info(
            "serial port config: %s %s%s%s",
            self.port,
            self.baudrate,
            self.parity,
            self.stopbits,
        )
        self.is_optical_inteface = interface_type == "OPTICAL"

        self.should_run = True
        self.is_running = False
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
            self.port, self.baudrate, self.bytesize, self.parity, self.stopbits
        )

    def disconnect(self):
        """Disconnect from serial port"""
        if self.ser and not self.ser.closed:
            self.ser.close()

    def optical_loop(self):
        """Read data from serial port and parse it."""
        while self.should_run:
            received_data = self.ser.read()  # read serial port
            sleep(0.5)
            data_left = self.ser.inWaiting()  # check for remaining byte
            received_data += self.ser.read(data_left)
            log.debug("received: %s", received_data)
            decrypted_data = parse_dlms_data(received_data, self.key)
            log.debug("values: %s", decrypted_data.value)
            if decrypted_data.value:
                data = MeterData(decrypted_data.value)
                log.debug("received meter data: %s", data)
                if self.callback:
                    self.callback(data)

    def phyiscal_loop(self):
        """Read data from the pyhsical serial port and parse it."""
        while self.should_run:
            received_data = self.ser.read()
            sleep(0.5)
            data_left = self.ser.inWaiting()  # check for remaining byte
            received_data += self.ser.read(data_left)
            log.debug("received: %s", received_data)
            try:
                parsed_xml = parse_pyhiscal_dlms_data(received_data, self.key)
                log.debug("XML Result:\n%s", parsed_xml)
                if parsed_xml and len(parsed_xml) > 0:
                    values = parse_xml(parsed_xml)
                    if values and len(values) > 0:
                        data = MeterData(values)
                        log.debug("received meter data: %s", data)
                        if self.callback:
                            self.callback(data)
            except Exception as e:
                log.exception("failed to parse data from serial port: %s", e)

    def start(self):
        """Start the read process"""
        self.is_running = True
        self.connect()

        if self.is_optical_inteface:
            self.optical_loop()
        else:
            self.phyiscal_loop()

        self.is_running = False
        self.disconnect()

    def stop(self):
        """Stop the read process"""
        self.should_run = False
