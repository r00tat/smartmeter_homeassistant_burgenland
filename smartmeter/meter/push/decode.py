"""Decode one framed unit into ``ObisMeterData``."""

from __future__ import annotations

from .axdr import DATA_NOTIFICATION_TAG, decode_data_notification
from .cipher import GLO_CIPHERING_TAGS, decrypt_envelope
from .dsmr import parse_telegram
from .registers import ObisMeterData, registers_from_dsmr, registers_from_notification


class WrongKeyError(ValueError):
    """Decryption produced something that is neither DLMS nor DSMR."""


def decode_unit(unit: bytes, key: bytes) -> ObisMeterData:
    """Decrypt (if needed) and decode a unit produced by ``PushFramer``."""
    if unit and unit[0] in GLO_CIPHERING_TAGS:
        plain = decrypt_envelope(unit, key)
        if not plain or plain[0] not in (DATA_NOTIFICATION_TAG, ord("/")):
            first = f"{plain[0]:#04x}" if plain else "empty"
            raise WrongKeyError(
                f"decrypted data starts with {first}, expected a data-notification "
                "(0x0f) or a DSMR telegram ('/') — check the decryption key"
            )
        unit = plain
    if unit and unit[0] == DATA_NOTIFICATION_TAG:
        return registers_from_notification(decode_data_notification(unit))
    if unit.startswith(b"/"):
        return registers_from_dsmr(parse_telegram(unit))
    first = f"{unit[0]:#04x}" if unit else "empty"
    raise ValueError(f"unsupported APDU (starts with {first})")
