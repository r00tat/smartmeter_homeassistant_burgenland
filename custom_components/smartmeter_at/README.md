# Smartmeter Austria – Home Assistant integration

Reads Austrian smart meters through their customer interface and exposes the
values as Home Assistant sensors. The meter is read directly on the Home
Assistant host: no MQTT broker and no add-on are needed, and the integration
also works with Home Assistant Container and Core.

This directory is the integration (domain `smartmeter_at`). Full
documentation, also in German: <https://github.com/r00tat/smartmeter_homeassistant_burgenland>
(meter details: [meters](https://github.com/r00tat/smartmeter_homeassistant_burgenland/blob/main/docs/en/meters.md)).

## Supported meters

| Meter type in the config flow | Interface |
| --- | --- |
| Netz Burgenland (Landis+Gyr E450) | IR reading head or wired |
| Netz NÖ / EVN (Sagemcom T210-D) | M-Bus |
| Wiener Netze (Siemens IM150/IM350/IM351, Iskraemeco AM550, Landis+Gyr E450) | IR reading head or wired |
| Energienetze Steiermark (Landis+Gyr E450, M-Bus) | M-Bus |
| Energienetze Steiermark (Sagemcom, DSMR P1) | P1 |
| Salzburg Netz (Kaifa/Honeywell MA309M) | M-Bus |
| TINETZ Tirol (Kaifa/Honeywell MA110M/MA309M) | M-Bus |
| Smart Meter 2.0 H1 interface (DSMR P1) | P1 |

## Prerequisites

- The customer interface is activated by your grid operator, and you have the
  key (32 hex characters) for it.
- The reading head or adapter is connected to the Home Assistant host and shows
  up as a serial port, ideally under `/dev/serial/by-id/`.
- The Smartmeter add-on does not read the same port. Use either the add-on or
  the integration for a meter, never both.

## Switching from the add-on

Stop the add-on and disable its autostart (keep MQTT running), wait a minute
and add the integration. After the connection check it finds the add-on's MQTT
device and offers *Take over the add-on sensors*. With that, the integration
registers its sensors under the add-on's entity ids and keeps their settings
and unit (Wh), so dashboards, automations, the energy dashboard, history and
statistics keep working. The add-on device is removed. Do not start the add-on
again afterwards. If you added the integration without taking over, stop the
add-on and use *Configure* → *Take over the add-on sensors* later; the
integration's own sensors are then replaced by the add-on's entity ids.
Details: [migration](https://github.com/r00tat/smartmeter_homeassistant_burgenland/blob/main/docs/en/migration.md).

## Installation

### Marketplace

[![Open your Home Assistant instance and open a repository inside the Home Assistant Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=r00tat&repository=smartmeter_homeassistant_burgenland&category=integration)

1. Click the badge above, or search for *Smartmeter Austria* under
   Settings → Marketplace. Before Home Assistant 2026.11 the badge opens
   HACS instead; search for *Smartmeter Austria* there.
2. Install *Smartmeter Austria* and restart Home Assistant.

### Manual

The meter code is not part of this directory: Home Assistant installs it
from PyPI as [`smartmeter-austria`](https://pypi.org/project/smartmeter-austria/)
(see `requirements` in `manifest.json`). Install the integration with one of
these:

- Download `smartmeter_at.zip` from a
  [release](https://github.com/r00tat/smartmeter_homeassistant_burgenland/releases)
  and unpack it into `/config/custom_components/smartmeter_at/`.
- Clone the repository into `/config` and symlink the integration, so you can
  update it with `git pull`:

  ```bash
  cd /config
  git clone https://github.com/r00tat/smartmeter_homeassistant_burgenland.git smartmeter-src
  mkdir -p /config/custom_components
  rm -rf /config/custom_components/smartmeter_at
  ln -s ../smartmeter-src/custom_components/smartmeter_at /config/custom_components/smartmeter_at
  ```

  Update later with `cd /config/smartmeter-src && git pull`. Keep the clone
  inside `/config` and the link relative, otherwise it is dangling inside the
  Home Assistant container.

Restart Home Assistant after installing or updating. Details:
[development](https://github.com/r00tat/smartmeter_homeassistant_burgenland/blob/main/docs/en/development.md#on-a-real-home-assistant).

## Configuration

Settings → Devices & services → *Add integration* → *Smartmeter Austria*.

| Field | Meaning |
| --- | --- |
| Grid operator / meter | Meter type from the table above |
| Serial port | Port of the reading head or adapter |
| Customer interface key | 32 hex characters from your grid operator; spaces are ignored |
| Interface | Optical (IR) or wired; only used for Burgenland and Wien |

Before it saves the entry, the integration reads one telegram from the meter
(up to 30 seconds). A wrong key, port or meter type therefore shows up as an
error right away instead of as missing values later.

Under *Configure* you set the update interval (default 10 s): the integration
publishes a new value at most this often. The serial settings are the defaults
of the selected meter type and cannot be changed.

## Entities

The integration creates one device per meter, with the meter's serial number
when the meter sends it. Sensors depend on the meter type and typically cover
energy consumed and fed in (kWh, usable in the energy dashboard), active power,
and voltage and current per phase. For Burgenland and Wien a few rarely
needed sensors are disabled by default; enable them on the device page.

All entities become unavailable when no telegram arrives for about a minute,
for example when the reading head slipped off.

The integration recovers on its own, so no restart automation is needed: if
the port fails (e.g. the USB adapter was unplugged) it reopens it every 10
seconds, and if the port stays open but no telegram arrives for 5 minutes (e.g.
a hung adapter) it closes and reopens it.

## Troubleshooting

- **Cannot connect:** the port does not exist or another process (often the
  add-on) holds it.
- **No data:** the port opens, but no telegram arrived in time. Check that the
  reading head sits on the IR window, the interface is activated and the meter
  type is right.
- **Invalid key:** the key is not 32 hex characters. A key with the right
  format but the wrong value shows up as *No data*.
- **Unexpected error:** the log contains details.
- Download the diagnostics from the device page when you open an issue; the
  key is redacted.

For debug logging add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.smartmeter_at: debug
    smartmeter_austria: debug
```

## Development

`./dev.sh` in the repository root starts a Home Assistant test instance in
Docker with this integration mirrored into it. The tests live in
`tests_integration/`. See [development](https://github.com/r00tat/smartmeter_homeassistant_burgenland/blob/main/docs/en/development.md).

Issues: <https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues>
