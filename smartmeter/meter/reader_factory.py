"""Instantiate the correct serial reader for a given meter profile."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import serial

from .noe.read import NoeMeterReader
from .profile import MeterProfile
from .serial.read import MeterReader as SerialMeterReader


def _dlms(config: dict) -> dict:
    return config.get("dlms") or {}


def build_reader(
    config: dict,
    profile: MeterProfile,
    callback: Callable[[Any], None],
) -> SerialMeterReader | NoeMeterReader:
    """Return a reader instance configured for ``profile``.

    Baudrate defaults come from the profile and are overridden by any
    explicit ``dlms.baudrate`` value in the user config.
    """
    dlms = _dlms(config)
    port = dlms.get("port", "/dev/ttyUSB0")
    baudrate = dlms.get("baudrate", profile.default_baudrate)
    parity = dlms.get("parity", serial.PARITY_NONE)
    bytesize = dlms.get("bytesize", serial.EIGHTBITS)
    stopbits = dlms.get("stopbits", serial.STOPBITS_ONE)
    timeout = dlms.get("timeout", 1.0)
    key = dlms.get("key") or ""

    if profile.name == "noe_evn":
        return NoeMeterReader(
            key_hex=key,
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=timeout,
            callback=callback,
        )

    return SerialMeterReader(
        key=key,
        port=port,
        baudrate=baudrate,
        bytesize=bytesize,
        parity=parity,
        stopbits=stopbits,
        interface_type=config.get("interface_type", "OPTICAL"),
        hdlc_frame_size=dlms.get("hdlc_frame_size", 120),
        timeout=timeout,
        callback=callback,
    )
