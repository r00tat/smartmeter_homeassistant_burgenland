#!/usr/bin/env python3
"""Manual test: print the readings of a Burgenland meter on /dev/ttyUSB0."""

import asyncio
import logging
import os

from smartmeter_austria.bgld.data import MeterData
from smartmeter_austria.profile import get_profile

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("smartmeter_austria.serial.test")


def reader_callback(data: MeterData) -> None:
    """Callback method for meter data."""
    log.info("reading: %s", data)


async def main() -> None:
    """Read until interrupted."""
    log.info("starting communication")
    config = {"dlms": {"key": os.environ["DLMS_ENCRYPTION_KEY"], "port": "/dev/ttyUSB0"}}
    reader = get_profile("burgenland").create_reader(config, reader_callback)
    await reader.run()


asyncio.run(main())
