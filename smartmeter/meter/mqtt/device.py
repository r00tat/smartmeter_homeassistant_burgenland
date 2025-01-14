import json
import logging

from ..bgld.data import MeterData
from .client import MqttClient

log = logging.getLogger("meter.mqtt.device")


class SmartMeterDevice(MqttClient):
    """SmartMeterDevice extends the functionality to publish the values at once with json."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)

    def publish_status(self, data: MeterData):
        """Publish the current status from meter data"""
        self.publish(self.topic_with_prefix("state"), data.to_json())

    @property
    def mqtt_device(self):
        return (
            {
                "ids": [self.device_id],
                "name": "Smart Meter",
                "mf": "Landis+Gyr",
                "mdl": "E450",
                "sw": "1.0",
            },
        )

    def ha_discovery(self) -> None:
        super().ha_discovery()

        log.info("publishing additional sensors")
        components = {}
        for device in self.devices():
            components[device.get("unique_id")] = device | {
                "~": self.base_topic,
                "state_topic": "~/state",
                "p": "sensor",
                #  'retain': True,
                "name": (
                    f"{self.config.get('name','Smart Meter')} " f"{device.get('name')}"
                ),
            }
            self.publish(
                (
                    f"homeassistant/sensor/f{self.device_id}"
                    f"{device.get('unique_id')}/config"
                ),
                json.dumps(
                    device
                    | {
                        "~": self.base_topic,
                        "state_topic": "~/state",
                        #  'retain': True,
                        "name": (
                            f"{self.config.get('','Smart Meter')} "
                            f"{device.get('name')}"
                        ),
                        "migrate_discovery": True,
                        "device": self.mqtt_device,
                    }
                ),
            )

        log.info("publishing home assistant auto discovery")
        self.publish(
            f"homeassistant/device/{self.device_id}/config",
            json.dumps(
                {
                    "dev": self.mqtt_device,
                    "o": {
                        "name": "smartmeter_homeassistant_burgenland",
                        "sw": "0.2.0",
                        "url": "https://github.com/r00tat/smartmeter_homeassistant_burgenland",
                    },
                    "cmps": components,
                }
            ),
        )

    def devices(self):
        """List devices"""
        return [
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
