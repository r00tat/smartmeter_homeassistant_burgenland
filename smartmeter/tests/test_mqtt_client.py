"""Tests for the asyncio MQTT client and device against a local test broker."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from smartmeter_austria.profile import get_profile
from smartmeter_austria.supervisor import cancel_and_wait

from meter.mqtt import client as client_mod
from meter.mqtt.client import MqttClient
from meter.mqtt.device import SmartMeterDevice
from tests.fake_broker import FakeBroker

STATE = "smartmeter/state"
AVAILABILITY = "smartmeter/availability"


class Reading:
    def __init__(self, meter_id: str | None = "1LGZ0012345678", value: int = 1) -> None:
        self.meter_id = meter_id
        self.value = value

    def to_json(self) -> str:
        return json.dumps({"value": self.value})


@pytest.fixture
async def broker() -> AsyncIterator[FakeBroker]:
    fake = FakeBroker()
    await fake.start()
    yield fake
    await fake.stop()


def make_device(broker: FakeBroker, **config) -> SmartMeterDevice:
    device = SmartMeterDevice(
        {"host": "127.0.0.1", "port": broker.port, "keepalive": 5, **config},
        profile=get_profile("burgenland"),
    )
    device.reconnect_seconds = 0.05
    return device


async def test_connect_announces_device_and_sets_last_will(broker: FakeBroker) -> None:
    device = make_device(broker, user="mqtt", password="secret")
    task = asyncio.create_task(device.run())
    try:
        await broker.wait_for(lambda: AVAILABILITY in broker.topics())
    finally:
        await cancel_and_wait(task)

    conn = broker.connections[0]
    assert (conn.username, conn.password) == ("mqtt", "secret")
    assert conn.will == (AVAILABILITY, b"offline", False)
    assert broker.topics()[-3:] == [
        "homeassistant/device/smartmeter/config",
        AVAILABILITY,
        AVAILABILITY,
    ]
    assert broker.payloads(AVAILABILITY) == ["online", "offline"]
    # legacy sensors are migrated as long as sensors_migrated is false
    assert "homeassistant/sensor/smartmeter/config" in broker.topics()
    discovery = json.loads(broker.payloads("homeassistant/device/smartmeter/config")[0])
    assert discovery["device"]["mf"] == "Landis+Gyr"
    assert len(discovery["components"]) == len(get_profile("burgenland").sensor_specs)


async def test_migrated_sensors_are_not_migrated_again(broker: FakeBroker) -> None:
    device = make_device(broker, sensors_migrated=True)
    task = asyncio.create_task(device.run())
    try:
        await broker.wait_for(lambda: AVAILABILITY in broker.topics())
    finally:
        await cancel_and_wait(task)

    assert "homeassistant/sensor/smartmeter/config" not in broker.topics()


async def test_readings_are_published_with_serial_number_discovery(broker: FakeBroker) -> None:
    device = make_device(broker)
    task = asyncio.create_task(device.run())
    try:
        await broker.wait_for(lambda: device.connected)
        device.publish_status(Reading(value=1))
        await broker.wait_for(lambda: len(broker.payloads(STATE)) == 1)
        device.publish_status(Reading(value=2))
        await broker.wait_for(lambda: len(broker.payloads(STATE)) == 2)
    finally:
        await cancel_and_wait(task)

    assert broker.payloads(STATE) == ['{"value": 1}', '{"value": 2}']
    # second discovery carries the serial number
    discovery = json.loads(broker.payloads("homeassistant/device/smartmeter/config")[-1])
    assert discovery["device"]["sn"] == "1LGZ0012345678"
    assert len(broker.payloads("homeassistant/device/smartmeter/config")) == 2


async def test_shutdown_announces_offline_and_disconnects_cleanly(broker: FakeBroker) -> None:
    device = make_device(broker)
    task = asyncio.create_task(device.run())
    await broker.wait_for(lambda: device.connected)

    await cancel_and_wait(task)

    assert broker.payloads(AVAILABILITY)[-1] == "offline"
    await broker.wait_for(lambda: broker.clean_disconnects == 1)
    assert not device.connected


async def test_reconnects_and_announces_again_after_broker_restart(broker: FakeBroker) -> None:
    device = make_device(broker)
    task = asyncio.create_task(device.run())
    try:
        await broker.wait_for(lambda: broker.payloads(AVAILABILITY) == ["online"])
        await broker.drop_clients()
        await broker.wait_for(lambda: len(broker.connections) == 2)
        await broker.wait_for(lambda: broker.payloads(AVAILABILITY).count("online") == 2)
        device.publish_status(Reading())
        await broker.wait_for(lambda: bool(broker.payloads(STATE)))
    finally:
        await cancel_and_wait(task)


async def test_messages_queued_while_broker_down_are_sent_after_connect() -> None:
    broker = FakeBroker()
    await broker.start()
    port = broker.port
    await broker.stop()  # nothing listens on the port yet

    device = make_device(broker)
    device.config["port"] = port
    task = asyncio.create_task(device.run())
    try:
        device.publish_status(Reading(value=7))
        await asyncio.sleep(0.15)  # a few failed connection attempts
        await broker.start(port)
        await broker.wait_for(lambda: bool(broker.payloads(STATE)))
    finally:
        await cancel_and_wait(task)
        await broker.stop()

    assert broker.payloads(STATE) == ['{"value": 7}']


async def test_rejected_connection_is_retried(broker: FakeBroker) -> None:
    broker.reject_with = 5  # not authorized
    device = make_device(broker)
    task = asyncio.create_task(device.run())
    try:
        await broker.wait_for(lambda: len(broker.connections) >= 2)
        broker.reject_with = 0
        await broker.wait_for(lambda: device.connected)
    finally:
        await cancel_and_wait(task)


async def test_availability_follows_the_meter(broker: FakeBroker) -> None:
    device = make_device(broker)
    task = asyncio.create_task(device.run())
    try:
        await broker.wait_for(lambda: device.connected)
        device.publish_status(Reading())
        await broker.wait_for(lambda: len(broker.payloads(STATE)) == 1)
        device.set_available(False)
        await broker.wait_for(lambda: broker.payloads(AVAILABILITY)[-1] == "offline")
        device.publish_status(Reading())
        await broker.wait_for(lambda: len(broker.payloads(STATE)) == 2)
    finally:
        await cancel_and_wait(task)

    # connect, discovery with serial, meter silent, meter back, shutdown
    assert broker.payloads(AVAILABILITY) == ["online", "online", "offline", "online", "offline"]
    assert device.available


async def test_subscriptions_are_renewed_and_dispatched(broker: FakeBroker) -> None:
    device = make_device(broker)
    received: list[bytes] = []

    def handler(message) -> None:
        received.append(message.payload)
        if message.payload == b"boom":
            raise RuntimeError("handler bug")

    device.subscribe("smartmeter/set", handler)
    task = asyncio.create_task(device.run())
    try:
        await broker.wait_for(lambda: device.connected)
        assert broker.subscriptions == ["smartmeter/set"]
        await broker.send("smartmeter/set", b"boom")  # must not end the connection
        await broker.send("smartmeter/set", b"one")
        await broker.wait_for(lambda: received == [b"boom", b"one"])
        assert len(broker.connections) == 1
        await broker.drop_clients()
        await broker.wait_for(lambda: len(broker.subscriptions) == 2)
        await broker.wait_for(lambda: device.connected)
        await broker.send("smartmeter/set", b"two")
        await broker.wait_for(lambda: received[-1] == b"two")
    finally:
        await cancel_and_wait(task)


def test_outbox_keeps_only_the_latest_message_per_topic() -> None:
    device = MqttClient({"host": "mqtt.local"})
    device.publish("state", "1")
    device.publish("availability", "offline")
    device.publish("state", "2")
    device.publish("availability", "online")

    assert device.pending() == [("state", "2", False), ("availability", "online", False)]


def test_full_outbox_drops_the_oldest_topic() -> None:
    device = MqttClient({"host": "mqtt.local"})
    for i in range(client_mod.OUTBOX_SIZE + 1):
        device.publish(f"t{i}", str(i))

    pending = device.pending()

    assert len(pending) == client_mod.OUTBOX_SIZE
    assert pending[0] == ("t1", "1", False)


class _StuckClient:
    """publish() fails with ``error`` or hangs until cancelled."""

    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.started = asyncio.Event()

    async def publish(self, topic, payload, retain=False) -> None:
        self.started.set()
        if self.error is not None:
            raise self.error
        await asyncio.Event().wait()


async def test_message_stays_queued_in_order_when_publishing_fails() -> None:
    device = MqttClient({"host": "mqtt.local"})
    device.publish("availability", "offline")
    device.publish("state", "1")

    with pytest.raises(client_mod.aiomqtt.MqttError):
        await device._send_outbox(_StuckClient(client_mod.aiomqtt.MqttError("gone")))

    assert device.pending() == [("availability", "offline", False), ("state", "1", False)]


async def test_message_stays_queued_when_cancelled_mid_publish() -> None:
    device = MqttClient({"host": "mqtt.local"})
    device.publish("state", "1")
    client = _StuckClient()
    task = asyncio.create_task(device._send_outbox(client))
    await client.started.wait()

    await cancel_and_wait(task)

    assert device.pending() == [("state", "1", False)]


async def test_newer_message_queued_during_publish_is_sent_next() -> None:
    device = MqttClient({"host": "mqtt.local"})
    sent: list[tuple[str, str]] = []

    class Client:
        async def publish(self, topic, payload, retain=False) -> None:
            if payload == "1":
                device.publish("state", "2")  # arrives while "1" is in flight
            sent.append((topic, payload))

    device.publish("state", "1")
    task = asyncio.create_task(device._send_outbox(Client()))
    async with asyncio.timeout(1):
        while len(sent) < 2:
            await asyncio.sleep(0.01)
    await cancel_and_wait(task)

    assert sent == [("state", "1"), ("state", "2")]
    assert device.pending() == []


async def test_reading_queued_during_broker_restart_is_delivered(broker: FakeBroker) -> None:
    device = make_device(broker)
    device.reconnect_seconds = 0.2
    task = asyncio.create_task(device.run())
    try:
        await broker.wait_for(lambda: device.connected)
        await broker.drop_clients()
        await broker.wait_for(lambda: not device.connected)
        device.publish_status(Reading(value=42))  # while disconnected
        await broker.wait_for(lambda: '{"value": 42}' in broker.payloads(STATE))
    finally:
        await cancel_and_wait(task)


def test_host_is_required() -> None:
    with pytest.raises(ValueError, match="host"):
        MqttClient({})


def test_base_topic_uses_prefix_and_device_id() -> None:
    client = MqttClient({"host": "h", "prefix": "home", "device_id": "meter1"})
    assert client.topic_with_prefix("state") == "home/meter1/state"
    assert MqttClient({"host": "h"}).base_topic == "smartmeter"


# --- TLS gating (issue #94) ---------------------------------------------------


def tls(config: dict):
    return MqttClient({"host": "mqtt.local", **config}).tls_settings()


def test_tls_not_enabled_when_key_absent() -> None:
    # Regression for #94: default config has no `tls` key.
    assert tls({}) == (None, None)


def test_tls_not_enabled_when_false_with_insecure_false() -> None:
    # The exact #94 trigger: tls_insecure default False must not enable TLS.
    assert tls({"tls": False, "tls_insecure": False}) == (None, None)


def test_tls_not_enabled_when_certs_present_but_tls_false() -> None:
    # No fallback: certs alone do not enable TLS.
    assert tls({"tls": False, "tls_ca": "/config/ca.pem"}) == (None, None)


def test_tls_enabled_without_certs_uses_system_ca() -> None:
    params, insecure = tls({"tls": True})
    assert params is not None
    assert (params.ca_certs, params.certfile, params.keyfile) == (None, None, None)
    assert insecure is None


def test_tls_enabled_with_ca_and_insecure() -> None:
    params, insecure = tls(
        {
            "tls": True,
            "tls_ca": "/config/ca.pem",
            "tls_cert": "/config/client.pem",
            "tls_key": "/config/client.key",
            "tls_insecure": True,
        }
    )
    assert params is not None
    assert (params.ca_certs, params.certfile, params.keyfile) == (
        "/config/ca.pem",
        "/config/client.pem",
        "/config/client.key",
    )
    assert insecure is True


async def test_create_client_passes_tls_and_credentials() -> None:
    client = MqttClient(
        {"host": "mqtt.local", "port": 8883, "user": "u", "password": "p", "tls": True}
    )
    with patch.object(client_mod.aiomqtt, "Client") as aiomqtt_client:
        client.create_client()
    kwargs = aiomqtt_client.call_args.kwargs
    assert kwargs["hostname"] == "mqtt.local"
    assert kwargs["port"] == 8883
    assert (kwargs["username"], kwargs["password"]) == ("u", "p")
    assert kwargs["tls_params"] is not None
    assert kwargs["will"].topic == AVAILABILITY
