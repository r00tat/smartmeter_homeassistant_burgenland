# Smartmeter Austria for Home Assistant

[Deutsche Version](README.md)

Reads Austrian smart meters through their customer interface and brings
consumption, feed-in, power, voltage and current into Home Assistant,
including the energy dashboard.

## Supported meters

| Grid operator | Meter | Interface | Status |
| --- | --- | --- | --- |
| Netz Burgenland | Landis+Gyr E450 | infrared (optical) or wired | tested |
| Netz NÖ / EVN | Sagemcom T210-D | M-Bus | tested |
| Wiener Netze | Siemens IM150/IM350/IM351, Iskraemeco AM550, Landis+Gyr E450 | infrared | tested |
| Energienetze Steiermark | Landis+Gyr E450 | M-Bus | from specification, untested |
| Energienetze Steiermark | Sagemcom | DSMR P1 | from specification, untested |
| Salzburg Netz | Kaifa / Honeywell MA309M | M-Bus | from specification, untested |
| TINETZ (Tyrol) | Kaifa / Honeywell MA110M / MA309M | M-Bus | from specification, untested |
| all (Smart Meter 2.0) | customer interface H1 | DSMR P1 | from specification, untested |

Details on every meter, activation and key:
[docs/en/meters.md](docs/en/meters.md). You have one of the untested meters?
[Help with a capture](docs/en/meters.md#real-data-wanted).

## What you need

1. **Activated customer interface:** request it from your grid operator and
   get the key (32 hex characters) from the customer portal.
2. **Reading head or adapter:** an infrared reading head (USB) for Burgenland
   and Vienna, an M-Bus adapter (M-Bus to USB) or a P1 cable for the others.
3. **Home Assistant.**

## Which way fits?

| The reading head is connected … | Way |
| --- | --- |
| … to the Home Assistant device | **[Integration via the Marketplace](#integration-via-the-marketplace-recommended)** (recommended) |
| … to another device (e.g. a Raspberry Pi at the meter cabinet) | **[Standalone Docker container](#standalone-docker-container)**, publishes via MQTT |

Other ways (Home Assistant add-on, systemd without Docker) are described in
[docs/en/installation.md](docs/en/installation.md).

### Integration via the Marketplace (recommended)

[![Open a repository inside the Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=r00tat&repository=smartmeter_homeassistant_burgenland&category=integration)

Reads the meter directly in Home Assistant, without MQTT broker and without
add-on. Works with Home Assistant OS, Container and Core.

1. Click the badge above, or *Settings → Marketplace → Add from link* →
   `https://github.com/r00tat/smartmeter_homeassistant_burgenland`.
2. Install *Smartmeter Austria* and restart Home Assistant.
3. *Settings → Devices & services → Add integration → Smartmeter Austria*.
4. Enter grid operator, serial port and key. The integration reads one
   telegram before it saves the entry, so a wrong key or port shows up right
   away.

Before Home Assistant 2026.11 the badge opens HACS. There add the repository
under *HACS → ⋮ → Custom repositories* (category *Integration*).

Using the add-on so far? The integration takes over its sensors including
history and statistics: [docs/en/migration.md](docs/en/migration.md).

### Standalone Docker container

For a reading head on a device other than Home Assistant. The container reads
the meter and publishes the values via MQTT; the sensors show up in Home
Assistant automatically.

Requirement: an MQTT broker (e.g. the *Mosquitto broker* add-on) and the MQTT
integration in Home Assistant.

1. Create `smartmeter-config.yaml`:

   ```yaml
   meter_type: burgenland        # see docs/en/meters.md
   interface_type: OPTICAL
   mqtt:
     host: homeassistant.local   # address of the MQTT broker
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

3. Start: `docker compose up -d`, logs: `docker compose logs -f`.

All options (TLS, interval, serial settings) are listed in
[docs/en/installation.md](docs/en/installation.md#standalone-docker-container).

## More documentation

- [Installation in detail](docs/en/installation.md): integration, Docker, add-on, systemd
- [Meters and grid operators](docs/en/meters.md): activation, key, technical details
- [Switching from the add-on to the integration](docs/en/migration.md)
- [Troubleshooting](docs/en/troubleshooting.md): error messages, debug logs, behaviour on failures
- [Development](docs/en/development.md): architecture, local test setup, adding a meter
- [Python library `smartmeter-austria`](packages/smartmeter-austria/README.md): the meter code for your own projects, on [PyPI](https://pypi.org/project/smartmeter-austria/)

Questions and bugs: [GitHub Issues](https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues)
