"""Config flow: pick meter, port and key, verify by reading one telegram."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import serial.tools.list_ports
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
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
    return await hass.async_add_executor_job(_list_ports)


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
        core = await async_load_core(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**user_input, CONF_KEY: user_input[CONF_KEY].strip()}
            if not core.config_validation.HEX_KEY_RE.match(data[CONF_KEY]):
                errors[CONF_KEY] = "invalid_key"
            else:
                try:
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
                        self._abort_if_unique_id_configured()
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


class SmartMeterOptionsFlow(OptionsFlow):
    """Options flow for the update interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
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
