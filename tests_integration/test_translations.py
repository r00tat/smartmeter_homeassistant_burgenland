"""Translations cover every meter type."""

import json
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant

from custom_components.smartmeter_at.core import async_load_core

TRANSLATIONS = Path(__file__).parents[1] / "custom_components/smartmeter_at/translations"


@pytest.mark.parametrize("language", ["en", "de"])
async def test_every_meter_type_has_a_selector_label(
    hass: HomeAssistant, language: str
) -> None:
    core = await async_load_core(hass)
    translations = json.loads((TRANSLATIONS / f"{language}.json").read_text())
    labels = translations["selector"]["meter_type"]["options"]
    assert set(labels) == set(core.profile.known_meter_types())
