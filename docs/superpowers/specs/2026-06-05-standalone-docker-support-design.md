# Standalone Docker Support — Design

**Date:** 2026-06-05
**Status:** Approved
**Related:** GitHub issue [#101](https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues/101)

## Problem

Running the project standalone (via `docker-compose`, without the Home Assistant
Supervisor) broke after commit `216f946`, which switched the container base image
to `ghcr.io/hassio-addons/base-python:stable`. That base ships **s6-overlay** plus
the HA add-on init services (`base-addon-banner`, `base-addon-log-level`, …), which
run **before** the `CMD` and unconditionally contact the Supervisor API:

```
curl: (6) Could not resolve host: supervisor
[..] FATAL: Unknown log_level:
s6-rc: warning: unable to start service base-addon-log-level: command exited 1
/run/s6/basedir/scripts/rc.init: fatal: stopping the container.
```

Standalone there is no `supervisor` host, so the init aborts and the container
stops. A secondary blocker: `run.sh` uses `#!/usr/bin/env bashio` and reads
`/data/options.json` (Supervisor-generated), neither of which exist standalone.

Key finding: the Python application itself (`python3 -m meter -c <file>`) has **no**
Supervisor dependency — it just loads a YAML/JSON config file. The entire breakage
lives in the container layer.

## Chosen Approach

**Approach A — separate standalone artifact** (selected over single-image
auto-detection variants). The HA add-on path (`Dockerfile`, `run.sh`, hassio base,
s6/bashio) stays **untouched**. A separate, Supervisor-free image is added for the
Docker/Compose use case, plus a multi-arch CI release.

## Files

### New

- **`smartmeter/Dockerfile.standalone`**
  - Base `python:3.13-slim` (glibc, official multi-arch amd64/arm64). No s6, no bashio.
  - Build context stays `smartmeter/` (same as the add-on `Dockerfile`).
  - Steps: `COPY requirements.txt` → `pip install --no-cache-dir -r requirements.txt`
    → `COPY meter ./meter/` → **`COPY config.yaml ./`** (required: `meter/mqtt/device.py`
    calls `get_sw_version()` which reads `config.yaml`) → `COPY standalone-entrypoint.sh ./`.
  - `ENTRYPOINT ["/app/standalone-entrypoint.sh"]`.
  - lxml/pycryptodomex resolve to manylinux wheels on slim → no compiler toolchain needed.

- **`smartmeter/standalone-entrypoint.sh`**
  - Plain `sh`/`bash`, no bashio.
  - Resolves config path from env `SMARTMETER_CONFIG`, default `/config/smartmeter-config.yaml`.
  - If the file is missing/empty → exit non-zero with a clear, human-readable message
    (not a Python traceback).
  - `cd /app` then `exec python3 -m meter -c "$CONFIG"` (`exec` so SIGTERM/SIGINT reach
    the app, which already installs signal handlers in `meter/__main__.py`).

- **`smartmeter/docker-compose.standalone.yml`**
  - Uses the published image
    `docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone:latest`.
  - Maps `/dev/ttyUSB0` device, mounts user config to `/config/smartmeter-config.yaml`,
    `restart: unless-stopped`.
  - Includes a commented-out `build:` block (`context: .`, `dockerfile: Dockerfile.standalone`)
    for building locally instead of pulling.

### Modified

- **`smartmeter/DOCS.md`** — new section "Standalone (Docker / docker-compose)":
  image name, the `SMARTMETER_CONFIG` convention + default path, and the compose example.
- **`.github/workflows/release.yml`** — new job `build-standalone` (see CI below).
- **`.github/workflows/pull_request.yml`** — new job `test-build-standalone` (build only, no push).

### Unchanged (explicitly)

- Add-on `Dockerfile`, `run.sh`, `build.yaml`, `config.yaml` schema/options.
- `smartmeter-config.example.yaml` stays as the standalone config template, referenced from docs.

## Config Convention

- Env var `SMARTMETER_CONFIG`, default `/config/smartmeter-config.yaml`.
- The user mounts their YAML there. Format is identical to the existing
  `smartmeter-config.example.yaml` — plain YAML, no `/data/options.json`, no JSON requirement.

## CI / Release (multi-arch)

- **`release.yml` → `build-standalone`** (runs alongside the existing `build` job):
  - `docker/setup-qemu-action` + `docker/setup-buildx-action` + `docker/login-action`
    (`DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` secrets, already present).
  - `docker/build-push-action` with `context: smartmeter`,
    `file: smartmeter/Dockerfile.standalone`, `platforms: linux/amd64,linux/arm64`.
  - Pushes a **single multi-arch manifest** to
    `docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone`
    with tags `<release-tag>` and `latest`.
- **`pull_request.yml` → `test-build-standalone`**:
  - Same buildx setup, `platforms: linux/amd64,linux/arm64`, `push: false` — build check only.

## Error Handling

- Entrypoint: missing/empty config → clear message + non-zero exit.
- Application: unchanged (existing `try/except` and signal handling in `meter/__main__.py`).

## Testing / Verification

- CI `test-build-standalone` verifies both arch images build.
- Manual: `docker compose -f docker-compose.standalone.yml up` with the example config
  and a serial device → container starts, no Supervisor contact, app loads config.
- Existing pytest/ruff/mypy jobs unaffected.

## Out of Scope (YAGNI)

- No changes to the add-on image / s6 / bashio.
- No auto-detection entrypoint (single-image approaches B/C rejected).
- No architectures beyond amd64/arm64 (the add-on publishes only these).
