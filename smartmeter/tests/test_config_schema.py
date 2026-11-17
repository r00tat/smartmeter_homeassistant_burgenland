"""The runtime config schema accepts the template and the mqtt.tls option."""

from __future__ import annotations

import json
import os

import yaml
from jsonschema import Draft202012Validator
from smartmeter_austria.config_validation import VALID_METER_TYPES
from smartmeter_austria.profile import known_meter_types

_HERE = os.path.dirname(os.path.dirname(__file__))  # smartmeter/
_SCHEMA = os.path.join(_HERE, "config.schema.json")
_TEMPLATE = os.path.join(_HERE, "smartmeter-config.example.yaml")


def _schema() -> dict:
    with open(_SCHEMA, encoding="utf-8") as fh:
        return json.load(fh)


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(_schema())


def test_example_config_matches_schema() -> None:
    # The shipped example config must validate as-is: it carries placeholder
    # values (host, 32-hex key) so users get no editor errors before editing.
    with open(_TEMPLATE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    Draft202012Validator(_schema()).validate(data)


def test_schema_allows_tls_boolean() -> None:
    schema = _schema()
    mqtt_props = schema["properties"]["mqtt"]["properties"]
    assert mqtt_props["tls"]["type"] == "boolean"


def test_schema_rejects_unknown_meter_type() -> None:
    cfg = {
        "meter_type": "bogus",
        "mqtt": {"host": "h"},
        "dlms": {"key": "00" * 16, "port": "/dev/ttyUSB0"},
    }
    errors = list(Draft202012Validator(_schema()).iter_errors(cfg))
    assert errors, "unknown meter_type should fail validation"


def test_schema_accepts_single_letter_parity() -> None:
    # config_validation.py accepts both pyserial letters and full names.
    cfg = {
        "mqtt": {"host": "h"},
        "dlms": {"key": "00" * 16, "port": "/dev/ttyUSB0", "parity": "E"},
    }
    errors = list(Draft202012Validator(_schema()).iter_errors(cfg))
    assert not errors, f"single-letter parity should be valid: {errors}"


def test_meter_types_are_consistent_across_config_files() -> None:
    known = set(known_meter_types())
    assert set(VALID_METER_TYPES) == known

    with open(os.path.join(_HERE, "config.schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    assert set(schema["properties"]["meter_type"]["enum"]) == known

    with open(os.path.join(_HERE, "config.yaml"), encoding="utf-8") as fh:
        addon = yaml.safe_load(fh)
    listed = addon["schema"]["meter_type"]
    assert listed.startswith("list(") and listed.endswith(")?")
    assert set(listed[len("list(") : -len(")?")].split("|")) == known


def test_addon_options_leave_serial_defaults_to_the_profile() -> None:
    # If the add-on options pinned baudrate/parity, Home Assistant would always
    # send them and the profile defaults (e.g. 2400 8E1 for noe_evn) never apply.
    with open(os.path.join(_HERE, "config.yaml"), encoding="utf-8") as fh:
        addon = yaml.safe_load(fh)
    dlms_options = addon["options"]["dlms"]
    for key in ("baudrate", "bytesize", "parity", "stopbits"):
        assert key not in dlms_options
        assert key in addon["schema"]["dlms"]
