"""Test XML parsing against a sample file (manual harness)."""

import logging

from .read import parse_xml

log = logging.getLogger("meter.main")


def test() -> None:
    """Run parse_xml against the committed sample XML."""
    logging.basicConfig(level=logging.INFO)
    log.info("reading xml")
    with open("meter/dlms/sample.xml", encoding="utf-8") as f:
        contents = f.read()

    values = parse_xml(contents)
    log.info("all values: %s", values)


if __name__ == "__main__":
    test()
