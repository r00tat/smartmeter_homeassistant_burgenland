"""Unit tests for meter.config_validation."""

import pytest

from meter.config_validation import ConfigError, validate_config


VALID_KEY = "0123456789abcdef0123456789ABCDEF"


def _valid_config(**overrides: object) -> dict:
    cfg = {
        "mqtt": {"host": "mqtt.example"},
        "dlms": {"key": VALID_KEY, "parity": "NONE"},
    }
    for k, v in overrides.items():
        cfg[k] = v
    return cfg


def test_valid_config_passes() -> None:
    validate_config(_valid_config())


def test_non_mapping_rejected() -> None:
    with pytest.raises(ConfigError):
        validate_config("nope")  # type: ignore[arg-type]


def test_missing_mqtt_host() -> None:
    with pytest.raises(ConfigError, match="mqtt.host"):
        validate_config(_valid_config(mqtt={}))


def test_missing_dlms_key() -> None:
    with pytest.raises(ConfigError, match="dlms.key"):
        validate_config(_valid_config(dlms={"key": "", "parity": "NONE"}))


def test_short_dlms_key_rejected() -> None:
    with pytest.raises(ConfigError, match="32-character hex"):
        validate_config(_valid_config(dlms={"key": "abcd", "parity": "NONE"}))


def test_non_hex_dlms_key_rejected() -> None:
    with pytest.raises(ConfigError, match="32-character hex"):
        validate_config(_valid_config(dlms={"key": "Z" * 32, "parity": "NONE"}))


def test_invalid_parity_rejected() -> None:
    with pytest.raises(ConfigError, match="parity"):
        validate_config(_valid_config(dlms={"key": VALID_KEY, "parity": "XYZ"}))


def test_parity_letter_accepted() -> None:
    validate_config(_valid_config(dlms={"key": VALID_KEY, "parity": "N"}))


def test_parity_empty_accepted() -> None:
    validate_config(_valid_config(dlms={"key": VALID_KEY, "parity": ""}))
