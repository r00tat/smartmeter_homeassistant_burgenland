# Design: Explicit MQTT TLS Configuration

- **Issue:** [#94](https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues/94)
- **Date:** 2026-05-31
- **Status:** Accepted – implementation pending

## Goal

Make MQTT TLS an explicit, opt-in feature controlled by a single boolean
switch, and fix the bug where TLS is enabled even when the user did not
ask for it. Trusted CA / client certificates remain configurable.

## Problem

`MqttClient._configure_tls()` currently enables TLS when *any* `tls_*`
value is "non-empty":

```python
if not any(
    value not in (None, "")
    for value in (tls_ca, tls_cert, tls_key, tls_insecure)
):
    return
```

The add-on default config ships `tls_insecure: false`. Because
`False not in (None, "")` evaluates to `True`, the `any(...)` is always
truthy, so TLS is **always** enabled — even with empty certificate fields
and the standard non-TLS port `1883`. paho then attempts a TLS handshake
against a plain broker and fails:

```
INFO  enabling MQTT TLS
ERROR [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol
```

This is exactly the failure reported in #94.

## Decision

- Introduce an explicit boolean option `mqtt.tls` (default `false`).
- TLS is enabled **only** when `tls: true`. There is **no** fallback that
  infers TLS from the presence of certificate fields.
- When `tls: true`, the existing flat `tls_*` keys are evaluated:
  - `tls_ca` — trusted CA / server certificate (PEM). If omitted, paho
    falls back to the system CA store (works with publicly trusted brokers).
  - `tls_cert` + `tls_key` — optional client certificate for mutual TLS.
  - `tls_insecure` — disable hostname/certificate verification (testing only).
- The default MQTT port stays `1883` (standard, non-TLS). The port is
  never changed automatically; TLS brokers commonly listen on a separate
  port (often `8883`) which the user must set manually.

Rationale for the strict (no-fallback) behaviour: it is maximally
predictable and cleanly fixes #94. The feature shipped in 0.6.0 and the
old auto-enable was buggy, so there is no well-behaved legacy config to
preserve. Existing users with certificates set must add `tls: true` once;
this is called out in DOCS.md and the changelog.

## Affected Components

1. **`smartmeter/meter/mqtt/client.py`** — `_configure_tls()`:
   replace the `any(...)` block with an early return guarded on the new
   switch:
   ```python
   if not self.config.get("tls"):
       return
   ```
   The remainder (`tls_set(...)`, `tls_insecure_set(...)`) is unchanged and
   keeps reading the flat `tls_*` keys.

2. **`smartmeter/config.yaml`** — add `tls: false` to `options.mqtt`
   (before the `tls_ca` field) and `tls: bool?` to `schema.mqtt`.

3. **`smartmeter/DOCS.md`** — rewrite the "Optional MQTT TLS" section: TLS
   is enabled via `tls: true`; the `tls_*` fields only take effect then;
   note the separate-port convention (e.g. `8883`) while keeping `1883`
   as the documented default.

4. **`smartmeter/CHANGELOG.md`** — add an entry under `[Unreleased]`
   documenting the bugfix and the new `tls` option.

5. **`smartmeter/config.schema.json`** (new) — a JSON Schema (Draft 2020-12)
   describing the runtime config structure (`logging`, `meter_type`,
   `interface_type`, `mqtt`, `dlms`), including the new `mqtt.tls`
   boolean. It mirrors the rules already enforced in
   `config_validation.py` (required `mqtt.host`, `dlms.key` 32-hex, parity
   enum, meter_type enum) so editors and CI can validate config files.
   `smartmeter-config-template.yaml` gets a
   `# yaml-language-server: $schema=./config.schema.json` header so editors
   pick up the schema automatically. The schema documents the **runtime**
   config consumed by `python -m meter -c <file>` (and the add-on's
   `/data/options.json`), not the Home Assistant add-on manifest, which
   keeps its own `schema:` block in `config.yaml`.

6. **`smartmeter/tests/`** — new unit tests for `_configure_tls`
   (mocking `mqtt.Client`):
   - `tls` missing → `tls_set` **not** called (regression test for #94).
   - `tls: false` with certs present → `tls_set` **not** called.
   - `tls: true`, no certs → `tls_set()` called with `ca_certs=None`.
   - `tls: true` with `tls_ca` and `tls_insecure: true` → `tls_set` and
     `tls_insecure_set(True)` called with the expected arguments.

## Out of Scope (YAGNI)

- Automatic switching of the port to `8883` when TLS is enabled.
- A nested `tls:` configuration block (would break the existing flat
  `tls_*` keys for no functional gain).
- Backward-compat fallback that infers TLS from certificate presence.

## Test / Verification

- `pytest` (new TLS tests pass, existing suite green).
- `ruff` clean.
- Manual: `tls: false` (or unset) connects to a plain broker on `1883`
  without attempting a handshake; `tls: true` against a TLS broker
  performs the handshake.
