r"""Parser for DSMR P1 text telegrams.

Smart Meter 2.0 (H1, Oesterreichs Energie Companion Standard 2026) and the
Sagemcom meters of Energienetze Steiermark output DSMR P1 telegrams::

    /EST5\253740976_A
    <blank line>
    0-0:1.0.0(190501160729S)
    1-0:1.8.0(000005562*Wh)
    1-0:32.7.0(230.1*V)
    !4E28

Each line becomes ``(OBIS code, value, unit)``. Values are normalised to
the base units the other profiles publish (Wh, W, varh, var, V, A).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_LINE_RE = re.compile(
    r"^(?P<obis>\d+-\d+:\d+\.\d+\.\d+)(?P<groups>(?:\([^()]*\))+)\s*$"
)
_GROUP_RE = re.compile(r"\(([^()]*)\)")
_CRC_RE = re.compile(rb"!([0-9A-Fa-f]{4})?")

# unit → (base unit, factor)
_UNIT_SCALE: dict[str, tuple[str, int]] = {
    "kWh": ("Wh", 1000),
    "kW": ("W", 1000),
    "kvarh": ("varh", 1000),
    "kvar": ("var", 1000),
    "kVArh": ("varh", 1000),
    "kVAr": ("var", 1000),
    "kV": ("V", 1000),
}


class DsmrError(ValueError):
    """Raised when a DSMR telegram is malformed."""


@dataclass(frozen=True)
class DsmrValue:
    """One data line of a telegram, value normalised to its base unit."""

    obis: str  # "1-0:1.8.0"
    value: float | int | str
    unit: str | None


def crc16(data: bytes) -> int:
    """CRC-16/ARC (polynomial 0xA001 reflected) as used by DSMR P1."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def telegram_end(data: bytes) -> int | None:
    """Index just past the telegram that starts at ``data[0]`` ("/").

    A telegram ends with ``!`` plus an optional 4-digit CRC and CR LF.
    Returns ``None`` while the end has not arrived yet.
    """
    bang = data.find(b"!")
    if bang < 0:
        return None
    newline = data.find(b"\n", bang)
    if newline < 0:
        # Without CRC (DSMR < 4) the line may be just "!"; wait for its LF.
        return None
    return newline + 1


def _number(text: str) -> float | int:
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise DsmrError(f"not a number: {text!r}") from exc
    return int(number) if number == number.to_integral_value() else float(number)


def _parse_group(text: str) -> tuple[float | int | str, str | None]:
    if "*" in text:
        raw, unit = text.split("*", 1)
        value = _number(raw)
        if unit in _UNIT_SCALE:
            base, factor = _UNIT_SCALE[unit]
            scaled = Decimal(str(value)) * factor
            value = (
                int(scaled) if scaled == scaled.to_integral_value() else float(scaled)
            )
            unit = base
        return value, unit
    return text, None


def parse_telegram(telegram: bytes, verify_crc: bool = True) -> list[DsmrValue]:
    """Parse one telegram (from ``/`` up to and including the CRC line)."""
    if not telegram.startswith(b"/"):
        raise DsmrError("telegram must start with '/'")
    match = _CRC_RE.search(telegram)
    if match is None:
        raise DsmrError("telegram has no '!' end marker")
    if verify_crc and match.group(1):
        expected = int(match.group(1), 16)
        actual = crc16(telegram[: match.start() + 1])
        if actual != expected:
            raise DsmrError(f"CRC mismatch: telegram says {expected:04X}, got {actual:04X}")

    values: list[DsmrValue] = []
    body = telegram[: match.start()].decode("ascii", errors="replace")
    for line in body.splitlines()[1:]:
        parsed = _LINE_RE.match(line.strip())
        if parsed is None:
            continue
        groups = _GROUP_RE.findall(parsed.group("groups"))
        # Multi-group lines (e.g. M-Bus channels: timestamp then value):
        # the measured value is the last group.
        value, unit = _parse_group(groups[-1])
        values.append(DsmrValue(parsed.group("obis"), value, unit))
    return values
