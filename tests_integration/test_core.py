"""Tests for the lazy core import and the gurux fix-up."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.smartmeter_at import core


def test_no_fixup_when_gurux_imports() -> None:
    with (
        patch.object(core, "_import_gurux") as import_gurux,
        patch.object(core.fix_source_encoding, "main") as fix,
    ):
        core.ensure_gurux_importable()
    import_gurux.assert_called_once()
    fix.assert_not_called()


def test_fixup_runs_after_syntax_error() -> None:
    with (
        patch.object(core, "_import_gurux", side_effect=[SyntaxError("bad"), None]) as import_gurux,
        patch.object(core.fix_source_encoding, "main") as fix,
    ):
        core.ensure_gurux_importable()
    fix.assert_called_once_with(["gurux_dlms", "gurux_common"])
    assert import_gurux.call_count == 2


async def test_async_load_core_is_cached(hass: HomeAssistant) -> None:
    first = await core.async_load_core(hass)
    second = await core.async_load_core(hass)
    assert first is second
    assert "burgenland" in first.profile.known_meter_types()
