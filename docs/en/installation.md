# Installation

[Deutsche Version](../installation.md) · [Back to the README](../../README.en.md)

Use exactly one reader per meter: the integration, the add-on or the
standalone container. Two readers on the same port corrupt each other's
telegrams.

| Way | When | MQTT needed |
| --- | --- | --- |
| [Integration (Marketplace)](#integration-marketplace) | reading head on the Home Assistant device, **recommended** | no |
| [Standalone Docker container](#standalone-docker-container) | reading head on another device | yes |
| [Home Assistant add-on](#home-assistant-add-on) | reading head on the Home Assistant device, existing installations | yes |
| [systemd without Docker](#systemd-without-docker) | another device without Docker | yes |

For every way, first have the grid operator activate the customer interface
and get the key, see [meters.md](meters.md).

Tested with a Raspberry Pi Zero 2 W (standalone), a Raspberry Pi 4 (add-on)
and the
[IR read/write head by Weidmann Elektronik](https://shop.weidmann-elektronik.de/index.php?page=product&info=24).

## Integration (Marketplace)

[![Open a repository inside the Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=r00tat&repository=smartmeter_homeassistant_burgenland&category=integration)

The integration reads the meter directly in Home Assistant. It needs no MQTT
broker and no add-on, and also runs with Home Assistant Container and Core
(no Supervisor).

### Install

1. Click the badge above, or *Settings → Marketplace → Add from link* →
   `https://github.com/r00tat/smartmeter_homeassistant_burgenland`.
   The Marketplace is built into Home Assistant since 2026.11 and replaces
   HACS. On older versions the badge opens HACS; there use *HACS → ⋮ →
   Custom repositories*, category *Integration*.
2. Install *Smartmeter Austria* and restart Home Assistant.

The Marketplace and HACS install the integration from the
`smartmeter_at.zip` file of a release.

### Set up

*Settings → Devices & services → Add integration → Smartmeter Austria*.

| Field | Meaning |
| --- | --- |
| Grid operator / meter | Meter type, see [meters.md](meters.md) |
| Serial port | Port of the reading head or adapter, ideally under `/dev/serial/by-id/` |
| Customer interface key | 32 hex characters from your grid operator; spaces are ignored |
| Interface | Optical (IR) or wired; only used for Burgenland and Wien |

Before it saves the entry, the integration reads one telegram (up to 30
seconds). A wrong key, port or meter type therefore shows up as an error
right away.

Under *Configure* you set the update interval (default 10 s): a new value is
taken over at most this often. The serial settings come from the meter type
and cannot be changed here.

### Sensors

The integration creates one device per meter, with the meter's serial number
when the meter sends it. Depending on the meter there is energy consumed and
fed in (for the energy dashboard), active power, and voltage and current per
phase. For Burgenland and Wien a few rarely needed sensors are disabled by
default; enable them on the device page.

### Manual installation

The integration is only the directory `custom_components/smartmeter_at/`;
Home Assistant installs the meter code as the Python package
[`smartmeter-austria`](https://pypi.org/project/smartmeter-austria/) from PyPI.

- unpack `smartmeter_at.zip` from a
  [release](https://github.com/r00tat/smartmeter_homeassistant_burgenland/releases)
  into `/config/custom_components/smartmeter_at/`, or
- clone the repository and link it, see [development.md](development.md#on-a-real-home-assistant).

Restart Home Assistant after installing or updating.

## Standalone Docker container

For a reading head on a device other than Home Assistant, e.g. a Raspberry Pi
at the meter cabinet. The container reads the meter and publishes the values
via MQTT; Home Assistant creates the sensors automatically through MQTT
discovery. The image runs without the Home Assistant Supervisor on any Docker
host (amd64 and arm64):

```text
docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone
```

### Requirements

- An MQTT broker, e.g. the *Mosquitto broker* add-on in Home Assistant, and
  the MQTT integration in Home Assistant.
- Docker with Compose on the device with the reading head.

### Set up

1. Create the configuration `smartmeter-config.yaml` (options see
   [below](#configuration-container-and-systemd)):

   ```yaml
   meter_type: burgenland
   interface_type: OPTICAL
   mqtt:
     host: homeassistant.local
     user: "mqtt-user"
     password: "secret"
   dlms:
     port: /dev/ttyUSB0
     key: "0123456789ABCDEF0123456789ABCDEF"
   ```

2. Create `docker-compose.yml` next to it:

   ```yaml
   services:
     smartmeter:
       image: docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone:latest
       restart: unless-stopped
       volumes:
         - ./smartmeter-config.yaml:/config/smartmeter-config.yaml:ro
       devices:
         - /dev/ttyUSB0:/dev/ttyUSB0
   ```

   If the reading head shows up as another device (`/dev/ttyUSB1`,
   `/dev/ttyAMA0`, …), adjust the path in `devices` and in `dlms.port`.

3. Start with `docker compose up -d`. `docker compose logs -f` shows the logs.

Without Compose:

```bash
docker run -d --restart unless-stopped \
  --device /dev/ttyUSB0:/dev/ttyUSB0 \
  -v "$(pwd)/smartmeter-config.yaml:/config/smartmeter-config.yaml:ro" \
  docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone:latest
```

If the configuration lives at another path inside the container, point the
`SMARTMETER_CONFIG` environment variable to it. The repository contains the
same files as templates: `smartmeter/docker-compose.standalone.yml` and
`smartmeter/smartmeter-config.example.yaml`.

### Configuration (container and systemd)

| Option | Default | Meaning |
| --- | --- | --- |
| `meter_type` | `burgenland` | meter type, see [meters.md](meters.md) |
| `interface_type` | `OPTICAL` | `OPTICAL` (IR) or `PHYSICAL` (wired), Burgenland and Wien only |
| `logging` | `INFO` | `DEBUG` shows every telegram |
| `mqtt.host` | – | address of the MQTT broker (required) |
| `mqtt.port` | `1883` | broker port |
| `mqtt.user`, `mqtt.password` | – | credentials |
| `mqtt.publish_interval` | `30` | seconds between two values |
| `mqtt.device_id` | `smartmeter` | MQTT topic and device id |
| `mqtt.name` | `Smart Meter` | device name in Home Assistant |
| `mqtt.prefix` | – | prefix for all topics |
| `mqtt.tls` | `false` | enable TLS, see below |
| `dlms.port` | `/dev/ttyUSB0` | serial port |
| `dlms.key` | – | key, 32 hex characters (required) |
| `dlms.baudrate`, `bytesize`, `parity`, `stopbits` | from the meter type | set only to override |
| `dlms.hdlc_frame_size` | `120` | minimum telegram length with `PHYSICAL` |

**MQTT over TLS:** set `mqtt.tls: true` and usually `mqtt.port: 8883`. Without
`tls_ca` the system CA store is used. `tls_ca` (CA certificate), `tls_cert`
and `tls_key` (client certificate for mTLS) are paths inside the container;
`tls_insecure: true` skips certificate verification (testing only). The TLS
options only apply with `tls: true`.

## Home Assistant add-on

The add-on reads the meter on the Home Assistant device and publishes via
MQTT. For new installations the [integration](#integration-marketplace) is
simpler; existing add-on users can [switch](migration.md). The add-on needs
Home Assistant OS or Supervised.

1. *Settings → Add-ons → Add-on Store*: install and start *Mosquitto broker*,
   then set up the MQTT integration.
2. In the add-on store open *⋮ → Repositories* and add
   `https://github.com/r00tat/smartmeter_homeassistant_burgenland`, then
   reload the page.
3. Install *Smartmeter Burgenland MQTT*.
4. In the *Configuration* tab enter meter type, port and key. As MQTT host use
   the address of Home Assistant, as user a Home Assistant user or
   credentials from the Mosquitto add-on. The options match the
   [table above](#configuration-container-and-systemd).
5. Start the add-on.

Put TLS certificates under `/share` or `/config`; both folders are mounted
read-only in the add-on.

## systemd without Docker

For a device without Docker, e.g. a Raspberry Pi with Raspberry Pi OS.
Requires [uv](https://docs.astral.sh/uv/).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/r00tat/smartmeter_homeassistant_burgenland.git
cd smartmeter_homeassistant_burgenland/smartmeter
cp smartmeter-config.example.yaml smartmeter-config.yaml
# edit smartmeter-config.yaml (options as above)
sudo ln -s "$(pwd)/smartmeter.service" /etc/systemd/system/smartmeter.service
sudo systemctl enable --now smartmeter
```

`smartmeter.service` expects the repository at
`/home/pi/smartmeter_homeassistant_burgenland` and the user `pi`; adjust the
file first for other paths. Status: `sudo systemctl status smartmeter`, logs:
`journalctl -u smartmeter -f`.

On every start `smartmeter.sh` installs the dependencies and the
`smartmeter-austria` library straight from the repository's `packages/`
(editable, not from PyPI). To update, run
`git pull && sudo systemctl restart smartmeter`; the service always runs
exactly the checked-out code.
