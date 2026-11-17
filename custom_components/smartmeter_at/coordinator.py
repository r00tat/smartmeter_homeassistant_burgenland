"""Push coordinator: the reader runs as a task on Home Assistant's event loop."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_INTERFACE_TYPE,
    CONF_KEY,
    CONF_METER_TYPE,
    CONF_PORT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_INTERFACE_TYPE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .core import Core

_LOGGER = logging.getLogger(__name__)

# Seconds to wait before the supervisor restarts a failed reader.
RETRY_SECONDS = 10.0

# Reopen the port when no telegram arrived for this long: a hung USB
# adapter can keep the port open without delivering data.
RESTART_AFTER_SECONDS = 300.0


def build_reader_factory(profile: Any, entry_data: Mapping[str, Any]) -> Callable[[Any], Any]:
    """Return ``callback -> reader`` for the profile and the entry's settings."""
    config = {
        "interface_type": str(
            entry_data.get(CONF_INTERFACE_TYPE, DEFAULT_INTERFACE_TYPE)
        ).upper(),
        "dlms": {"port": entry_data[CONF_PORT], "key": entry_data[CONF_KEY]},
    }
    return partial(profile.create_reader, config)


class SmartMeterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the latest reading; the reader pushes, nothing is polled."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, core: Core) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None
        )
        self.profile = core.profile.get_profile(entry.data[CONF_METER_TYPE])
        self.meter_id: str | None = None
        # Entities go unavailable when no telegram arrives for this long.
        self.stale_after = self.profile.stale_after_seconds
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        self._supervisor = core.supervisor.ReaderSupervisor(
            build_reader_factory(self.profile, entry.data),
            on_data=self._async_handle_data,
            on_error=self.async_set_update_error,
            every=self.profile.readings_per_publish(float(interval)),
            retry_seconds=RETRY_SECONDS,
            stale_after=self.stale_after,
            restart_after=RESTART_AFTER_SECONDS,
        )
        self._task: asyncio.Task[None] | None = None
        self._cancel_and_wait = core.supervisor.cancel_and_wait

    @callback
    def async_start(self) -> None:
        """Start reading in a background task of the config entry."""
        assert self.config_entry is not None
        self._task = self.config_entry.async_create_background_task(
            self.hass,
            self._supervisor.run(),
            name=f"{DOMAIN} reader {self.config_entry.title}",
        )

    async def async_stop(self) -> None:
        """Stop reading and wait until the serial port is closed."""
        task, self._task = self._task, None
        if task is not None:
            await self._cancel_and_wait(task)

    @callback
    def _async_handle_data(self, data: Any) -> None:
        if data.meter_id and self.meter_id is None:
            self.meter_id = data.meter_id
            self._async_set_device_serial(data.meter_id)
        self.async_set_updated_data(data.to_dict())

    @callback
    def _async_set_device_serial(self, serial_number: str) -> None:
        assert self.config_entry is not None
        dev_reg = dr.async_get(self.hass)
        dev_reg.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            serial_number=serial_number,
        )


type SmartMeterConfigEntry = ConfigEntry[SmartMeterCoordinator]
