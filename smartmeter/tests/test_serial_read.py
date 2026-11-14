"""Tests for telegram assembly on the optical interface (``meter.serial.read``).

The meter pushes one telegram every 5 seconds. These tests replay such a
line on a simulated clock to make sure telegrams are never cut in two,
whatever the phase between the reader loop and the meter (#128).
"""

from __future__ import annotations

import pytest

from meter.serial import read as serial_read
from meter.serial.read import MeterReader

TIMEOUT = 1.0
BYTE_TIME = 0.00104  # one byte at 9600 baud, 8N1


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class TimedSerial:
    """Serial port replaying bytes at fixed points in simulated time."""

    def __init__(self, clock: FakeClock, schedule: list[tuple[float, int]]) -> None:
        # schedule: list of (arrival time, byte value)
        self.clock = clock
        self.schedule = sorted(schedule, key=lambda item: item[0])
        self.pos = 0
        self.closed = False

    def _available(self) -> int:
        count = 0
        while (
            self.pos + count < len(self.schedule)
            and self.schedule[self.pos + count][0] <= self.clock.now
        ):
            count += 1
        return count

    def _take(self, n: int) -> bytes:
        data = bytes(b for _, b in self.schedule[self.pos : self.pos + n])
        self.pos += n
        return data

    def read(self, size: int = 1) -> bytes:
        if self._available() == 0:
            if self.pos >= len(self.schedule):
                self.clock.now += TIMEOUT
                return b""
            next_at = self.schedule[self.pos][0]
            if next_at - self.clock.now > TIMEOUT:
                self.clock.now += TIMEOUT
                return b""
            self.clock.now = next_at
        return self._take(min(size, self._available()))

    def inWaiting(self) -> int:
        return self._available()

    def close(self) -> None:
        self.closed = True


def telegram(index: int, length: int = 250) -> bytes:
    return (
        bytes([0x7E, index])
        + bytes((index + i) % 256 for i in range(length - 3))
        + b"\x7e"
    )


def schedule_for(telegrams: list[bytes], start: float, period: float = 5.0):
    schedule = []
    for n, frame in enumerate(telegrams):
        t0 = start + n * period
        schedule += [(t0 + i * BYTE_TIME, b) for i, b in enumerate(frame)]
    return schedule


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(serial_read, "sleep", fake.sleep)
    monkeypatch.setattr(serial_read, "monotonic", fake.monotonic, raising=False)
    return fake


def make_reader(ser: TimedSerial) -> MeterReader:
    reader = MeterReader(key="00" * 16, interface_type="OPTICAL", timeout=TIMEOUT)
    reader.ser = ser  # type: ignore[assignment]
    return reader


def run_loop(reader: MeterReader, ser: TimedSerial, clock: FakeClock, until: float):
    frames: list[bytes] = []

    def handler(data: bytes) -> None:
        frames.append(data)

    original_read = ser.read

    def read(size: int = 1) -> bytes:
        if clock.now >= until:
            reader.stop()
        return original_read(size)

    ser.read = read  # type: ignore[method-assign]
    reader._read_loop(handler, 1)
    return frames


@pytest.mark.parametrize("start", [i * 0.05 for i in range(40)])
def test_every_telegram_is_received_complete(clock: FakeClock, start: float) -> None:
    """Regardless of the phase, no telegram may be split or dropped."""
    telegrams = [telegram(i) for i in range(12)]
    ser = TimedSerial(clock, schedule_for(telegrams, start=start))
    reader = make_reader(ser)

    frames = run_loop(reader, ser, clock, until=start + 12 * 5.0)

    assert frames == telegrams


def test_telegram_arriving_in_usb_chunks_is_assembled(clock: FakeClock) -> None:
    """USB adapters deliver data in bursts; small pauses must not split it."""
    frame = telegram(1, length=300)
    schedule = [(0.3 + (i // 64) * 0.05, b) for i, b in enumerate(frame)]
    ser = TimedSerial(clock, schedule)
    reader = make_reader(ser)

    assert reader._read_frame(1) == frame


def test_read_timeout_returns_no_data_and_skips_parsing(clock: FakeClock) -> None:
    ser = TimedSerial(clock, [])
    reader = make_reader(ser)

    assert reader._read_frame(1) == b""
    assert run_loop(reader, ser, clock, until=3.0) == []


def test_endless_stream_is_cut_after_max_frame_time(clock: FakeClock) -> None:
    schedule = [(0.1 + i * 0.01, i % 256) for i in range(1000)]
    ser = TimedSerial(clock, schedule)
    reader = make_reader(ser)

    data = reader._read_frame(1)

    assert 0 < len(data) < 1000
    assert clock.now - 0.1 <= serial_read.OPTICAL_MAX_FRAME_SECONDS + 0.1
