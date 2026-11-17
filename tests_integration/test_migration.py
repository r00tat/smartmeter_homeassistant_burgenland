"""Tests for taking over the sensors of the Smartmeter add-on (MQTT)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from custom_components.smartmeter_at.const import (
    CONF_ADDON_DEVICE,
    CONF_MIGRATE,
    DOMAIN,
)

from .conftest import ENTRY_DATA, sample_reading, wait_for_data

FLOW = "custom_components.smartmeter_at.config_flow"
ADDON_DEVICE_ID = "smartmeter"
# Entity ids the add-on's discovery gets on a current Home Assistant.
OLD_ENERGY = "sensor.smart_meter_smart_meter_total_energy_consumed"
OLD_ANGLE = "sensor.smart_meter_smart_meter_angle_between_voltage_l1_to_current_l1"
OLD_RAW = "sensor.smart_meter_smart_meter_raw_data"

# The MQTT integration keeps a periodic timer running after the test.
pytestmark = pytest.mark.parametrize("expected_lingering_timers", [True])


def addon_discovery(device_id: str = ADDON_DEVICE_ID) -> list[tuple[str, str]]:
    """The discovery messages the add-on publishes, built by its own code."""
    from custom_components.smartmeter_at.meter.mqtt import device as mqtt_device
    from custom_components.smartmeter_at.meter.profile import get_profile

    with patch.object(mqtt_device, "get_sw_version", return_value="0.8.1"):
        device = mqtt_device.SmartMeterDevice(
            {"host": "mqtt.local", "device_id": device_id, "sensors_migrated": True},
            get_profile("burgenland"),
        )
    device.serial_number = "1LGZ0012345678"
    return [(topic, payload) for topic, payload, _ in device.discovery_messages()]


@pytest.fixture
async def addon(hass: HomeAssistant, mock_hass_config: None, mqtt_mock_entry) -> Any:
    """MQTT set up with the add-on's sensors discovered (add-on stopped)."""
    mqtt_mock = await mqtt_mock_entry()
    for topic, payload in addon_discovery():
        async_fire_mqtt_message(hass, topic, payload)
    await hass.async_block_till_done()
    assert hass.states.get(OLD_ENERGY) is not None
    return mqtt_mock


def addon_device(hass: HomeAssistant) -> dr.DeviceEntry:
    mqtt_entry = hass.config_entries.async_entries("mqtt")[0]
    device = dr.async_get(hass).async_get_device_by_identifier(
        ("mqtt", ADDON_DEVICE_ID), mqtt_entry.entry_id
    )
    assert device is not None
    return device


async def _flow_to_migrate_step(hass: HomeAssistant) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with (
        patch(f"{FLOW}.async_list_ports", return_value=["/dev/ttyUSB0"]),
        patch(f"{FLOW}.async_check_port", return_value=None),
        patch(f"{FLOW}.async_probe", return_value=sample_reading()),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "migrate"
    return result


@pytest.fixture
def no_setup():
    with patch("custom_components.smartmeter_at.async_setup_entry", return_value=True):
        yield


async def test_flow_offers_takeover_and_stores_device(
    hass: HomeAssistant, addon: Any, no_setup: None
) -> None:
    result = await _flow_to_migrate_step(hass)
    assert result["description_placeholders"]["count"] == "13"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MIGRATE: True}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {**ENTRY_DATA, CONF_ADDON_DEVICE: addon_device(hass).id}


async def test_flow_without_takeover_keeps_addon(
    hass: HomeAssistant, addon: Any, no_setup: None
) -> None:
    result = await _flow_to_migrate_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MIGRATE: False}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA
    assert hass.states.get(OLD_ENERGY) is not None


async def test_flow_refuses_while_addon_reports(
    hass: HomeAssistant, addon: Any, no_setup: None
) -> None:
    async_fire_mqtt_message(hass, f"{ADDON_DEVICE_ID}/state", sample_reading().to_json())
    await hass.async_block_till_done()
    result = await _flow_to_migrate_step(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MIGRATE: True}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "addon_running"}


async def test_flow_skips_step_without_addon(
    hass: HomeAssistant, mock_hass_config: None, mqtt_mock_entry, no_setup: None
) -> None:
    await mqtt_mock_entry()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with (
        patch(f"{FLOW}.async_list_ports", return_value=["/dev/ttyUSB0"]),
        patch(f"{FLOW}.async_check_port", return_value=None),
        patch(f"{FLOW}.async_probe", return_value=sample_reading()),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_takeover_keeps_entity_ids_settings_and_values(
    hass: HomeAssistant, addon: Any, fake_readers: list
) -> None:
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    old_device = addon_device(hass)
    kitchen = ar.async_get(hass).async_create("Keller")
    dev_reg.async_update_device(old_device.id, area_id=kitchen.id, name_by_user="Zähler")
    # A user-chosen entity id and name must survive as well.
    ent_reg.async_update_entity(
        "sensor.smart_meter_smart_meter_power_consumed",
        new_entity_id="sensor.netzbezug",
        name="Netzbezug",
    )
    await hass.async_block_till_done()
    old_unique_ids = {e.unique_id for e in ent_reg.entities.values() if e.platform == "mqtt"}

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**ENTRY_DATA, CONF_ADDON_DEVICE: old_device.id},
        title="Smart Meter Landis+Gyr E450",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for_data(entry.runtime_data)
    await hass.async_block_till_done()

    # Old ids now belong to the integration.
    energy = ent_reg.async_get(OLD_ENERGY)
    assert energy is not None
    assert energy.platform == DOMAIN
    assert energy.unique_id == f"{entry.entry_id}_total_energy_consumed"
    power = ent_reg.async_get("sensor.netzbezug")
    assert power is not None and power.platform == DOMAIN
    assert power.name == "Netzbezug"
    # Sensors disabled by the add-on stay disabled.
    angle = ent_reg.async_get(OLD_ANGLE)
    assert angle is not None and angle.platform == DOMAIN
    assert angle.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    # Same values and unit as before (Wh), so templates and cards still fit.
    state = hass.states.get(OLD_ENERGY)
    assert state.state == "49244276"
    assert state.attributes["unit_of_measurement"] == "Wh"
    assert hass.states.get("sensor.netzbezug").state == "3314"

    # The add-on device and all its entities are gone, the raw sensor too.
    assert dev_reg.async_get(old_device.id) is None
    assert not [e for e in ent_reg.entities.values() if e.platform == "mqtt"]
    assert hass.states.get(OLD_RAW) is None
    assert old_unique_ids

    # The new device carries over area and name.
    device = dev_reg.async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)
    assert device.area_id == kitchen.id
    assert device.name_by_user == "Zähler"

    # The retained discovery message was cleared, so the add-on sensors do
    # not come back after a restart.
    cleared = [
        call.args
        for call in addon.async_publish.call_args_list
        if call.args[0].startswith("homeassistant/") and not call.args[1]
    ]
    assert cleared
    assert all(args[3] is True for args in cleared)

    # The one-off migration flag is dropped from the entry.
    assert CONF_ADDON_DEVICE not in entry.data


async def test_fresh_setup_uses_short_entity_ids(hass: HomeAssistant, fake_readers: list) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Smart Meter Landis+Gyr E450")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for_data(entry.runtime_data)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.smart_meter_total_energy_consumed") is not None


async def test_options_take_over_replaces_existing_sensors(
    hass: HomeAssistant, addon: Any, fake_readers: list
) -> None:
    """Integration set up without take-over first, take-over later via options."""
    ent_reg = er.async_get(hass)
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Smart Meter Landis+Gyr E450")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for_data(entry.runtime_data)
    await hass.async_block_till_done()
    first_id = ent_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_total_energy_consumed"
    )
    assert first_id is not None and first_id != OLD_ENERGY
    # Both the add-on sensor and the integration sensor exist now.
    assert ent_reg.async_get(OLD_ENERGY).platform == "mqtt"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert CONF_MIGRATE in result["data_schema"].schema
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"update_interval": 20, CONF_MIGRATE: True, CONF_ADDON_DEVICE: addon_device(hass).id},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    await wait_for_data(entry.runtime_data)
    await hass.async_block_till_done()

    energy = ent_reg.async_get(OLD_ENERGY)
    assert energy.platform == DOMAIN
    assert energy.unique_id == f"{entry.entry_id}_total_energy_consumed"
    assert ent_reg.async_get(first_id) is None
    assert hass.states.get(OLD_ENERGY).state == "49244276"
    assert not [e for e in ent_reg.entities.values() if e.platform == "mqtt"]
    # The update interval is kept, the one-off flag is dropped.
    assert entry.options == {"update_interval": 20}


async def test_options_refuse_while_addon_reports(
    hass: HomeAssistant, addon: Any, fake_readers: list
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Smart Meter Landis+Gyr E450")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, f"{ADDON_DEVICE_ID}/state", sample_reading().to_json())
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"update_interval": 10, CONF_MIGRATE: True, CONF_ADDON_DEVICE: addon_device(hass).id},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "addon_running"}


async def test_options_without_addon_only_show_interval(
    hass: HomeAssistant, fake_readers: list
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Smart Meter Landis+Gyr E450")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert list(result["data_schema"].schema) == ["update_interval"]
