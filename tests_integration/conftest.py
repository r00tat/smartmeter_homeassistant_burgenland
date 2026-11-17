"""Shared fixtures for the Home Assistant integration tests."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from custom_components.smartmeter_at.const import (
    CONF_INTERFACE_TYPE,
    CONF_KEY,
    CONF_METER_TYPE,
    CONF_PORT,
)

# Same values as smartmeter/smartmeter-austria/tests/fixtures/bgld_sample_frame.EXPECTED_VALUES.
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


def sample_telegram() -> Any:
    """An encrypted Burgenland telegram (add-on test fixture, same key)."""
    path = Path(__file__).parents[1] / "smartmeter/smartmeter-austria/tests/fixtures/bgld_sample_frame.py"
    spec = importlib.util.spec_from_file_location("bgld_sample_frame", path)
    assert spec is not None and spec.loader is not None
    module = sys.modules.get(spec.name)
    if module is None:
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # dataclasses look their module up
        spec.loader.exec_module(module)
    return module.build_sample_telegram()


def addon_module(name: str) -> Any:
    """Import a module of the MQTT add-on (``smartmeter/meter``)."""
    addon_root = str(Path(__file__).parents[1] / "smartmeter")
    if addon_root not in sys.path:
        sys.path.append(addon_root)
    return importlib.import_module(name)


def sample_reading() -> Any:
    from smartmeter_austria.bgld.data import MeterData

    return MeterData(list(METER_VALUES))


class FakeReader:
    """Delivers one reading, then reads on until cancelled."""

    def __init__(self, callback: Callable[[Any], None]) -> None:
        self.callback = callback
        self.cancelled = False

    async def run(self) -> None:
        self.callback(sample_reading())
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


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
