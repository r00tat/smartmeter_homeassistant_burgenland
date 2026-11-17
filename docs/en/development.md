# Development

[Deutsche Version](../entwicklung.md) · [Back to the README](../../README.en.md)

## Repository layout

| Path | Contents |
| --- | --- |
| `smartmeter/meter/` | core: serial transport, a reader per meter type, supervisor, MQTT |
| `smartmeter/` | add-on and standalone image (Dockerfiles, `config.yaml`, tests in `tests/`) |
| `custom_components/smartmeter_at/` | Home Assistant integration, tests in `tests_integration/` |
| `docs/` | documentation (German, English under `docs/en/`) |

The integration has no copy of the core: `meter/` and
`fix_source_encoding.py` are symlinks into `smartmeter/`.

## Architecture

The add-on and the integration share the core. Everything runs on one
asyncio event loop, without threads:

```text
serial port ──(pyserial-asyncio-fast)──> reader.run() ──callback──> supervisor
                                                                   │
              add-on: SmartMeterDevice (aiomqtt) <── on_data ──────┤
       integration: SmartMeterCoordinator        <── on_error ─────┘
```

- `meter/serial/transport.py` opens the port in an executor and delivers
  bytes as they arrive. Readers await data instead of polling with read
  timeouts; an unplugged adapter ends the stream with an error right away.
- A reader (`MeterReaderLike`) has one method, `async run()`: it reads until
  it is cancelled and raises on any fault. Readers never retry themselves.
- `meter/supervisor.py` (`ReaderSupervisor`) is the single place for
  recovery: it replaces a failed reader after a pause, reports a silent meter
  (`stale_after`) and reopens the port when it stays silent
  (`restart_after`). Cancelling it stops the reader and closes the port.
- Parsing (gurux, about 1–2 ms per telegram) runs on the loop; at one
  telegram every 1–5 seconds that is well below 1 % of the loop's time.

## Tests

The tests need no hardware and no broker: a scripted port
(`smartmeter/tests/fake_port.py`), a small MQTT broker
(`smartmeter/tests/fake_broker.py`) and pseudo terminals for the real serial
transport.

Add-on and core (Python 3.15):

```bash
cd smartmeter
uv venv && source .venv/bin/activate
uv pip install -r requirements-dev.txt
python3 fix_source_encoding.py gurux_dlms gurux_common
ruff check && pytest tests
cd .. && mypy --config-file mypy.ini
```

Integration (Python version from `tests_integration/.python-version`):

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements-ha-test.txt ruff
python3 smartmeter/fix_source_encoding.py gurux_dlms gurux_common
ruff check custom_components tests_integration && pytest tests_integration
```

## Testing the integration locally

Always work with the whole repository: copying only
`custom_components/smartmeter_at/` leaves dangling symlinks. Either symlink
the directory out of a clone, or resolve the links when copying (as the
release zip does).

**Test instance in Docker:** `./dev.sh` mirrors the integration (links
resolved) into `config/` and starts Home Assistant in the container
`smartmeter-ha-dev` on <http://localhost:8124>. Run it again after a change to
sync and restart. `HTTP_PORT` changes the port, `--recreate` recreates the
container, `--no-logs` keeps it running in the background. On a Linux host,
`SERIAL_DEVICE=/dev/ttyUSB0 ./dev.sh` passes the reading head into the
container; Docker Desktop on macOS/Windows cannot pass USB serial devices.

### On a real Home Assistant

Clone the repository into `/config` (e.g. with the *Terminal & SSH* add-on)
and symlink the integration into `custom_components`. Updating is then a
plain `git pull`:

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

Without `git` on the Home Assistant host, copy the directory with links
resolved, e.g. `cp -rL`, or from another machine
`rsync -aL --delete --exclude __pycache__ custom_components/smartmeter_at/ root@homeassistant.local:/config/custom_components/smartmeter_at/`
(the SSH add-on needs `rsync`; `scp -r` follows links as well).

## Building the add-on images

```bash
cd smartmeter
DOCKERHUB_USER=… DOCKERHUB_PASSWORD=… ./build_images.sh
```

builds the add-on images for all architectures with the Home Assistant
builder and pushes them to Docker Hub. The version comes from `config.yaml`.

## Adding a meter

Everything specific to a meter's customer interface lives in its profile in
`smartmeter/meter/profile.py`: serial settings, push interval, which reader
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
