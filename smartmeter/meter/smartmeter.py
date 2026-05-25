"""combine the serial read functionality with the mqtt functionality"""

import logging
import threading
from typing import Any

import yaml

from .config_validation import DEFAULT_METER_TYPE, validate_config
from .mqtt.device import SmartMeterDevice
from .noe.read import NoeMeterReader
from .profile import get_profile
from .reader_factory import build_reader
from .serial.read import MeterReader

log = logging.getLogger("meter.smartmeter")

_SECRET_KEYS = ("key", "password")


def _redact(cfg: dict) -> dict:
    """Return a shallow copy of cfg with sensitive values replaced by '***'."""
    return {k: ("***" if k in _SECRET_KEYS and v else v) for k, v in cfg.items()}


class SmartMqttMeter:
    """Connect the smart meter from serial to MQTT."""

    def __init__(self, config: dict) -> None:
        validate_config(config)
        self.config = config
        self.reader: MeterReader | NoeMeterReader | None = None
        self.mqtt: SmartMeterDevice | None = None
        self.reader_thread: threading.Thread | None = None
        self.mqtt_thread: threading.Thread | None = None
        self.counter = 0
        self.publish_interval = 6
        self._stop = threading.Event()

        self.setup()

    def setup(self):
        log.info("starting setup")
        meter_type = self.config.get("meter_type", DEFAULT_METER_TYPE)
        profile = get_profile(meter_type)
        log.info(
            "meter profile: %s (%s %s)",
            profile.name,
            profile.manufacturer,
            profile.model,
        )
        dlms_config = self.config.get("dlms", {})
        log.info("dlms config \n%s", yaml.safe_dump(_redact(dlms_config)))
        self.reader = build_reader(
            self.config,
            profile,
            callback=self.got_meter_data,
        )
        log.info("connecting to serial port")
        self.reader.connect()

        mqtt_config = self.config.get("mqtt", {})
        log.info("mqtt config: \n%s", yaml.safe_dump(_redact(mqtt_config)))
        self.mqtt = SmartMeterDevice(mqtt_config, profile=profile)
        # we get data every 5 seconds, so we publish every 6th time (30s)
        # unless configured otherwise
        self.publish_interval = int(mqtt_config.get("publish_interval", 30) / 5)
        log.info(
            "publishing every %d readings and every %d seconds",
            self.publish_interval,
            mqtt_config.get("publish_interval", 30),
        )

        log.info("setup complete")

    def got_meter_data(self, data: Any):
        log.info(
            "got meter data, "
            f"{'publishing to mqtt' if self.counter % self.publish_interval == 0 else 'skipping'}"
            f": {data}"
        )
        if self.counter % self.publish_interval == 0 and self.mqtt is not None:
            self.mqtt.publish_status(data)
        self.counter += 1

    SHUTDOWN_TIMEOUT_SECONDS = 10

    def start(self):
        if self.reader is None or self.mqtt is None:
            raise RuntimeError("setup() must be called before start()")
        try:
            self.reader_thread = threading.Thread(target=self.reader.start)
            self.mqtt_thread = threading.Thread(target=self.mqtt.start)

            log.info("start reading from serial port and sending to mqtt")
            self.reader_thread.start()
            self.mqtt_thread.start()

            log.info("waiting for serial port to complete")
            while not self._stop.is_set():
                if not self.reader_thread.is_alive():
                    log.info("reader thread exited, shutting down")
                    break
                if not self.mqtt_thread.is_alive():
                    log.info("mqtt thread exited, shutting down")
                    break
                self._stop.wait(timeout=1.0)
        finally:
            self.stop()

    def stop(self):
        """Signal all components to stop and wait for shutdown."""
        already_stopping = self._stop.is_set()
        self._stop.set()
        if self.reader:
            self.reader.stop()
        if self.mqtt:
            self.mqtt.stop()

        if already_stopping:
            return
        for thread in (self.reader_thread, self.mqtt_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=self.SHUTDOWN_TIMEOUT_SECONDS)
                if thread.is_alive():
                    log.warning(
                        "thread %s did not exit within %ds",
                        thread.name,
                        self.SHUTDOWN_TIMEOUT_SECONDS,
                    )
