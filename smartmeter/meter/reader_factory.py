"""Instantiate the correct serial reader for a given meter profile."""

from __future__ import annotations

from .profile import MeterDataCallback, MeterProfile, MeterReaderLike


def build_reader(
    config: dict,
    profile: MeterProfile,
    callback: MeterDataCallback,
) -> MeterReaderLike:
    """Return a reader instance configured for ``profile``.

    The profile owns every interface decision (reader type, serial
    defaults); explicit ``dlms.*`` values in the user config override the
    serial defaults.
    """
    return profile.create_reader(config, callback)
