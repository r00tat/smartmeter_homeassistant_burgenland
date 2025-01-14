import json
import logging

from ..bgld.data import MeterData
from ..config import get_sw_version
from .client import MqttClient

log = logging.getLogger("meter.mqtt.device")


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
                    f"{self.config.get('name','Smart Meter')} " f"{device.get('name')}"
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
                (
                    f"homeassistant/sensor/f{self.device_id}"
                    f"{device.get('unique_id')}/config"
                ),
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
                (
                    f"homeassistant/sensor/f{self.device_id}"
                    f"{device.get('unique_id')}/config"
                ),
                json.dumps(
                    {
                        "migrate_discovery": True,
                    }
                ),
            )

    def devices(self):
        """List devices"""
        return [
            {
                # "~": self.base_topic,
                "name": "Raw Data",
                "state_topic": f"{self.base_topic}/state",
                "availability_topic": f"{self.base_topic}/availability",
                # "retain": True,
                "unique_id": self.device_id,
            },
            {
                "name": "Total Energy consumed",
                "unique_id": f"{self.device_id}_total_energy_consumed",
                "value_template": "{{ value_json.total_consumed }}",
                "unit_of_measurement": "Wh",
                "device_class": "energy",
                "state_class": "total_increasing",
            },
            {
                "name": "Total Energy provided",
                "unique_id": f"{self.device_id}_total_energy_provided",
                "value_template": "{{ value_json.total_provided }}",
                "unit_of_measurement": "Wh",
                "device_class": "energy",
                "state_class": "total_increasing",
            },
            {
                "name": "Power consumed",
                "unique_id": f"{self.device_id}_power_consumed",
                "value_template": "{{ value_json.power_consumed }}",
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            },
            {
                "name": "Power provided",
                "unique_id": f"{self.device_id}_power_provided",
                "value_template": "{{ value_json.power_provided }}",
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            },
            {
                "name": "Voltage L1",
                "unique_id": f"{self.device_id}_voltage_l1",
                "value_template": "{{ value_json.voltage_l1 }}",
                "unit_of_measurement": "V",
                "device_class": "voltage",
                "state_class": "measurement",
            },
            {
                "name": "Voltage L1",
                "unique_id": f"{self.device_id}_voltage_l1",
                "value_template": "{{ value_json.voltage_l1 }}",
                "unit_of_measurement": "V",
                "device_class": "voltage",
                "state_class": "measurement",
            },
            {
                "name": "Voltage L2",
                "unique_id": f"{self.device_id}_voltage_l2",
                "value_template": "{{ value_json.voltage_l2 }}",
                "unit_of_measurement": "V",
                "device_class": "voltage",
                "state_class": "measurement",
            },
            {
                "name": "Voltage L3",
                "unique_id": f"{self.device_id}_voltage_l3",
                "value_template": "{{ value_json.voltage_l3 }}",
                "unit_of_measurement": "V",
                "device_class": "voltage",
                "state_class": "measurement",
            },
            {
                "name": "Current L1",
                "unique_id": f"{self.device_id}_current_l1",
                "value_template": "{{ value_json.current_l1 }}",
                "unit_of_measurement": "A",
                "device_class": "current",
                "state_class": "measurement",
            },
            {
                "name": "Current L2",
                "unique_id": f"{self.device_id}_current_l2",
                "value_template": "{{ value_json.current_l2 }}",
                "unit_of_measurement": "A",
                "device_class": "current",
                "state_class": "measurement",
            },
            {
                "name": "Current L3",
                "unique_id": f"{self.device_id}_current_l3",
                "value_template": "{{ value_json.current_l3 }}",
                "unit_of_measurement": "A",
                "device_class": "current",
                "state_class": "measurement",
            },
        ]
