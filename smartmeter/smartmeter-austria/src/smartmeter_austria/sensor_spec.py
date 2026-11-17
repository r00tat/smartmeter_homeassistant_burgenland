"""Sensor-spec dataclass shared across meter profiles."""

from __future__ import annotations

import re
from dataclasses import dataclass

_VALUE_KEY_RE = re.compile(r"^\{\{\s*value_json\.(\w+)\s*\}\}$")


@dataclass(frozen=True)
class SensorSpec:
    """Static description of a Home Assistant sensor for this device."""

    name: str
    suffix: str  # appended to device_id for unique_id; empty means use device_id
    value_template: str | None = None
    unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    enabled_by_default: bool | None = None
    raw: bool = False  # the 'Raw Data' sensor has a different shape

    @property
    def value_key(self) -> str | None:
        """Key in ``MeterData.to_dict()`` this sensor reads.

        The native Home Assistant integration has no Jinja templates, so it
        needs the plain key behind ``{{ value_json.<key> }}``.
        """
        if self.value_template is None:
            return None
        match = _VALUE_KEY_RE.match(self.value_template)
        if match is None:
            raise ValueError(
                f"value_template {self.value_template!r} is not a plain "
                "'{{ value_json.<key> }}' lookup"
            )
        return match.group(1)
