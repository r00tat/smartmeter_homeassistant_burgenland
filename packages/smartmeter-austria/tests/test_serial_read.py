"""Tests for the HDLC reader (``smartmeter_austria.serial.read``) on a scripted port.

The optical interface pushes one telegram every few seconds; the reader
must hand each one to the parser complete, whatever the phase between
the reader and the meter and however the USB adapter chunks the bytes
(#128). Time is scaled down: idle gap 50 ms, telegrams 300 ms apart.
"""

from __future__ import annotations

import asyncio

import pytest

from smartmeter_austria.serial import read as serial_read
from smartmeter_austria.serial.read import MeterReader
from smartmeter_austria.serial.transport import PortClosedError
from tests.fake_port import EOF, SETTINGS, FakePort, chunks, run_until
from tests.fixtures.bgld_sample_frame import build_sample_telegram

IDLE_GAP = 0.05
PERIOD = 0.3


@pytest.fixture(autouse=True)
def fast_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(serial_read, "OPTICAL_IDLE_GAP_SECONDS", IDLE_GAP)
    monkeypatch.setattr(serial_read, "OPTICAL_MAX_FRAME_SECONDS", 0.5)


def telegram(index: int, length: int = 250) -> bytes:
    return bytes([0x7E, index]) + bytes((index + i) % 256 for i in range(length - 3)) + b"\x7e"


def make_reader(port: FakePort, interface_type: str = "OPTICAL", **kwargs) -> MeterReader:
    return MeterReader(
        key="00" * 16,
        settings=SETTINGS,
        interface_type=interface_type,
        open_stream=port,
        **kwargs,
    )


async def collect_frames(reader: MeterReader, count: int) -> list[bytes]:
    """Run the reader with a recording parser until ``count`` frames arrived."""
    frames: list[bytes] = []
    reader._handle_optical_frame = frames.append  # type: ignore[method-assign]
    reader._handle_physical_frame = frames.append  # type: ignore[method-assign]
    await run_until(reader.run, lambda: len(frames) >= count)
    return frames


@pytest.mark.parametrize("start", [0.0, 0.01, 0.07, 0.15])
async def test_every_telegram_is_received_complete(start: float) -> None:
    """Regardless of the phase, no telegram may be split or merged."""
    telegrams = [telegram(i) for i in range(4)]
    steps: list = [start] if start else []
    for frame in telegrams:
        steps += chunks(frame, 64, pause=0.005)
        steps.append(PERIOD)
    reader = make_reader(FakePort(steps))

    assert await collect_frames(reader, 4) == telegrams


async def test_usb_bursts_shorter_than_the_idle_gap_are_one_telegram() -> None:
    frame = telegram(1, length=300)
    reader = make_reader(FakePort(chunks(frame, 64, pause=IDLE_GAP / 3)))

    assert await collect_frames(reader, 1) == [frame]


async def test_endless_stream_is_cut_after_max_frame_time(
    caplog: pytest.LogCaptureFixture,
) -> None:
    steps: list = []
    for _ in range(200):
        steps += [b"\x55" * 8, 0.01]
    reader = make_reader(FakePort(steps))

    frames = await collect_frames(reader, 1)

    assert 0 < len(frames[0]) < 200 * 8
    assert "exceeded" in caplog.text


async def test_physical_interface_reads_at_least_the_frame_size() -> None:
    frame = telegram(2, length=150)
    reader = make_reader(
        FakePort(chunks(frame, 50, pause=0.01)), interface_type="PHYSICAL", hdlc_frame_size=120
    )

    frames = await collect_frames(reader, 1)

    assert frames[0] == frame


async def test_port_closed_ends_the_reader_with_an_error() -> None:
    port = FakePort([EOF])
    reader = make_reader(port)

    task = await run_until(reader.run, lambda: False)

    assert isinstance(task.exception(), PortClosedError)
    assert port.closed == 1


async def test_port_error_is_raised_and_the_port_closed() -> None:
    port = FakePort([OSError("device disconnected")])
    reader = make_reader(port)

    task = await run_until(reader.run, lambda: False)

    assert isinstance(task.exception(), OSError)
    assert port.closed == 1


async def test_open_failure_is_raised() -> None:
    reader = make_reader(FakePort(OSError("no such port")))

    task = await run_until(reader.run, lambda: False)

    assert "no such port" in str(task.exception())


async def test_cancel_closes_the_port_immediately() -> None:
    port = FakePort([])  # silent line
    reader = make_reader(port)
    task = asyncio.create_task(reader.run())
    while not port.is_open:
        await asyncio.sleep(0)

    task.cancel()
    await asyncio.wait({task}, timeout=0.1)

    assert task.cancelled()
    assert port.closed == 1


async def test_telegrams_are_decoded_and_garbage_is_skipped() -> None:
    sample = build_sample_telegram()
    corrupted = bytearray(sample.frame)
    corrupted[40] ^= 0xFF
    received: list = []
    reader = MeterReader(
        key=sample.key_hex,
        settings=SETTINGS,
        callback=received.append,
        open_stream=FakePort([bytes(corrupted), 0.1, sample.frame, 0.1, sample.frame]),
    )

    task = await run_until(reader.run, lambda: len(received) == 2)

    assert task.cancelled()
    assert received[0].to_dict() == received[1].to_dict()


async def test_repeated_parse_failures_end_the_reader() -> None:
    sample = build_sample_telegram()
    corrupted = bytearray(sample.frame)
    corrupted[40] ^= 0xFF
    steps: list = []
    for _ in range(serial_read.MAX_CONSECUTIVE_FAILURES):
        steps += [bytes(corrupted), 0.06]
    received: list = []
    reader = MeterReader(
        key=sample.key_hex,
        settings=SETTINGS,
        callback=received.append,
        open_stream=FakePort(steps),
    )

    task = await run_until(reader.run, lambda: False)

    assert task.exception() is not None
    assert received == []
