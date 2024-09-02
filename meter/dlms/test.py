"""Test for dlms read."""

import logging
import os
from .read import parse_dlms_data, convert_to_xml

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("meter.dlms.test")

key = os.environ["DLMS_ENCRYPTION_KEY"]

try:
    log.info("reading file")
    with open("smartmeter-data.raw", "rb") as input:
        buffer = input.read()
    log.info("encrypted data")
    log.info("%s", buffer)
    decrypted_data = parse_dlms_data(buffer, key)
    log.info("decrypted data:")
    log.info("%s", decrypted_data)
    log.info("xml version of data")
    log.info("%s", convert_to_xml(decrypted_data))
    (
        voltage_l1,
        voltage_l2,
        voltage_l3,
        current_l1,
        current_l2,
        current_l3,
        power_consumed,
        power_provided,
        total_consumed,
        total_provided,
        x_1,
        x_2,
        x_3,
        meter_id,
        *rest,
    ) = decrypted_data.value

    log.info(
        f"MeterData: "
        f"U({voltage_l1},{voltage_l2},{voltage_l3}),"
        f"I({current_l1},{current_l2},{current_l3}),"
        f"P({power_consumed},-{power_provided}),"
        f"W({total_consumed},-{total_provided})"
    )
    log.info("%sV %sA = %s?", voltage_l1, current_l1, x_1)
    log.info("%sV %sA = %s?", voltage_l2, current_l2, x_2)
    log.info("%sV %sA = %s?", voltage_l3, current_l3, x_3)
    log.info("meter_id: %s", meter_id)
except Exception as err:
    log.exception("failed to parse dlms data: %s", err)
