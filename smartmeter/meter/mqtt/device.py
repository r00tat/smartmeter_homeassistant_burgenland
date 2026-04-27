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

from ..config import get_sw_version
from ..profile import MeterProfile, get_profile
from .client import MqttClient
from .sensor_spec import SensorSpec

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

    def publish_status(self, data: _MeterDataLike) -> None:
        """Publish the current status from meter data"""
        self.publish(self.topic_with_prefix("state"), data.to_json())
        if self.serial_number == "" and data.meter_id:
            self.serial_number = data.meter_id
            self.ha_discovery()

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

    def ha_discovery(self) -> None:
        log.info("publishing additional sensors")
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

        if not self.sensors_migrated:
            self.migrate_old_sensors()

        log.info("publishing home assistant auto discovery")
        self.publish(
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
        )

        log.info("setting sensor to online")
        self.publish(f"{self.base_topic}/availability", "online")

    def migrate_old_sensors(self) -> None:
        """Migrate sensors to a device."""
        log.info("migrating old sensors")
        self.publish(
            f"homeassistant/sensor/{self.device_id}/config",
            json.dumps(
                {
                    "migrate_discovery": True,
                    "device": self.mqtt_device,
                    "state_topic": f"{self.base_topic}/state",
                }
            ),
        )
        self.publish(
            f"homeassistant/sensor/{self.device_id}/config",
            json.dumps(
                {
                    "migrate_discovery": True,
                }
            ),
        )
        for device in self.devices()[1:]:
            self.publish(
                f"homeassistant/sensor/{self.device_id}_{device.get('unique_id')}/config",
                json.dumps(
                    {
                        "migrate_discovery": True,
                        "unique_id": device["unique_id"],
                        "device": self.mqtt_device,
                        "state_topic": f"{self.base_topic}/state",
                        "value_template": device["value_template"],
                    }
                ),
            )
            self.publish(
                f"homeassistant/sensor/{self.device_id}_{device.get('unique_id')}/config",
                json.dumps(
                    {
                        "migrate_discovery": True,
                    }
                ),
            )

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
