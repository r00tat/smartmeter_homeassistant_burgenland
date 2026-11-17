"""Config flow: pick meter, port and key, verify by reading one telegram."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import serial
import serial.tools.list_ports
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_ADDON_DEVICE,
    CONF_INTERFACE_TYPE,
    CONF_KEY,
    CONF_METER_TYPE,
    CONF_MIGRATE,
    CONF_PORT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_INTERFACE_TYPE,
    DEFAULT_METER_TYPE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    INTERFACE_TYPES,
)
from .coordinator import build_reader_factory
from .core import Core, async_load_core
from .migration import (
    AddonDevice,
    async_addon_active,
    async_find_addon_devices,
    sensor_suffixes,
)

_LOGGER = logging.getLogger(__name__)

# Wait for at least three telegrams (Burgenland/NÖ push every 5 s).
PROBE_TELEGRAMS = 3
MIN_PROBE_SECONDS = 10.0
SERIAL_BY_ID = Path("/dev/serial/by-id")


def _list_ports() -> list[str]:
    """Serial ports, preferring the stable /dev/serial/by-id/ name."""
    by_id: dict[str, str] = {}
    if SERIAL_BY_ID.is_dir():
        for link in SERIAL_BY_ID.iterdir():
            by_id[str(link.resolve())] = str(link)
    return sorted(by_id.get(port.device, port.device) for port in serial.tools.list_ports.comports())


async def async_list_ports(hass: HomeAssistant) -> list[str]:
    """List serial ports without blocking the event loop."""
    try:
        return await hass.async_add_executor_job(_list_ports)
    except OSError:
        _LOGGER.warning("Could not list serial ports", exc_info=True)
        return []


def _check_port(port: str) -> None:
    """Open and close the port once; raises ``OSError`` if that fails."""
    serial.Serial(port).close()


async def async_check_port(hass: HomeAssistant, port: str) -> None:
    """Check that the port can be opened (readers reconnect silently otherwise)."""
    await hass.async_add_executor_job(_check_port, port)


async def async_realpath(hass: HomeAssistant, port: str) -> str:
    """Resolve symlinks (e.g. /dev/serial/by-id) without blocking the loop."""
    return await hass.async_add_executor_job(os.path.realpath, port)


async def async_probe(hass: HomeAssistant, core: Core, data: dict[str, Any]) -> Any | None:
    """Read one telegram with the given settings (``None`` on timeout)."""
    profile = core.profile.get_profile(data[CONF_METER_TYPE])
    timeout = max(MIN_PROBE_SECONDS, PROBE_TELEGRAMS * profile.push_interval_seconds)
    return await core.supervisor.probe(build_reader_factory(profile, data), timeout)


def _user_schema(meter_types: list[str], ports: list[str]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_METER_TYPE, default=DEFAULT_METER_TYPE): SelectSelector(
                SelectSelectorConfig(
                    options=meter_types,
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_METER_TYPE,
                )
            ),
            vol.Required(CONF_PORT): SelectSelector(
                SelectSelectorConfig(
                    options=ports, custom_value=True, mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(CONF_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_INTERFACE_TYPE, default=DEFAULT_INTERFACE_TYPE): SelectSelector(
                SelectSelectorConfig(options=INTERFACE_TYPES, translation_key=CONF_INTERFACE_TYPE)
            ),
        }
    )


class SmartMeterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for one smart meter."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._title = ""
        self._addon_devices: list[AddonDevice] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SmartMeterOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        try:
            core = await async_load_core(self.hass)
        except HomeAssistantError:
            _LOGGER.exception("Smartmeter core could not be loaded")
            return self.async_abort(reason="core_unavailable")
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**user_input, CONF_KEY: "".join(user_input[CONF_KEY].split())}
            if not core.config_validation.HEX_KEY_RE.match(data[CONF_KEY]):
                errors[CONF_KEY] = "invalid_key"
            elif await self._port_in_use(data[CONF_PORT]):
                errors[CONF_PORT] = "port_in_use"
            else:
                try:
                    await async_check_port(self.hass, data[CONF_PORT])
                    reading = await async_probe(self.hass, core, data)
                except OSError:  # includes serial.SerialException
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error while probing the meter")
                    errors["base"] = "unknown"
                else:
                    if reading is None:
                        errors["base"] = "no_data"
                    else:
                        await self.async_set_unique_id(reading.meter_id or data[CONF_PORT])
                        self._abort_if_unique_id_configured(updates={CONF_PORT: data[CONF_PORT]})
                        profile = core.profile.get_profile(data[CONF_METER_TYPE])
                        self._data = data
                        self._title = f"Smart Meter {profile.manufacturer} {profile.model}"
                        self._addon_devices = async_find_addon_devices(
                            self.hass, sensor_suffixes(profile)
                        )
                        if self._addon_devices:
                            return await self.async_step_migrate()
                        return self.async_create_entry(title=self._title, data=data)

        ports = await async_list_ports(self.hass)
        schema = self.add_suggested_values_to_schema(
            _user_schema(core.profile.known_meter_types(), ports), user_input
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_migrate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer to take over the sensors of the Smartmeter add-on."""
        devices = {device.device_id: device for device in self._addon_devices}
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_MIGRATE]:
                return self.async_create_entry(title=self._title, data=self._data)
            device = devices[user_input.get(CONF_ADDON_DEVICE, self._addon_devices[0].device_id)]
            if async_addon_active(self.hass, device):
                errors["base"] = "addon_running"
            else:
                return self.async_create_entry(
                    title=self._title, data={**self._data, CONF_ADDON_DEVICE: device.device_id}
                )

        fields: dict[Any, Any] = {vol.Required(CONF_MIGRATE, default=True): BooleanSelector()}
        if len(self._addon_devices) > 1:
            fields[
                vol.Required(CONF_ADDON_DEVICE, default=self._addon_devices[0].device_id)
            ] = _addon_device_selector(self._addon_devices)
        first = self._addon_devices[0]
        return self.async_show_form(
            step_id="migrate",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), user_input),
            errors=errors,
            description_placeholders={
                "device": first.name,
                "count": str(len(first.entities)),
            },
        )

    async def _port_in_use(self, port: str) -> bool:
        """Return True if an entry already reads this device (never open it twice)."""
        wanted = await async_realpath(self.hass, port)
        for entry in self._async_current_entries(include_ignore=False):
            if await async_realpath(self.hass, entry.data[CONF_PORT]) == wanted:
                return True
        return False


class SmartMeterOptionsFlow(OptionsFlow):
    """Options flow for the update interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        addon_devices = await self._async_addon_devices()
        errors: dict[str, str] = {}
        if user_input is not None:
            options: dict[str, Any] = {
                CONF_UPDATE_INTERVAL: int(user_input[CONF_UPDATE_INTERVAL])
            }
            if addon_devices and user_input.get(CONF_MIGRATE):
                devices = {device.device_id: device for device in addon_devices}
                device = devices[user_input.get(CONF_ADDON_DEVICE, addon_devices[0].device_id)]
                if async_addon_active(self.hass, device):
                    errors["base"] = "addon_running"
                else:
                    # Picked up by async_setup_entry on the reload that saving
                    # the options triggers, then dropped again.
                    options[CONF_ADDON_DEVICE] = device.device_id
            if not errors:
                return self.async_create_entry(data=options)

        fields: dict[Any, Any] = {
            vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=3600, step=1, unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            )
        }
        if addon_devices:
            fields[vol.Required(CONF_MIGRATE, default=False)] = BooleanSelector()
            fields[
                vol.Required(CONF_ADDON_DEVICE, default=addon_devices[0].device_id)
            ] = _addon_device_selector(addon_devices)
        schema = vol.Schema(fields)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or self.config_entry.options
            ),
            errors=errors,
        )

    async def _async_addon_devices(self) -> list[AddonDevice]:
        """Add-on MQTT devices whose sensors match this entry's meter."""
        try:
            core = await async_load_core(self.hass)
        except HomeAssistantError:
            return []
        profile = core.profile.get_profile(self.config_entry.data[CONF_METER_TYPE])
        return async_find_addon_devices(self.hass, sensor_suffixes(profile))


def _addon_device_selector(devices: list[AddonDevice]) -> SelectSelector:
    """Select an add-on device, labelled with its name and matching sensor count."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(
                    value=device.device_id, label=f"{device.name} ({len(device.entities)})"
                )
                for device in devices
            ]
        )
    )
