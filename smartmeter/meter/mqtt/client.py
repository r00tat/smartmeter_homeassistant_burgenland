"""Asyncio MQTT client with Home Assistant discovery and automatic reconnect.

``publish`` can be called from any code on the event loop without
awaiting: messages go into a bounded outbox that ``run`` sends while the
broker is connected. When the connection drops, ``run`` reconnects after
``reconnect_seconds`` and announces the device again, so Home Assistant
picks it up after a broker restart.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

import aiomqtt

log = logging.getLogger(__name__)

RECONNECT_SECONDS = 10.0
# Messages kept while the broker is unreachable; the oldest are dropped.
OUTBOX_SIZE = 100
# How long a clean shutdown may spend announcing "offline".
OFFLINE_TIMEOUT_SECONDS = 2.0

Message = tuple[str, Any, bool]  # topic, payload, retain


class MqttClient:
    """MQTT client."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.message_callbacks: dict[str, Callable[[aiomqtt.Message], None]] = {}
        self.topic_prefix: str = config.get("prefix", "")
        self.device_id: str = config.get("device_id", "smartmeter")
        self.reconnect_seconds = RECONNECT_SECONDS
        if not config.get("host"):
            raise ValueError("mqtt.host is required")
        self._outbox: asyncio.Queue[Message] = asyncio.Queue(maxsize=OUTBOX_SIZE)
        self.connected = False

    def create_client(self) -> aiomqtt.Client:
        """Build the aiomqtt client for one connection attempt."""
        tls_params, tls_insecure = self.tls_settings()
        return aiomqtt.Client(
            hostname=self.config["host"],
            port=int(self.config.get("port", 1883)),
            username=self.config.get("user"),
            password=self.config.get("password"),
            keepalive=int(self.config.get("keepalive", 60)),
            tls_params=tls_params,
            tls_insecure=tls_insecure,
            # Mark the sensors unavailable when the add-on dies or the
            # connection is lost without a clean disconnect.
            will=aiomqtt.Will(self.topic_with_prefix("availability"), "offline"),
        )

    def tls_settings(self) -> tuple[aiomqtt.TLSParameters | None, bool | None]:
        """TLS parameters, only when explicitly switched on via ``tls: true``."""
        if not self.config.get("tls"):
            return None, None
        log.info("enabling MQTT TLS")
        params = aiomqtt.TLSParameters(
            ca_certs=self.config.get("tls_ca") or None,
            certfile=self.config.get("tls_cert") or None,
            keyfile=self.config.get("tls_key") or None,
        )
        tls_insecure = self.config.get("tls_insecure")
        return params, None if tls_insecure is None else bool(tls_insecure)

    @property
    def base_topic(self) -> str:
        """Get the base topic"""
        return f"{self.topic_prefix}/{self.device_id}".lstrip("/")

    def topic_with_prefix(self, topic: str) -> str:
        return f"{self.base_topic}/{topic}"

    def discovery_messages(self) -> list[Message]:
        """Home Assistant auto discovery

        @see https://www.home-assistant.io/integrations/mqtt/#sensors
        @see https://www.home-assistant.io/integrations/sensor.mqtt/
        @see https://www.home-assistant.io/integrations/sensor/#device-class
        """
        return [
            (
                f"homeassistant/sensor/{self.device_id}/config",
                json.dumps(
                    {
                        "~": self.base_topic,
                        "name": self.config.get("name", "Smart Meter"),
                        "state_topic": "~/state",
                        "availability_topic": "~/availability",
                        "retain": True,
                        "unique_id": self.device_id,
                    }
                ),
                False,
            ),
            (self.topic_with_prefix("availability"), "online", False),
        ]

    def ha_discovery(self) -> None:
        """Queue the discovery messages (sent on every connect anyway)."""
        log.info("publishing home assistant auto discovery")
        for topic, payload, retain in self.discovery_messages():
            self.publish(topic, payload, retain=retain)

    def publish(self, topic: str, payload: Any = None, retain: bool = False) -> None:
        """Queue a message; it is sent as soon as the broker is connected."""
        log.debug("queueing mqtt message to %s: %s", topic, payload)
        if self._outbox.full():
            dropped = self._outbox.get_nowait()
            log.warning("mqtt outbox full, dropping message to %s", dropped[0])
        self._outbox.put_nowait((topic, payload, retain))

    def subscribe(self, topic: str, callback: Callable[[aiomqtt.Message], None]) -> None:
        """Subscribe to a MQTT topic (renewed on every connect)."""
        self.message_callbacks[topic] = callback

    def on_message(self, message: aiomqtt.Message) -> None:
        """New message received"""
        log.info("got a message %s %s", message.topic, message.payload)
        callback = self.message_callbacks.get(str(message.topic))
        if callback is not None:
            callback(message)

    async def run(self) -> None:
        """Stay connected until cancelled; announce "offline" on the way out."""
        while True:
            try:
                await self._run_connection()
            except* aiomqtt.MqttError as group:
                log.warning(
                    "mqtt connection failed: %s, reconnecting in %.1fs",
                    group.exceptions[0],
                    self.reconnect_seconds,
                )
            await asyncio.sleep(self.reconnect_seconds)

    async def _run_connection(self) -> None:
        async with self.create_client() as client:
            log.info("connected to MQTT broker %s", self.config["host"])
            try:
                for topic in self.message_callbacks:
                    await client.subscribe(topic)
                for topic, payload, retain in self.discovery_messages():
                    await client.publish(topic, payload, retain=retain)
                self.connected = True
                async with asyncio.TaskGroup() as tasks:
                    tasks.create_task(self._send_outbox(client))
                    tasks.create_task(self._receive(client))
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    async with asyncio.timeout(OFFLINE_TIMEOUT_SECONDS):
                        await client.publish(self.topic_with_prefix("availability"), "offline")
                raise
            finally:
                self.connected = False

    async def _send_outbox(self, client: aiomqtt.Client) -> None:
        while True:
            topic, payload, retain = await self._outbox.get()
            log.debug("publishing mqtt message to %s: %s", topic, payload)
            try:
                await client.publish(topic, payload, retain=retain)
            except aiomqtt.MqttError:
                # Keep the message for the next connection.
                self.publish(topic, payload, retain)
                raise

    async def _receive(self, client: aiomqtt.Client) -> None:
        # Ends with MqttError when the connection drops.
        async for message in client.messages:
            self.on_message(message)
