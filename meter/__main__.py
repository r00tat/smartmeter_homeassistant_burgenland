# Smart Meter Reader
import argparse
import logging
import yaml

from .smartmeter import SmartMqttMeter

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("meter.main")

parser = argparse.ArgumentParser(
    description="Connect the smart meter via MQTT to Home Assistant"
)
parser.add_argument("--config", "-c", help="config file to load", required=True)
args = parser.parse_args()

try:
    log.info("loading config")
    with open(args.config) as stream:
        config = yaml.safe_load(stream)

    log.info("initializing smart meter")
    meter = SmartMqttMeter(config)
    log.info("starting smart meter")
    meter.start()
except Exception as err:
    log.exception("mqtt smart reader failed %s", err)
finally:
    log.info("done")
