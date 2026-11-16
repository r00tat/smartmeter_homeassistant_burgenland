"""Tests for ``SensorSpec.value_key``."""

import pytest

from meter.mqtt.sensor_spec import SensorSpec
from meter.profile import get_profile, known_meter_types


def test_value_key_is_parsed_from_template() -> None:
    spec = SensorSpec(name="x", suffix="_x", value_template="{{ value_json.total_con }}")
    assert spec.value_key == "total_con"


def test_value_key_is_none_without_template() -> None:
    assert SensorSpec(name="Raw Data", suffix="", raw=True).value_key is None


def test_value_key_rejects_complex_templates() -> None:
    spec = SensorSpec(name="x", suffix="_x", value_template="{{ value_json.a * 2 }}")
    with pytest.raises(ValueError, match="value_json"):
        _ = spec.value_key


@pytest.mark.parametrize("meter_type", known_meter_types())
def test_every_catalog_sensor_has_a_value_key(meter_type: str) -> None:
    for spec in get_profile(meter_type).sensor_specs:
        if spec.raw:
            continue
        assert spec.value_key, f"{meter_type}: {spec.name} has no value key"
