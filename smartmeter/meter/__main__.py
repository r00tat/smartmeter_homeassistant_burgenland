"""Smart Meter Reader: ``python -m meter -c config.yaml``."""

import argparse
import asyncio
import logging
import signal
import sys

import yaml

from .smartmeter import SmartMqttMeter

log = logging.getLogger("meter.main")


async def run(config: dict) -> None:
    """Run until SIGTERM/SIGINT."""
    log.info("initializing smart meter")
    meter = SmartMqttMeter(config)
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, _stop, meter, signum)
    log.info("starting smart meter")
    await meter.run()


def _stop(meter: SmartMqttMeter, signum: int) -> None:
    log.info("received signal %s, shutting down", signal.Signals(signum).name)
    meter.stop()


def main(argv: list[str] | None = None) -> int:
    """Load the config and run the reader; return the exit code."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s:%(name)s:%(message)s"
    )
    parser = argparse.ArgumentParser(
        description="Connect the smart meter via MQTT to Home Assistant"
    )
    parser.add_argument("--config", "-c", help="config file to load", required=True)
    args = parser.parse_args(argv)
    try:
        log.info("loading config")
        with open(args.config) as stream:
            config = yaml.safe_load(stream)

        logging.getLogger().setLevel(
            logging.getLevelNamesMapping().get(config.get("logging", "INFO"), logging.INFO)
        )
        asyncio.run(run(config))
    except Exception as err:
        log.exception("mqtt smart reader failed %s", err)
        return 1
    finally:
        log.info("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
