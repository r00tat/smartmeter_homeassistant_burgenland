"""Fail-fast validation for the add-on configuration."""

import re

import serial

HEX_KEY_RE = re.compile(r"^[0-9a-fA-F]{32}$")

VALID_PARITY_LETTERS = set(serial.PARITY_NAMES.keys())
VALID_PARITY_NAMES = {name.upper() for name in serial.PARITY_NAMES.values()}


class ConfigError(ValueError):
    """Raised when the add-on configuration is invalid."""


def validate_config(config: dict) -> None:
    """Validate required add-on configuration keys.

    Raises ConfigError if anything mandatory is missing or malformed.
    """
    if not isinstance(config, dict):
        raise ConfigError("config must be a mapping")

    mqtt = config.get("mqtt") or {}
    if not isinstance(mqtt, dict):
        raise ConfigError("mqtt config must be a mapping")
    if not mqtt.get("host"):
        raise ConfigError("mqtt.host is required")

    dlms = config.get("dlms") or {}
    if not isinstance(dlms, dict):
        raise ConfigError("dlms config must be a mapping")

    key = dlms.get("key")
    if not key or not HEX_KEY_RE.match(str(key)):
        raise ConfigError("dlms.key must be a 32-character hex string")

    parity = dlms.get("parity")
    if parity is not None and parity != "":
        parity_str = str(parity)
        if (
            parity_str not in VALID_PARITY_LETTERS
            and parity_str.upper() not in VALID_PARITY_NAMES
        ):
            allowed = sorted(VALID_PARITY_LETTERS | VALID_PARITY_NAMES)
            raise ConfigError(
                f"dlms.parity {parity_str!r} is not valid; allowed: {allowed}"
            )
