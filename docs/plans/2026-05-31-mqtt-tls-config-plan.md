# MQTT TLS Explicit-Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MQTT TLS opt-in via an explicit `mqtt.tls` boolean and stop TLS from being force-enabled by the `tls_insecure: false` default (bug #94).

**Architecture:** Gate `MqttClient._configure_tls()` on a single boolean config key (`tls`). When false/absent, return immediately and never touch paho's `tls_set`. When true, evaluate the existing flat `tls_*` keys exactly as today. Add the option to the add-on schema, document it, and lock the behaviour with unit tests.

**Tech Stack:** Python 3.14, paho-mqtt, pytest, ruff. Tests run from the `smartmeter/` directory: `python -m pytest tests/`.

---

## File Structure

- `smartmeter/meter/mqtt/client.py` — `_configure_tls()` gate logic (the fix).
- `smartmeter/config.yaml` — add-on `options.mqtt.tls` default + `schema.mqtt.tls` type.
- `smartmeter/tests/test_mqtt_tls.py` — **new** unit tests for the gate.
- `smartmeter/DOCS.md` — "Optional MQTT TLS" section rewrite.
- `smartmeter/CHANGELOG.md` — `[Unreleased]` entry.
- `smartmeter/config.schema.json` — **new** JSON Schema (Draft 2020-12) for the runtime config, including `mqtt.tls`.
- `smartmeter/smartmeter-config-template.yaml` — add `# yaml-language-server: $schema=./config.schema.json` header.

---

## Task 1: Fix and lock `_configure_tls` behaviour (TDD)

**Files:**
- Test: `smartmeter/tests/test_mqtt_tls.py` (create)
- Modify: `smartmeter/meter/mqtt/client.py:46-66`

- [ ] **Step 1: Write the failing tests**

Create `smartmeter/tests/test_mqtt_tls.py` with:

```python
"""Tests for MqttClient._configure_tls TLS gating (issue #94)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from meter.mqtt.client import MqttClient


def _make_client(mqtt_cfg: dict) -> MagicMock:
    """Instantiate MqttClient with paho Client patched; return the mock client."""
    cfg = {"host": "mqtt.local", **mqtt_cfg}
    with patch("meter.mqtt.client.mqtt.Client") as client_cls:
        client_instance = MagicMock()
        client_cls.return_value = client_instance
        MqttClient(cfg)
    return client_instance


def test_tls_not_enabled_when_key_absent() -> None:
    # Regression for #94: default config has no `tls` key.
    client = _make_client({})
    client.tls_set.assert_not_called()


def test_tls_not_enabled_when_false_with_insecure_false() -> None:
    # The exact #94 trigger: tls_insecure default False must not enable TLS.
    client = _make_client({"tls": False, "tls_insecure": False})
    client.tls_set.assert_not_called()


def test_tls_not_enabled_when_certs_present_but_tls_false() -> None:
    # No fallback: certs alone do not enable TLS.
    client = _make_client({"tls": False, "tls_ca": "/config/ca.pem"})
    client.tls_set.assert_not_called()


def test_tls_enabled_without_certs_uses_system_ca() -> None:
    client = _make_client({"tls": True})
    client.tls_set.assert_called_once_with(
        ca_certs=None, certfile=None, keyfile=None
    )


def test_tls_enabled_with_ca_and_insecure() -> None:
    client = _make_client(
        {
            "tls": True,
            "tls_ca": "/config/ca.pem",
            "tls_cert": "/config/client.pem",
            "tls_key": "/config/client.key",
            "tls_insecure": True,
        }
    )
    client.tls_set.assert_called_once_with(
        ca_certs="/config/ca.pem",
        certfile="/config/client.pem",
        keyfile="/config/client.key",
    )
    client.tls_insecure_set.assert_called_once_with(True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `smartmeter/`): `python -m pytest tests/test_mqtt_tls.py -v`
Expected: `test_tls_not_enabled_when_key_absent`, `test_tls_not_enabled_when_false_with_insecure_false`, and `test_tls_not_enabled_when_certs_present_but_tls_false` FAIL (current code calls `tls_set` because `tls_insecure: False` / certs trigger the buggy `any(...)`). The two `tls: True` tests should pass already.

- [ ] **Step 3: Apply the minimal fix**

In `smartmeter/meter/mqtt/client.py`, replace the body of `_configure_tls` (lines 46-66) with:

```python
    def _configure_tls(self) -> None:
        """Enable TLS only when explicitly switched on via ``tls: true``."""
        if not self.config.get("tls"):
            return

        tls_ca = self.config.get("tls_ca")
        tls_cert = self.config.get("tls_cert")
        tls_key = self.config.get("tls_key")
        tls_insecure = self.config.get("tls_insecure")

        log.info("enabling MQTT TLS")
        self.client.tls_set(
            ca_certs=tls_ca or None,
            certfile=tls_cert or None,
            keyfile=tls_key or None,
        )
        if tls_insecure is not None:
            self.client.tls_insecure_set(bool(tls_insecure))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `smartmeter/`): `python -m pytest tests/test_mqtt_tls.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Run the full suite + ruff**

Run (from `smartmeter/`): `python -m pytest tests/ -q && ruff check meter tests`
Expected: all tests pass, ruff reports no errors.

- [ ] **Step 6: Commit**

```bash
git add smartmeter/meter/mqtt/client.py smartmeter/tests/test_mqtt_tls.py
git commit -m "fix(mqtt): only enable TLS when tls: true (#94)"
```

---

## Task 2: Add `tls` to the add-on config schema

**Files:**
- Modify: `smartmeter/config.yaml:34` (options) and `:61` (schema)

- [ ] **Step 1: Add the option default**

In `smartmeter/config.yaml`, under `options.mqtt`, add `tls: false` immediately **before** the `tls_ca: ""` line so the block reads:

```yaml
    sensors_migrated: false
    publish_interval: 30
    tls: false
    tls_ca: ""
    tls_cert: ""
    tls_key: ""
    tls_insecure: false
```

- [ ] **Step 2: Add the schema type**

In `smartmeter/config.yaml`, under `schema.mqtt`, add `tls: bool?` immediately **before** the `tls_ca: "str?"` line so the block reads:

```yaml
    sensors_migrated: bool?
    publish_interval: int?
    tls: bool?
    tls_ca: "str?"
    tls_cert: "str?"
    tls_key: "str?"
    tls_insecure: bool?
```

- [ ] **Step 3: Verify the YAML still parses**

Run (from repo root): `python -c "import yaml; yaml.safe_load(open('smartmeter/config.yaml'))" && echo OK`
Expected: prints `OK` with no traceback.

- [ ] **Step 4: Commit**

```bash
git add smartmeter/config.yaml
git commit -m "feat(mqtt): add explicit tls option to add-on schema (#94)"
```

---

## Task 3: Update DOCS.md and CHANGELOG.md

**Files:**
- Modify: `smartmeter/DOCS.md` ("Optional MQTT TLS" section, ~line 35-37)
- Modify: `smartmeter/CHANGELOG.md` (`[Unreleased]` section near the top)

- [ ] **Step 1: Rewrite the DOCS.md TLS section**

Replace the existing "## Optional MQTT TLS" section body in `smartmeter/DOCS.md` with:

```markdown
## Optional MQTT TLS

TLS is disabled by default. To connect to an MQTT broker over TLS, set
`tls: true` under `mqtt`. The default port stays `1883`; TLS brokers
usually listen on a separate port (commonly `8883`), so set `port`
accordingly.

When `tls: true`, the following options take effect (they are ignored
while `tls` is `false`):

- `tls_ca`: path to a CA certificate (PEM) the broker is trusted against.
  If left empty, the system CA store is used (works with publicly trusted
  brokers).
- `tls_cert` and `tls_key`: enable mutual TLS with a client certificate
  and key.
- `tls_insecure: true`: skip hostname/certificate verification (testing
  only).

Certificate paths must be readable from within the add-on container (e.g.
mounted via `share:ro` or `config:ro`).
```

- [ ] **Step 2: Add the CHANGELOG entry**

In `smartmeter/CHANGELOG.md`, under the `## [Unreleased]` heading, add a `**Fixed bugs:**` block (or extend it if present) and an enhancement note:

```markdown
**Fixed bugs:**

- MQTT no longer attempts a TLS handshake on the plain `1883` port. TLS
  was previously force-enabled by the `tls_insecure: false` default,
  causing `[SSL: UNEXPECTED_EOF_WHILE_READING]` connection failures
  ([\#94](https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues/94)).

**Implemented enhancements:**

- Add explicit `mqtt.tls` option. TLS is now opt-in via `tls: true`; the
  `tls_ca` / `tls_cert` / `tls_key` / `tls_insecure` options only apply
  when TLS is enabled.
```

(If `## [Unreleased]` already contains an `**Implemented enhancements:**`
block for the Netz NÖ feature, add the new bullet to it rather than
duplicating the heading, and add the `**Fixed bugs:**` block above it.)

- [ ] **Step 3: Verify markdown is well-formed**

Run (from repo root): `grep -n "tls" smartmeter/DOCS.md && grep -n "#94\|tls" smartmeter/CHANGELOG.md`
Expected: the new TLS lines appear in both files.

- [ ] **Step 4: Commit**

```bash
git add smartmeter/DOCS.md smartmeter/CHANGELOG.md
git commit -m "docs: document explicit MQTT tls option (#94)"
```

---

## Task 4: Add JSON Schema for the runtime config + editor header

**Files:**
- Create: `smartmeter/config.schema.json`
- Modify: `smartmeter/smartmeter-config-template.yaml:1` (add schema header)
- Test: `smartmeter/tests/test_config_schema.py` (create)

- [ ] **Step 0: Add the `jsonschema` dev dependency**

`jsonschema` is not currently installed. Add this line to
`smartmeter/requirements-dev.txt`:

```text
jsonschema~=4.0
```

Then install (from `smartmeter/`): `pip install -r requirements-dev.txt`
Expected: `jsonschema` installs without error.

- [ ] **Step 1: Write the failing test**

Create `smartmeter/tests/test_config_schema.py`. It validates the bundled
template against the schema and checks the `tls` option is present and
boolean.

```python
"""The runtime config schema accepts the template and the mqtt.tls option."""

from __future__ import annotations

import json
import os

import yaml
from jsonschema import Draft202012Validator

_HERE = os.path.dirname(os.path.dirname(__file__))  # smartmeter/
_SCHEMA = os.path.join(_HERE, "config.schema.json")
_TEMPLATE = os.path.join(_HERE, "smartmeter-config-template.yaml")


def _schema() -> dict:
    with open(_SCHEMA, encoding="utf-8") as fh:
        return json.load(fh)


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(_schema())


def test_template_matches_schema() -> None:
    with open(_TEMPLATE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    # template ships an empty host/key (user fills them); validate shape only
    data.setdefault("mqtt", {})["host"] = "mqtt.local"
    data.setdefault("dlms", {})["key"] = "00" * 16
    Draft202012Validator(_schema()).validate(data)


def test_schema_allows_tls_boolean() -> None:
    schema = _schema()
    mqtt_props = schema["properties"]["mqtt"]["properties"]
    assert mqtt_props["tls"]["type"] == "boolean"


def test_schema_rejects_unknown_meter_type() -> None:
    cfg = {
        "meter_type": "bogus",
        "mqtt": {"host": "h"},
        "dlms": {"key": "00" * 16, "port": "/dev/ttyUSB0"},
    }
    errors = list(Draft202012Validator(_schema()).iter_errors(cfg))
    assert errors, "unknown meter_type should fail validation"
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `smartmeter/`): `python -m pytest tests/test_config_schema.py -v`
Expected: FAIL — `config.schema.json` does not exist yet (FileNotFoundError).

- [ ] **Step 3: Create the schema file**

Create `smartmeter/config.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/r00tat/smartmeter_homeassistant_burgenland/config.schema.json",
  "title": "Smartmeter add-on runtime configuration",
  "type": "object",
  "additionalProperties": true,
  "properties": {
    "logging": {
      "type": "string",
      "enum": ["INFO", "WARNING", "ERROR", "CRITICAL", "DEBUG"]
    },
    "meter_type": {
      "type": "string",
      "enum": ["burgenland", "noe_evn"],
      "default": "burgenland"
    },
    "interface_type": {
      "type": "string",
      "enum": ["OPTICAL", "PHYSICAL"]
    },
    "mqtt": {
      "type": "object",
      "required": ["host"],
      "additionalProperties": false,
      "properties": {
        "device_id": {"type": "string"},
        "name": {"type": "string"},
        "host": {"type": "string", "minLength": 1},
        "port": {"type": "integer", "minimum": 1, "maximum": 65535},
        "user": {"type": "string"},
        "password": {"type": "string"},
        "keepalive": {"type": "integer", "minimum": 1},
        "prefix": {"type": "string"},
        "sensors_migrated": {"type": "boolean"},
        "publish_interval": {"type": "integer", "minimum": 1},
        "tls": {
          "type": "boolean",
          "default": false,
          "description": "Enable MQTT over TLS. The tls_* options apply only when true."
        },
        "tls_ca": {"type": "string"},
        "tls_cert": {"type": "string"},
        "tls_key": {"type": "string"},
        "tls_insecure": {"type": "boolean"}
      }
    },
    "dlms": {
      "type": "object",
      "required": ["key", "port"],
      "additionalProperties": false,
      "properties": {
        "port": {"type": "string", "minLength": 1},
        "baudrate": {"type": "integer"},
        "bytesize": {"type": "integer"},
        "parity": {
          "type": "string",
          "enum": ["NONE", "EVEN", "ODD", "MARK", "SPACE"]
        },
        "stopbits": {"type": "integer"},
        "key": {"type": "string", "pattern": "^[0-9a-fA-F]{32}$"},
        "hdlc_frame_size": {"type": "integer"}
      }
    }
  }
}
```

- [ ] **Step 4: Add the schema header to the template**

Add as the **first line** of `smartmeter/smartmeter-config-template.yaml`:

```yaml
# yaml-language-server: $schema=./config.schema.json
```

(Keep the existing `logging: INFO` line as line 2.)

- [ ] **Step 5: Run the tests to verify they pass**

Run (from `smartmeter/`): `python -m pytest tests/test_config_schema.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Run the full suite + ruff + JSON sanity**

Run (from `smartmeter/`):
`python -m pytest tests/ -q && ruff check meter tests && python -c "import json; json.load(open('config.schema.json'))" && echo OK`
Expected: tests pass, ruff clean, prints `OK`.

- [ ] **Step 7: Commit**

```bash
git add smartmeter/config.schema.json smartmeter/smartmeter-config-template.yaml smartmeter/tests/test_config_schema.py smartmeter/requirements-dev.txt
git commit -m "feat: add JSON schema for runtime config validation (#94)"
```

---

## Self-Review Notes

- **Spec coverage:** Task 1 = client gate fix + regression tests; Task 2 = add-on schema option; Task 3 = DOCS + CHANGELOG; Task 4 = JSON Schema + template header. All design "Affected Components" covered.
- **No fallback:** `test_tls_not_enabled_when_certs_present_but_tls_false` locks the strict no-fallback decision.
- **Type consistency:** the config key is `tls` (boolean) everywhere — config.yaml options, add-on schema, JSON schema, `self.config.get("tls")`, and all tests.
- **Schema scope:** `config.schema.json` validates the runtime config (template / `/data/options.json`), mirroring `config_validation.py`; the HA add-on manifest keeps its own `schema:` block in `config.yaml`.
- **Port unchanged:** no task modifies the default `1883`; docs only mention `8883` as a manual choice.
