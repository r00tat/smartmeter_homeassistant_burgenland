"""Combine the serial reader with the MQTT publisher on one event loop."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import yaml
from smartmeter_austria.config_validation import DEFAULT_METER_TYPE, validate_config
from smartmeter_austria.profile import MeterDataCallback, MeterReaderLike, get_profile
from smartmeter_austria.supervisor import ReaderSupervisor

from .mqtt.device import SmartMeterDevice
from .reader_factory import build_reader

log = logging.getLogger("meter.smartmeter")

_SECRET_KEYS = ("key", "password")

# Seconds to wait before a failed reader is started again.
RETRY_SECONDS = 10.0
# Reopen the port when no telegram arrived for this long: a hung USB
# adapter can keep the port open without delivering data.
RESTART_AFTER_SECONDS = 300.0


def _redact(cfg: dict) -> dict:
    """Return a shallow copy of cfg with sensitive values replaced by '***'."""
    return {k: ("***" if k in _SECRET_KEYS and v else v) for k, v in cfg.items()}


class SmartMqttMeter:
    """Connect the smart meter from serial to MQTT."""

    def __init__(self, config: dict) -> None:
        validate_config(config)
        self.config = config
        self.publish_interval = 6
        self._stop = asyncio.Event()

        self.setup()

    def setup(self) -> None:
        log.info("starting setup")
        meter_type = self.config.get("meter_type", DEFAULT_METER_TYPE)
        self.profile = profile = get_profile(meter_type)
        log.info(
            "meter profile: %s (%s %s)",
            profile.name,
            profile.manufacturer,
            profile.model,
        )
        dlms_config = self.config.get("dlms", {})
        log.info("dlms config \n%s", yaml.safe_dump(_redact(dlms_config)))

        mqtt_config = self.config.get("mqtt", {})
        log.info("mqtt config: \n%s", yaml.safe_dump(_redact(mqtt_config)))
        self.mqtt = SmartMeterDevice(mqtt_config, profile=profile)
        # The meter pushes a telegram every ``profile.push_interval_seconds``
        # (5s for Burgenland/NÖ, 1s for Wien); publish only every n-th one so
        # MQTT sees a value roughly every ``publish_interval`` seconds.
        publish_seconds = mqtt_config.get("publish_interval", 30)
        self.publish_interval = profile.readings_per_publish(publish_seconds)
        log.info(
            "publishing every %d readings and every %d seconds",
            self.publish_interval,
            publish_seconds,
        )
        # The supervisor opens the port only when ``run`` starts it.
        self.supervisor = ReaderSupervisor(
            self.create_reader,
            on_data=self.got_meter_data,
            on_skipped=self.skipped_meter_data,
            on_error=self.reader_failed,
            every=self.publish_interval,
            retry_seconds=RETRY_SECONDS,
            stale_after=profile.stale_after_seconds,
            restart_after=RESTART_AFTER_SECONDS,
        )
        log.info("setup complete")

    def create_reader(self, callback: MeterDataCallback) -> MeterReaderLike:
        return build_reader(self.config, self.profile, callback=callback)

    def got_meter_data(self, data: Any) -> None:
        log.info("got meter data, publishing to mqtt: %s", data)
        self.mqtt.publish_status(data)

    def skipped_meter_data(self, data: Any) -> None:
        log.info("got meter data, skipping: %s", data)

    def reader_failed(self, error: Exception) -> None:
        log.warning("no current meter data (%s), marking sensors unavailable", error)
        if self.mqtt.available:
            self.mqtt.set_available(False)

    async def run(self) -> None:
        """Read and publish until ``stop()``; raise if a component crashes."""
        log.info("start reading from serial port and sending to mqtt")
        async with asyncio.TaskGroup() as tasks:
            reader = tasks.create_task(self.supervisor.run(), name="smartmeter-supervisor")
            mqtt = tasks.create_task(self.mqtt.run(), name="smartmeter-mqtt")
            await self._stop.wait()
            log.info("shutting down")
            reader.cancel()
            mqtt.cancel()
        log.info("shutdown complete")

    def stop(self) -> None:
        """Ask ``run`` to stop the reader and disconnect from MQTT."""
        self._stop.set()
