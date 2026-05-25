"""Unit tests for the reader factory used by SmartMqttMeter."""

from meter.bgld.data import MeterData as BgldMeterData
from meter.noe.data import MeterData as NoeMeterData
from meter.noe.read import NoeMeterReader
from meter.profile import get_profile
from meter.reader_factory import build_reader
from meter.serial.read import MeterReader as SerialMeterReader


VALID_KEY = "000102030405060708090A0B0C0D0E0F"


def _noop(_data: object) -> None:
    return None


def test_burgenland_profile_returns_serial_meter_reader() -> None:
    cfg = {"dlms": {"key": VALID_KEY, "port": "/dev/ttyUSB0"}}
    reader = build_reader(cfg, get_profile("burgenland"), callback=_noop)
    assert isinstance(reader, SerialMeterReader)


def test_noe_profile_returns_noe_meter_reader() -> None:
    cfg = {"dlms": {"key": VALID_KEY, "port": "/dev/ttyUSB0"}}
    reader = build_reader(cfg, get_profile("noe_evn"), callback=_noop)
    assert isinstance(reader, NoeMeterReader)


def test_noe_profile_applies_default_baudrate() -> None:
    cfg = {"dlms": {"key": VALID_KEY, "port": "/dev/ttyUSB0"}}
    reader = build_reader(cfg, get_profile("noe_evn"), callback=_noop)
    assert reader.baudrate == 2400


def test_noe_profile_respects_explicit_baudrate_override() -> None:
    cfg = {"dlms": {"key": VALID_KEY, "port": "/dev/ttyUSB0", "baudrate": 9600}}
    reader = build_reader(cfg, get_profile("noe_evn"), callback=_noop)
    assert reader.baudrate == 9600


def test_burgenland_profile_applies_default_baudrate() -> None:
    cfg = {"dlms": {"key": VALID_KEY, "port": "/dev/ttyUSB0"}}
    reader = build_reader(cfg, get_profile("burgenland"), callback=_noop)
    assert reader.baudrate == 9600


def test_data_types_are_distinct() -> None:
    # Sanity: the two profiles produce different MeterData classes downstream.
    assert BgldMeterData is not NoeMeterData
