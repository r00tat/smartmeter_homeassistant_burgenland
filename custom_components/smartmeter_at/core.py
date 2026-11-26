"""Import the smartmeter-austria library lazily, off the event loop.

The library imports gurux-dlms at import time, which is slow and blocking.
gurux-dlms is pinned to a release that imports cleanly on every supported
Python; if it does not import anyway, setup fails with a clear error instead
of touching the installed packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DATA_CORE


@dataclass(frozen=True)
class Core:
    """The core modules the integration uses."""

    profile: ModuleType
    supervisor: ModuleType
    config_validation: ModuleType


def load_core() -> Core:
    """Blocking: import the core modules (and with them gurux-dlms)."""
    try:
        from smartmeter_austria import config_validation, profile, supervisor
    except (ImportError, SyntaxError) as err:
        raise HomeAssistantError(
            "The smartmeter-austria library or its gurux-dlms dependency cannot "
            f"be imported on this Python version: {err}"
        ) from err

    return Core(profile=profile, supervisor=supervisor, config_validation=config_validation)


async def async_load_core(hass: HomeAssistant) -> Core:
    """Load the core once per Home Assistant instance, off the event loop."""
    core: Core | None = hass.data.get(DATA_CORE)
    if core is None:
        core = await hass.async_add_import_executor_job(load_core)
        hass.data[DATA_CORE] = core
    return core
