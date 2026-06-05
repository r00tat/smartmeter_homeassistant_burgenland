"""Unit tests for ``meter.noe.read.NoeMeterReader``.

The test wires a ``FakeSerial`` that yields a pre-encrypted M-Bus frame
through the reader and asserts that the callback receives a populated
``MeterData`` object.
"""

from __future__ import annotations

import logging
from collections import deque
from threading import Thread

import pytest
import serial

from meter.noe.data import MeterData
from meter.noe.read import NoeMeterReader
from tests.fixtures.noe_sample_frame import build_sample_frame


class FakeSerial:
    """Minimal stand-in for pyserial's ``Serial`` class used by the reader."""

    def __init__(self, payload: bytes) -> None:
        self._chunks: deque[bytes] = deque([payload[i : i + 8] for i in range(0, len(payload), 8)])
        self.closed = False

    def read(self, size: int = 1) -> bytes:
        if not self._chunks:
            return b""
        buf = bytearray()
        while self._chunks and len(buf) < size:
            chunk = self._chunks.popleft()
            take = min(size - len(buf), len(chunk))
            buf += chunk[:take]
            if take < len(chunk):
                self._chunks.appendleft(chunk[take:])
        return bytes(buf)

    def close(self) -> None:
        self.closed = True

    @property
    def in_waiting(self) -> int:
        return sum(len(c) for c in self._chunks)


def test_reader_invokes_callback_with_decoded_meter_data() -> None:
    sample = build_sample_frame()
    payload = bytes.fromhex(sample.frame_hex)

    received: list[MeterData] = []

    def callback(data: MeterData) -> None:
        received.append(data)
        reader.stop()

    reader = NoeMeterReader(
        key_hex=sample.key.hex(),
        serial_factory=lambda: FakeSerial(payload + b"\x00" * 64),
        callback=callback,
    )

    thread = Thread(target=reader.start)
    thread.start()
    thread.join(timeout=5.0)
    assert not thread.is_alive(), "reader did not terminate"

    assert len(received) == 1
    data = received[0]
    assert data.voltage_l1 == 230.1
    assert data.current_l1 == 5.0
    assert data.power_factor == 0.98
    assert data.total_consumed == 12345678


@pytest.mark.parametrize(
    "given, expected",
    [
        ("NONE", serial.PARITY_NONE),
        ("none", serial.PARITY_NONE),
        ("EVEN", serial.PARITY_EVEN),
        ("Odd", serial.PARITY_ODD),
        ("N", serial.PARITY_NONE),
        ("E", serial.PARITY_EVEN),
    ],
)
def test_reader_normalizes_parity_name_to_pyserial_letter(given, expected) -> None:
    """Config supplies human-readable parity names; pyserial wants letters.

    Regression test for issue #97: ``parity="NONE"`` crashed ``serial.Serial``
    with ``ValueError: Not a valid parity: 'NONE'``.
    """
    reader = NoeMeterReader(key_hex="00" * 16, parity=given)
    assert reader.parity == expected


class TimeoutThenFrameSerial(FakeSerial):
    """Serial stub that times out (empty reads) before delivering a frame.

    Real pyserial returns ``b""`` from ``read()`` whenever the configured
    ``timeout`` elapses without a byte arriving -- which happens constantly
    between frames and in the window after connecting, before the meter
    pushes its first frame. An empty read is a *timeout*, not end-of-stream,
    and must not terminate the reader.
    """

    def __init__(self, payload: bytes, timeouts_before: int = 3) -> None:
        super().__init__(payload)
        self._timeouts_before = timeouts_before

    def read(self, size: int = 1) -> bytes:
        if self._timeouts_before > 0:
            self._timeouts_before -= 1
            return b""
        return super().read(size)


def test_reader_survives_serial_timeouts_before_first_frame() -> None:
    """Regression test for issue #97 (second report).

    The reader exited on the first serial timeout, shutting the whole app
    down without reading a single frame and without crashing.
    """
    sample = build_sample_frame()
    payload = bytes.fromhex(sample.frame_hex)

    received: list[MeterData] = []

    def callback(data: MeterData) -> None:
        received.append(data)
        reader.stop()

    reader = NoeMeterReader(
        key_hex=sample.key.hex(),
        serial_factory=lambda: TimeoutThenFrameSerial(payload + b"\x00" * 64),
        callback=callback,
    )

    thread = Thread(target=reader.start)
    thread.start()
    thread.join(timeout=5.0)
    assert not thread.is_alive(), "reader did not terminate"
    assert len(received) == 1, "reader exited on a timeout instead of reading the frame"


def test_reader_skips_garbage_until_mbus_start() -> None:
    sample = build_sample_frame()
    payload = bytes.fromhex(sample.frame_hex)
    # Prepend 10 bytes of garbage that do not look like an M-Bus start.
    noisy = b"\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99" + payload

    received: list[MeterData] = []

    def callback(data: MeterData) -> None:
        received.append(data)
        reader.stop()

    reader = NoeMeterReader(
        key_hex=sample.key.hex(),
        serial_factory=lambda: FakeSerial(noisy + b"\x00" * 64),
        callback=callback,
    )

    thread = Thread(target=reader.start)
    thread.start()
    thread.join(timeout=5.0)
    assert not thread.is_alive(), "reader did not terminate"
    assert len(received) == 1


class RaisingSerial:
    """Serial stub whose ``read`` raises, simulating a port fault."""

    def __init__(self) -> None:
        self.closed = False

    def read(self, size: int = 1) -> bytes:
        raise serial.SerialException("simulated serial fault")

    def close(self) -> None:
        self.closed = True


def test_reader_reconnects_after_serial_error() -> None:
    """A serial fault must reconnect, not kill the thread (and the app)."""
    sample = build_sample_frame()
    payload = bytes.fromhex(sample.frame_hex)

    attempts = [0]
    received: list[MeterData] = []

    def callback(data: MeterData) -> None:
        received.append(data)
        reader.stop()

    def factory() -> object:
        attempts[0] += 1
        if attempts[0] == 1:
            return RaisingSerial()
        return FakeSerial(payload + b"\x00" * 64)

    reader = NoeMeterReader(
        key_hex=sample.key.hex(),
        serial_factory=factory,
        callback=callback,
    )
    reader.reconnect_backoff_seconds = 0  # no real sleep in tests

    thread = Thread(target=reader.start)
    thread.start()
    thread.join(timeout=5.0)
    assert not thread.is_alive(), "reader did not terminate"
    assert attempts[0] == 2, "reader did not reopen the port after the fault"
    assert len(received) == 1


def test_reader_logs_heartbeat_with_diagnostic_when_no_data(caplog) -> None:
    """When nothing is read, the heartbeat must point at the likely cause."""
    box: list[NoeMeterReader] = []
    clock = [0.0]

    def fake_monotonic() -> float:
        clock[0] += 100.0  # advance past the heartbeat interval each call
        return clock[0]

    class SilentSerial:
        def __init__(self) -> None:
            self.closed = False
            self._reads = 0

        def read(self, size: int = 1) -> bytes:
            self._reads += 1
            if self._reads >= 4:
                box[0].stop()
            return b""  # always a timeout, never any data

        def close(self) -> None:
            self.closed = True

    reader = NoeMeterReader(
        key_hex="00" * 16,
        serial_factory=SilentSerial,
        monotonic=fake_monotonic,
    )
    box.append(reader)

    with caplog.at_level(logging.INFO, logger="meter.noe.read"):
        thread = Thread(target=reader.start)
        thread.start()
        thread.join(timeout=5.0)

    assert not thread.is_alive(), "reader did not terminate"
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "reader heartbeat" in messages
    assert "no bytes received" in messages
