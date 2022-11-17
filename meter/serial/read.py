#!/usr/bin/env python3
import serial
import logging
from time import sleep
from typing import Callable

from ..dlms.read import parse_dlms_data
from ..bgld.data import MeterData

log = logging.getLogger("meter.serial.read")


class MeterReader():
    """
    read smart meter data and parse it
    """

    def __init__(self,
                 key: str,
                 port: str = "/dev/ttyUSB0",
                 baudrate=9600,
                 bytesize=serial.EIGHTBITS,
                 parity=serial.PARITY_NONE,
                 stopbits=serial.STOPBITS_ONE,
                 callback: Callable[[MeterData], None] = None):
        """create a meter reader"""
        self.key = key

        self.ser: serial.Serial = None
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits

        self.should_run = True
        self.is_running = False
        self.callback = callback

    def connect(self):
        """connect serial port"""
        log.info("connecting to serial port %s with %s%s%s", self.port,
                 self.baudrate,
                 "N" if self.parity == serial.PARITY_NONE else "Y",
                 self.stopbits)
        self.ser = serial.Serial(self.port, self.baudrate, self.bytesize,
                                 self.parity, self.stopbits)

    def disconnect(self):
        """disconnect from serial port"""
        if self.ser and not self.ser.closed:
            self.ser.close()

    def start(self):
        """start the read process"""
        self.is_running = True
        self.connect()
        while self.should_run:
            received_data = self.ser.read()  # read serial port
            sleep(0.5)
            data_left = self.ser.inWaiting()  # check for remaining byte
            received_data += self.ser.read(data_left)
            log.debug("received: %s", received_data)
            decrypted_data = parse_dlms_data(received_data, self.key)
            log.debug("values: %s", decrypted_data.value)
            if decrypted_data.value:
                data = MeterData(decrypted_data)
                log.info("received meter data: %s", data)
                if self.callback:
                    self.callback(data)

        self.is_running = False
        self.disconnect()

    def stop(self):
        """stop the read process"""
        self.should_run = False
