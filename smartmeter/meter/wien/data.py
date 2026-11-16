"""Decoded data notification of a Wiener Netze smart meter.

Wiener Netze meters (Siemens IM150/IM350/IM351, Iskraemeco AM550,
Landis+Gyr E450) push a DLMS data notification every second over the
infrared customer interface. Unlike Burgenland and NÖ, it carries no OBIS
codes, units or scalers, just a structure in a fixed order:

    [serial number]  octet-string, 16 ASCII chars (not sent by every meter)
    timestamp        octet-string, 12 byte DLMS date-time
    +A  active energy imported     uint32, Wh    (1-0:1.8.0)
    -A  active energy exported     uint32, Wh    (1-0:2.8.0)
    +R  reactive energy imported   uint32, varh  (1-0:3.8.0)
    -R  reactive energy exported   uint32, varh  (1-0:4.8.0)
    +P  active power imported      uint32, W     (1-0:1.7.0)
    -P  active power exported      uint32, W     (1-0:2.7.0)
    +Q  reactive power imported    uint32, var   (1-0:3.7.0)
    -Q  reactive power exported    uint32, var   (1-0:4.7.0)

Layout taken from https://www.wienernetze.at/smart-meter-kundenschnittstelle
and the MIT-licensed readers bernikr/esphome-wienernetze-smartmeter and
tofuSCHNITZEL/wiener-netze-smartmeter-serial.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..meter_data import BaseMeterData

_VALUE_COUNT = 8
_DLMS_DATETIME_LENGTH = 12
_DEVIATION_UNSPECIFIED = -0x8000


def _is_number(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_dlms_datetime(raw: bytes | bytearray) -> str | None:
    """Return a 12-byte DLMS date-time as ISO 8601 string, or ``None``."""
    if len(raw) != _DLMS_DATETIME_LENGTH:
        return None
    year = int.from_bytes(raw[0:2], "big")
    month, day = raw[2], raw[3]
    hour, minute, second = raw[5], raw[6], raw[7]
    deviation = int.from_bytes(raw[9:11], "big", signed=True)
    try:
        if deviation == _DEVIATION_UNSPECIFIED:
            return datetime(year, month, day, hour, minute, second).isoformat()
        # DLMS defines deviation as UTC minus local time, in minutes.
        tz = timezone(timedelta(minutes=-deviation))
        return datetime(year, month, day, hour, minute, second, tzinfo=tz).isoformat()
    except ValueError:
        # Not-specified fields (0xFF) or garbage: leave the timestamp out.
        return None


class MeterData(BaseMeterData):
    """Wiener Netze reading built from the decoded notification structure."""

    def __init__(self, values: list[Any]):
        self.values = values
        numbers = [v for v in values if _is_number(v)]
        others = [v for v in values if not _is_number(v)]
        if len(numbers) != _VALUE_COUNT:
            raise ValueError(
                f"expected {_VALUE_COUNT} counter values in a Wiener Netze "
                f"notification, got {len(numbers)}: {values!r}"
            )

        (
            self.total_consumed,
            self.total_provided,
            self.reactive_total_consumed,
            self.reactive_total_provided,
            self.power_consumed,
            self.power_provided,
            self.reactive_power_consumed,
            self.reactive_power_provided,
        ) = numbers

        self.meter_id: str | None = None
        self.meter_time: str | None = None
        # Leading octet strings: optional serial number, then the timestamp.
        if len(others) >= 2:
            self.meter_id = _to_text(others[0])
        if others:
            self.meter_time = _to_timestamp(others[-1])

    def __str__(self) -> str:
        return (
            "MeterData["
            f"P({self.power_consumed}W,-{self.power_provided}W),"
            f"Q({self.reactive_power_consumed}var,-{self.reactive_power_provided}var),"
            f"W({self.total_consumed}Wh,-{self.total_provided}Wh),"
            f"R({self.reactive_total_consumed}varh,-{self.reactive_total_provided}varh),"
            f"t({self.meter_time})"
            "]"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "w_con": self.power_consumed,
            "w_prov": self.power_provided,
            "total_con": self.total_consumed,
            "total_prov": self.total_provided,
            "var_con": self.reactive_power_consumed,
            "var_prov": self.reactive_power_provided,
            "reactive_total_con": self.reactive_total_consumed,
            "reactive_total_prov": self.reactive_total_provided,
            "meter_time": self.meter_time,
        }


def _to_text(value: Any) -> str | None:
    if isinstance(value, (bytes, bytearray)):
        text = bytes(value).decode("ascii", errors="replace").strip("\x00 ")
        return text or None
    return str(value) if value is not None else None


def _to_timestamp(value: Any) -> str | None:
    if isinstance(value, (bytes, bytearray)):
        return parse_dlms_datetime(value)
    # gurux may already hand over a GXDateTime; its str() is readable.
    return str(value) if value is not None else None
