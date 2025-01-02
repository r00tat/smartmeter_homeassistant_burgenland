from .data import MeterData
from ..dlms.read import parse_dlms_data


def parse_dlms_data_bgld(data: bytes, key: str):
    """Parse the data and construct a MeterData object"""
    decrypted_data = parse_dlms_data(data, key)
    return MeterData(decrypted_data)
