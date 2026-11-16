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
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_INTERFACE_TYPE,
    CONF_KEY,
    CONF_METER_TYPE,
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
    return await hass.async_add_executor_job(
        core.supervisor.probe, build_reader_factory(profile, data), timeout
    )


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
                        return self.async_create_entry(
                            title=f"Smart Meter {profile.manufacturer} {profile.model}",
                            data=data,
                        )

        ports = await async_list_ports(self.hass)
        schema = self.add_suggested_values_to_schema(
            _user_schema(core.profile.known_meter_types(), ports), user_input
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

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
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_UPDATE_INTERVAL: int(user_input[CONF_UPDATE_INTERVAL])}
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=3600, step=1, unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
