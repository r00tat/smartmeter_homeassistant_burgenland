"""Config flow placeholder, replaced by the real flow in the config flow task."""

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class SmartMeterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Minimal flow so entries can be set up in tests until the real one lands."""

    VERSION = 1
