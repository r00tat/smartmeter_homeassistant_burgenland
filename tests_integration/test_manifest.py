"""The integration is discoverable by Home Assistant."""

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_custom_components

from custom_components.smartmeter_at.const import DOMAIN


async def test_integration_is_discovered(hass: HomeAssistant) -> None:
    integrations = await async_get_custom_components(hass)
    assert DOMAIN in integrations
    assert integrations[DOMAIN].config_flow is True
