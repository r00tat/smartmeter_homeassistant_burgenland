"""Raw serial capture in the debug log: format, parsing and replay.

The round-trip tests read a real pseudo terminal through the real
transport, take the ``meter.serial.raw`` lines from the log, replay them
through a scripted port and expect the same readings: a debug log from a
bug report can become a test without hand work.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Iterator

import pytest

from meter.profile import get_profile
from meter.serial import rawlog
from meter.serial import read as serial_read
from meter.serial.transport import SerialSettings, open_serial, read_some
from tests.fake_port import EOF, FakePort, run_until, steps_from_capture
from tests.fixtures.bgld_sample_frame import build_sample_telegram
from tests.fixtures.noe_sample_frame import build_sample_frame


@pytest.fixture
def pty() -> Iterator[tuple[int, str]]:
    master, slave = os.openpty()
    name = os.ttyname(slave)
    os.close(slave)
    try:
        yield master, name
    finally:
        os.close(master)


@pytest.fixture
def raw_debug(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG, logger=rawlog.LOGGER_NAME)
    return caplog


def test_format_and_parse_round_trip() -> None:
    line = rawlog.format_chunk(12.3456, b"\x7e\xa0\x01")
    assert line == "rx +12.346s 3 bytes: 7ea001"
    assert rawlog.parse(line) == [(12.346, b"\x7e\xa0\x01")]


def test_parse_ignores_prefixes_and_other_lines() -> None:
    text = (
        "2026-11-17 07:00:00,123 DEBUG:meter.serial.raw:rx +0.010s 2 bytes: 6868\n"
        "2026-11-17 07:00:00,200 INFO:meter.smartmeter:got meter data, skipping: x\n"
        "DEBUG    meter.serial.raw:transport.py:1 rx +0.250s 1 bytes: 16\n"
    )
    assert rawlog.parse(text) == [(0.01, b"\x68\x68"), (0.25, b"\x16")]


def test_steps_from_capture_keeps_the_pauses() -> None:
    steps = steps_from_capture([(0.5, b"a"), (0.5, b"b"), (1.25, b"c")])
    assert steps == [0.5, b"a", b"b", 0.75, b"c"]


async def test_transport_logs_every_chunk_with_timing(
    pty: tuple[int, str], raw_debug: pytest.LogCaptureFixture
) -> None:
    master, name = pty
    settings = SerialSettings(port=name, baudrate=9600, bytesize=8, parity="N", stopbits=1)
    async with open_serial(settings) as stream:
        os.write(master, b"\x01\x02")
        assert await asyncio.wait_for(read_some(stream), 2) == b"\x01\x02"
        await asyncio.sleep(0.2)
        os.write(master, b"\x03")
        assert await asyncio.wait_for(read_some(stream), 2) == b"\x03"

    captured = rawlog.parse(raw_debug.text)
    assert b"".join(data for _, data in captured) == b"\x01\x02\x03"
    assert captured[-1][0] - captured[0][0] >= 0.15


async def test_nothing_is_logged_without_debug(
    pty: tuple[int, str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=rawlog.LOGGER_NAME)
    master, name = pty
    settings = SerialSettings(port=name, baudrate=9600, bytesize=8, parity="N", stopbits=1)
    async with open_serial(settings) as stream:
        os.write(master, b"\x01")
        await asyncio.wait_for(read_some(stream), 2)

    assert rawlog.parse(caplog.text) == []


async def capture_from_pty(
    pty: tuple[int, str], meter_type: str, key_hex: str, writes: list, count: int
) -> list:
    """Run the real reader on a pty until ``count`` readings arrived."""
    master, name = pty
    received: list = []
    # Linux pseudo terminals reject even parity (EINVAL), so use no parity.
    reader = get_profile(meter_type).create_reader(
        {"dlms": {"key": key_hex, "port": name, "parity": "NONE"}}, received.append
    )

    async def meter() -> None:
        await asyncio.sleep(0.1)
        for item in writes:
            if isinstance(item, bytes):
                os.write(master, item)
            else:
                await asyncio.sleep(item)

    feeder = asyncio.create_task(meter())
    task = await run_until(reader.run, lambda: len(received) >= count)
    await feeder
    assert task.cancelled(), f"reader ended early: {task.exception()!r}"
    assert len(received) == count
    return received


async def replay(meter_type: str, key_hex: str, captured: list) -> list:
    received: list = []
    reader = get_profile(meter_type).create_reader({"dlms": {"key": key_hex}}, received.append)
    # Pause before closing the port, so the last telegram is complete.
    reader._open_stream = FakePort([*steps_from_capture(captured), 0.3, EOF])
    await run_until(reader.run, lambda: False)
    return received


async def test_burgenland_capture_replays_to_the_same_readings(
    pty: tuple[int, str],
    raw_debug: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(serial_read, "OPTICAL_IDLE_GAP_SECONDS", 0.05)
    sample = build_sample_telegram()
    writes = [sample.frame[:40], 0.01, sample.frame[40:], 0.2, sample.frame]

    live = await capture_from_pty(pty, "burgenland", sample.key_hex, writes, 2)
    replayed = await replay("burgenland", sample.key_hex, rawlog.parse(raw_debug.text))

    assert [d.to_dict() for d in replayed] == [d.to_dict() for d in live]
    assert len(replayed) == 2


async def test_noe_capture_keeps_garbage_and_broken_frames(
    pty: tuple[int, str], raw_debug: pytest.LogCaptureFixture
) -> None:
    sample = build_sample_frame()
    frame = bytes.fromhex(sample.frame_hex)
    broken = frame[:-1] + b"\x00"  # wrong trailer byte
    writes = [b"\x00\x11\x22", 0.05, broken, 0.05, frame]

    live = await capture_from_pty(pty, "noe_evn", sample.key.hex(), writes, 1)
    captured = rawlog.parse(raw_debug.text)
    replayed = await replay("noe_evn", sample.key.hex(), captured)

    # Everything the meter sent is in the log, also what the reader dropped.
    assert b"".join(data for _, data in captured) == b"\x00\x11\x22" + broken + frame
    assert [d.to_json() for d in replayed] == [d.to_json() for d in live]
