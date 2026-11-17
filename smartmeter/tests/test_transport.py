"""Tests for ``meter.serial.transport`` against a real pseudo terminal.

A pty behaves like a serial port for pyserial, so these tests run the
real ``pyserial-asyncio-fast`` transport without hardware.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator

import pytest

from meter.profile import get_profile
from meter.serial import transport
from meter.serial.transport import (
    PortClosedError,
    SerialSettings,
    open_serial,
    periodically,
    read_exactly,
    read_some,
)
from tests.fake_port import run_until
from tests.fixtures.bgld_sample_frame import EXPECTED_VALUES, build_sample_telegram


@pytest.fixture
def pty() -> Iterator[tuple[int, str]]:
    master, slave = os.openpty()
    name = os.ttyname(slave)
    os.close(slave)  # pyserial opens the slave by name
    try:
        yield master, name
    finally:
        os.close(master)


def settings_for(port: str) -> SerialSettings:
    return SerialSettings(port=port, baudrate=9600, bytesize=8, parity="N", stopbits=1)


async def test_bytes_written_to_the_line_are_read(pty: tuple[int, str]) -> None:
    master, name = pty
    async with open_serial(settings_for(name)) as stream:
        os.write(master, b"\x7e\xa0\x01")
        assert await asyncio.wait_for(read_exactly(stream, 3), 2) == b"\x7e\xa0\x01"
        os.write(master, b"hello")
        assert await asyncio.wait_for(read_some(stream), 2) == b"hello"


def open_fds_to(path: str) -> int:
    """How many file descriptors of this process point to ``path``."""
    count = 0
    for fd in os.listdir("/proc/self/fd"):
        try:
            if os.readlink(f"/proc/self/fd/{fd}") == path:
                count += 1
        except OSError:
            pass
    return count


async def test_port_is_closed_on_exit_and_can_be_reopened(pty: tuple[int, str]) -> None:
    master, name = pty
    for _ in range(2):
        async with open_serial(settings_for(name)) as stream:
            assert open_fds_to(name) == 1
            os.write(master, b"x")
            assert await asyncio.wait_for(read_some(stream), 2) == b"x"
        assert open_fds_to(name) == 0


async def test_cancelled_reader_closes_the_port(pty: tuple[int, str]) -> None:
    _, name = pty

    async def read_forever() -> None:
        async with open_serial(settings_for(name)) as stream:
            await read_some(stream)

    task = asyncio.create_task(read_forever())
    async with asyncio.timeout(2):
        while open_fds_to(name) == 0:
            await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.wait({task})

    assert task.cancelled()
    assert open_fds_to(name) == 0


async def test_missing_port_raises() -> None:
    with pytest.raises(Exception, match="nonexistent"):
        async with open_serial(settings_for("/dev/nonexistent-smartmeter")):
            pass


async def test_cancelled_open_closes_the_port(
    pty: tuple[int, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, name = pty
    opened = asyncio.Event()
    release = asyncio.Event()
    writers: list[asyncio.StreamWriter] = []
    real_open = transport._open

    async def slow_open(settings: SerialSettings):
        reader, writer = await real_open(settings)
        writers.append(writer)
        opened.set()
        await release.wait()
        return reader, writer

    monkeypatch.setattr(transport, "_open", slow_open)

    async def use_port() -> None:
        async with open_serial(settings_for(name)):
            pass

    task = asyncio.create_task(use_port())
    await opened.wait()
    task.cancel()
    await asyncio.wait({task})
    release.set()
    await asyncio.sleep(0.05)

    assert task.cancelled()
    assert writers[0].is_closing()


async def test_eof_and_incomplete_reads_raise_port_closed() -> None:
    stream = asyncio.StreamReader()
    stream.feed_data(b"ab")
    stream.feed_eof()
    with pytest.raises(PortClosedError):
        await read_exactly(stream, 3)
    with pytest.raises(PortClosedError):
        await read_some(stream)


async def test_periodically_calls_back_until_the_block_ends() -> None:
    calls: list[int] = []

    def tick() -> None:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("callback bug")  # logged, not fatal

    async with periodically(0.01, tick):
        await asyncio.sleep(0.06)
    count = len(calls)
    await asyncio.sleep(0.03)

    assert count >= 3
    assert len(calls) == count


async def test_burgenland_reader_decodes_a_telegram_from_a_pty(
    pty: tuple[int, str],
) -> None:
    """End to end: profile → reader → real transport → gurux → MeterData."""
    master, name = pty
    sample = build_sample_telegram()
    received: list = []
    reader = get_profile("burgenland").create_reader(
        {"dlms": {"key": sample.key_hex, "port": name}}, received.append
    )

    async def meter() -> None:
        await asyncio.sleep(0.1)
        os.write(master, sample.frame[:40])
        await asyncio.sleep(0.01)
        os.write(master, sample.frame[40:])

    feeder = asyncio.create_task(meter())
    await run_until(reader.run, lambda: bool(received))
    await feeder

    assert received[0].meter_id == EXPECTED_VALUES[-1].decode()
