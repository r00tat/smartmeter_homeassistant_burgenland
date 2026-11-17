"""Smartmeter Austria: read Austrian smart meters directly from the serial port."""

from __future__ import annotations

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .const import CONF_ADDON_DEVICE
from .coordinator import SmartMeterConfigEntry, SmartMeterCoordinator
from .core import async_load_core
from .migration import async_migrate_from_addon

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: SmartMeterConfigEntry) -> bool:
    """Set up a config entry: load the core, start the coordinator."""
    core = await async_load_core(hass)
    coordinator = SmartMeterCoordinator(hass, entry, core)
    entry.runtime_data = coordinator

    # Take over the add-on's sensors: requested by the config flow (data) or
    # later in the options flow (options). One-off, before the sensors are
    # added: they must be registered under the add-on's entity ids. Updating
    # the entry does not reload it, the update listener is only added below.
    addon_device = entry.data.get(CONF_ADDON_DEVICE) or entry.options.get(CONF_ADDON_DEVICE)
    if addon_device:
        await async_migrate_from_addon(hass, entry, coordinator.profile, addon_device)
        hass.config_entries.async_update_entry(
            entry,
            data={k: v for k, v in entry.data.items() if k != CONF_ADDON_DEVICE},
            options={k: v for k, v in entry.options.items() if k != CONF_ADDON_DEVICE},
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Start after the platforms so the device exists when the first reading
    # (with the meter serial number) arrives.
    coordinator.async_start()

    async def _async_stop(_event: Event) -> None:
        await coordinator.async_stop()

    entry.async_on_unload(hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, _async_stop))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmartMeterConfigEntry) -> bool:
    """Unload a config entry, stop the reader and close the port."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: SmartMeterConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
