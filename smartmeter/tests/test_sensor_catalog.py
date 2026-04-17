"""Unit tests for the SENSOR_SPECS catalog in meter.mqtt.device."""

from meter.mqtt.device import SENSOR_SPECS, SensorSpec


def test_first_entry_is_raw_sensor() -> None:
    assert SENSOR_SPECS[0].raw is True
    assert SENSOR_SPECS[0].suffix == ""


def test_only_one_raw_sensor() -> None:
    raw = [spec for spec in SENSOR_SPECS if spec.raw]
    assert len(raw) == 1


def test_non_raw_specs_have_unique_suffixes() -> None:
    suffixes = [spec.suffix for spec in SENSOR_SPECS if not spec.raw]
    assert len(suffixes) == len(set(suffixes)), "duplicate sensor suffixes"


def test_non_raw_specs_have_value_template_and_unit() -> None:
    for spec in SENSOR_SPECS:
        if spec.raw:
            continue
        assert spec.value_template, f"{spec.name} missing value_template"
        assert spec.unit_of_measurement, f"{spec.name} missing unit_of_measurement"


def test_no_duplicate_voltage_l1() -> None:
    """Regression: review docs/code-review-2026-04-17.md §3 found a duplicate."""
    voltage_l1 = [spec for spec in SENSOR_SPECS if spec.suffix == "_voltage_l1"]
    assert len(voltage_l1) == 1


def test_sensor_spec_is_frozen() -> None:
    spec = SENSOR_SPECS[1]
    import dataclasses

    assert dataclasses.is_dataclass(SensorSpec)
    try:
        spec.name = "changed"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("SensorSpec should be frozen")
