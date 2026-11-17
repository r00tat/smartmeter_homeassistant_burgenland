"""Home Assistant MQTT sensor catalog for the Wiener Netze profile."""

from __future__ import annotations

from ..sensor_spec import SensorSpec

SENSOR_SPECS: tuple[SensorSpec, ...] = (
    SensorSpec(name="Raw Data", suffix="", raw=True),
    SensorSpec(
        name="Total Energy consumed",
        suffix="_total_energy_consumed",
        value_template="{{ value_json.total_con }}",
        unit_of_measurement="Wh",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorSpec(
        name="Total Energy provided",
        suffix="_total_energy_provided",
        value_template="{{ value_json.total_prov }}",
        unit_of_measurement="Wh",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorSpec(
        name="Power consumed",
        suffix="_power_consumed",
        value_template="{{ value_json.w_con }}",
        unit_of_measurement="W",
        device_class="power",
        state_class="measurement",
    ),
    SensorSpec(
        name="Power provided",
        suffix="_power_provided",
        value_template="{{ value_json.w_prov }}",
        unit_of_measurement="W",
        device_class="power",
        state_class="measurement",
    ),
    SensorSpec(
        name="Total Reactive Energy consumed",
        suffix="_total_reactive_energy_consumed",
        value_template="{{ value_json.reactive_total_con }}",
        unit_of_measurement="varh",
        device_class="reactive_energy",
        state_class="total_increasing",
        enabled_by_default=False,
    ),
    SensorSpec(
        name="Total Reactive Energy provided",
        suffix="_total_reactive_energy_provided",
        value_template="{{ value_json.reactive_total_prov }}",
        unit_of_measurement="varh",
        device_class="reactive_energy",
        state_class="total_increasing",
        enabled_by_default=False,
    ),
    SensorSpec(
        name="Reactive Power consumed",
        suffix="_reactive_power_consumed",
        value_template="{{ value_json.var_con }}",
        unit_of_measurement="var",
        device_class="reactive_power",
        state_class="measurement",
        enabled_by_default=False,
    ),
    SensorSpec(
        name="Reactive Power provided",
        suffix="_reactive_power_provided",
        value_template="{{ value_json.var_prov }}",
        unit_of_measurement="var",
        device_class="reactive_power",
        state_class="measurement",
        enabled_by_default=False,
    ),
)
