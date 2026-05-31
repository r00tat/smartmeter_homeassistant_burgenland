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

## Self-Review Notes

- **Spec coverage:** Task 1 = client gate fix + regression tests; Task 2 = schema option; Task 3 = DOCS + CHANGELOG. All design "Affected Components" covered.
- **No fallback:** `test_tls_not_enabled_when_certs_present_but_tls_false` locks the strict no-fallback decision.
- **Type consistency:** the config key is `tls` (boolean) everywhere — config.yaml options, schema, `self.config.get("tls")`, and all tests.
- **Port unchanged:** no task modifies the default `1883`; docs only mention `8883` as a manual choice.
