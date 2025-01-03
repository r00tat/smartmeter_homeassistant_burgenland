"""combine the serial read functionality with the mqtt functionality"""

import logging
import threading
import serial
import yaml

from .bgld.data import MeterData
from .mqtt.device import SmartMeterDevice
from .serial.read import MeterReader

log = logging.getLogger("meter.smartmeter")


class SmartMqttMeter:
    """Connect the smart meter from serial to MQTT."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.reader: MeterReader = None
        self.mqtt: SmartMeterDevice = None
        self.reader_thread: threading.Thread = None
        self.mqtt_thread: threading.Thread = None
        self.counter = 0

        self.setup()

    def setup(self):
        log.info("starting setup")
        dlms_config = self.config.get("dlms", {})
        log.info("dlms config \n%s", yaml.safe_dump(dlms_config))
        self.reader = MeterReader(
            dlms_config.get("key"),
            dlms_config.get("port", "/dev/ttyUSB0"),
            baudrate=dlms_config.get("baudrate", 9600),
            bytesize=dlms_config.get("bytesize", serial.EIGHTBITS),
            stopbits=dlms_config.get("stopbits", serial.STOPBITS_ONE),
            parity=dlms_config.get("parity", serial.PARITY_NONE),
            callback=self.got_meter_data,
        )
        log.info("connecting to serial port")
        self.reader.connect()

        log.info("mqtt config: \n%s", yaml.safe_dump(self.config.get("mqtt", {})))
        self.mqtt = SmartMeterDevice(self.config.get("mqtt", {}))

        log.info("setup complete")

    def got_meter_data(self, data: MeterData):
        log.info(
            "got meter data, "
            f"{'publishing to mqtt' if self.counter % 6 == 0 else 'skipping'}"
            f": {data}"
        )
        if self.counter % 6 == 0:
            self.mqtt.publish_status(data)
        self.counter += 1

    def start(self):
        try:
            self.reader_thread = threading.Thread(target=self.reader.start)
            self.mqtt_thread = threading.Thread(target=self.mqtt.start)

            log.info("start reading from serial port and sending to mqtt")
            self.reader_thread.start()
            self.mqtt_thread.start()

            log.info("wating for serial port to complete")
            self.reader_thread.join()
        finally:
            self.reader.stop()
            self.mqtt.stop()
