"""Sensor-spec dataclass shared across meter profiles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SensorSpec:
    """Static description of a Home Assistant MQTT sensor for this device."""

    name: str
    suffix: str  # appended to device_id for unique_id; empty means use device_id
    value_template: str | None = None
    unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    enabled_by_default: bool | None = None
    raw: bool = False  # the 'Raw Data' sensor has a different shape
