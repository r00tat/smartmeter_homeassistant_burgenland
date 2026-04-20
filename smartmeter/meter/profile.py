"""Meter-profile registry.

A profile bundles provider-specific knowledge (manufacturer, model,
default serial speed, sensor catalog) so the rest of the program can
stay agnostic of which smart meter is attached.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bgld.sensors import SENSOR_SPECS as BGLD_SENSORS
from .mqtt.sensor_spec import SensorSpec
from .noe.sensors import SENSOR_SPECS as NOE_SENSORS


@dataclass(frozen=True)
class MeterProfile:
    """Bundle of provider-specific defaults and artefacts."""

    name: str
    manufacturer: str
    model: str
    default_baudrate: int
    sensor_specs: tuple[SensorSpec, ...]


_PROFILES: dict[str, MeterProfile] = {
    "burgenland": MeterProfile(
        name="burgenland",
        manufacturer="Landis+Gyr",
        model="E450",
        default_baudrate=9600,
        sensor_specs=BGLD_SENSORS,
    ),
    "noe_evn": MeterProfile(
        name="noe_evn",
        manufacturer="Sagemcom",
        model="T210-D",
        default_baudrate=2400,
        sensor_specs=NOE_SENSORS,
    ),
}


def get_profile(meter_type: str) -> MeterProfile:
    """Return the ``MeterProfile`` for ``meter_type`` or raise."""
    try:
        return _PROFILES[meter_type]
    except KeyError as exc:
        raise ValueError(
            f"unknown meter_type {meter_type!r}; "
            f"known: {sorted(_PROFILES)}"
        ) from exc
