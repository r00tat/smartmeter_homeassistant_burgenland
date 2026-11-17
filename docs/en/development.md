# Development

[Deutsche Version](../entwicklung.md) · [Back to the README](../../README.en.md)

## Repository layout

| Path | Contents |
| --- | --- |
| `smartmeter/smartmeter-austria/` | library [`smartmeter-austria`](https://pypi.org/project/smartmeter-austria/) (import `smartmeter_austria`): serial transport, a reader per meter type, supervisor; tests in `tests/` |
| `smartmeter/` | add-on and standalone image: MQTT bridge in `meter/`, Dockerfiles, `config.yaml`, tests in `tests/` |
| `custom_components/smartmeter_at/` | Home Assistant integration, tests in `tests_integration/` |
| `docs/` | documentation (German, English under `docs/en/`) |

As Home Assistant
[recommends](https://contributors.home-assistant.io/core/integrations/api-library/), the
integration contains no protocol code: it installs the library from PyPI as a
requirement (`manifest.json`). The add-on installs it from the same commit at
image build time. Library, integration and add-on share one version number,
see [Release](#release).

## Architecture

The add-on and the integration share the core. Everything runs on one
asyncio event loop, without threads:

```text
serial port ──(pyserial-asyncio-fast)──> reader.run() ──callback──> supervisor
                                                                   │
              add-on: SmartMeterDevice (aiomqtt) <── on_data ──────┤
       integration: SmartMeterCoordinator        <── on_error ─────┘
```

- `smartmeter_austria/serial/transport.py` opens the port in an executor and delivers
  bytes as they arrive. Readers await data instead of polling with read
  timeouts; an unplugged adapter ends the stream with an error right away.
- A reader (`MeterReaderLike`) has one method, `async run()`: it reads until
  it is cancelled and raises on any fault. Readers never retry themselves.
- `smartmeter_austria/supervisor.py` (`ReaderSupervisor`) is the single place for
  recovery: it replaces a failed reader after a pause, reports a silent meter
  (`stale_after`) and reopens the port when it stays silent
  (`restart_after`). Cancelling it stops the reader and closes the port.
- Parsing (gurux, about 1–2 ms per telegram) runs on the loop; at one
  telegram every 1–5 seconds that is well below 1 % of the loop's time.

## Tests

The tests need no hardware and no broker: a scripted port
(`smartmeter/smartmeter-austria/tests/fake_port.py`), a small MQTT broker
(`smartmeter/tests/fake_broker.py`) and pseudo terminals for the real serial
transport.

Library and add-on (Python 3.15, from the repository root):

```bash
uv venv && source .venv/bin/activate
uv pip install -r smartmeter/requirements-dev.txt -e smartmeter/smartmeter-austria
python3 -m smartmeter_austria.fix_source_encoding gurux_dlms gurux_common
ruff check smartmeter && mypy --config-file mypy.ini
(cd smartmeter/smartmeter-austria && pytest tests)
(cd smartmeter && pytest tests)
```

Integration (Python version from `tests_integration/.python-version`, separate
venv); the library is installed editable from the repository:

```bash
uv venv .venv-ha && source .venv-ha/bin/activate
uv pip install -r requirements-ha-test.txt -e smartmeter/smartmeter-austria ruff
python3 -m smartmeter_austria.fix_source_encoding gurux_dlms gurux_common
python3 .github/scripts/check_requirements_sync.py
ruff check custom_components tests_integration && pytest tests_integration
```

### Turning a debug log into a test

The `smartmeter_austria.serial.raw` lines (see
[troubleshooting.md](troubleshooting.md#debug-logs)) can be replayed directly,
including the pauses:

```python
from smartmeter_austria.serial import rawlog
from tests.fake_port import EOF, FakePort, run_until, steps_from_capture

captured = rawlog.parse(open("report.log").read())
reader = get_profile("noe_evn").create_reader({"dlms": {"key": KEY}}, received.append)
reader._open_stream = FakePort([*steps_from_capture(captured), 0.3, EOF])
await run_until(reader.run, lambda: False)
```

`tests/test_rawlog.py` shows the full round trip: a real pseudo terminal is
read, the log captured and replayed, with the same readings as the result.

## Testing the integration locally

`manifest.json` requires the library in exactly the version from
`smartmeter/smartmeter-austria/pyproject.toml`, and Home Assistant installs it
from PyPI. Library changes on a branch therefore only reach Home Assistant
after a release, unless you install the library yourself as `./dev.sh` does.

**Test instance in Docker:** `./dev.sh` mirrors the integration and the
library into `config/`, installs the library from that copy every time the
container starts, and starts Home Assistant in the container
`smartmeter-ha-dev` on <http://localhost:8124>. Run it again after a change to
sync and restart. `HTTP_PORT` changes the port, `--recreate` recreates the
container, `--no-logs` keeps it running in the background. On a Linux host,
`SERIAL_DEVICE=/dev/ttyUSB0 ./dev.sh` passes the reading head into the
container; Docker Desktop on macOS/Windows cannot pass USB serial devices.

### On a real Home Assistant

Clone the repository into `/config` (e.g. with the *Terminal & SSH* add-on)
and symlink the integration into `custom_components`. Updating is then a
plain `git pull`. Home Assistant installs the library version from
`manifest.json` from PyPI, so a branch that changes the library can only be
tested with `./dev.sh`.

```bash
cd /config
git clone https://github.com/r00tat/smartmeter_homeassistant_burgenland.git smartmeter-src
# to test a branch that is not released yet:
# git clone -b <branch> https://github.com/r00tat/smartmeter_homeassistant_burgenland.git smartmeter-src
mkdir -p /config/custom_components
rm -rf /config/custom_components/smartmeter_at
ln -s ../smartmeter-src/custom_components/smartmeter_at /config/custom_components/smartmeter_at
```

Restart Home Assistant and add the integration. Update with
`cd /config/smartmeter-src && git pull` and restart Home Assistant afterwards;
reloading the integration is not enough, because Python keeps the old code
loaded. Switching branches works the same way with `git checkout <branch>`.

Notes on the symlink:

- Keep the clone inside `/config` and the link relative. Home Assistant OS and
  Container only see `/config`; a link outside of it or an absolute host path
  is dangling inside the container.
- Do not install via the Marketplace at the same time, both use
  `custom_components/smartmeter_at`. Remove the link before switching to the
  Marketplace.
- The clone ends up in Home Assistant backups. Exclude it, or remove it once
  you no longer need it.

Without `git` on the Home Assistant host, copy the directory, e.g. from
another machine
`rsync -a --delete --exclude __pycache__ custom_components/smartmeter_at/ root@homeassistant.local:/config/custom_components/smartmeter_at/`
(the SSH add-on needs `rsync`) or with `scp -r`.

## Testing the add-on and standalone locally

Every variant uses the library from `smartmeter/smartmeter-austria/` of the
working tree, not the version on PyPI:

| Variant | Test with |
| --- | --- |
| Integration | `./dev.sh`, see [above](#testing-the-integration-locally) |
| Add-on | `./dev-addon.sh` on a Home Assistant with Supervisor |
| Standalone container | `build:` block in `smartmeter/docker-compose.standalone.yml` |
| Standalone without Docker | `smartmeter/smartmeter.sh`, see [installation](installation.md#systemd-without-docker) |

### Add-on

`./dev-addon.sh` copies `smartmeter/` including the library over SSH to
`/addons/smartmeter_dev` on the Home Assistant host. It removes `image:` from
`config.yaml` so the Supervisor builds the add-on itself, appends "(dev)" to
the name and sets the version to `X.Y.Z-dev.<commit>`.

Requirements: the *Terminal & SSH* (or *Advanced SSH & Web Terminal*) add-on
with `rsync` and an SSH key for `root`, and `yq` locally. Set target and port
with `HA_HOST` (default `root@homeassistant.local`) and `HA_SSH_PORT`.

1. Run `./dev-addon.sh`.
2. The first time, install and configure "Smartmeter Burgenland MQTT (dev)"
   under *Settings → Add-ons → Add-on Store*, section *Local add-ons*.
3. After every change run `./dev-addon.sh` again; it updates and rebuilds the
   add-on (`ha addons update local_smartmeter_bgld_mqtt`).

The local add-on (`local_smartmeter_bgld_mqtt`) sits next to the published
one. Do not run both with the same reading head at the same time.

### Building the images without Supervisor

The build context is `smartmeter/`, as for the Supervisor:

```bash
docker build -t smartmeter-addon smartmeter
docker build -f smartmeter/Dockerfile.standalone -t smartmeter-standalone smartmeter
```

The release pipeline builds and publishes the images.
`cd smartmeter && DOCKERHUB_USER=… DOCKERHUB_PASSWORD=… ./build_images.sh`
builds them manually with the Home Assistant builder for all architectures
and pushes them to Docker Hub.

## Release

A GitHub release with the tag `X.Y.Z` (no `v`) starts
`.github/workflows/release.yml`:

1. It sets the version in `smartmeter/config.yaml`, `manifest.json` (version
   and pin `smartmeter-austria==X.Y.Z`) and
   `smartmeter/smartmeter-austria/pyproject.toml` and commits them to `main`.
2. It builds the library and publishes it to PyPI with
   [Trusted Publishing](https://docs.pypi.org/trusted-publishers/), without an
   API token.
3. It builds the add-on and standalone images and pushes them to Docker Hub.
4. Only after the PyPI upload it attaches `smartmeter_at.zip` for HACS to the
   release; otherwise Home Assistant could not install the pinned version.

One-time setup on pypi.org: under *Publishing*, add a *pending publisher* for
the project `smartmeter-austria` with owner `r00tat`, repository
`smartmeter_homeassistant_burgenland`, workflow `release.yml` and environment
`pypi`. In the GitHub repository, create the environment `pypi` (Settings →
Environments), optionally with a required reviewer.

## Adding a meter

Everything specific to a meter's customer interface lives in its profile in
`smartmeter/smartmeter-austria/src/smartmeter_austria/profile.py`: serial settings, push interval, which reader
handles the line, how a decoded telegram becomes a `MeterData` object, and
the Home Assistant device metadata and sensors.

- `MeterProfile` is the abstract base class. `HdlcDlmsProfile` (DLMS in HDLC
  frames, Burgenland and Wien), `MBusDlmsProfile` (DLMS in M-Bus frames,
  Netz NÖ) and `ObisProfile` (the OBIS pipeline) implement `create_reader`,
  which returns a reader with `async run()`.
- A meter that sends OBIS codes usually only needs a new `ObisProfile`
  instance with the right transports and fields.
- A meter with a fixed layout without OBIS codes that reuses an existing
  interface needs a new profile instance, a `MeterData` subclass of
  `BaseMeterData` and a sensor catalog.
- Register the name in `smartmeter/config.yaml` and
  `smartmeter/config.schema.json` too; a test checks that the lists match.

Technical details on the existing meters: [meters.md](meters.md).
