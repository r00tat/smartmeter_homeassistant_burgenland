"""Take over the sensors of the Smartmeter add-on.

The add-on publishes its sensors via MQTT discovery: one device with the
identifier ``("mqtt", <device_id>)`` and sensors with the unique id
``<device_id><suffix>``. The integration uses the same suffixes behind its
config entry id, so every add-on sensor maps to exactly one integration
sensor.

Dashboards, automations, the energy dashboard, history and long-term
statistics all refer to the entity id. The migration therefore removes the
add-on's registry entries (the MQTT integration then clears the retained
discovery message) and registers the integration's sensors under the old
entity ids, keeping the user's settings.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback, split_entity_id
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DEVICE_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

MQTT_DOMAIN = "mqtt"
SENSOR_DOMAIN = "sensor"
# An add-on sensor that reported within this window means the add-on still
# reads the meter.
ADDON_ACTIVE_SECONDS = 60
# How long to wait for the removed add-on entities to leave the state machine.
STATE_REMOVAL_TIMEOUT = 5.0


@dataclass(frozen=True)
class AddonDevice:
    """An MQTT device created by the add-on, with the sensors that map."""

    device_id: str  # device registry id
    name: str
    entities: dict[str, str]  # sensor suffix -> add-on entity id


def sensor_suffixes(profile: Any) -> list[str]:
    """Suffixes of the integration's sensors for a meter profile."""
    return [spec.suffix for spec in profile.sensor_specs if not spec.raw]


@callback
def async_find_addon_devices(hass: HomeAssistant, suffixes: Iterable[str]) -> list[AddonDevice]:
    """Find add-on MQTT devices whose sensors match the given suffixes."""
    suffixes = [suffix for suffix in suffixes if suffix]
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    found: list[AddonDevice] = []
    devices = {
        device.id: device
        for mqtt_entry in hass.config_entries.async_entries(MQTT_DOMAIN)
        for device in dr.async_entries_for_config_entry(dev_reg, mqtt_entry.entry_id)
    }
    for device in devices.values():
        prefixes = [ident for domain, ident in device.identifiers if domain == MQTT_DOMAIN]
        if not prefixes:
            continue
        unique_ids = {
            entry.unique_id: entry.entity_id
            for entry in er.async_entries_for_device(
                ent_reg, device.id, include_disabled_entities=True
            )
            if entry.platform == MQTT_DOMAIN and entry.domain == SENSOR_DOMAIN
        }
        for prefix in prefixes:
            mapping = {
                suffix: unique_ids[prefix + suffix]
                for suffix in suffixes
                if prefix + suffix in unique_ids
            }
            if mapping:
                found.append(
                    AddonDevice(
                        device_id=device.id,
                        name=device.name_by_user or device.name or prefix,
                        entities=mapping,
                    )
                )
                break
    return sorted(found, key=lambda device: device.name)


@callback
def async_addon_active(hass: HomeAssistant, device: AddonDevice) -> bool:
    """Return True if one of the add-on's sensors reported recently."""
    cutoff = dt_util.utcnow() - timedelta(seconds=ADDON_ACTIVE_SECONDS)
    for entity_id in device.entities.values():
        state = hass.states.get(entity_id)
        if (
            state is not None
            and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)
            and state.last_reported >= cutoff
        ):
            return True
    return False


async def _async_wait_for_states_removed(hass: HomeAssistant, entity_ids: list[str]) -> None:
    """Wait until removed entities left the state machine, so their ids are free."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + STATE_REMOVAL_TIMEOUT
    while loop.time() < deadline:
        if all(hass.states.get(entity_id) is None for entity_id in entity_ids):
            return
        await asyncio.sleep(0.05)
    for entity_id in entity_ids:
        if hass.states.get(entity_id) is not None:
            _LOGGER.debug("Removing leftover state of %s", entity_id)
            hass.states.async_remove(entity_id)


async def async_migrate_from_addon(
    hass: HomeAssistant, entry: ConfigEntry, profile: Any, addon_device_id: str
) -> None:
    """Move the add-on's sensors (entity ids and settings) to this entry."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    old_device = dev_reg.async_get(addon_device_id)
    if old_device is None:
        _LOGGER.warning("Add-on device %s no longer exists, nothing to migrate", addon_device_id)
        return

    addon = next(
        (
            device
            for device in async_find_addon_devices(hass, sensor_suffixes(profile))
            if device.device_id == addon_device_id
        ),
        None,
    )
    old_entries: dict[str, er.RegistryEntry] = {}
    if addon is not None:
        for suffix, entity_id in addon.entities.items():
            if (old := ent_reg.async_get(entity_id)) is not None:
                old_entries[suffix] = old

    # Remove every entity of the add-on device (also the ones without a
    # counterpart, e.g. the raw data sensor) and the device itself. The MQTT
    # integration clears the retained discovery message of removed entities,
    # so they are not rediscovered as long as the add-on stays stopped.
    removed = [
        entity.entity_id
        for entity in er.async_entries_for_device(
            ent_reg, addon_device_id, include_disabled_entities=True
        )
    ]
    # When the take-over runs for an existing entry (options flow), the
    # integration already registered these sensors under new entity ids.
    # Drop them so the add-on's ids can be used; their short history stays
    # in the database under the dropped ids.
    for suffix in old_entries:
        existing = ent_reg.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, f"{entry.entry_id}{suffix}")
        if existing is not None:
            removed.append(existing)
    for entity_id in removed:
        ent_reg.async_remove(entity_id)
    # The MQTT integration may already have dropped the now empty device.
    if dev_reg.async_get(addon_device_id) is not None:
        dev_reg.async_remove_device(addon_device_id)
    await _async_wait_for_states_removed(hass, removed)

    new_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=DEVICE_NAME,
        manufacturer=profile.manufacturer,
        model=profile.model,
    )
    # Settings of the add-on device win, but do not wipe settings the user
    # already made on an existing integration device.
    dev_reg.async_update_device(
        new_device.id,
        name=DEVICE_NAME,
        area_id=old_device.area_id or new_device.area_id,
        name_by_user=old_device.name_by_user or new_device.name_by_user,
        labels=set(old_device.labels) | set(new_device.labels),
    )

    for suffix, old in old_entries.items():
        _, object_id = split_entity_id(old.entity_id)
        new = ent_reg.async_get_or_create(
            SENSOR_DOMAIN,
            DOMAIN,
            f"{entry.entry_id}{suffix}",
            config_entry=entry,
            device_id=new_device.id,
            suggested_object_id=object_id,
            disabled_by=old.disabled_by,
            hidden_by=old.hidden_by,
        )
        # The registry restores the entity id of a deleted entry with the
        # same unique id (options flow: the sensor removed above) and then
        # ignores the suggestion, so rename explicitly.
        if (
            new.entity_id != old.entity_id
            and not ent_reg.async_is_registered(old.entity_id)
            and hass.states.get(old.entity_id) is None
        ):
            new = ent_reg.async_update_entity(new.entity_id, new_entity_id=old.entity_id)
        if new.entity_id != old.entity_id:
            _LOGGER.warning(
                "Entity id %s is taken, the sensor is registered as %s instead",
                old.entity_id,
                new.entity_id,
            )
        ent_reg.async_update_entity(
            new.entity_id,
            name=old.name,
            icon=old.icon,
            area_id=old.area_id,
            aliases=old.aliases,
            labels=set(old.labels),
            categories=dict(old.categories),
            device_class=old.device_class,
        )
        # Keep the unit the add-on reported (e.g. Wh), so states, templates and
        # cards show the same numbers as before. The user can switch to kWh in
        # the entity settings; long-term statistics are converted.
        sensor_options = dict(old.options.get(SENSOR_DOMAIN, {}))
        if old.unit_of_measurement and "unit_of_measurement" not in sensor_options:
            sensor_options["unit_of_measurement"] = old.unit_of_measurement
        if sensor_options:
            ent_reg.async_update_entity_options(new.entity_id, SENSOR_DOMAIN, sensor_options)

    _LOGGER.info(
        "Took over %d sensors from the add-on device %s, removed %d add-on entities",
        len(old_entries),
        old_device.name_by_user or old_device.name,
        len(removed),
    )
