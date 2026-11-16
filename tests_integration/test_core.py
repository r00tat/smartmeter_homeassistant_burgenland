"""Tests for the lazy core import and the gurux fix-up."""

import sys
from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

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
        patch.dict(sys.modules),
        patch.object(core, "_import_gurux", side_effect=[SyntaxError("bad"), None]) as import_gurux,
        patch.object(core.fix_source_encoding, "main") as fix,
    ):
        sys.modules["gurux_dlms.fake_sub"] = object()  # type: ignore[assignment]
        core.ensure_gurux_importable()
        assert "gurux_dlms.fake_sub" not in sys.modules
    fix.assert_called_once_with(["gurux_dlms", "gurux_common"])
    assert import_gurux.call_count == 2


@pytest.mark.parametrize("failure", [OSError("read-only"), SystemExit("no sources")])
def test_failed_fixup_raises_home_assistant_error(failure: BaseException) -> None:
    with (
        patch.dict(sys.modules),
        patch.object(core, "_import_gurux", side_effect=SyntaxError("bad")),
        patch.object(core.fix_source_encoding, "main", side_effect=failure),
        pytest.raises(HomeAssistantError, match="could not be re-encoded"),
    ):
        core.ensure_gurux_importable()


async def test_async_load_core_is_cached(hass: HomeAssistant) -> None:
    first = await core.async_load_core(hass)
    second = await core.async_load_core(hass)
    assert first is second
    assert "burgenland" in first.profile.known_meter_types()
