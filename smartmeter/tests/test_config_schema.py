"""The runtime config schema accepts the template and the mqtt.tls option."""

from __future__ import annotations

import json
import os

import yaml
from jsonschema import Draft202012Validator

_HERE = os.path.dirname(os.path.dirname(__file__))  # smartmeter/
_SCHEMA = os.path.join(_HERE, "config.schema.json")
_TEMPLATE = os.path.join(_HERE, "smartmeter-config-template.yaml")


def _schema() -> dict:
    with open(_SCHEMA, encoding="utf-8") as fh:
        return json.load(fh)


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(_schema())


def test_template_matches_schema() -> None:
    with open(_TEMPLATE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    # template ships an empty host/key (user fills them); validate shape only
    data.setdefault("mqtt", {})["host"] = "mqtt.local"
    data.setdefault("dlms", {})["key"] = "00" * 16
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
