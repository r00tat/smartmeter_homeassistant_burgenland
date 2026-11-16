"""Diagnostics download for the config entry."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_KEY
from .coordinator import SmartMeterConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SmartMeterConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for the config entry."""
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), {CONF_KEY}),
        "options": dict(entry.options),
        "profile": coordinator.profile.name,
        "meter_id_known": coordinator.meter_id is not None,
        "last_update_success": coordinator.last_update_success,
        "data": coordinator.data,
    }
