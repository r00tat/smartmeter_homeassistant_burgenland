"""Unit tests for ``meter.noe.read.NoeMeterReader``.

The test wires a ``FakeSerial`` that yields a pre-encrypted M-Bus frame
through the reader and asserts that the callback receives a populated
``MeterData`` object.
"""

from __future__ import annotations

from collections import deque
from threading import Thread

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
