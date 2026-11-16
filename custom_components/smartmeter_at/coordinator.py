"""Push coordinator: readings from the reader thread onto the event loop."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
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

# How often to check whether the meter went silent.
STALE_CHECK_INTERVAL = timedelta(seconds=30)


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
        self.stale_after = max(60.0, 6 * self.profile.push_interval_seconds)
        self._last_data = time.monotonic()
        self._unsub_stale_check: Callable[[], None] | None = None
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        self._supervisor = core.supervisor.ReaderSupervisor(
            build_reader_factory(self.profile, entry.data),
            on_data=self._on_data_from_thread,
            on_error=self._on_error_from_thread,
            every=self.profile.readings_per_publish(float(interval)),
            retry_seconds=RETRY_SECONDS,
        )

    def start(self) -> None:
        self._last_data = time.monotonic()
        self._unsub_stale_check = async_track_time_interval(
            self.hass, self.async_check_stale, STALE_CHECK_INTERVAL
        )
        self._supervisor.start()

    @callback
    def async_check_stale(self, now: datetime | None = None) -> None:
        """Mark the data as failed once when no telegram arrived for too long."""
        if not self.last_update_success:
            return
        silent = time.monotonic() - self._last_data
        if silent > self.stale_after:
            self.async_set_update_error(
                TimeoutError(f"no telegram for {self.stale_after:.0f} s")
            )

    async def async_stop(self) -> None:
        if self._unsub_stale_check is not None:
            self._unsub_stale_check()
            self._unsub_stale_check = None
        await self.hass.async_add_executor_job(self._supervisor.stop)

    def _on_data_from_thread(self, data: Any) -> None:
        self.hass.loop.call_soon_threadsafe(self._async_handle_data, data)

    def _on_error_from_thread(self, err: Exception) -> None:
        self.hass.loop.call_soon_threadsafe(self.async_set_update_error, err)

    @callback
    def _async_handle_data(self, data: Any) -> None:
        self._last_data = time.monotonic()
        if data.meter_id and self.meter_id is None:
            self.meter_id = data.meter_id
            self._async_set_device_serial(data.meter_id)
        self.async_set_updated_data(data.to_dict())

    @callback
    def _async_set_device_serial(self, serial_number: str) -> None:
        dev_reg = dr.async_get(self.hass)
        dev_reg.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            serial_number=serial_number,
        )


type SmartMeterConfigEntry = ConfigEntry[SmartMeterCoordinator]
