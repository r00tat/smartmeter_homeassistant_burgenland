"""Tests for ``SmartMqttMeter``: profile wiring and serial → MQTT end to end."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from meter import smartmeter as smartmeter_mod
from meter.__main__ import main
from meter.serial import read as serial_read
from meter.smartmeter import SmartMqttMeter
from meter.supervisor import cancel_and_wait
from tests.fake_broker import FakeBroker
from tests.fake_port import FakePort
from tests.fixtures.bgld_sample_frame import build_sample_telegram

VALID_KEY = "000102030405060708090A0B0C0D0E0F"

_BASE_CFG = {
    "mqtt": {"host": "mqtt.local"},
    "dlms": {"key": VALID_KEY, "port": "/dev/ttyUSB0"},
}


def test_setup_uses_burgenland_profile_by_default() -> None:
    meter = SmartMqttMeter(dict(_BASE_CFG))
    assert meter.profile.name == "burgenland"
    assert meter.mqtt.profile is meter.profile


def test_setup_uses_noe_profile_when_configured() -> None:
    meter = SmartMqttMeter(dict(_BASE_CFG, meter_type="noe_evn"))
    assert meter.profile.name == "noe_evn"
    assert meter.mqtt.profile.name == "noe_evn"


def test_setup_does_not_open_serial_port() -> None:
    # The supervisor opens the port when ``run`` starts, never in setup.
    with patch.object(smartmeter_mod, "build_reader") as build_reader:
        SmartMqttMeter(dict(_BASE_CFG))
    build_reader.assert_not_called()


def test_reader_gets_the_supervisor_callback() -> None:
    meter = SmartMqttMeter(dict(_BASE_CFG))
    with patch.object(smartmeter_mod, "build_reader") as build_reader:
        meter.create_reader(meter.got_meter_data)
    args, kwargs = build_reader.call_args
    assert args == (meter.config, meter.profile)
    assert kwargs["callback"] == meter.got_meter_data


def test_setup_uses_wien_profile_and_scales_publish_interval() -> None:
    # Wien pushes every second, so 30s means every 30th reading (not 6th).
    meter = SmartMqttMeter(dict(_BASE_CFG, meter_type="wien"))
    assert meter.publish_interval == 30
    assert meter.supervisor._every == 30


def test_setup_keeps_publish_interval_for_burgenland() -> None:
    meter = SmartMqttMeter(dict(_BASE_CFG))
    assert meter.publish_interval == 6


def test_supervisor_watches_for_a_silent_meter() -> None:
    meter = SmartMqttMeter(dict(_BASE_CFG, meter_type="wien"))
    assert meter.supervisor._stale_after == 60.0
    assert meter.supervisor._restart_after == smartmeter_mod.RESTART_AFTER_SECONDS


# --- end to end -------------------------------------------------------------


@pytest.fixture
async def broker():
    fake = FakeBroker()
    await fake.start()
    yield fake
    await fake.stop()


def e2e_meter(broker: FakeBroker, port: FakePort, **mqtt) -> tuple[SmartMqttMeter, object]:
    sample = build_sample_telegram()
    config = {
        "mqtt": {"host": "127.0.0.1", "port": broker.port, "publish_interval": 1, **mqtt},
        "dlms": {"key": sample.key_hex, "port": "/dev/ttyFAKE"},
    }
    meter = SmartMqttMeter(config)
    real_create = meter.create_reader

    def create_reader(callback):
        reader = real_create(callback)
        reader._open_stream = port
        return reader

    meter.supervisor._factory = create_reader
    meter.supervisor._retry_seconds = 0.05
    return meter, sample


async def test_telegrams_are_published_and_shutdown_goes_offline(
    broker: FakeBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serial_read, "OPTICAL_IDLE_GAP_SECONDS", 0.02)
    sample = build_sample_telegram()
    port = FakePort([sample.frame, 0.1, sample.frame])
    meter, _ = e2e_meter(broker, port)

    task = asyncio.create_task(meter.run())
    await broker.wait_for(lambda: len(broker.payloads("smartmeter/state")) == 2)
    meter.stop()
    await asyncio.wait_for(task, 3)

    state = json.loads(broker.payloads("smartmeter/state")[0])
    assert state["u1"] == 236
    assert broker.payloads("smartmeter/availability")[-1] == "offline"
    assert port.closed == 1
    discovery = json.loads(broker.payloads("homeassistant/device/smartmeter/config")[-1])
    assert discovery["device"]["sn"] == "1LGZ0012345678"


async def test_every_reading_is_logged_also_between_publishes(
    broker: FakeBroker,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: readings that are not published must still be logged."""
    monkeypatch.setattr(serial_read, "OPTICAL_IDLE_GAP_SECONDS", 0.02)
    sample = build_sample_telegram()
    steps: list = []
    for _ in range(4):
        steps += [sample.frame, 0.1]
    meter, _ = e2e_meter(broker, FakePort(steps))
    meter.supervisor._every = 2  # publish every 2nd reading

    with caplog.at_level(logging.INFO, logger="meter.smartmeter"):
        task = asyncio.create_task(meter.run())
        try:
            await broker.wait_for(lambda: caplog.text.count("got meter data") == 4)
        finally:
            meter.stop()
            await asyncio.wait_for(task, 3)

    lines = [r.getMessage() for r in caplog.records if "got meter data" in r.getMessage()]
    assert [line.split(":")[0] for line in lines] == [
        "got meter data, publishing to mqtt",
        "got meter data, skipping",
        "got meter data, publishing to mqtt",
        "got meter data, skipping",
    ]
    assert all("U(236V" in line for line in lines)


async def test_port_failure_marks_sensors_unavailable_and_recovers(
    broker: FakeBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serial_read, "OPTICAL_IDLE_GAP_SECONDS", 0.02)
    sample = build_sample_telegram()
    port = FakePort(OSError("adapter unplugged"), [sample.frame])
    meter, _ = e2e_meter(broker, port)

    task = asyncio.create_task(meter.run())
    try:
        await broker.wait_for(lambda: bool(broker.payloads("smartmeter/state")))
    finally:
        await cancel_and_wait(task)

    # offline while the port failed, online again with the first reading,
    # offline on shutdown
    availability = broker.payloads("smartmeter/availability")
    assert "offline" in availability[:-1]
    assert availability[-2:] == ["online", "offline"]
    assert len(port.opened) == 2


async def test_crashing_component_ends_run_with_an_error(broker: FakeBroker) -> None:
    meter, _ = e2e_meter(broker, FakePort())

    async def broken() -> None:
        raise RuntimeError("bug")

    meter.mqtt.run = broken  # type: ignore[method-assign]
    with pytest.raises(ExceptionGroup):
        await asyncio.wait_for(meter.run(), 3)


def test_main_runs_until_sigterm(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "mqtt: {host: 127.0.0.1, port: 1}\n"
        f"dlms: {{key: {VALID_KEY}, port: /dev/nonexistent-smartmeter}}\n"
    )
    started: list[SmartMqttMeter] = []
    real_run = SmartMqttMeter.run

    async def run_and_signal(self: SmartMqttMeter) -> None:
        started.append(self)
        asyncio.get_running_loop().call_later(0.2, os.kill, os.getpid(), signal.SIGTERM)
        await real_run(self)

    monkeypatch.setattr(SmartMqttMeter, "run", run_and_signal)

    assert main(["-c", str(config_file)]) == 0
    assert started


def test_main_returns_an_error_for_an_invalid_config(tmp_path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("mqtt: {}\ndlms: {key: short}\n")

    assert main(["-c", str(config_file)]) == 1


async def test_addon_process_end_to_end(broker: FakeBroker, tmp_path) -> None:
    """``python -m meter`` as a real process: pty meter, MQTT, SIGTERM."""
    sample = build_sample_telegram()
    master, slave = os.openpty()
    pty_name = os.ttyname(slave)
    os.close(slave)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"mqtt: {{host: 127.0.0.1, port: {broker.port}, publish_interval: 1}}\n"
        f"dlms: {{key: {sample.key_hex}, port: {pty_name}}}\n"
    )
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "meter", "-c", str(config_file),
        cwd=Path(__file__).parents[1],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        await broker.wait_for(lambda: "smartmeter/availability" in broker.topics(), timeout=20)
        for _ in range(2):
            os.write(master, sample.frame)
            await asyncio.sleep(0.4)  # > optical idle gap: separate telegrams
        await broker.wait_for(lambda: len(broker.payloads("smartmeter/state")) == 2)

        proc.send_signal(signal.SIGTERM)
        exit_code = await asyncio.wait_for(proc.wait(), 10)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        os.close(master)
    output = (await proc.stdout.read()).decode() if proc.stdout else ""

    assert exit_code == 0, output
    assert json.loads(broker.payloads("smartmeter/state")[0])["u1"] == 236
    assert broker.payloads("smartmeter/availability")[-1] == "offline"
    await broker.wait_for(lambda: broker.clean_disconnects == 1)
    assert broker.connections[0].will == ("smartmeter/availability", b"offline", False)
    assert "received signal SIGTERM" in output
