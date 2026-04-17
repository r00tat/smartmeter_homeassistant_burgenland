# Smart Meter Reader
import argparse
import logging
import signal
import sys
import yaml

from .smartmeter import SmartMqttMeter

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("meter.main")

parser = argparse.ArgumentParser(
    description="Connect the smart meter via MQTT to Home Assistant"
)
parser.add_argument("--config", "-c", help="config file to load", required=True)
args = parser.parse_args()

meter: SmartMqttMeter | None = None


def _handle_signal(signum, _frame):
    log.info("received signal %s, shutting down", signum)
    if meter is not None:
        meter.stop()


try:
    log.info("loading config")
    with open(args.config) as stream:
        config = yaml.safe_load(stream)

    logging.getLogger().setLevel(
        logging.getLevelNamesMapping().get(config.get("logging", "INFO"), logging.INFO)
    )
    log.info("initializing smart meter")
    meter = SmartMqttMeter(config)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    log.info("starting smart meter")
    meter.start()
except Exception as err:
    log.exception("mqtt smart reader failed %s", err)
    sys.exit(1)
finally:
    log.info("done")
