# Smartmeter Burgenland (AT) MQTT Addon

This Addon connects your Austrian Smart Meter to Home Assistant via MQTT.
It has been tested with a Raspberry Pi Zero W 2 and a
[Weidmann Elektronik IR Schreib/Lesekopf](https://shop.weidmann-elektronik.de/index.php?page=product&info=24).

Supported meters (select via `meter_type`):

- `burgenland` *(default)* — Netz Burgenland
  [Landis+Gyr E450](https://www.netzburgenland.at/fileadmin/NB_pdf_NEU/Smart_Meter/Spezifikation_Kundenschnittstelle_E450_korr_2.pdf)
  over DLMS/HDLC at 9600 baud. The IR customer interface must be unlocked
  by Netz Burgenland and the AES key obtained from the customer portal.
- `noe_evn` — Netz Niederösterreich / EVN
  [Sagemcom T210-D](https://www.netz-noe.at/Download-(1)/Smart-Meter/218_9_SmartMeter_Kundenschnittstelle_Lastenheft2-0.aspx)
  over DLMS via M-Bus framing at 2400 baud (8E1). The M-Bus customer
  interface must be activated and the AES key requested via the Netz NÖ
  customer portal.
- `wien` — Wiener Netze (Siemens IM150/IM350/IM351, Iskraemeco AM550,
  Landis+Gyr E450) over DLMS/HDLC on the
  [infrared customer interface](https://www.wienernetze.at/smart-meter-kundenschnittstelle)
  at 9600 baud (8N1). Activate the customer interface and copy the AES key
  from the [Wiener Netze Smart Meter portal](https://smartmeter-web.wienernetze.at/).

Implemented from the grid operators' specifications but **not yet tested
with a real meter** (please report your results, see
[Real data wanted](https://github.com/r00tat/smartmeter_homeassistant_burgenland/blob/main/docs/en/meters.md#real-data-wanted)):

- `steiermark` — Energienetze Steiermark, Landis+Gyr E450 on the wired M-Bus
  customer interface (RJ12) at 2400 baud (8E1). Use the GUEK from the
  [Energienetze portal](https://portal.e-netze.at/) as key.
- `steiermark_sagemcom` — Energienetze Steiermark, Sagemcom on the DSMR P1
  customer interface (RJ12) at 115200 baud (8N1). Use the GUEK as key.
- `salzburg` — Salzburg Netz, Kaifa / Honeywell on the wired M-Bus customer
  interface (RJ12) at 2400 baud (8E1). Activate it and download the key in the
  [Salzburg Netz portal](https://portal.salzburgnetz.at/).
- `tirol` — TINETZ, Kaifa / Honeywell on the wired M-Bus customer interface
  (RJ12) at 2400 baud (8E1). Activate it in the TINETZ customer portal; the
  key is sent to you.
- `h1` — the *Smart Meter 2.0* customer interface H1 that all Austrian grid
  operators will install (DSMR P1, 115200 baud, one telegram per second).

The wired M-Bus interfaces need an M-Bus slave adapter (M-Bus to USB); the
DSMR P1 interfaces need a P1 cable. `interface_type` is ignored by these
profiles.

Full documentation (German, with English versions) is on the [GitHub page](https://github.com/r00tat/smartmeter_homeassistant_burgenland). If the reading head is connected to the Home Assistant device, the [Home Assistant integration](https://github.com/r00tat/smartmeter_homeassistant_burgenland/blob/main/docs/en/installation.md#integration-marketplace) reads the meter without MQTT; it can [take over this add-on's sensors](https://github.com/r00tat/smartmeter_homeassistant_burgenland/blob/main/docs/en/migration.md).

## Meter selection

Set the top-level `meter_type` option to switch between providers. When
omitted, the addon behaves exactly as before and uses the `burgenland`
profile. The profile decides everything about the meter's interface: the
serial settings (9600 8N1 for `burgenland` and `wien`; 2400 8E1 for
`noe_evn`, `steiermark`, `salzburg` and `tirol`; 115200 8N1 for `h1` and
`steiermark_sagemcom`), how often the meter sends data, how the data is decoded, the
Home Assistant device manufacturer/model metadata and the sensor list.

Leave `baudrate`, `bytesize`, `parity` and `stopbits` empty to use the
profile's settings; set them only to override. Installations that already
saved explicit values keep them.

The `noe_evn` profile publishes the subset of OBIS registers emitted by
the Sagemcom T210-D: instantaneous voltages (L1–L3), currents (L1–L3),
active power in/out, power factor, and cumulative import/export energy.
Phase-angle sensors (which the E450 exposes) are omitted because the
T210-D does not publish them.

The `wien` profile publishes what Wiener Netze meters send every second:
active energy in/out, active power in/out and, disabled by default,
reactive energy and reactive power in/out. The meters send no voltages or
currents. The meter clock is included in the raw state as `meter_time`.
`publish_interval` is respected: with the default of 30 seconds every 30th
reading is published.

The `steiermark`, `steiermark_sagemcom`, `salzburg`, `tirol` and `h1`
profiles publish the values their meters send, named as in the other
profiles: energy and power in/out, voltages and currents (Salzburg, Tirol,
H1), tariff 1/2 energy (Steiermark), and, disabled by default, reactive
energy and power. Values a meter does not send are published as `null`.
With `logging: DEBUG` the raw serial bytes and every telegram are logged
as hex — please attach them when you report a problem.

## Availability and recovery

The add-on recovers on its own, so no restart automation is needed:

- If the serial port fails (for example the USB adapter was unplugged), the
  sensors are marked unavailable and the port is opened again every 10
  seconds until it works.
- If no telegram arrives for about a minute (six missed telegrams, at least
  60 seconds), the sensors are marked unavailable until the next telegram.
- If the port stays open but no telegram arrives for 5 minutes (for example a
  hung USB adapter), the port is closed and opened again.
- If the MQTT broker is unreachable or restarts, the add-on reconnects every
  10 seconds and announces the device again. Readings received in the
  meantime are queued (up to 100 messages).
- The MQTT last will marks the sensors unavailable if the add-on stops
  without a clean shutdown.

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

Certificate paths must be readable from within the add-on container. The
add-on mounts the Home Assistant `share` folder read-only at `/share` and the
Home Assistant configuration folder read-only at `/config`, so certificates
placed in either directory can be referenced as `/share/...` or `/config/...`.

## Standalone (Docker / docker-compose)

The standalone image runs **without** the Home Assistant Supervisor, making it
suitable for any host that can run Docker (a plain Raspberry Pi, a NAS, a VPS,
etc.). It is published as a multi-arch image (amd64 and arm64) at:

```text
docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone
```

### Configuration

The standalone image reads a plain YAML config file — the same format as
`smartmeter-config.example.yaml`. Mount it into the container at
`/config/smartmeter-config.yaml`:

```bash
# One-time setup
cp smartmeter-config.example.yaml smartmeter-config.yaml
# Edit smartmeter-config.yaml: set mqtt.host, dlms.key, dlms.port, …
```

To use a different path inside the container, set the `SMARTMETER_CONFIG`
environment variable:

```bash
# Minimal example — illustrates the env var only. For real use, add the serial
# device (--device), detach (-d), and a restart policy (--restart), or use the
# docker-compose.standalone.yml example below.
docker run -e SMARTMETER_CONFIG=/myconfig.yaml \
  -v /path/to/myconfig.yaml:/myconfig.yaml \
  docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone:latest
```

### docker compose (recommended)

Use the provided `docker-compose.standalone.yml` example. Run it from inside
the `smartmeter/` directory (where the compose file and your
`smartmeter-config.yaml` live):

```bash
cd smartmeter
docker compose -f docker-compose.standalone.yml up -d
```

The compose file mounts `./smartmeter-config.yaml` and maps the serial device
`/dev/ttyUSB0`. Adjust the device path in the file if your IR reader appears on
a different node (e.g. `/dev/ttyUSB1` or `/dev/ttyAMA0`).

### Minimal docker run

```bash
docker run -d --restart unless-stopped \
  --device /dev/ttyUSB0:/dev/ttyUSB0 \
  -v "$(pwd)/smartmeter-config.yaml:/config/smartmeter-config.yaml:ro" \
  docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone:latest
```
