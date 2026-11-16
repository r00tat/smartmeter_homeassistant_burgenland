# Smartmeter Austria – Home Assistant integration

Reads Austrian smart meters through their customer interface and exposes the
values as Home Assistant sensors. The meter is read directly on the Home
Assistant host: no MQTT broker and no add-on are needed, and the integration
also works with Home Assistant Container and Core.

This directory is the integration (domain `smartmeter_at`). The repository
README covers the add-on, the standalone reader and the meter interfaces in
detail: <https://github.com/r00tat/smartmeter_homeassistant_burgenland>.

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

## Installation

### HACS

1. HACS → ⋮ → *Custom repositories* → add
   `https://github.com/r00tat/smartmeter_homeassistant_burgenland`, category
   *Integration*.
2. Install *Smartmeter Austria* and restart Home Assistant.

### Manual

`meter/` and `fix_source_encoding.py` in this directory are symlinks into the
repository's `smartmeter/` directory. Copying only this directory leaves them
dangling, so use one of these:

- Download `smartmeter_at.zip` from a
  [release](https://github.com/r00tat/smartmeter_homeassistant_burgenland/releases)
  and unpack it into `/config/custom_components/smartmeter_at/`.
- Clone the repository and copy the directory with links resolved:

  ```bash
  cd /config
  git clone https://github.com/r00tat/smartmeter_homeassistant_burgenland.git smartmeter-src
  mkdir -p /config/custom_components
  rm -rf /config/custom_components/smartmeter_at
  cp -rL smartmeter-src/custom_components/smartmeter_at /config/custom_components/
  ```

Restart Home Assistant afterwards.

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
    meter: debug
```

## Development

`./dev.sh` in the repository root starts a Home Assistant test instance in
Docker with this integration mirrored into it. The tests live in
`tests_integration/`. See *Integration Development* in the repository README.

Issues: <https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues>
