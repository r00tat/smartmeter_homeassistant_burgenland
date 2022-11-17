#!/usr/bin/env python3
import os
import logging

from .read import MeterReader
from ..bgld.data import MeterData

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("meter.serial.test")

log.info("starting communication")

key = os.environ['DLMS_ENCRYPTION_KEY']


def reader_callback(data: MeterData):
    """callback for meter data"""
    pass


try:
    reader = MeterReader(key, "/dev/ttyUSB0", callback=reader_callback)

    reader.start()

finally:
    reader.disconnect()