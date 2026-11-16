"""Shared fixtures for the Home Assistant integration tests."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import patch

import pytest

from custom_components.smartmeter_at.const import (
    CONF_INTERFACE_TYPE,
    CONF_KEY,
    CONF_METER_TYPE,
    CONF_PORT,
)

# Same values as smartmeter/tests/fixtures/bgld_sample_frame.EXPECTED_VALUES.
METER_VALUES: list[Any] = [
    236, 235, 237, 512, 48, 1999, 3314, 0, 49244276, 1234567, 17, 195, 304,
    b"1LGZ0012345678",
]
METER_ID = "1LGZ0012345678"
KEY = "36C66639E48A8CA4D6BC8B282A793BBB"
ENTRY_DATA = {
    CONF_METER_TYPE: "burgenland",
    CONF_PORT: "/dev/ttyUSB0",
    CONF_KEY: KEY,
    CONF_INTERFACE_TYPE: "optical",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load integrations from custom_components/."""
    yield


def sample_reading() -> Any:
    from custom_components.smartmeter_at.meter.bgld.data import MeterData

    return MeterData(list(METER_VALUES))


class FakeReader:
    """Delivers one reading, then blocks until stopped."""

    def __init__(self, callback: Callable[[Any], None]) -> None:
        self.callback = callback
        self.stopped = threading.Event()

    def start(self) -> None:
        self.callback(sample_reading())
        self.stopped.wait(5)

    def stop(self) -> None:
        self.stopped.set()


@pytest.fixture
def fake_readers() -> Iterator[list[FakeReader]]:
    """Replace the serial reader of every config entry by a FakeReader."""
    readers: list[FakeReader] = []

    def factory(callback: Callable[[Any], None]) -> FakeReader:
        reader = FakeReader(callback)
        readers.append(reader)
        return reader

    with patch(
        "custom_components.smartmeter_at.coordinator.build_reader_factory",
        return_value=factory,
    ):
        yield readers


async def wait_for_data(coordinator: Any) -> None:
    for _ in range(200):
        if coordinator.data is not None:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("coordinator received no data")
