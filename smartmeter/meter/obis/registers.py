"""Turn decoded telegrams into OBIS registers and ``ObisMeterData``.

Unlike Burgenland and Wien, the meters handled here name every value by
its OBIS code, so one mapping serves all of them. Two layouts occur in a
data-notification body, both handled by ``registers_from_notification``:

- Kaifa / Honeywell (Salzburg Netz, TINETZ)::

      structure { clock, OBIS, value, {scaler, unit}, OBIS, value, {…}, … }

- Landis+Gyr E450 (Energienetze Steiermark)::

      structure { clock, OBIS, value, OBIS, value, … }        (no scalers)
"""

from __future__ import annotations

import string
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from ..meter_data import BaseMeterData
from ..wien.data import parse_dlms_datetime
from .axdr import DataNotification
from .dsmr import DsmrValue

# OBIS code (A-B:C.D.E, without F) → key in the published JSON.
FIELD_BY_OBIS: dict[str, str] = {
    "1-0:32.7.0": "u1",
    "1-0:52.7.0": "u2",
    "1-0:72.7.0": "u3",
    "1-0:31.7.0": "i1",
    "1-0:51.7.0": "i2",
    "1-0:71.7.0": "i3",
    "1-0:1.7.0": "w_con",
    "1-0:2.7.0": "w_prov",
    "1-0:3.7.0": "var_con",
    "1-0:4.7.0": "var_prov",
    "1-0:1.8.0": "total_con",
    "1-0:2.8.0": "total_prov",
    "1-0:1.8.1": "total_con_t1",
    "1-0:1.8.2": "total_con_t2",
    "1-0:2.8.1": "total_prov_t1",
    "1-0:2.8.2": "total_prov_t2",
    "1-0:3.8.0": "reactive_total_con",
    "1-0:4.8.0": "reactive_total_prov",
    "1-0:13.7.0": "power_factor",
}
FIELDS: tuple[str, ...] = tuple(dict.fromkeys(FIELD_BY_OBIS.values()))

_METER_ID_OBIS = ("0-0:96.1.0", "0-0:96.1.1")
_DEVICE_NAME_OBIS = "0-0:42.0.0"
_CLOCK_OBIS = "0-0:1.0.0"
_OBIS_LENGTH = 6
_DATETIME_LENGTH = 12
_PRINTABLE = set(string.printable) - set("\t\n\r\x0b\x0c")


def obis_to_str(raw: bytes) -> str:
    """``0100010800FF`` → ``1-0:1.8.0`` (group F is always 255 here)."""
    a, b, c, d, e, _f = raw
    return f"{a}-{b}:{c}.{d}.{e}"


def _scaled(value: int, scaler: int) -> int | float:
    if scaler == 0:
        return value
    result = Decimal(value).scaleb(scaler)
    return int(result) if result == result.to_integral_value() else float(result)


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip("\x00 ") or None
    if isinstance(value, (bytes, bytearray)):
        text = bytes(value).decode("ascii", errors="replace").strip("\x00 ")
        if text and set(text) <= _PRINTABLE:
            return text
        return bytes(value).hex().upper() or None
    return None


def _is_scaler_unit(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    )


def _is_obis(value: Any) -> bool:
    return isinstance(value, (bytes, bytearray)) and len(value) == _OBIS_LENGTH


def _walk(items: list[Any], found: list[tuple[str, Any]], loose: list[Any]) -> None:
    i = 0
    while i < len(items):
        item = items[i]
        if _is_obis(item) and i + 1 < len(items) and not isinstance(items[i + 1], list):
            obis = obis_to_str(bytes(item))
            value = items[i + 1]
            i += 2
            if i < len(items) and _is_scaler_unit(items[i]):
                scaler = items[i][0]
                i += 1
                if isinstance(value, int) and not isinstance(value, bool):
                    value = _scaled(value, scaler)
            found.append((obis, value))
        elif isinstance(item, list):
            _walk(item, found, loose)
            i += 1
        else:
            loose.append(item)
            i += 1


class ObisMeterData(BaseMeterData):
    """A reading keyed by OBIS code; publishes every field in ``FIELDS``.

    Fields the meter did not send are published as ``null`` so Home
    Assistant shows them as unknown instead of logging template errors.
    """

    def __init__(
        self,
        registers: dict[str, Any],
        meter_id: str | None = None,
        meter_time: str | None = None,
    ) -> None:
        self.registers = registers
        self.meter_id = meter_id
        self.meter_time = meter_time
        self.values: dict[str, Any] = {
            FIELD_BY_OBIS[obis]: value
            for obis, value in registers.items()
            if obis in FIELD_BY_OBIS
        }

    def __getattr__(self, name: str) -> Any:
        # Convenience for logs and tests: data.w_con, data.total_con, …
        if name in FIELDS:
            return self.__dict__["values"].get(name)
        raise AttributeError(name)

    def __str__(self) -> str:
        present = ",".join(f"{k}={v}" for k, v in self.values.items())
        return f"ObisMeterData[{present},t({self.meter_time})]"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {field: self.values.get(field) for field in FIELDS}
        result["meter_time"] = self.meter_time
        return result


def _build(
    pairs: Iterable[tuple[str, Any]], meter_time: str | None
) -> ObisMeterData:
    registers: dict[str, Any] = {}
    meter_id: str | None = None
    device_name: str | None = None
    for obis, value in pairs:
        if obis in _METER_ID_OBIS:
            meter_id = meter_id or _text(value)
        elif obis == _DEVICE_NAME_OBIS:
            device_name = _text(value)
        elif obis == _CLOCK_OBIS:
            if isinstance(value, (bytes, bytearray)):
                meter_time = parse_dlms_datetime(value) or meter_time
            elif isinstance(value, str):
                meter_time = parse_dsmr_timestamp(value) or meter_time
        else:
            registers[obis] = value
    if not any(obis in FIELD_BY_OBIS for obis in registers):
        raise ValueError(
            f"telegram contains no known OBIS register: {sorted(registers)}"
        )
    return ObisMeterData(registers, meter_id or device_name, meter_time)


def registers_from_notification(notification: DataNotification) -> ObisMeterData:
    """Map a decoded data-notification onto ``ObisMeterData``."""
    found: list[tuple[str, Any]] = []
    loose: list[Any] = []
    body = notification.body if isinstance(notification.body, list) else [notification.body]
    _walk(body, found, loose)

    meter_time: str | None = None
    # A bare 12-byte octet-string (no OBIS before it) is the clock value.
    for item in loose:
        if isinstance(item, (bytes, bytearray)) and len(item) == _DATETIME_LENGTH:
            meter_time = parse_dlms_datetime(item)
            if meter_time:
                break
    if meter_time is None and notification.timestamp:
        meter_time = parse_dlms_datetime(notification.timestamp)
    return _build(found, meter_time)


def parse_dsmr_timestamp(text: str) -> str | None:
    """``190501160729S`` → ``2019-05-01T16:07:29+02:00`` (S = summer time)."""
    if len(text) != 13 or not text[:12].isdigit() or text[12] not in "SW":
        return None
    offset = timedelta(hours=2 if text[12] == "S" else 1)
    try:
        moment = datetime.strptime(text[:12], "%y%m%d%H%M%S")
    except ValueError:
        return None
    return moment.replace(tzinfo=timezone(offset)).isoformat()


def _dsmr_meter_id(value: Any) -> Any:
    """DSMR sends the equipment id hex-encoded (``4E...`` → ``N...``)."""
    if isinstance(value, str) and value and len(value) % 2 == 0:
        try:
            decoded = bytes.fromhex(value).decode("ascii")
        except ValueError:
            return value
        if set(decoded) <= _PRINTABLE:
            return decoded
    return value


def registers_from_dsmr(values: Iterable[DsmrValue]) -> ObisMeterData:
    """Map parsed DSMR lines onto ``ObisMeterData``."""
    pairs: list[tuple[str, Any]] = []
    for item in values:
        value = item.value
        if item.obis in _METER_ID_OBIS:
            value = _dsmr_meter_id(value)
        pairs.append((item.obis, value))
    return _build(pairs, None)
