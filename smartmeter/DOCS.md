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

You can read more about the underlying python program at the [github page](https://github.com/r00tat/smartmeter_homeassistant_burgenland).

## Meter selection

Set the top-level `meter_type` option to switch between providers. When
omitted, the addon behaves exactly as before and uses the `burgenland`
profile. Changing the profile also switches the default serial baudrate
(9600 for `burgenland`, 2400 for `noe_evn`) and the Home Assistant
device manufacturer/model metadata.

The `noe_evn` profile publishes the subset of OBIS registers emitted by
the Sagemcom T210-D: instantaneous voltages (L1–L3), currents (L1–L3),
active power in/out, power factor, and cumulative import/export energy.
Phase-angle sensors (which the E450 exposes) are omitted because the
T210-D does not publish them.

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
docker run -e SMARTMETER_CONFIG=/myconfig.yaml \
  -v /path/to/myconfig.yaml:/myconfig.yaml \
  docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone:latest
```

### docker compose (recommended)

Use the provided `docker-compose.standalone.yml` example:

```bash
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
