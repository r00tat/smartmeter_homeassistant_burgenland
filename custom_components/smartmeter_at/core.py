"""Import the smartmeter-austria library lazily, after making gurux importable.

The library imports gurux-dlms at import time. gurux-dlms 1.0.197 ships a
Latin-1 source file that Python 3.15 rejects; the add-on images re-encode
it at build time, the integration has to do it at runtime because Home
Assistant installs the requirements itself.
"""

from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass
from types import ModuleType

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from smartmeter_austria import fix_source_encoding

from .const import DATA_CORE

_LOGGER = logging.getLogger(__name__)
_GURUX_PACKAGES = ["gurux_dlms", "gurux_common"]


@dataclass(frozen=True)
class Core:
    """The core modules the integration uses."""

    profile: ModuleType
    supervisor: ModuleType
    config_validation: ModuleType


def _import_gurux() -> None:
    for name in _GURUX_PACKAGES:
        importlib.import_module(name)


def ensure_gurux_importable() -> None:
    """Import gurux; re-encode its sources once if Python refuses them."""
    try:
        _import_gurux()
        return
    except SyntaxError as err:
        _LOGGER.warning(
            "gurux-dlms is not importable on this Python (%s), re-encoding its sources",
            err,
        )
    try:
        fix_source_encoding.main(list(_GURUX_PACKAGES))
    except (OSError, SystemExit) as err:
        raise HomeAssistantError(
            "gurux-dlms cannot be imported on this Python and its sources "
            f"could not be re-encoded: {err}"
        ) from err
    for name in [m for m in sys.modules if m.split(".")[0] in _GURUX_PACKAGES]:
        del sys.modules[name]
    importlib.invalidate_caches()
    _import_gurux()


def load_core() -> Core:
    """Blocking: fix gurux if needed and import the core modules."""
    ensure_gurux_importable()
    from smartmeter_austria import config_validation, profile, supervisor

    return Core(profile=profile, supervisor=supervisor, config_validation=config_validation)


async def async_load_core(hass: HomeAssistant) -> Core:
    """Load the core once per Home Assistant instance, off the event loop."""
    core: Core | None = hass.data.get(DATA_CORE)
    if core is None:
        core = await hass.async_add_import_executor_job(load_core)
        hass.data[DATA_CORE] = core
    return core
