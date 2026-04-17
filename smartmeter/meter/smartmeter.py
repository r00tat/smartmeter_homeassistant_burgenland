"""combine the serial read functionality with the mqtt functionality"""

import logging
import threading
import serial
import yaml

from .bgld.data import MeterData
from .mqtt.device import SmartMeterDevice
from .serial.read import MeterReader

log = logging.getLogger("meter.smartmeter")

_SECRET_KEYS = ("key", "password")


def _redact(cfg: dict) -> dict:
    """Return a shallow copy of cfg with sensitive values replaced by '***'."""
    return {k: ("***" if k in _SECRET_KEYS and v else v) for k, v in cfg.items()}


class SmartMqttMeter:
    """Connect the smart meter from serial to MQTT."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.reader: MeterReader = None
        self.mqtt: SmartMeterDevice = None
        self.reader_thread: threading.Thread = None
        self.mqtt_thread: threading.Thread = None
        self.counter = 0
        self.publish_interval = 6
        self._stop = threading.Event()

        self.setup()

    def setup(self):
        log.info("starting setup")
        dlms_config = self.config.get("dlms", {})
        log.info("dlms config \n%s", yaml.safe_dump(_redact(dlms_config)))
        self.reader = MeterReader(
            dlms_config.get("key"),
            dlms_config.get("port", "/dev/ttyUSB0"),
            baudrate=dlms_config.get("baudrate", 9600),
            bytesize=dlms_config.get("bytesize", serial.EIGHTBITS),
            stopbits=dlms_config.get("stopbits", serial.STOPBITS_ONE),
            parity=dlms_config.get("parity", serial.PARITY_NONE),
            interface_type=self.config.get("interface_type", "OPTICAL"),
            hdlc_frame_size=dlms_config.get("hdlc_frame_size", 120),
            callback=self.got_meter_data,
        )
        log.info("connecting to serial port")
        self.reader.connect()

        mqtt_config = self.config.get("mqtt", {})
        log.info("mqtt config: \n%s", yaml.safe_dump(_redact(mqtt_config)))
        self.mqtt = SmartMeterDevice(mqtt_config)
        # we get data every 5 seconds, so we publish every 6th time (30s)
        # unless configured otherwise
        self.publish_interval = int(mqtt_config.get("publish_interval", 30) / 5)
        log.info(
            "publishing every %d readings and every %d seconds",
            self.publish_interval,
            mqtt_config.get("publish_interval", 30),
        )

        log.info("setup complete")

    def got_meter_data(self, data: MeterData):
        log.info(
            "got meter data, "
            f"{'publishing to mqtt' if self.counter % self.publish_interval == 0 else 'skipping'}"
            f": {data}"
        )
        if self.counter % self.publish_interval == 0:
            self.mqtt.publish_status(data)
        self.counter += 1

    SHUTDOWN_TIMEOUT_SECONDS = 10

    def start(self):
        try:
            self.reader_thread = threading.Thread(target=self.reader.start)
            self.mqtt_thread = threading.Thread(target=self.mqtt.start)

            log.info("start reading from serial port and sending to mqtt")
            self.reader_thread.start()
            self.mqtt_thread.start()

            log.info("wating for serial port to complete")
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
