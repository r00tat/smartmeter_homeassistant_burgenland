#!/usr/bin/env python3
# configure a i2c display over MQTT

# pip3 install paho-mqtt
from typing import Callable, Any
import paho.mqtt.client as mqtt
import json
import logging

log = logging.getLogger(__name__)


class MqttClient():

    def __init__(self, config: dict) -> None:
        self.config = config
        self.connect_mqtt()

    def connect_mqtt(self) -> None:
        """setup MQTT connection"""
        log.debug("setup of mqtt connection")
        self.topic_prefix: str = self.config.get('prefix', '')
        self.device_id: str = self.config.get("device_id", "smartmeter")
        self.client: mqtt.Client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.username_pw_set(username=self.config.get('user'),
                                    password=self.config.get('password'))
        self.client.connect(self.config.get('host'),
                            self.config.get('port', 1883),
                            self.config.get('keepalive', 60))

    @property
    def base_topic(self) -> str:
        """get the base topic"""
        return "{}/{}".format(self.topic_prefix, self.device_id).lstrip("/")

    def on_connect(self, client: mqtt.Client, userdata: Any, flags, rc):
        """on connect"""
        log.info("Connected to MQTT with result code " + str(rc))
        if rc != 0:
            raise RuntimeError(
                "MQTT connection failed with error {}".format(rc))
        self.message_callbacks: dict[str, Callable[[], None]] = {}

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        # client.subscribe("$SYS/#")
        # self.subscribe(self.topic_with_prefix("config"), self.display_config)
        # self.subscribe(self.topic_with_prefix("set"), self.set_display)
        # self.subscribe(self.topic_with_prefix("backlight/set"),
        #                self.display_backlight)
        self.publish(self.topic_with_prefix("availability"), "online")

        self.ha_discovery()

    def ha_discovery(self) -> None:
        """
        Home Assistant auto discovery

        @see https://www.home-assistant.io/integrations/mqtt/#sensors
        @see https://www.home-assistant.io/integrations/sensor.mqtt/
        @see https://www.home-assistant.io/integrations/sensor/#device-class
        """
        log.info("publishing home assistant auto discovery")
        self.publish(
            f"homeassistant/sensor/{self.device_id}/config",
            json.dumps({
                '~': self.base_topic,
                'name': self.config.get('name', 'Smart Meter'),
                'state_topic': '~/state',
                'availability_topic': '~/availability',
                'retain': True,
                'unique_id': self.device_id,
            }))
        log.info("setting sensor to online")
        self.publish(f"{self.base_topic}/availability", "online")

    def publish(self,
                topic: str,
                payload=None,
                qos: int = 0,
                retain: bool = False,
                properties=None):
        log.debug("publishing mqtt message to %s: %s", topic, str(payload))
        self.client.publish(topic, payload, qos, retain, properties)

    def subscribe(self, topic: str, callback: Callable[[mqtt.MQTTMessage],
                                                       None]) -> None:
        """subscribe to a MQTT topic"""
        log.info("subscribing to %s", topic)
        self.client.subscribe(topic)
        if callback:
            self.message_callbacks[topic] = callback

    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client: mqtt.Client, userdata: Any,
                   msg: mqtt.MQTTMessage):
        """new message received"""
        log.info("got a message %s %s", msg.topic, str(msg.payload))

        if self.message_callbacks[msg.topic]:
            self.message_callbacks[msg.topic](msg)

    def topic_with_prefix(self, topic: str) -> str:
        return "{}/{}".format(self.base_topic, topic)

    def start(self):
        """start mqtt processor"""
        # Blocking call that processes network traffic, dispatches callbacks
        # and handles reconnecting.
        # Other loop*() functions are available that give a threaded interface
        # and a manual interface.
        try:
            log.info("starting mqtt loop")
            self.client.loop_forever()
        except:  # noqa
            log.exception("loop interrupted")
            self.stop()

    def stop(self) -> None:
        """shutdown"""
        if self.client:
            try:
                self.publish(self.topic_with_prefix("availability"), "offline")
                self.client.disconnect()
            except:  # noqa
                pass
