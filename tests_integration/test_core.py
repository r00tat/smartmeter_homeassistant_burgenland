"""Tests for the lazy core import."""

import sys
from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.smartmeter_at import core


def test_import_failure_raises_home_assistant_error() -> None:
    # A None entry in sys.modules makes the import raise ImportError.
    with (
        patch.dict(sys.modules, {"smartmeter_austria": None}),
        pytest.raises(HomeAssistantError, match="cannot be imported"),
    ):
        core.load_core()


async def test_async_load_core_is_cached(hass: HomeAssistant) -> None:
    first = await core.async_load_core(hass)
    second = await core.async_load_core(hass)
    assert first is second
    assert "burgenland" in first.profile.known_meter_types()
