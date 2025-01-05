"""Test XML parsing"""

import logging
from bs4 import BeautifulSoup


log = logging.getLogger("meter.main")


def parse_xml(xml: str):
    """Parsing xml"""
    soup = BeautifulSoup(xml, "xml")
    struct = soup.find("Structure")

    all_values = []

    log.info("struct: %s", struct)
    for child in struct.findChildren():
        log.info("child: %s", child)
        log.info("type: %s", child.name)
        log.info("value: %s", child["Value"])
        parsed_value = None
        if child.name.startswith("UInt"):
            parsed_value = int(child["Value"], 16)

        if child.name.startswith("OctetString"):
            parsed_value = str(bytearray.fromhex(child["Value"]), encoding="utf-8")

        if parsed_value is not None:
            all_values.append(parsed_value)

    log.info("all values: %s", all_values)
    return all_values


def test():
    """Test XML parsing."""
    logging.basicConfig(level=logging.INFO)
    log.info("reading xml")
    with open("meter/dlms/sample.xml", encoding="utf-8") as f:
        contents = f.read()

    parse_xml(contents)


test()
