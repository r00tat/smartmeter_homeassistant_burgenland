import json
import logging
from dataclasses import dataclass

from ..bgld.data import MeterData
from ..config import get_sw_version
from .client import MqttClient

log = logging.getLogger("meter.mqtt.device")


@dataclass(frozen=True)
class SensorSpec:
    """Static description of a Home Assistant MQTT sensor for this device."""

    name: str
    suffix: str  # appended to device_id for unique_id; empty means use device_id
    value_template: str | None = None
    unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    enabled_by_default: bool | None = None
    raw: bool = False  # the 'Raw Data' sensor has a different shape


SENSOR_SPECS: tuple[SensorSpec, ...] = (
    SensorSpec(name="Raw Data", suffix="", raw=True),
    SensorSpec(
        name="Total Energy consumed",
        suffix="_total_energy_consumed",
        value_template="{{ value_json.total_con }}",
        unit_of_measurement="Wh",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorSpec(
        name="Total Energy provided",
        suffix="_total_energy_provided",
        value_template="{{ value_json.total_prov }}",
        unit_of_measurement="Wh",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorSpec(
        name="Power consumed",
        suffix="_power_consumed",
        value_template="{{ value_json.w_con }}",
        unit_of_measurement="W",
        device_class="power",
        state_class="measurement",
    ),
    SensorSpec(
        name="Power provided",
        suffix="_power_provided",
        value_template="{{ value_json.w_prov }}",
        unit_of_measurement="W",
        device_class="power",
        state_class="measurement",
    ),
    SensorSpec(
        name="Voltage L1",
        suffix="_voltage_l1",
        value_template="{{ value_json.u1 }}",
        unit_of_measurement="V",
        device_class="voltage",
        state_class="measurement",
    ),
    SensorSpec(
        name="Voltage L2",
        suffix="_voltage_l2",
        value_template="{{ value_json.u2 }}",
        unit_of_measurement="V",
        device_class="voltage",
        state_class="measurement",
    ),
    SensorSpec(
        name="Voltage L3",
        suffix="_voltage_l3",
        value_template="{{ value_json.u3 }}",
        unit_of_measurement="V",
        device_class="voltage",
        state_class="measurement",
    ),
    SensorSpec(
        name="Current L1",
        suffix="_current_l1",
        value_template="{{ value_json.i1 }}",
        unit_of_measurement="A",
        device_class="current",
        state_class="measurement",
    ),
    SensorSpec(
        name="Current L2",
        suffix="_current_l2",
        value_template="{{ value_json.i2 }}",
        unit_of_measurement="A",
        device_class="current",
        state_class="measurement",
    ),
    SensorSpec(
        name="Current L3",
        suffix="_current_l3",
        value_template="{{ value_json.i3 }}",
        unit_of_measurement="A",
        device_class="current",
        state_class="measurement",
    ),
    SensorSpec(
        name="Angle between voltage L1 to current L1",
        suffix="_angle_l1",
        value_template="{{ value_json.angle1 }}",
        unit_of_measurement="°",
        state_class="measurement",
        enabled_by_default=False,
    ),
    SensorSpec(
        name="Angle between voltage L2 to current L3",
        suffix="_angle_l2",
        value_template="{{ value_json.angle2 }}",
        unit_of_measurement="°",
        state_class="measurement",
        enabled_by_default=False,
    ),
    SensorSpec(
        name="Angle between voltage L3 to current L3",
        suffix="_angle_l3",
        value_template="{{ value_json.angle3 }}",
        unit_of_measurement="°",
        state_class="measurement",
        enabled_by_default=False,
    ),
)


class SmartMeterDevice(MqttClient):
    """SmartMeterDevice extends the functionality to publish the values at once with json."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)

        self.sensors_migrated = config.get("sensors_migrated", False)
        self.serial_number = ""
        self.sw_version = get_sw_version()

    def publish_status(self, data: MeterData):
        """Publish the current status from meter data"""
        self.publish(self.topic_with_prefix("state"), data.to_json())
        if self.serial_number == "" and data.meter_id:
            self.serial_number = data.meter_id
            self.ha_discovery()

    @property
    def mqtt_device(self):
        return {
            "identifiers": [self.device_id],
            "name": "Smart Meter",
            "mf": "Landis+Gyr",
            "mdl": "E450",
            "sw": self.sw_version,
            "sn": self.serial_number,
        }

    def ha_discovery(self) -> None:
        # super().ha_discovery()

        log.info("publishing additional sensors")
        components = {}

        for device in self.devices():
            components[device.get("unique_id")] = device | {
                # "~": self.base_topic,
                "state_topic": f"{self.base_topic}/state",
                "p": "sensor",
                #  'retain': True,
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
                    # "migrate_discovery": True
                }
            ),
        )

        log.info("setting sensor to online")
        self.publish(f"{self.base_topic}/availability", "online")

    def migrate_old_sensors(self):
        """Migrate sensors to a device."""
        log.info("migrating old sensors")
        # to be removed later on
        self.publish(
            f"homeassistant/sensor/{self.device_id}/config",
            json.dumps(
                {
                    "migrate_discovery": True,
                    # "unique_id": self.device_id,
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

    def _spec_to_device(self, spec: SensorSpec) -> dict:
        if spec.raw:
            return {
                "name": spec.name,
                "state_topic": f"{self.base_topic}/state",
                "availability_topic": f"{self.base_topic}/availability",
                "unique_id": self.device_id,
            }
        entry: dict = {
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

    def devices(self) -> list[dict]:
        """List sensor dicts for Home Assistant discovery."""
        return [self._spec_to_device(spec) for spec in SENSOR_SPECS]
