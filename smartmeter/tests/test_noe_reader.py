"""Unit tests for ``meter.noe.read.NoeMeterReader`` on a scripted port.

A pre-encrypted M-Bus frame goes through the reader; the callback must
receive a populated ``MeterData`` object.
"""

from __future__ import annotations

import logging

import pytest

from meter.noe import read as noe_read
from meter.noe.data import MeterData
from meter.noe.read import NoeMeterReader
from meter.serial.transport import PortClosedError
from tests.fake_port import EOF, SETTINGS, FakePort, chunks, run_until
from tests.fixtures.noe_sample_frame import build_sample_frame


def sample_payload() -> tuple[bytes, str]:
    sample = build_sample_frame()
    return bytes.fromhex(sample.frame_hex), sample.key.hex()


def make_reader(port: FakePort, key_hex: str, received: list) -> NoeMeterReader:
    return NoeMeterReader(
        key_hex=key_hex, settings=SETTINGS, callback=received.append, open_stream=port
    )


async def test_reader_invokes_callback_with_decoded_meter_data() -> None:
    payload, key_hex = sample_payload()
    received: list[MeterData] = []
    reader = make_reader(FakePort(chunks(payload, 8)), key_hex, received)

    await run_until(reader.run, lambda: bool(received))

    data = received[0]
    assert data.voltage_l1 == 230.1
    assert data.current_l1 == 5.0
    assert data.power_factor == 0.98
    assert data.total_consumed == 12345678


async def test_reader_waits_for_a_frame_on_a_silent_line() -> None:
    """Regression for #97: silence after connecting is not end-of-stream."""
    payload, key_hex = sample_payload()
    received: list[MeterData] = []
    reader = make_reader(FakePort([0.2, payload]), key_hex, received)

    await run_until(reader.run, lambda: bool(received))

    assert len(received) == 1


async def test_reader_skips_garbage_until_mbus_start() -> None:
    payload, key_hex = sample_payload()
    noisy = b"\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99" + payload
    received: list[MeterData] = []
    reader = make_reader(FakePort(chunks(noisy, 5)), key_hex, received)

    await run_until(reader.run, lambda: bool(received))

    assert len(received) == 1


async def test_reader_decodes_consecutive_frames() -> None:
    payload, key_hex = sample_payload()
    received: list[MeterData] = []
    reader = make_reader(FakePort([payload, 0.01, payload, 0.01, payload]), key_hex, received)

    await run_until(reader.run, lambda: len(received) == 3)

    assert len({d.to_json() for d in received}) == 1


async def test_bad_trailer_byte_is_a_frame_failure_not_a_crash() -> None:
    payload, key_hex = sample_payload()
    broken = payload[:-1] + b"\x00"
    received: list[MeterData] = []
    reader = make_reader(FakePort([broken, payload]), key_hex, received)

    task = await run_until(reader.run, lambda: bool(received))

    assert task.cancelled()
    assert len(received) == 1
    assert reader._frame_failures == 1


async def test_repeated_failures_end_the_reader() -> None:
    payload, key_hex = sample_payload()
    broken = payload[:-1] + b"\x00"
    received: list[MeterData] = []
    reader = make_reader(
        FakePort([broken] * noe_read.MAX_CONSECUTIVE_FAILURES), key_hex, received
    )

    task = await run_until(reader.run, lambda: False)

    assert task.exception() is not None
    assert received == []


async def test_port_closed_mid_frame_raises() -> None:
    payload, key_hex = sample_payload()
    port = FakePort([payload[:20], EOF])
    reader = make_reader(port, key_hex, [])

    task = await run_until(reader.run, lambda: False)

    assert isinstance(task.exception(), PortClosedError)
    assert port.closed == 1


async def test_reader_logs_heartbeat_while_silent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """When nothing is read, the heartbeat must point at the likely cause."""
    monkeypatch.setattr(noe_read, "HEARTBEAT_SECONDS", 0.02)
    reader = make_reader(FakePort([]), "00" * 16, [])

    with caplog.at_level(logging.INFO, logger="meter.noe.read"):
        await run_until(reader.run, lambda: "reader heartbeat" in caplog.text)

    assert "no bytes received" in caplog.text


@pytest.mark.parametrize(
    ("bytes_read", "syncs", "decoded", "hint"),
    [
        (0, 0, 0, "no bytes received"),
        (100, 0, 0, "no M-Bus frame sync"),
        (100, 1, 0, "check the decryption key"),
        (100, 1, 1, None),
    ],
)
def test_diagnostic_hint(bytes_read: int, syncs: int, decoded: int, hint: str | None) -> None:
    reader = NoeMeterReader(key_hex="00" * 16, settings=SETTINGS)
    reader._bytes_read = bytes_read
    reader._sync_hits = syncs
    reader._frames_decoded = decoded

    result = reader.diagnostic_hint()

    if hint is None:
        assert result is None
    else:
        assert hint in (result or "")
