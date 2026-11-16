# Home Assistant Custom Component Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the smart meter reader additionally as a Home Assistant custom integration (`smartmeter_at`, installable via HACS) that reads the serial port directly and creates native sensor entities — no MQTT broker, no Supervisor — while the add-on and the standalone image keep working unchanged.

**Architecture:** The protocol core in `smartmeter/meter/` stays the single source of truth. The integration lives in `custom_components/smartmeter_at/` and reaches the core through a symlink (`meter -> ../../smartmeter/meter`); the release workflow zips the integration with symlinks resolved and attaches the zip to the GitHub release for HACS. A new HA-free `ReaderSupervisor` in the core runs the blocking reader in a daemon thread and restarts it after failures; a push-style `DataUpdateCoordinator` marshals readings onto the event loop with `call_soon_threadsafe`, and one `SensorEntity` per `SensorSpec` of the selected meter profile reads its value from the coordinator data.

**Tech Stack:** Python, Home Assistant config entries / `DataUpdateCoordinator` / `SensorEntity`, pyserial, gurux-dlms, pytest, `pytest-homeassistant-custom-component`, GitHub Actions (hassfest, HACS action).

---

## Background the implementer needs

- **Meter profiles** ([smartmeter/meter/profile.py](../../../smartmeter/meter/profile.py)): `get_profile(meter_type)` returns a `MeterProfile` with `manufacturer`, `model`, `sensor_specs`, `push_interval_seconds`, `readings_per_publish(seconds)` and `create_reader(config, callback)`. `known_meter_types()` lists `burgenland`, `noe_evn`, `wien`. `create_reader` expects the add-on config shape: `{"interface_type": "OPTICAL"|"PHYSICAL", "dlms": {"port": ..., "key": ...}}`.
- **Readers** block in `start()` until `stop()` is called. The callback receives a `BaseMeterData` with `to_dict()` (keys like `u1`, `total_con`) and `meter_id` (meter serial or `None`).
- **Sensor catalog**: `SensorSpec` ([smartmeter/meter/mqtt/sensor_spec.py](../../../smartmeter/meter/mqtt/sensor_spec.py)) has `name`, `suffix`, `value_template` (always of the form `{{ value_json.<key> }}`), `unit_of_measurement`, `device_class`, `state_class`, `enabled_by_default`, `raw`. The `raw` spec ("Raw Data", the whole JSON) is MQTT-only and is skipped by the integration.
- **gurux on Python 3.15:** gurux-dlms 1.0.197 ships a Latin-1 source file that Python 3.15 refuses to import. The Dockerfiles run `smartmeter/fix_source_encoding.py gurux_dlms gurux_common` after `pip install`. In HA the integration's requirements are installed by HA itself, so the integration must apply this fix-up at runtime before importing the core (Task 5).
- **Core imports gurux at import time** (`profile` → `serial.read` → `dlms.read` → `gurux_dlms`). Never import `.meter.profile` at module level in the integration; always go through `async_load_core()` (Task 5).
- **Core tests** run from `smartmeter/`: `cd smartmeter && python3 -m pytest tests/ -v`. Lint: `cd smartmeter && python3 -m ruff check`. Types: `python3 -m mypy --config-file mypy.ini` from repo root.
- **Integration tests** need Home Assistant installed. They run in a separate virtualenv (`.venv-ha`) from the repo root: `python -m pytest tests_integration -v`.

## File structure

| Path | Status | Responsibility |
|---|---|---|
| `smartmeter/meter/mqtt/sensor_spec.py` | modify | add `SensorSpec.value_key` (data key parsed from `value_template`) |
| `smartmeter/meter/serial/read.py` | modify | `MeterReader.start()` closes the port also when the loop raises |
| `smartmeter/meter/supervisor.py` | create | HA-free `ReaderSupervisor` (thread + restart) and `probe()` (one reading or timeout) |
| `smartmeter/tests/test_sensor_spec.py` | create | tests for `value_key` |
| `smartmeter/tests/test_serial_read.py` | modify | test for port closing |
| `smartmeter/tests/test_supervisor.py` | create | tests for supervisor and probe |
| `custom_components/smartmeter_at/meter` | create (symlink) | → `../../smartmeter/meter` |
| `custom_components/smartmeter_at/fix_source_encoding.py` | create (symlink) | → `../../smartmeter/fix_source_encoding.py` |
| `custom_components/smartmeter_at/manifest.json` | create | integration manifest |
| `custom_components/smartmeter_at/const.py` | create | domain, config keys, defaults |
| `custom_components/smartmeter_at/core.py` | create | gurux fix-up + lazy, cached import of the core |
| `custom_components/smartmeter_at/coordinator.py` | create | push coordinator wrapping `ReaderSupervisor`; `build_reader_factory()` |
| `custom_components/smartmeter_at/__init__.py` | create | setup / unload / reload of config entries |
| `custom_components/smartmeter_at/sensor.py` | create | `SensorSpec` → `SensorEntityDescription`, sensor entities |
| `custom_components/smartmeter_at/config_flow.py` | create | user step (meter type, port, key, interface) with live probe; options flow (update interval) |
| `custom_components/smartmeter_at/diagnostics.py` | create | redacted diagnostics |
| `custom_components/smartmeter_at/translations/en.json`, `de.json` | create | UI texts |
| `hacs.json` | create | HACS metadata (zip release) |
| `tests_integration/` | create | HA test harness and integration tests |
| `requirements-ha-test.txt` | create | pinned HA test dependencies |
| `.github/workflows/integration.yml` | create | hassfest, HACS validation, integration tests |
| `.github/workflows/release.yml` | modify | bump manifest version, upload `smartmeter_at.zip` |
| `README.md`, `.gitignore` | modify | docs, ignore `.venv-ha` |

---

### Task 0: Preparation

**Files:**
- Create: `requirements-ha-test.txt`, `tests_integration/.python-version`
- Modify: `.gitignore`

- [ ] **Step 1: Create a worktree and branch**

```bash
cd /Users/paul/Documents/developing/hassio/smartmeter_homeassistant_burgenland
git worktree add .worktrees/ha-custom-component -b feat/ha-custom-component
cd .worktrees/ha-custom-component
```

All further paths are relative to this worktree.

- [ ] **Step 2: Find the Python version and pins for the HA test environment**

`pytest-homeassistant-custom-component` pins one exact Home Assistant version, which in turn requires a specific Python. Try 3.14 first, fall back to 3.15:

```bash
uv venv -p 3.14 .venv-ha && uv pip install -p .venv-ha pytest-homeassistant-custom-component \
  || (rm -rf .venv-ha && uv venv -p 3.15 .venv-ha && uv pip install -p .venv-ha pytest-homeassistant-custom-component)
.venv-ha/bin/python --version
uv pip freeze -p .venv-ha | grep -E '^(pytest-homeassistant-custom-component|homeassistant)=='
```

Expected: one Python version and two pinned lines, e.g. `homeassistant==2026.11.x` and `pytest-homeassistant-custom-component==0.13.x`.

- [ ] **Step 3: Record the pins**

Write `requirements-ha-test.txt` (use the exact `pytest-homeassistant-custom-component` version from Step 2):

```text
# Same requirements as custom_components/smartmeter_at/manifest.json; the
# add-on's requirements.txt cannot be reused because Home Assistant pins an
# older paho-mqtt than the add-on (the integration does not use MQTT).
gurux-common==1.0.13
gurux-dlms==1.0.197
pycryptodomex>=3.24
pyserial>=3.5
beautifulsoup4>=4.15
lxml>=6.1
pytest-homeassistant-custom-component==<version printed in Step 2>
```

(Done: Python 3.14, `homeassistant==2026.10.4`, `pytest-homeassistant-custom-component==0.13.375`.)

Write the major.minor Python version from Step 2 into `tests_integration/.python-version`, e.g.:

```text
3.14
```

Append to `.gitignore`:

```text
.venv-ha/
```

- [ ] **Step 4: Install and apply the gurux fix-up in the HA venv**

```bash
uv pip install -p .venv-ha -r requirements-ha-test.txt
.venv-ha/bin/python smartmeter/fix_source_encoding.py gurux_dlms gurux_common
uv pip show -p .venv-ha gurux-dlms homeassistant | grep -E '^(Name|Version)'
```

Expected: name and version of both packages. Whether gurux actually imports is covered by the tests in Task 5.

- [ ] **Step 5: Commit**

```bash
git add .gitignore requirements-ha-test.txt tests_integration/.python-version
```

```bash
git commit -m "chore: pin Home Assistant test environment for the custom component"
```

---

### Task 1: `SensorSpec.value_key`

The integration needs the data key behind each sensor (`total_con`), which today only exists inside the Jinja template string.

**Files:**
- Modify: `smartmeter/meter/mqtt/sensor_spec.py`
- Test: `smartmeter/tests/test_sensor_spec.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for ``SensorSpec.value_key``."""

import pytest

from meter.mqtt.sensor_spec import SensorSpec
from meter.profile import get_profile, known_meter_types


def test_value_key_is_parsed_from_template() -> None:
    spec = SensorSpec(name="x", suffix="_x", value_template="{{ value_json.total_con }}")
    assert spec.value_key == "total_con"


def test_value_key_is_none_without_template() -> None:
    assert SensorSpec(name="Raw Data", suffix="", raw=True).value_key is None


def test_value_key_rejects_complex_templates() -> None:
    spec = SensorSpec(name="x", suffix="_x", value_template="{{ value_json.a * 2 }}")
    with pytest.raises(ValueError, match="value_json"):
        _ = spec.value_key


@pytest.mark.parametrize("meter_type", known_meter_types())
def test_every_catalog_sensor_has_a_value_key(meter_type: str) -> None:
    for spec in get_profile(meter_type).sensor_specs:
        if spec.raw:
            continue
        assert spec.value_key, f"{meter_type}: {spec.name} has no value key"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd smartmeter && python3 -m pytest tests/test_sensor_spec.py -v`
Expected: FAIL with `AttributeError: 'SensorSpec' object has no attribute 'value_key'`

- [ ] **Step 3: Implement**

Replace `smartmeter/meter/mqtt/sensor_spec.py` with:

```python
"""Sensor-spec dataclass shared across meter profiles."""

from __future__ import annotations

import re
from dataclasses import dataclass

_VALUE_KEY_RE = re.compile(r"^\{\{\s*value_json\.(\w+)\s*\}\}$")


@dataclass(frozen=True)
class SensorSpec:
    """Static description of a Home Assistant sensor for this device."""

    name: str
    suffix: str  # appended to device_id for unique_id; empty means use device_id
    value_template: str | None = None
    unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    enabled_by_default: bool | None = None
    raw: bool = False  # the 'Raw Data' sensor has a different shape

    @property
    def value_key(self) -> str | None:
        """Key in ``MeterData.to_dict()`` this sensor reads.

        The native Home Assistant integration has no Jinja templates, so it
        needs the plain key behind ``{{ value_json.<key> }}``.
        """
        if self.value_template is None:
            return None
        match = _VALUE_KEY_RE.match(self.value_template)
        if match is None:
            raise ValueError(
                f"value_template {self.value_template!r} is not a plain "
                "'{{ value_json.<key> }}' lookup"
            )
        return match.group(1)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd smartmeter && python3 -m pytest tests/test_sensor_spec.py -v`
Expected: 6 passed (1 + 1 + 1 + 3 parametrized)

- [ ] **Step 5: Lint and commit**

```bash
cd smartmeter && python3 -m ruff check && cd .. && python3 -m mypy --config-file mypy.ini
```

```bash
git add smartmeter/meter/mqtt/sensor_spec.py smartmeter/tests/test_sensor_spec.py
```

```bash
git commit -m "feat(core): expose the data key behind each sensor spec"
```

---

### Task 2: HDLC reader closes the port when the loop raises

`MeterReader.start()` ([smartmeter/meter/serial/read.py](../../../smartmeter/meter/serial/read.py)) only disconnects after a clean loop exit. After 10 parse failures the loop raises and the port stays open. In the add-on the process exits anyway; the integration restarts the reader in the same process and would fail with "port busy".

**Files:**
- Modify: `smartmeter/meter/serial/read.py` (method `start`)
- Test: `smartmeter/tests/test_serial_read.py`

- [ ] **Step 1: Write the failing test** (append to `smartmeter/tests/test_serial_read.py`)

```python
class ClosableSerial:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_start_closes_port_when_loop_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = MeterReader(key="00" * 16, interface_type="OPTICAL")
    port = ClosableSerial()

    def connect() -> None:
        reader.ser = port  # type: ignore[assignment]

    def failing_loop() -> None:
        raise RuntimeError("too many parse failures")

    monkeypatch.setattr(reader, "connect", connect)
    monkeypatch.setattr(reader, "optical_loop", failing_loop)

    with pytest.raises(RuntimeError, match="parse failures"):
        reader.start()

    assert port.closed
    assert reader.is_running is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd smartmeter && python3 -m pytest tests/test_serial_read.py::test_start_closes_port_when_loop_raises -v`
Expected: FAIL on `assert port.closed`

- [ ] **Step 3: Implement** — replace `start` in `smartmeter/meter/serial/read.py`:

```python
    def start(self):
        """Start the read process"""
        self.is_running = True
        try:
            self.connect()
            if self.is_optical_interface:
                self.optical_loop()
            else:
                self.physical_loop()
        finally:
            # Also on errors: a reader that is restarted in the same process
            # (Home Assistant integration) must not find its own port busy.
            self.is_running = False
            self.disconnect()
```

- [ ] **Step 4: Run the whole serial test module**

Run: `cd smartmeter && python3 -m pytest tests/test_serial_read.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add smartmeter/meter/serial/read.py smartmeter/tests/test_serial_read.py
```

```bash
git commit -m "fix(serial): close the port when the read loop raises"
```

---

### Task 3: `ReaderSupervisor` and `probe` in the core

HA-free, so it is tested by the existing core suite on Python 3.15 and is reusable by the add-on later.

**Files:**
- Create: `smartmeter/meter/supervisor.py`
- Test: `smartmeter/tests/test_supervisor.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for ``meter.supervisor``."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from meter.supervisor import ReaderSupervisor, probe


class FakeReader:
    """Emits ``items``, then raises ``fail`` or blocks until stopped."""

    def __init__(
        self,
        callback: Callable[[Any], None],
        items: list[Any] | None = None,
        fail: Exception | None = None,
        block: bool = True,
    ) -> None:
        self.callback = callback
        self.items = items or []
        self.fail = fail
        self.block = block
        self.stopped = threading.Event()

    def start(self) -> None:
        for item in self.items:
            self.callback(item)
        if self.fail is not None:
            raise self.fail
        if self.block:
            self.stopped.wait(5)

    def stop(self) -> None:
        self.stopped.set()


def wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_forwards_every_nth_reading() -> None:
    data: list[Any] = []
    supervisor = ReaderSupervisor(
        lambda cb: FakeReader(cb, items=[0, 1, 2, 3, 4, 5]),
        on_data=data.append,
        on_error=lambda err: None,
        every=2,
    )
    supervisor.start()
    assert wait_for(lambda: len(data) == 3)
    supervisor.stop()
    assert data == [0, 2, 4]


def test_restarts_reader_after_failure() -> None:
    data: list[Any] = []
    errors: list[Exception] = []
    readers = iter(
        [
            lambda cb: FakeReader(cb, fail=OSError("port gone")),
            lambda cb: FakeReader(cb, items=["ok"]),
        ]
    )
    supervisor = ReaderSupervisor(
        lambda cb: next(readers)(cb),
        on_data=data.append,
        on_error=errors.append,
        retry_seconds=0.01,
    )
    supervisor.start()
    assert wait_for(lambda: data == ["ok"])
    supervisor.stop()
    assert [str(err) for err in errors] == ["port gone"]


def test_reader_that_returns_on_its_own_is_reported() -> None:
    errors: list[Exception] = []
    supervisor = ReaderSupervisor(
        lambda cb: FakeReader(cb, block=False),
        on_data=lambda data: None,
        on_error=errors.append,
        retry_seconds=0.01,
    )
    supervisor.start()
    assert wait_for(lambda: len(errors) >= 1)
    supervisor.stop()
    assert isinstance(errors[0], RuntimeError)


def test_stop_ends_thread_without_reporting_an_error() -> None:
    errors: list[Exception] = []
    supervisor = ReaderSupervisor(
        lambda cb: FakeReader(cb), on_data=lambda data: None, on_error=errors.append
    )
    supervisor.start()
    assert wait_for(supervisor.is_running)
    supervisor.stop()
    assert not supervisor.is_running()
    assert errors == []


def test_every_must_be_positive() -> None:
    with pytest.raises(ValueError):
        ReaderSupervisor(lambda cb: FakeReader(cb), lambda d: None, lambda e: None, every=0)


def test_probe_returns_first_reading() -> None:
    assert probe(lambda cb: FakeReader(cb, items=["a", "b"]), timeout=1.0) == "a"


def test_probe_raises_reader_error() -> None:
    with pytest.raises(OSError, match="no port"):
        probe(lambda cb: FakeReader(cb, fail=OSError("no port")), timeout=1.0)


def test_probe_returns_none_on_timeout() -> None:
    assert probe(lambda cb: FakeReader(cb), timeout=0.05) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd smartmeter && python3 -m pytest tests/test_supervisor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'meter.supervisor'`

- [ ] **Step 3: Implement `smartmeter/meter/supervisor.py`**

```python
"""Run a meter reader in a background thread and restart it after failures.

Used by the Home Assistant integration, which cannot let a reader fault end
the process the way the add-on does. Nothing in here depends on Home
Assistant; the integration passes thread-safe callbacks.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from .profile import MeterDataCallback, MeterReaderLike

log = logging.getLogger("meter.supervisor")

ReaderFactory = Callable[[MeterDataCallback], MeterReaderLike]


class ReaderSupervisor:
    """Keep one reader running until ``stop()``.

    ``on_data`` receives every ``every``-th reading, ``on_error`` every
    reader failure (including a reader that returns without being stopped).
    Both are called from the reader thread.
    """

    def __init__(
        self,
        reader_factory: ReaderFactory,
        on_data: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        every: int = 1,
        retry_seconds: float = 10.0,
    ) -> None:
        if every < 1:
            raise ValueError("every must be >= 1")
        self._factory = reader_factory
        self._on_data = on_data
        self._on_error = on_error
        self._every = every
        self._retry_seconds = retry_seconds
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._reader: MeterReaderLike | None = None
        self._thread: threading.Thread | None = None
        self._count = 0

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("supervisor already started")
        self._thread = threading.Thread(
            target=self._run, name="smartmeter-reader", daemon=True
        )
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the reader and wait for the thread. Safe to call twice."""
        self._stop.set()
        with self._lock:
            reader = self._reader
        if reader is not None:
            reader.stop()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                log.warning("reader thread did not exit within %.0fs", timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            error: Exception | None = None
            try:
                with self._lock:
                    if self._stop.is_set():
                        break
                    reader = self._factory(self._handle)
                    self._reader = reader
                reader.start()
                if not self._stop.is_set():
                    error = RuntimeError("meter reader stopped unexpectedly")
            except Exception as err:  # any reader fault must lead to a restart
                log.warning("meter reader failed: %s", err, exc_info=True)
                error = err
            finally:
                with self._lock:
                    self._reader = None
            if error is not None and not self._stop.is_set():
                self._on_error(error)
            self._stop.wait(self._retry_seconds)

    def _handle(self, data: Any) -> None:
        if self._count % self._every == 0:
            self._on_data(data)
        self._count += 1


def probe(reader_factory: ReaderFactory, timeout: float) -> Any | None:
    """Run a reader until the first reading or ``timeout`` seconds.

    Returns the first reading, ``None`` on timeout, and re-raises the
    reader's exception if it failed before delivering anything (e.g. the
    serial port does not exist).
    """
    received: list[Any] = []
    errors: list[Exception] = []
    done = threading.Event()

    def on_data(data: Any) -> None:
        if not received:
            received.append(data)
        done.set()

    reader = reader_factory(on_data)

    def run() -> None:
        try:
            reader.start()
        except Exception as err:  # reported to the caller below
            errors.append(err)
        finally:
            done.set()

    thread = threading.Thread(target=run, name="smartmeter-probe", daemon=True)
    thread.start()
    done.wait(timeout)
    reader.stop()
    thread.join(timeout=5.0)
    if received:
        return received[0]
    if errors:
        raise errors[0]
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd smartmeter && python3 -m pytest tests/test_supervisor.py -v`
Expected: 8 passed

- [ ] **Step 5: Full core suite, lint, types, commit**

```bash
cd smartmeter && python3 -m pytest tests/ -q && python3 -m ruff check && cd .. && python3 -m mypy --config-file mypy.ini
```

```bash
git add smartmeter/meter/supervisor.py smartmeter/tests/test_supervisor.py
```

```bash
git commit -m "feat(core): reader supervisor with restart and one-shot probe"
```

---

### Task 4: Integration skeleton and HA test harness

**Files:**
- Create: `custom_components/smartmeter_at/{__init__.py,const.py,manifest.json}`, symlinks `meter`, `fix_source_encoding.py`
- Create: `hacs.json`
- Create: `tests_integration/{__init__.py,pytest.ini,conftest.py,test_manifest.py}`

- [ ] **Step 1: Create the directory and symlinks**

```bash
mkdir -p custom_components/smartmeter_at/translations
cd custom_components/smartmeter_at
ln -s ../../smartmeter/meter meter
ln -s ../../smartmeter/fix_source_encoding.py fix_source_encoding.py
cd ../..
ls -l custom_components/smartmeter_at
```

Expected: two symlinks pointing into `smartmeter/`.

- [ ] **Step 2: `custom_components/smartmeter_at/manifest.json`**

```json
{
  "domain": "smartmeter_at",
  "name": "Smartmeter Austria",
  "codeowners": ["@r00tat"],
  "config_flow": true,
  "documentation": "https://github.com/r00tat/smartmeter_homeassistant_burgenland",
  "integration_type": "device",
  "iot_class": "local_push",
  "issue_tracker": "https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues",
  "loggers": ["meter", "gurux_dlms"],
  "requirements": [
    "gurux-common==1.0.13",
    "gurux-dlms==1.0.197",
    "pycryptodomex>=3.24",
    "pyserial>=3.5",
    "beautifulsoup4>=4.15",
    "lxml>=6.1"
  ],
  "version": "0.8.1"
}
```

The gurux pins must match `smartmeter/requirements.txt`; Task 10 adds a CI check for that.

- [ ] **Step 3: `custom_components/smartmeter_at/const.py`**

```python
"""Constants for the Smartmeter Austria integration."""

DOMAIN = "smartmeter_at"

CONF_METER_TYPE = "meter_type"
CONF_PORT = "port"
CONF_KEY = "key"
CONF_INTERFACE_TYPE = "interface_type"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_METER_TYPE = "burgenland"
# Lower case: Home Assistant requires lower-case selector option keys for
# translations. Converted to the core's "OPTICAL"/"PHYSICAL" when building
# the reader.
INTERFACE_TYPES = ["optical", "physical"]
DEFAULT_INTERFACE_TYPE = "optical"
# Seconds between entity updates. The meter pushes every 1-5 s; writing each
# telegram to the recorder would bloat the database.
DEFAULT_UPDATE_INTERVAL = 10

DATA_CORE = f"{DOMAIN}_core"
```

- [ ] **Step 4: Minimal `custom_components/smartmeter_at/__init__.py`**

```python
"""Smartmeter Austria: read Austrian smart meters directly from the serial port."""
```

- [ ] **Step 5: `hacs.json` (repo root)**

```json
{
  "name": "Smartmeter Austria",
  "homeassistant": "2025.2.0",
  "render_readme": true,
  "zip_release": true,
  "filename": "smartmeter_at.zip"
}
```

- [ ] **Step 6: Test harness**

`tests_integration/__init__.py`: empty file.

`tests_integration/pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
pythonpath = ..
testpaths = .
```

`tests_integration/conftest.py`:

```python
"""Shared fixtures for the Home Assistant integration tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load integrations from custom_components/."""
    yield
```

- [ ] **Step 7: Write the smoke test** — `tests_integration/test_manifest.py`

```python
"""The integration is discoverable by Home Assistant."""

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_custom_components

from custom_components.smartmeter_at.const import DOMAIN


async def test_integration_is_discovered(hass: HomeAssistant) -> None:
    integrations = await async_get_custom_components(hass)
    assert DOMAIN in integrations
    assert integrations[DOMAIN].config_flow is True
```

- [ ] **Step 8: Run it**

Run: `.venv-ha/bin/python -m pytest tests_integration -v`
Expected: 1 passed

- [ ] **Step 9: Commit**

```bash
git add custom_components hacs.json tests_integration
```

```bash
git commit -m "feat(integration): skeleton, manifest and HA test harness"
```

---

### Task 5: Core loader with runtime gurux fix-up

**Files:**
- Create: `custom_components/smartmeter_at/core.py`
- Test: `tests_integration/test_core.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the lazy core import and the gurux fix-up."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.smartmeter_at import core


def test_no_fixup_when_gurux_imports() -> None:
    with (
        patch.object(core, "_import_gurux") as import_gurux,
        patch.object(core.fix_source_encoding, "main") as fix,
    ):
        core.ensure_gurux_importable()
    import_gurux.assert_called_once()
    fix.assert_not_called()


def test_fixup_runs_after_syntax_error() -> None:
    with (
        patch.object(core, "_import_gurux", side_effect=[SyntaxError("bad"), None]) as import_gurux,
        patch.object(core.fix_source_encoding, "main") as fix,
    ):
        core.ensure_gurux_importable()
    fix.assert_called_once_with(["gurux_dlms", "gurux_common"])
    assert import_gurux.call_count == 2


async def test_async_load_core_is_cached(hass: HomeAssistant) -> None:
    first = await core.async_load_core(hass)
    second = await core.async_load_core(hass)
    assert first is second
    assert "burgenland" in first.profile.known_meter_types()
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv-ha/bin/python -m pytest tests_integration/test_core.py -v`
Expected: FAIL with `ImportError: cannot import name 'core'`

- [ ] **Step 3: Implement `custom_components/smartmeter_at/core.py`**

```python
"""Import the meter core lazily, after making gurux importable.

The core imports gurux-dlms at import time. gurux-dlms 1.0.197 ships a
Latin-1 source file that Python 3.15 rejects; the add-on images re-encode
it at build time, the integration has to do it at runtime because Home
Assistant installs the requirements itself.
"""

from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass
from types import ModuleType

from homeassistant.core import HomeAssistant

from . import fix_source_encoding
from .const import DATA_CORE

_LOGGER = logging.getLogger(__name__)
_GURUX_PACKAGES = ["gurux_dlms", "gurux_common"]


@dataclass(frozen=True)
class Core:
    """The core modules the integration uses."""

    profile: ModuleType
    supervisor: ModuleType
    config_validation: ModuleType


def _import_gurux() -> None:
    for name in _GURUX_PACKAGES:
        importlib.import_module(name)


def ensure_gurux_importable() -> None:
    """Import gurux; re-encode its sources once if Python refuses them."""
    try:
        _import_gurux()
        return
    except SyntaxError as err:
        _LOGGER.warning(
            "gurux-dlms is not importable on this Python (%s), re-encoding its sources",
            err,
        )
    fix_source_encoding.main(list(_GURUX_PACKAGES))
    for name in [m for m in sys.modules if m.split(".")[0] in _GURUX_PACKAGES]:
        del sys.modules[name]
    importlib.invalidate_caches()
    _import_gurux()


def load_core() -> Core:
    """Blocking: fix gurux if needed and import the core modules."""
    ensure_gurux_importable()
    from .meter import config_validation, profile, supervisor

    return Core(profile=profile, supervisor=supervisor, config_validation=config_validation)


async def async_load_core(hass: HomeAssistant) -> Core:
    """Load the core once per Home Assistant instance, off the event loop."""
    core: Core | None = hass.data.get(DATA_CORE)
    if core is None:
        core = await hass.async_add_import_executor_job(load_core)
        hass.data[DATA_CORE] = core
    return core
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv-ha/bin/python -m pytest tests_integration/test_core.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/smartmeter_at/core.py tests_integration/test_core.py
```

```bash
git commit -m "feat(integration): lazy core import with runtime gurux fix-up"
```

---

### Task 6: Push coordinator

**Files:**
- Create: `custom_components/smartmeter_at/coordinator.py`
- Modify: `tests_integration/conftest.py`
- Test: `tests_integration/test_coordinator.py`

- [ ] **Step 1: Replace `tests_integration/conftest.py`** with shared test data, the fake reader and the existing autouse fixture

```python
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
```

- [ ] **Step 2: Write the failing tests** — `tests_integration/test_coordinator.py`

```python
"""Tests for the push coordinator."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at.const import CONF_UPDATE_INTERVAL, DOMAIN
from custom_components.smartmeter_at.coordinator import (
    SmartMeterCoordinator,
    build_reader_factory,
)
from custom_components.smartmeter_at.core import async_load_core

from .conftest import ENTRY_DATA, METER_ID, wait_for_data


async def test_coordinator_receives_readings(hass: HomeAssistant, fake_readers) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, options={CONF_UPDATE_INTERVAL: 10})
    entry.add_to_hass(hass)
    coordinator = SmartMeterCoordinator(hass, entry, await async_load_core(hass))
    coordinator.start()
    try:
        await wait_for_data(coordinator)
    finally:
        await coordinator.async_stop()

    assert coordinator.data["u1"] == 236
    assert coordinator.data["total_con"] == 49244276
    assert coordinator.meter_id == METER_ID
    assert coordinator.last_update_success


async def test_reader_error_marks_update_failed(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    coordinator = SmartMeterCoordinator(hass, entry, await async_load_core(hass))
    coordinator.async_set_update_error(OSError("port gone"))
    assert not coordinator.last_update_success


async def test_build_reader_factory_maps_entry_data(hass: HomeAssistant) -> None:
    core = await async_load_core(hass)
    profile = core.profile.get_profile("burgenland")
    reader = build_reader_factory(profile, ENTRY_DATA)(lambda data: None)
    assert reader.port == "/dev/ttyUSB0"
    assert reader.key == ENTRY_DATA["key"]
    assert reader.is_optical_interface is True
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv-ha/bin/python -m pytest tests_integration/test_coordinator.py -v`
Expected: FAIL with `ModuleNotFoundError: ... coordinator`

- [ ] **Step 4: Implement `custom_components/smartmeter_at/coordinator.py`**

```python
"""Push coordinator: readings from the reader thread onto the event loop."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_INTERFACE_TYPE,
    CONF_KEY,
    CONF_METER_TYPE,
    CONF_PORT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_INTERFACE_TYPE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .core import Core

_LOGGER = logging.getLogger(__name__)


def build_reader_factory(profile: Any, entry_data: Mapping[str, Any]) -> Callable[[Any], Any]:
    """Return ``callback -> reader`` for the profile and the entry's settings."""
    config = {
        "interface_type": str(
            entry_data.get(CONF_INTERFACE_TYPE, DEFAULT_INTERFACE_TYPE)
        ).upper(),
        "dlms": {"port": entry_data[CONF_PORT], "key": entry_data[CONF_KEY]},
    }
    return partial(profile.create_reader, config)


class SmartMeterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the latest reading; the reader pushes, nothing is polled."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, core: Core) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None
        )
        self.profile = core.profile.get_profile(entry.data[CONF_METER_TYPE])
        self.meter_id: str | None = None
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        self._supervisor = core.supervisor.ReaderSupervisor(
            build_reader_factory(self.profile, entry.data),
            on_data=self._on_data_from_thread,
            on_error=self._on_error_from_thread,
            every=self.profile.readings_per_publish(float(interval)),
        )

    def start(self) -> None:
        self._supervisor.start()

    async def async_stop(self) -> None:
        await self.hass.async_add_executor_job(self._supervisor.stop)

    def _on_data_from_thread(self, data: Any) -> None:
        self.hass.loop.call_soon_threadsafe(self._async_handle_data, data)

    def _on_error_from_thread(self, err: Exception) -> None:
        self.hass.loop.call_soon_threadsafe(self.async_set_update_error, err)

    @callback
    def _async_handle_data(self, data: Any) -> None:
        if data.meter_id and self.meter_id is None:
            self.meter_id = data.meter_id
            self._async_set_device_serial(data.meter_id)
        self.async_set_updated_data(data.to_dict())

    @callback
    def _async_set_device_serial(self, serial_number: str) -> None:
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device(
            identifiers={(DOMAIN, self.config_entry.entry_id)}
        )
        if device is not None:
            dev_reg.async_update_device(device.id, serial_number=serial_number)


type SmartMeterConfigEntry = ConfigEntry[SmartMeterCoordinator]
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv-ha/bin/python -m pytest tests_integration/test_coordinator.py -v`
Expected: 3 passed (no "lingering thread" error — `async_stop` joins the thread)

- [ ] **Step 6: Commit**

```bash
git add custom_components/smartmeter_at/coordinator.py tests_integration/conftest.py tests_integration/test_coordinator.py
```

```bash
git commit -m "feat(integration): push coordinator around the reader supervisor"
```

---

### Task 7: Sensor platform and entry setup

**Files:**
- Create: `custom_components/smartmeter_at/sensor.py`
- Modify: `custom_components/smartmeter_at/__init__.py`
- Test: `tests_integration/test_sensor.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for entry setup and the sensor entities."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at.const import DOMAIN
from custom_components.smartmeter_at.core import async_load_core
from custom_components.smartmeter_at.sensor import description_from_spec

from .conftest import ENTRY_DATA, METER_ID, wait_for_data


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Smart Meter")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for_data(entry.runtime_data)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, entry: MockConfigEntry, suffix: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}{suffix}"
    )
    assert entity_id is not None, suffix
    return hass.states.get(entity_id)


async def test_sensors_show_meter_values(hass: HomeAssistant, fake_readers) -> None:
    entry = await _setup(hass)
    try:
        assert _state(hass, entry, "_voltage_l1").state == "236"
        assert float(_state(hass, entry, "_current_l1").state) == pytest.approx(5.12)
        assert _state(hass, entry, "_power_consumed").state == "3314"
        energy = _state(hass, entry, "_total_energy_consumed")
        assert float(energy.state) == pytest.approx(49244.276)
        assert energy.attributes["unit_of_measurement"] == "kWh"
        assert energy.attributes["state_class"] == "total_increasing"
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_angle_sensors_are_disabled_by_default(hass: HomeAssistant, fake_readers) -> None:
    entry = await _setup(hass)
    try:
        entity_id = er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_angle_l1"
        )
        assert er.async_get(hass).async_get(entity_id).disabled_by is not None
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_device_gets_meter_serial(hass: HomeAssistant, fake_readers) -> None:
    entry = await _setup(hass)
    try:
        device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
        assert device.manufacturer == "Landis+Gyr"
        assert device.model == "E450"
        assert device.serial_number == METER_ID
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_stops_reader(hass: HomeAssistant, fake_readers) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert all(reader.stopped.is_set() for reader in fake_readers)


@pytest.mark.parametrize(
    "meter_type",
    ["burgenland", "noe_evn", "wien", "steiermark", "steiermark_sagemcom", "salzburg", "tirol", "h1"],
)
async def test_every_catalog_maps_to_valid_descriptions(
    hass: HomeAssistant, meter_type: str
) -> None:
    core = await async_load_core(hass)
    for spec in core.profile.get_profile(meter_type).sensor_specs:
        if not spec.raw:
            description_from_spec(spec)  # raises on unknown device/state class
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv-ha/bin/python -m pytest tests_integration/test_sensor.py -v`
Expected: FAIL with `ModuleNotFoundError: ... sensor`

- [ ] **Step 3: Implement `custom_components/smartmeter_at/sensor.py`**

```python
"""Sensor entities, one per sensor spec of the selected meter profile."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartMeterConfigEntry, SmartMeterCoordinator


def description_from_spec(spec: Any) -> SensorEntityDescription:
    """Translate a core ``SensorSpec`` into a Home Assistant description."""
    unit = spec.unit_of_measurement or None  # "" (power factor) means no unit
    return SensorEntityDescription(
        key=spec.value_key,
        name=spec.name,
        device_class=SensorDeviceClass(spec.device_class) if spec.device_class else None,
        state_class=SensorStateClass(spec.state_class) if spec.state_class else None,
        native_unit_of_measurement=unit,
        suggested_unit_of_measurement=(
            UnitOfEnergy.KILO_WATT_HOUR if unit == UnitOfEnergy.WATT_HOUR else None
        ),
        entity_registry_enabled_default=spec.enabled_by_default is not False,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartMeterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SmartMeterSensor(coordinator, description_from_spec(spec), spec.suffix)
        for spec in coordinator.profile.sensor_specs
        if not spec.raw
    )


class SmartMeterSensor(CoordinatorEntity[SmartMeterCoordinator], SensorEntity):
    """One value of the latest meter reading."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmartMeterCoordinator,
        description: SensorEntityDescription,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=coordinator.profile.manufacturer,
            model=coordinator.profile.model,
        )

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.key)
```

- [ ] **Step 4: Replace `custom_components/smartmeter_at/__init__.py`**

```python
"""Smartmeter Austria: read Austrian smart meters directly from the serial port."""

from __future__ import annotations

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .coordinator import SmartMeterConfigEntry, SmartMeterCoordinator
from .core import async_load_core

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: SmartMeterConfigEntry) -> bool:
    core = await async_load_core(hass)
    coordinator = SmartMeterCoordinator(hass, entry, core)
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Start after the platforms so the device exists when the first reading
    # (with the meter serial number) arrives.
    coordinator.start()

    async def _async_stop(_event: Event) -> None:
        await coordinator.async_stop()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmartMeterConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: SmartMeterConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv-ha/bin/python -m pytest tests_integration -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add custom_components/smartmeter_at/__init__.py custom_components/smartmeter_at/sensor.py tests_integration/test_sensor.py
```

```bash
git commit -m "feat(integration): native sensor entities per meter profile"
```

---

### Task 8: Config flow, options flow, translations

**Files:**
- Create: `custom_components/smartmeter_at/config_flow.py`
- Create: `custom_components/smartmeter_at/translations/en.json`, `de.json`
- Test: `tests_integration/test_config_flow.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the config and options flow."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at.const import CONF_UPDATE_INTERVAL, DOMAIN

from .conftest import ENTRY_DATA, METER_ID, sample_reading

FLOW = "custom_components.smartmeter_at.config_flow"


@pytest.fixture(autouse=True)
def no_real_ports_or_setup():
    with (
        patch(f"{FLOW}.async_list_ports", return_value=["/dev/ttyUSB0"]),
        patch("custom_components.smartmeter_at.async_setup_entry", return_value=True),
    ):
        yield


async def _start(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await _start(hass)
    with patch(f"{FLOW}.async_probe", return_value=sample_reading()):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Smart Meter Landis+Gyr E450"
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == METER_ID


async def test_invalid_key_is_rejected_without_probe(hass: HomeAssistant) -> None:
    result = await _start(hass)
    with patch(f"{FLOW}.async_probe") as probe:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**ENTRY_DATA, "key": "not-hex"}
        )
    probe.assert_not_called()
    assert result["errors"] == {"key": "invalid_key"}


@pytest.mark.parametrize(
    ("probe_result", "error"),
    [
        (OSError("no such port"), "cannot_connect"),
        (None, "no_data"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_probe_errors(hass: HomeAssistant, probe_result, error: str) -> None:
    result = await _start(hass)
    kwargs = (
        {"side_effect": probe_result}
        if isinstance(probe_result, Exception)
        else {"return_value": probe_result}
    )
    with patch(f"{FLOW}.async_probe", **kwargs):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_same_meter_cannot_be_added_twice(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=METER_ID).add_to_hass(hass)
    result = await _start(hass)
    with patch(f"{FLOW}.async_probe", return_value=sample_reading()):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_sets_update_interval(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=METER_ID)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_UPDATE_INTERVAL: 30}
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv-ha/bin/python -m pytest tests_integration/test_config_flow.py -v`
Expected: FAIL (`ModuleNotFoundError ... config_flow` or flow "not found")

- [ ] **Step 3: Implement `custom_components/smartmeter_at/config_flow.py`**

```python
"""Config flow: pick meter, port and key, verify by reading one telegram."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import serial.tools.list_ports
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_INTERFACE_TYPE,
    CONF_KEY,
    CONF_METER_TYPE,
    CONF_PORT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_INTERFACE_TYPE,
    DEFAULT_METER_TYPE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    INTERFACE_TYPES,
)
from .coordinator import build_reader_factory
from .core import Core, async_load_core

_LOGGER = logging.getLogger(__name__)

# Wait for at least three telegrams (Burgenland/NÖ push every 5 s).
PROBE_TELEGRAMS = 3
MIN_PROBE_SECONDS = 10.0
SERIAL_BY_ID = Path("/dev/serial/by-id")


def _list_ports() -> list[str]:
    """Serial ports, preferring the stable /dev/serial/by-id/ name."""
    by_id: dict[str, str] = {}
    if SERIAL_BY_ID.is_dir():
        for link in SERIAL_BY_ID.iterdir():
            by_id[str(link.resolve())] = str(link)
    return sorted(by_id.get(port.device, port.device) for port in serial.tools.list_ports.comports())


async def async_list_ports(hass: HomeAssistant) -> list[str]:
    return await hass.async_add_executor_job(_list_ports)


async def async_probe(hass: HomeAssistant, core: Core, data: dict[str, Any]) -> Any | None:
    """Read one telegram with the given settings (``None`` on timeout)."""
    profile = core.profile.get_profile(data[CONF_METER_TYPE])
    timeout = max(MIN_PROBE_SECONDS, PROBE_TELEGRAMS * profile.push_interval_seconds)
    return await hass.async_add_executor_job(
        core.supervisor.probe, build_reader_factory(profile, data), timeout
    )


def _user_schema(meter_types: list[str], ports: list[str]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_METER_TYPE, default=DEFAULT_METER_TYPE): SelectSelector(
                SelectSelectorConfig(
                    options=meter_types,
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_METER_TYPE,
                )
            ),
            vol.Required(CONF_PORT): SelectSelector(
                SelectSelectorConfig(
                    options=ports, custom_value=True, mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(CONF_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_INTERFACE_TYPE, default=DEFAULT_INTERFACE_TYPE): SelectSelector(
                SelectSelectorConfig(options=INTERFACE_TYPES, translation_key=CONF_INTERFACE_TYPE)
            ),
        }
    )


class SmartMeterConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SmartMeterOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        core = await async_load_core(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**user_input, CONF_KEY: user_input[CONF_KEY].strip()}
            if not core.config_validation.HEX_KEY_RE.match(data[CONF_KEY]):
                errors[CONF_KEY] = "invalid_key"
            else:
                try:
                    reading = await async_probe(self.hass, core, data)
                except OSError:  # includes serial.SerialException
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error while probing the meter")
                    errors["base"] = "unknown"
                else:
                    if reading is None:
                        errors["base"] = "no_data"
                    else:
                        await self.async_set_unique_id(reading.meter_id or data[CONF_PORT])
                        self._abort_if_unique_id_configured()
                        profile = core.profile.get_profile(data[CONF_METER_TYPE])
                        return self.async_create_entry(
                            title=f"Smart Meter {profile.manufacturer} {profile.model}",
                            data=data,
                        )

        ports = await async_list_ports(self.hass)
        schema = self.add_suggested_values_to_schema(
            _user_schema(core.profile.known_meter_types(), ports), user_input
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class SmartMeterOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema(
            {
                vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=3600, step=1, unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
```

- [ ] **Step 4: `custom_components/smartmeter_at/translations/en.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Smart meter",
        "description": "Connect the IR reading head to the meter and to this Home Assistant host. Stop the Smartmeter add-on first if it uses the same port.",
        "data": {
          "meter_type": "Grid operator / meter",
          "port": "Serial port",
          "key": "Customer interface key",
          "interface_type": "Interface"
        },
        "data_description": {
          "key": "32 hex characters, sent to you by your grid operator.",
          "interface_type": "Only used for Burgenland and Wien. NÖ always uses the wired M-Bus port."
        }
      }
    },
    "error": {
      "invalid_key": "The key must be exactly 32 hex characters.",
      "cannot_connect": "The serial port cannot be opened.",
      "no_data": "No valid telegram received. Check the key, the meter type, the reading head position and that the customer interface is activated.",
      "unknown": "Unexpected error, see the log."
    },
    "abort": {
      "already_configured": "This meter is already configured."
    }
  },
  "options": {
    "step": {
      "init": {
        "data": {
          "update_interval": "Update interval"
        },
        "data_description": {
          "update_interval": "Seconds between entity updates. The meter sends every 1-5 seconds; lower values write more to the database."
        }
      }
    }
  },
  "selector": {
    "meter_type": {
      "options": {
        "burgenland": "Netz Burgenland (Landis+Gyr E450)",
        "noe_evn": "Netz NÖ / EVN (Sagemcom T210-D)",
        "wien": "Wiener Netze (Siemens IM150/IM350/IM351, Iskraemeco AM550, Landis+Gyr E450)",
        "steiermark": "Energienetze Steiermark (Landis+Gyr E450, M-Bus)",
        "steiermark_sagemcom": "Energienetze Steiermark (Sagemcom, DSMR P1)",
        "salzburg": "Salzburg Netz (Kaifa/Honeywell MA309M)",
        "tirol": "TINETZ Tirol (Kaifa/Honeywell MA110M/MA309M)",
        "h1": "Smart Meter 2.0 H1 interface (DSMR P1)"
      }
    },
    "interface_type": {
      "options": {
        "optical": "Optical (IR reading head)",
        "physical": "Wired"
      }
    }
  }
}
```

- [ ] **Step 5: `custom_components/smartmeter_at/translations/de.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Smart Meter",
        "description": "Verbinde den IR-Lesekopf mit dem Zähler und mit diesem Home-Assistant-Host. Stoppe vorher das Smartmeter-Add-on, falls es denselben Port verwendet.",
        "data": {
          "meter_type": "Netzbetreiber / Zähler",
          "port": "Serieller Port",
          "key": "Schlüssel der Kundenschnittstelle",
          "interface_type": "Schnittstelle"
        },
        "data_description": {
          "key": "32 Hex-Zeichen, die du von deinem Netzbetreiber bekommst.",
          "interface_type": "Nur für Burgenland und Wien relevant. NÖ nutzt immer die M-Bus-Schnittstelle."
        }
      }
    },
    "error": {
      "invalid_key": "Der Schlüssel muss genau 32 Hex-Zeichen lang sein.",
      "cannot_connect": "Der serielle Port kann nicht geöffnet werden.",
      "no_data": "Kein gültiges Telegramm empfangen. Prüfe Schlüssel, Zählertyp, Position des Lesekopfs und ob die Kundenschnittstelle aktiviert ist.",
      "unknown": "Unerwarteter Fehler, siehe Log."
    },
    "abort": {
      "already_configured": "Dieser Zähler ist bereits eingerichtet."
    }
  },
  "options": {
    "step": {
      "init": {
        "data": {
          "update_interval": "Aktualisierungsintervall"
        },
        "data_description": {
          "update_interval": "Sekunden zwischen zwei Aktualisierungen. Der Zähler sendet alle 1–5 Sekunden; kleinere Werte schreiben mehr in die Datenbank."
        }
      }
    }
  },
  "selector": {
    "meter_type": {
      "options": {
        "burgenland": "Netz Burgenland (Landis+Gyr E450)",
        "noe_evn": "Netz NÖ / EVN (Sagemcom T210-D)",
        "wien": "Wiener Netze (Siemens IM150/IM350/IM351, Iskraemeco AM550, Landis+Gyr E450)",
        "steiermark": "Energienetze Steiermark (Landis+Gyr E450, M-Bus)",
        "steiermark_sagemcom": "Energienetze Steiermark (Sagemcom, DSMR P1)",
        "salzburg": "Salzburg Netz (Kaifa/Honeywell MA309M)",
        "tirol": "TINETZ Tirol (Kaifa/Honeywell MA110M/MA309M)",
        "h1": "Smart Meter 2.0 H1 interface (DSMR P1)"
      }
    },
    "interface_type": {
      "options": {
        "optical": "Optisch (IR-Lesekopf)",
        "physical": "Kabelgebunden"
      }
    }
  }
}
```

- [ ] **Step 6: Run to verify they pass**

Run: `.venv-ha/bin/python -m pytest tests_integration -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add custom_components/smartmeter_at/config_flow.py custom_components/smartmeter_at/translations tests_integration/test_config_flow.py
```

```bash
git commit -m "feat(integration): config flow with live probe and options flow"
```

---

### Task 9: Diagnostics

**Files:**
- Create: `custom_components/smartmeter_at/diagnostics.py`
- Test: `tests_integration/test_diagnostics.py`

- [ ] **Step 1: Write the failing test**

```python
"""Diagnostics never leak the meter key."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmeter_at.const import DOMAIN
from custom_components.smartmeter_at.diagnostics import async_get_config_entry_diagnostics

from .conftest import ENTRY_DATA, KEY, wait_for_data


async def test_diagnostics_redact_key(hass: HomeAssistant, fake_readers) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for_data(entry.runtime_data)
    try:
        result = await async_get_config_entry_diagnostics(hass, entry)
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)

    assert KEY not in str(result)
    assert result["entry_data"]["key"] == "**REDACTED**"
    assert result["meter_id_known"] is True
    assert result["data"]["u1"] == 236
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv-ha/bin/python -m pytest tests_integration/test_diagnostics.py -v`
Expected: FAIL with `ModuleNotFoundError ... diagnostics`

- [ ] **Step 3: Implement `custom_components/smartmeter_at/diagnostics.py`**

```python
"""Diagnostics download for the config entry."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_KEY
from .coordinator import SmartMeterConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SmartMeterConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), {CONF_KEY}),
        "options": dict(entry.options),
        "profile": coordinator.profile.name,
        "meter_id_known": coordinator.meter_id is not None,
        "last_update_success": coordinator.last_update_success,
        "data": coordinator.data,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv-ha/bin/python -m pytest tests_integration -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/smartmeter_at/diagnostics.py tests_integration/test_diagnostics.py
```

```bash
git commit -m "feat(integration): diagnostics with redacted key"
```

---

### Task 10: CI for the integration

**Files:**
- Create: `.github/workflows/integration.yml`
- Create: `.github/scripts/check_requirements_sync.py`

- [ ] **Step 1: Requirements sync check** — `.github/scripts/check_requirements_sync.py`

The manifest's gurux pins must equal the add-on's, otherwise the integration runs a gurux version the contract tests never saw.

```python
"""Fail if manifest.json pins gurux differently from smartmeter/requirements.txt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINNED = ("gurux-common", "gurux-dlms")


def pins(lines: list[str]) -> dict[str, str]:
    result = {}
    for line in lines:
        name, sep, version = line.strip().partition("==")
        if sep and name in PINNED:
            result[name] = version
    return result


def main() -> int:
    addon = pins((ROOT / "smartmeter/requirements.txt").read_text().splitlines())
    manifest = json.loads((ROOT / "custom_components/smartmeter_at/manifest.json").read_text())
    integration = pins(manifest["requirements"])
    if addon != integration:
        print(f"gurux pins differ: add-on {addon}, integration {integration}")
        return 1
    print(f"gurux pins in sync: {addon}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run: `python3 .github/scripts/check_requirements_sync.py`
Expected: `gurux pins in sync: {'gurux-common': '1.0.13', 'gurux-dlms': '1.0.197'}`

- [ ] **Step 2: `.github/workflows/integration.yml`**

```yaml
name: "Home Assistant integration"

on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main
  workflow_dispatch:

permissions: {}

jobs:
  hassfest:
    name: "hassfest"
    runs-on: "ubuntu-latest"
    permissions:
      contents: read
    steps:
      - uses: "actions/checkout@v7.0.1"
      - uses: "home-assistant/actions/hassfest@master"

  hacs:
    name: "HACS validation"
    runs-on: "ubuntu-latest"
    permissions:
      contents: read
    steps:
      - uses: "hacs/action@main"
        with:
          category: "integration"
          ignore: "brands"

  tests:
    name: "Integration tests"
    runs-on: "ubuntu-latest"
    permissions:
      contents: read
    steps:
      - name: "Checkout the repository"
        uses: "actions/checkout@v7.0.1"

      - name: "Set up Python"
        uses: actions/setup-python@v7.1.0
        with:
          python-version-file: "tests_integration/.python-version"
          allow-prereleases: true
          cache: "pip"

      - name: "Check gurux pins"
        run: python3 .github/scripts/check_requirements_sync.py

      - name: "Install requirements"
        run: |
          python3 -m pip install uv &&
          uv venv -p "$(command -v python3)" &&
          source .venv/bin/activate &&
          uv pip install -r requirements-ha-test.txt ruff

      - name: "Apply the gurux fix-up"
        run: |
          source .venv/bin/activate &&
          python3 smartmeter/fix_source_encoding.py gurux_dlms gurux_common

      - name: "Lint"
        run: |
          source .venv/bin/activate &&
          python3 -m ruff check custom_components tests_integration .github/scripts

      - name: "Test"
        run: |
          source .venv/bin/activate &&
          python3 -m pytest tests_integration -v
```

- [ ] **Step 3: Lint locally**

Run: `.venv-ha/bin/python -m pip install ruff >/dev/null; .venv-ha/bin/python -m ruff check custom_components tests_integration .github/scripts`
Expected: `All checks passed!` (fix any finding, then re-run)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/integration.yml .github/scripts/check_requirements_sync.py
```

```bash
git commit -m "ci: hassfest, HACS validation and tests for the integration"
```

---

### Task 11: Release — version bump and HACS zip

**Files:**
- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: Bump the manifest version in the `prepare` job**

In `.github/workflows/release.yml`, extend the step "Adjust version number" so its `run` reads:

```yaml
        run: |
          yq -i '.version=strenv(RELEASE_TAG)' \
            "${{ github.workspace }}/smartmeter/config.yaml"
          manifest="${{ github.workspace }}/custom_components/smartmeter_at/manifest.json"
          jq --arg v "$RELEASE_TAG" '.version=$v' "$manifest" > "$manifest.tmp"
          mv "$manifest.tmp" "$manifest"
```

and extend `file_pattern` of the "Commit config.yaml" step:

```yaml
          file_pattern: smartmeter/config.yaml smartmeter/CHANGELOG.md custom_components/smartmeter_at/manifest.json
```

- [ ] **Step 2: Add the zip job** (append under `jobs:`)

```yaml
  integration-zip:
    name: "Attach HACS zip"
    needs: prepare
    runs-on: "ubuntu-latest"
    permissions:
      contents: write
    steps:
      - name: "Checkout the repository"
        uses: "actions/checkout@v7.0.1"
        with:
          ref: main

      - name: "Build smartmeter_at.zip (symlinks resolved)"
        run: |
          cd custom_components/smartmeter_at
          zip -r ../../smartmeter_at.zip . \
            -x '*/__pycache__/*' 'meter/__main__.py' 'meter/dlms/test*.py' 'meter/serial/test.py'
          cd ../..
          unzip -l smartmeter_at.zip | grep -E 'manifest.json|meter/profile.py|fix_source_encoding.py'

      - name: "Upload to the release"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          RELEASE_TAG: ${{ github.event.release.tag_name }}
        run: gh release upload "$RELEASE_TAG" smartmeter_at.zip --clobber
```

`zip` follows symlinks by default, so `meter/` and `fix_source_encoding.py` end up as real files in the archive.

- [ ] **Step 3: Verify the zip build locally**

```bash
out="$(mktemp -d)"
cd custom_components/smartmeter_at && zip -qr "$out/smartmeter_at.zip" . -x '*/__pycache__/*' 'meter/__main__.py' 'meter/dlms/test*.py' 'meter/serial/test.py' && cd ../..
unzip -l "$out/smartmeter_at.zip" | grep -E 'manifest.json|meter/profile.py|fix_source_encoding.py'
rm -r "$out"
```

Expected: three lines, all with non-zero sizes.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml
```

```bash
git commit -m "ci(release): bump integration version and attach HACS zip"
```

---

### Task 12: Documentation

**Files:**
- Modify: `README.md` (new section after "Standalone (Docker)")

- [ ] **Step 1: Add the section**

````markdown
### Home Assistant integration (HACS)

Reads the meter directly in Home Assistant: no MQTT broker and no add-on
needed, and it also works with Home Assistant Container and Core (no
Supervisor). The IR reading head must be connected to the Home Assistant host.

1. Request the activation of the customer interface (see above).
2. In HACS: ⋮ → Custom repositories → add
   `https://github.com/r00tat/smartmeter_homeassistant_burgenland`, category
   *Integration*.
3. Install *Smartmeter Austria* and restart Home Assistant.
4. Settings → Devices & services → Add integration → *Smartmeter Austria*.
5. Select grid operator, serial port and enter the key. The integration reads
   one telegram before it saves the entry, so a wrong key or port shows up
   right away.

Use either the add-on or the integration for a meter, never both: only one of
them can open the serial port. When you switch from the add-on, the
integration creates new entities; the energy dashboard has to be pointed to
the new *Total Energy consumed/provided* sensors.

The update interval (default 10 s) is set under the integration's
*Configure* button.
````

- [ ] **Step 2: Commit**

```bash
git add README.md
```

```bash
git commit -m "docs: document the Home Assistant integration"
```

---

### Task 13: End-to-end verification and PR

- [ ] **Step 1: Full local check**

```bash
cd smartmeter && python3 -m pytest tests/ -q && python3 -m ruff check && cd ..
python3 -m mypy --config-file mypy.ini
.venv-ha/bin/python -m pytest tests_integration -q
python3 .github/scripts/check_requirements_sync.py
```

Expected: everything green.

- [ ] **Step 2: Real hardware test (you, on a Home Assistant test instance)**

1. Stop the Smartmeter add-on.
2. Copy the integration with symlinks resolved: `cp -rL custom_components/smartmeter_at /config/custom_components/` (via Samba/SSH add-on), restart HA.
3. Add the integration, pick port and key. Expected: entry created, device shows manufacturer, model and serial number.
4. After one minute: voltage, current, power and energy sensors have plausible values; the energy sensors can be selected in the energy dashboard.
5. Pull the IR head out for 30 s: sensors become unavailable after the reader fails; reconnect: values return within ~20 s.
6. Options → update interval 30 → entities update about every 30 s.
7. Download diagnostics: the key shows as `**REDACTED**`.

- [ ] **Step 3: Push and open the PR**

```bash
git push -u origin feat/ha-custom-component
```

```bash
unset GITHUB_TOKEN && gh pr create --title "feat: Home Assistant custom integration (HACS)" --body "$(printf '%s\n\n%s' 'Adds custom_components/smartmeter_at: native sensors, config flow with live probe, reader supervisor with restart, runtime gurux fix-up, HACS zip release. Add-on and standalone image unchanged.' '🤖 Generated with [Claude Code](https://claude.com/claude-code)')"
```

- [ ] **Step 4: After merge (you)**

Add the GitHub topics `home-assistant`, `hacs`, `integration` to the repository (HACS validation checks for them on the default branch) and publish a release so the zip asset exists.

---

## Out of scope (follow-ups)

- Reconfigure flow (change port/key without deleting the entry).
- Repair issue when the add-on and the integration use the same port.
- Moving the core into its own PyPI package (only worth it if a third consumer appears or the integration should go into HA Core).
- Running the add-on itself on `ReaderSupervisor` instead of exiting on reader failure.
- Type checking `custom_components/` with mypy (needs Home Assistant in the lint venv).
