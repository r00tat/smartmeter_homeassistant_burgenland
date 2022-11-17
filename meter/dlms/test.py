import logging
import os
from .read import parse_dlms_data

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("meter.dlms.test")

key = os.environ['DLMS_ENCRYPTION_KEY']

try:
    log.info("reading file")
    with open("smartmeter-data.raw", "rb") as input:
        buffer = input.read()
    log.info("encrypted data")
    log.info("%s", buffer)
    decrypted_data = parse_dlms_data(buffer, key)
    log.info("decrypted data:")
    log.info("%s", decrypted_data)
except Exception as err:
    log.exception("failed to parse dlms data: %s", err)
