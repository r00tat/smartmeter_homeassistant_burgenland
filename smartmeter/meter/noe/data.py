"""Parsed meter data from the Sagemcom T210-D (Netz NÖ / EVN)."""

from __future__ import annotations

import json
from typing import Any

# Scaling is expressed as a divisor (not a float multiplier) to keep
# the serialised result exact (2301/10 == 230.1, but 2301*0.1 is not).
_VOLTAGE_DIVISOR = 10
_CURRENT_DIVISOR = 100
_POWER_FACTOR_DIVISOR = 1000


class MeterData:
    """Netz-NÖ meter data keyed by OBIS field name.

    Values are provided by the meter as plain integers and must be
    scaled for the physical quantity they represent.
    """

    def __init__(self, obis_values: dict[str, Any]):
        self.obis_values = obis_values

        self.voltage_l1: float = obis_values.get("voltage_l1", 0) / _VOLTAGE_DIVISOR
        self.voltage_l2: float = obis_values.get("voltage_l2", 0) / _VOLTAGE_DIVISOR
        self.voltage_l3: float = obis_values.get("voltage_l3", 0) / _VOLTAGE_DIVISOR

        self.current_l1: float = obis_values.get("current_l1", 0) / _CURRENT_DIVISOR
        self.current_l2: float = obis_values.get("current_l2", 0) / _CURRENT_DIVISOR
        self.current_l3: float = obis_values.get("current_l3", 0) / _CURRENT_DIVISOR

        self.power_consumed: int = obis_values.get("power_consumed", 0)
        self.power_provided: int = obis_values.get("power_provided", 0)

        self.total_consumed: int = obis_values.get("energy_consumed", 0)
        self.total_provided: int = obis_values.get("energy_provided", 0)

        self.power_factor: float = (
            obis_values.get("power_factor", 0) / _POWER_FACTOR_DIVISOR
        )

        self.meter_id: str | None = None

    def __str__(self) -> str:
        return (
            f"MeterData["
            f"U({self.voltage_l1}V,{self.voltage_l2}V,{self.voltage_l3}V),"
            f"I({self.current_l1}A,{self.current_l2}A,{self.current_l3}A),"
            f"P({self.power_consumed}W,-{self.power_provided}W),"
            f"W({self.total_consumed}Wh,-{self.total_provided}Wh),"
            f"pf({self.power_factor})"
            f"]"
        )

    def to_dict(self) -> dict:
        return {
            "u1": self.voltage_l1,
            "u2": self.voltage_l2,
            "u3": self.voltage_l3,
            "i1": self.current_l1,
            "i2": self.current_l2,
            "i3": self.current_l3,
            "w_con": self.power_consumed,
            "w_prov": self.power_provided,
            "total_con": self.total_consumed,
            "total_prov": self.total_provided,
            "power_factor": self.power_factor,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
