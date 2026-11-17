"""Home-Assistant-facing MQTT device publisher.

The ``SmartMeterDevice`` is meter-profile agnostic: at construction time
it receives the sensor catalog and device metadata from the selected
``MeterProfile``. Any ``MeterData``-like object that exposes ``to_json``
and an optional ``meter_id`` can be published.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from smartmeter_austria.profile import MeterProfile, get_profile
from smartmeter_austria.sensor_spec import SensorSpec

from ..config import get_sw_version
from .client import Message, MqttClient

log = logging.getLogger("meter.mqtt.device")


class _MeterDataLike(Protocol):
    meter_id: str | None

    def to_json(self) -> str: ...


# Re-exported for backward compatibility with callers that imported
# ``SensorSpec`` / ``SENSOR_SPECS`` from this module before the profile
# refactor.
__all__ = ["SensorSpec", "SENSOR_SPECS", "SmartMeterDevice"]

# Default catalog = Burgenland catalog – existing deployments see the
# exact list they always did.
SENSOR_SPECS = get_profile("burgenland").sensor_specs


class SmartMeterDevice(MqttClient):
    """SmartMeterDevice extends the functionality to publish the values at once with json."""

    def __init__(
        self,
        config: dict,
        profile: MeterProfile | None = None,
    ) -> None:
        super().__init__(config)

        self.profile = profile or get_profile("burgenland")
        self.sensors_migrated = config.get("sensors_migrated", False)
        self.serial_number = ""
        self.sw_version = get_sw_version()
        self.available = True

    def publish_status(self, data: _MeterDataLike) -> None:
        """Publish the current status from meter data"""
        was_available = self.available
        self.available = True
        if self.serial_number == "" and data.meter_id:
            # Discovery again, now with the serial number (and "online").
            self.serial_number = data.meter_id
            self.ha_discovery()
        elif not was_available:
            self.set_available(True)
        self.publish(self.topic_with_prefix("state"), data.to_json())

    def set_available(self, available: bool) -> None:
        """Mark the sensors (un)available, e.g. while the meter is silent."""
        self.available = available
        self.publish(
            self.topic_with_prefix("availability"), "online" if available else "offline"
        )

    @property
    def mqtt_device(self) -> dict[str, Any]:
        return {
            "identifiers": [self.device_id],
            "name": "Smart Meter",
            "mf": self.profile.manufacturer,
            "mdl": self.profile.model,
            "sw": self.sw_version,
            "sn": self.serial_number,
        }

    def discovery_messages(self) -> list[Message]:
        components = {}

        for device in self.devices():
            components[device.get("unique_id")] = device | {
                "state_topic": f"{self.base_topic}/state",
                "p": "sensor",
                "name": (
                    f"{self.config.get('name', 'Smart Meter')} {device.get('name')}"
                ),
                "device": self.mqtt_device,
            }

        messages = [] if self.sensors_migrated else self.migration_messages()
        messages.append((
            f"homeassistant/device/{self.device_id}/config",
            json.dumps(
                {
                    "device": self.mqtt_device,
                    "o": {
                        "name": "smartmeter_homeassistant_burgenland",
                        "sw": self.sw_version,
                        "url": "https://github.com/r00tat/smartmeter_homeassistant_burgenland",
                    },
                    "components": components,
                }
            ),
            False,
        ))
        messages.append(
            (
                f"{self.base_topic}/availability",
                "online" if self.available else "offline",
                False,
            )
        )
        return messages

    def migration_messages(self) -> list[Message]:
        """Migrate the legacy single-component sensors to device discovery.

        Home Assistant validates migration messages against a schema that
        allows the ``migrate_discovery`` key and nothing else, so any extra
        option in the payload makes it reject the whole message and log a
        warning. Publish the bare flag to every legacy discovery topic.
        """
        migrate_payload = json.dumps({"migrate_discovery": True})
        messages: list[Message] = [
            (f"homeassistant/sensor/{self.device_id}/config", migrate_payload, False)
        ]
        for device in self.devices()[1:]:
            messages.append(
                (
                    f"homeassistant/sensor/{self.device_id}_{device.get('unique_id')}/config",
                    migrate_payload,
                    False,
                )
            )
        return messages

    def _spec_to_device(self, spec: SensorSpec) -> dict[str, Any]:
        if spec.raw:
            return {
                "name": spec.name,
                "state_topic": f"{self.base_topic}/state",
                "availability_topic": f"{self.base_topic}/availability",
                "unique_id": self.device_id,
            }
        entry: dict[str, Any] = {
            "name": spec.name,
            "unique_id": f"{self.device_id}{spec.suffix}",
        }
        if spec.value_template is not None:
            entry["value_template"] = spec.value_template
        if spec.unit_of_measurement is not None:
            entry["unit_of_measurement"] = spec.unit_of_measurement
        if spec.device_class is not None:
            entry["device_class"] = spec.device_class
        if spec.state_class is not None:
            entry["state_class"] = spec.state_class
        if spec.enabled_by_default is not None:
            entry["enabled_by_default"] = spec.enabled_by_default
        return entry

    def devices(self) -> list[dict[str, Any]]:
        """List sensor dicts for Home Assistant discovery."""
        return [self._spec_to_device(spec) for spec in self.profile.sensor_specs]
