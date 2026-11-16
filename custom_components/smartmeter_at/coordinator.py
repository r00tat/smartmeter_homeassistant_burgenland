"""Push coordinator: readings from the reader thread onto the event loop."""

from __future__ import annotations

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
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        self._supervisor = core.supervisor.ReaderSupervisor(
            build_reader_factory(self.profile, entry.data),
            on_data=self._on_data_from_thread,
            on_error=self._on_error_from_thread,
            every=self.profile.readings_per_publish(float(interval)),
        )

    def start(self) -> None:
        self._supervisor.start()

    async def async_stop(self) -> None:
        await self.hass.async_add_executor_job(self._supervisor.stop)

    def _on_data_from_thread(self, data: Any) -> None:
        self.hass.loop.call_soon_threadsafe(self._async_handle_data, data)

    def _on_error_from_thread(self, err: Exception) -> None:
        self.hass.loop.call_soon_threadsafe(self.async_set_update_error, err)

    @callback
    def _async_handle_data(self, data: Any) -> None:
        if data.meter_id and self.meter_id is None:
            self.meter_id = data.meter_id
            self._async_set_device_serial(data.meter_id)
        self.async_set_updated_data(data.to_dict())

    @callback
    def _async_set_device_serial(self, serial_number: str) -> None:
        dev_reg = dr.async_get(self.hass)
        identifier = (DOMAIN, self.config_entry.entry_id)
        if hasattr(dev_reg, "async_get_device_by_identifier"):
            device = dev_reg.async_get_device_by_identifier(
                identifier, self.config_entry.entry_id
            )
        else:  # Home Assistant before the per-entry lookup existed
            device = dev_reg.async_get_device(identifiers={identifier})
        if device is not None:
            dev_reg.async_update_device(device.id, serial_number=serial_number)


type SmartMeterConfigEntry = ConfigEntry[SmartMeterCoordinator]
