"""Home Assistant sensor catalog for the OBIS-based profiles.

Each profile picks the fields its meters actually send; the specs below
keep names and unique-id suffixes identical to the Burgenland, NÖ and
Wien profiles so dashboards and statistics carry over.
"""

from __future__ import annotations

from ..mqtt.sensor_spec import SensorSpec

_RAW = SensorSpec(name="Raw Data", suffix="", raw=True)


def _energy(name: str, suffix: str, key: str, unit: str = "Wh",
            device_class: str = "energy", enabled: bool | None = None) -> SensorSpec:
    return SensorSpec(
        name=name,
        suffix=suffix,
        value_template=f"{{{{ value_json.{key} }}}}",
        unit_of_measurement=unit,
        device_class=device_class,
        state_class="total_increasing",
        enabled_by_default=enabled,
    )


def _measurement(name: str, suffix: str, key: str, unit: str | None,
                 device_class: str, enabled: bool | None = None) -> SensorSpec:
    return SensorSpec(
        name=name,
        suffix=suffix,
        value_template=f"{{{{ value_json.{key} }}}}",
        unit_of_measurement=unit,
        device_class=device_class,
        state_class="measurement",
        enabled_by_default=enabled,
    )


SPEC_BY_FIELD: dict[str, SensorSpec] = {
    "total_con": _energy("Total Energy consumed", "_total_energy_consumed", "total_con"),
    "total_prov": _energy("Total Energy provided", "_total_energy_provided", "total_prov"),
    "total_con_t1": _energy(
        "Energy consumed tariff 1", "_energy_consumed_t1", "total_con_t1", enabled=False
    ),
    "total_con_t2": _energy(
        "Energy consumed tariff 2", "_energy_consumed_t2", "total_con_t2", enabled=False
    ),
    "total_prov_t1": _energy(
        "Energy provided tariff 1", "_energy_provided_t1", "total_prov_t1", enabled=False
    ),
    "total_prov_t2": _energy(
        "Energy provided tariff 2", "_energy_provided_t2", "total_prov_t2", enabled=False
    ),
    "w_con": _measurement("Power consumed", "_power_consumed", "w_con", "W", "power"),
    "w_prov": _measurement("Power provided", "_power_provided", "w_prov", "W", "power"),
    "u1": _measurement("Voltage L1", "_voltage_l1", "u1", "V", "voltage"),
    "u2": _measurement("Voltage L2", "_voltage_l2", "u2", "V", "voltage"),
    "u3": _measurement("Voltage L3", "_voltage_l3", "u3", "V", "voltage"),
    "i1": _measurement("Current L1", "_current_l1", "i1", "A", "current"),
    "i2": _measurement("Current L2", "_current_l2", "i2", "A", "current"),
    "i3": _measurement("Current L3", "_current_l3", "i3", "A", "current"),
    "power_factor": _measurement(
        "Power Factor", "_power_factor", "power_factor", None, "power_factor"
    ),
    "reactive_total_con": _energy(
        "Total Reactive Energy consumed", "_total_reactive_energy_consumed",
        "reactive_total_con", unit="varh", device_class="reactive_energy", enabled=False,
    ),
    "reactive_total_prov": _energy(
        "Total Reactive Energy provided", "_total_reactive_energy_provided",
        "reactive_total_prov", unit="varh", device_class="reactive_energy", enabled=False,
    ),
    "var_con": _measurement(
        "Reactive Power consumed", "_reactive_power_consumed", "var_con", "var",
        "reactive_power", enabled=False,
    ),
    "var_prov": _measurement(
        "Reactive Power provided", "_reactive_power_provided", "var_prov", "var",
        "reactive_power", enabled=False,
    ),
}


def build_sensor_specs(fields: tuple[str, ...]) -> tuple[SensorSpec, ...]:
    """Raw-data sensor followed by one sensor per field, in catalog order."""
    unknown = set(fields) - set(SPEC_BY_FIELD)
    if unknown:
        raise ValueError(f"no sensor spec for fields {sorted(unknown)}")
    return (_RAW, *(spec for key, spec in SPEC_BY_FIELD.items() if key in fields))


# Field sets per meter family (from the operators' specifications).
KAIFA_FIELDS = (
    "total_con", "total_prov", "w_con", "w_prov",
    "u1", "u2", "u3", "i1", "i2", "i3",
    "reactive_total_con", "reactive_total_prov",
)
E450_STEIERMARK_FIELDS = (
    "total_con", "total_prov", "w_con", "w_prov",
    "total_con_t1", "total_con_t2", "total_prov_t1", "total_prov_t2",
    "reactive_total_con", "reactive_total_prov", "var_con", "var_prov",
)
H1_FIELDS = (
    "total_con", "total_prov", "w_con", "w_prov",
    "u1", "u2", "u3", "i1", "i2", "i3",
    "reactive_total_con", "reactive_total_prov", "var_con", "var_prov",
)
