# Smart Meter Reader Burgenland - AT

This python program connects your Austrian Smart Meter to Home Assistant
via MQTT.
Alternatively, the [Home Assistant integration (HACS)](#home-assistant-integration-hacs)
reads the meter directly, without MQTT broker and add-on.

Supported meters (select via `meter_type`):

- `burgenland` *(default)* — Netz Burgenland
  [Landis+Gyr E450](https://www.netzburgenland.at/fileadmin/NB_pdf_NEU/Smart_Meter/Spezifikation_Kundenschnittstelle_E450_korr_2.pdf)
  via DLMS/HDLC at 9600 baud.
- `noe_evn` — Netz Niederösterreich / EVN Sagemcom T210-D via DLMS over
  M-Bus framing at 2400 baud (8E1).
- `wien` — Wiener Netze (Siemens IM150/IM350/IM351, Iskraemeco AM550,
  Landis+Gyr E450) via DLMS/HDLC on the infrared interface at 9600 baud.

Implemented from the grid operators' specifications, **not yet tested with
a real meter** — [real telegrams wanted](#real-data-wanted):

- `steiermark` — Energienetze Steiermark, Landis+Gyr E450 via wired M-Bus
  (RJ12) at 2400 baud (8E1).
- `steiermark_sagemcom` — Energienetze Steiermark, Sagemcom via DSMR P1
  (RJ12) at 115200 baud (8N1).
- `salzburg` — Salzburg Netz, Kaifa / Honeywell via wired M-Bus (RJ12) at
  2400 baud (8E1).
- `tirol` — TINETZ, Kaifa / Honeywell via wired M-Bus (RJ12) at 2400 baud
  (8E1).
- `h1` — the future *Smart Meter 2.0* customer interface H1 (Oesterreichs
  Energie Companion Standard 2026, all Austrian grid operators): DSMR P1 at
  115200 baud, one telegram per second, DLMS Security Suite 0.

## Real data wanted

The profiles `steiermark`, `steiermark_sagemcom`, `salzburg`, `tirol` and
`h1` follow the published specifications and are covered by tests with
telegrams built exactly to those specifications. **No telegram from a real
meter has been decoded with them yet.** Meters do not always behave as
their documentation says (Salzburg Netz, for example, documents AES-CBC,
while community projects report AES-GCM), so expect rough edges until
someone confirms a profile.

If you have one of these meters, please help:

1. Set `logging: DEBUG` and the matching `meter_type`, and let the add-on run
   for a minute.
2. Open an [issue](https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues)
   with your grid operator, meter model, the `raw bytes:` / `telegram (…):`
   log lines and whether values showed up in Home Assistant.
3. If you can, include a capture together with its key so it can become a
   test fixture. The key only decrypts the customer interface of your own
   meter; you can have your grid operator issue a new one afterwards. If you
   do not want to share the key, the decoded values the add-on logged (or the
   values on the meter display at that moment) help as well.

Not supported yet: Netz Oberösterreich (AMIS, plain OMS M-Bus with AES
mode 5), Vorarlberg Netz (AES-CBC with CMAC) and Kärnten Netz (no public
specification found). Captures for these are welcome too.

It has been tested with a Raspberry Pi Zero 2 W as a standalone device
and with a Raspberry Pi 4 as Home Assistant Addon.

The addon uses Mosquitto MQTT server to manage the connection from the addon to HomeAssistant. You need to install the addon first.

## Quickstart

### Homeassistant Addon

To use this program on the homeassistant raspberry pi as addon follow this steps:

1. Request the [activation of the customer interface](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/kundenschnittstelle.html) and select IR as transport.
2. Connect the IR reader to the smart meter
3. Connect the IR reader to your raspberry pi
4. Open homeassistant web ui and go to Settings -> Add-ons -> Add-on Store
5. Install and start `Mosquitto broker` to setup the MQTT server.
6. Go to Settings > Devices > Integrations and add the Mosquitto MQTT integration
7. Go back to the Addon store
8. Click on the 3 dots on the top right and click on Repositories
9. Add `https://github.com/r00tat/smartmeter_homeassistant_burgenland` as a repository.
10. Reload the page
11. Install the Smartmeter Burgenland MQTT Addon
12. Configure the smartmeter connection.
    As hostname use the homeassistant address. As username / password use a normal home assistant user or configure credentials in the Mosquitto broker.
13. start the addon

### Standalone (Docker)

The add-on image requires the Home Assistant Supervisor and cannot run on a
plain Docker host. A separate standalone image is provided for exactly this use
case ([#101](https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues/101)).
It is published as a multi-arch image (amd64/arm64):

```text
docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone
```

**Steps:**

1. Request the [activation of the customer interface](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/kundenschnittstelle.html) and select IR as transport.
1. Connect the IR reader to the smart meter and to your host machine.
1. Copy and edit the example config:

```bash
cd smartmeter/
cp smartmeter-config.example.yaml smartmeter-config.yaml
# Edit smartmeter-config.yaml: set mqtt.host, dlms.key, dlms.port, …
```

1. Start with docker compose (from inside `smartmeter/`, using the provided `docker-compose.standalone.yml`):

```bash
docker compose -f docker-compose.standalone.yml up -d
```

Or run directly with `docker run` (also from inside `smartmeter/`):

```bash
docker run -d --restart unless-stopped \
  --device /dev/ttyUSB0:/dev/ttyUSB0 \
  -v "$(pwd)/smartmeter-config.yaml:/config/smartmeter-config.yaml:ro" \
  docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone:latest
```

Adjust `/dev/ttyUSB0` if your IR reader appears on a different device node.

### Home Assistant integration (HACS)

Reads the meter directly in Home Assistant: no MQTT broker and no add-on
needed, and it also works with Home Assistant Container and Core (no
Supervisor). The meter's customer interface (IR reading head, M-Bus or P1
adapter) must be connected to the Home Assistant host.

1. Request the activation of the customer interface (see above).
2. In HACS: ⋮ → Custom repositories → add
   `https://github.com/r00tat/smartmeter_homeassistant_burgenland`, category
   *Integration*.
3. Install *Smartmeter Austria* and restart Home Assistant.
4. Settings → Devices & services → Add integration → *Smartmeter Austria*.
5. Select grid operator, serial port and enter the key. The integration reads
   one telegram before it saves the entry, so a wrong key or port shows up
   right away.

Use either the add-on or the integration for a meter, never both: only one of
them can open the serial port. When you switch from the add-on, the
integration creates new entities; the energy dashboard has to be pointed to
the new *Total Energy consumed/provided* sensors.

The update interval (default 10 s) is set under the integration's
*Configure* button.

### Standalone (systemd / uv)

To use this program on an external raspberry pi follow this steps:

1. Request the [activation of the customer interface](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/kundenschnittstelle.html) and select IR as transport.
2. Connect the IR reader to the smart meter
3. Connect the IR reader to your raspberry pi
4. Clone the repo with `git clone https://github.com/r00tat/smartmeter_homeassistant_burgenland.git smartmeter`
5. Setup your config in `config.yaml`
6. Install the service with `sudo ln -s "$(pwd)/smartmeter.service" /etc/systemd/system/smartmeter.service && sudo systemctl enable smartmeter && sudo systemctl start smartmeter`

This are the commands to get started:

```bash
git clone https://github.com/r00tat/smartmeter_homeassistant_burgenland.git smartmeter
cd smartmeter
cp smartmeter-config.example.yaml smartmeter-config.yaml
# now edit the config
# if you are on debian make sure you got everything you need:
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo ln -s "$(pwd)/smartmeter.service" /etc/systemd/system/smartmeter.service && sudo systemctl enable smartmeter && sudo systemctl start smartmeter
```

To view the status of the service you can use `sudo systemctl status smartmeter` and to restart it `sudo systemctl restart smartmeter`

To follow the output of the program you can use `tail -f /var/log/daemon.log`.

## Development

Initialize virtual environment:

```bash
uv venv
source .venv/bin/activate
pip3 install -r requirements.txt

```

If you install additional pacakges, save the current installed dependencies to `requirements.txt` with:
`pip freeze -l | grep -v flake8 > requirements.txt`

### Addon Development

Building a version and pushing to docker hub:

```bash
./smartmeter/build_images.sh
```

## useful links

- [Netz Burgenland Zählerbeschreibung](https://www.netzburgenland.at/smart-meter/)
- [Netz Burgenland Kundenschnittstelle](https://www.netzburgenland.at/smart-meter/)
- [Optische Schnittstelle](https://assets.netzburgenland.at/Netz_Burgenland_Beschreibung_Endkundenschnittstelle_02_c72d3973e9.pdf)

### Interface description

#### Sagemcom T210-D (Netz NÖ / EVN)

The Sagemcom T210-D exposes an **M-Bus** customer interface (not DLMS/HDLC).
Frames are pushed roughly every 5 seconds at **2400 baud, 8E1**. Each frame is
an M-Bus long frame (`68 LL LL 68 … CS 16`) that wraps a DLMS/COSEM
data-notification APDU. The APDU is encrypted with **AES-128-GCM**
(DLMS/COSEM Security Suite 0). The 12-byte nonce is the concatenation of
the 8-byte system title and the 4-byte frame counter taken from the
M-Bus header.

Order the M-Bus customer interface via the Netz NÖ portal and request
the AES key. Set `meter_type: noe_evn` in the addon config.

Published OBIS registers: voltages L1–L3, currents L1–L3, active power
+P / −P, cumulative import/export energy, power factor (no phase
angles — the T210-D does not publish them).

Further reading: [Netz NÖ Kundenschnittstelle Lastenheft (PDF)](https://www.netz-noe.at/Download-(1)/Smart-Meter/218_9_SmartMeter_Kundenschnittstelle_Lastenheft2-0.aspx),
[greenMikeEU/SmartMeterEVN](https://github.com/greenMikeEU/SmartMeterEVN).

#### Wiener Netze (Siemens IM150/IM350/IM351, Iskraemeco AM550, Landis+Gyr E450)

Wiener Netze meters push a DLMS/COSEM data-notification **every second** on
the infrared customer interface at **9600 baud, 8N1**, in a single HDLC
frame (`7E A0 …`) with `general-glo-ciphering` (encryption only,
AES-128-GCM without authentication tag) — the same transport as the
Burgenland E450, so the same reader is used.

The decrypted notification carries no OBIS codes, units or scalers, only a
structure in a fixed order: an optional 16-character serial number (not
sent by every meter), the timestamp, then `+A`, `−A`, `+R`, `−R` (Wh/varh)
and `+P`, `−P`, `+Q`, `−Q` (W/var). There are no voltages or currents.

Activate the customer interface and copy the AES key in the
[Wiener Netze Smart Meter portal](https://smartmeter-web.wienernetze.at/),
then set `meter_type: wien`.

Further reading: [Wiener Netze Kundenschnittstelle](https://www.wienernetze.at/smart-meter-kundenschnittstelle),
[bernikr/esphome-wienernetze-smartmeter](https://github.com/bernikr/esphome-wienernetze-smartmeter),
[tofuSCHNITZEL/wiener-netze-smartmeter-serial](https://github.com/tofuSCHNITZEL/wiener-netze-smartmeter-serial).

#### OBIS pipeline: Steiermark, Salzburg, Tirol, H1

These meters name every value by its OBIS code, so they share one
pipeline in `smartmeter/meter/obis/` instead of a reader each:

```text
serial bytes → framing → general-glo-ciphering (AES-128-GCM)
             → data-notification (A-XDR) or DSMR text → OBIS registers
```

- **Salzburg Netz / TINETZ (Kaifa, Honeywell):** wired M-Bus master on RJ12
  pins 3/4, 2400 baud 8E1, push every 5 s. Messages above 250 bytes are
  split into several M-Bus frames; bit 4 of the CI field marks the last
  segment (`CI=00`, then `CI=11`). The payload is
  `DB 08 <system title> <length> <SC> <frame counter> <ciphertext>`;
  register values come with scaler and unit. Activate the interface and
  get the key in the [Salzburg Netz portal](https://portal.salzburgnetz.at/)
  or the TINETZ customer portal.
  Specifications: [Salzburg Netz](https://www.salzburgnetz.at/content/dam/salzburgnetz/dokumente/stromnetz/Technische-Beschreibung-Kundenschnittstelle.pdf),
  [TINETZ](https://www.tinetz.at/uploads/tx_bh/101/tinetz_smart-meter_beschreibung-kundenschnittstelle_001.pdf).
- **Energienetze Steiermark, Landis+Gyr E450:** wired M-Bus on RJ12 pins 3/4
  at 2400 baud, push every 10 s. Community reports show three HDLC frames
  per push carrying DLMS general-block-transfer blocks; the notification
  holds the clock and 16 OBIS/value pairs (energy and power ±A/±R, tariffs
  1 and 2) without scalers. The reader also accepts M-Bus long frames in
  case your meter uses them. Use the GUEK from the
  [Energienetze portal](https://portal.e-netze.at/) as `key`; the GAK is not
  needed.
- **Energienetze Steiermark, Sagemcom:** DSMR 5.0.2 P1 on RJ12 at 115200 baud,
  push every 10 s, encrypted with the GUEK. Use `meter_type:
  steiermark_sagemcom`.
  Specification: [Energienetze Steiermark](https://www.e-netze.at/downloads-data/pdf.aspx?pdf=EN_Update+Kundenschnittstelle+Smart+Meter+%2803_2024%29_WEB_RGB.pdf).
- **Smart Meter 2.0 H1:** the Oesterreichs Energie Companion Standard 2026
  defines H1 as DSMR P1 at 115200 baud, one push per second, encrypted with
  DLMS Security Suite 0 (AES-GCM-128), carrying voltages, currents, ±P, ±Q,
  ±A and ±R. The exact frame format is not public yet, so `h1` accepts
  encrypted DSMR telegrams, plain DSMR telegrams and DLMS notifications
  (raw or in HDLC frames).
  Specification: [OE Companion Standard Smart Meter 2.0](https://oesterreichsenergie.at/fileadmin/user_upload/Oesterreichs_Energie/Publikationsdatenbank/Diverses/2026/OE_Companion_Standard_V1.0.pdf),
  chapter C.6.

Fields a meter does not send (for example L2/L3 on single-phase meters) are
published as `null`, so Home Assistant shows them as unknown.

#### Adding another meter

Everything that is specific to a meter's customer interface lives in its
profile in `smartmeter/meter/profile.py`: serial defaults, push interval,
which reader handles the line, how a decoded telegram becomes a
`MeterData` object, and the Home Assistant metadata and sensors.
`MeterProfile` is the abstract base class; `HdlcDlmsProfile` (DLMS in HDLC
frames, e.g. Burgenland and Wien), `MBusDlmsProfile` (DLMS in M-Bus
frames, Netz NÖ) and `ObisProfile` (the OBIS pipeline)
implement `create_reader`. A meter that sends OBIS codes usually only needs
a new `ObisProfile` instance with the right transports and field list.
A meter with a fixed, OBIS-less layout that reuses one of the other
interfaces needs a new profile instance, a `MeterData` subclass of
`BaseMeterData` and a sensor catalog. Register the name in
`config.yaml` and `config.schema.json` too; a test checks that the lists
match.

#### Landis+Gyr E450

The programm has been tested with the Landis+Gyr E450 Smart Meter, but not with
the wired connection, but with the IR interface. If you order the customer
interface, you can select the optical interface as the desired option.

Source: [Spezifikation Kundenschnittstelle L+G E450](https://assets.netzburgenland.at/Spezifikation_Kundenschnittstelle_E450_korr_2_009418889e.pdf)

##### Datenausgabe und Zeitintervall

Die Datenausgabe und das Zeitintervall sind durch den Netzbetreiber festgelegt. Entsprechend der
vorliegenden Konfiguration des Zählers werden die nachstehen Daten in einem periodischen
Zeitintervall von 5sek ausgegeben:

- Zeitstempel
- Momentanspannung L1
- Momentanspannung L2
- Momentanspannung L3
- Momentanstrom L1
- Momentanstrom L2
- Momentanstrom L3
- Wirkleistung +P
- Wirkleistung –P
- Wirkenergietotal +A
- Wirkenergietotal –A
- Winkel Spannung L1 zu Strom L1
- Winkel Spannung L2 zu Strom L3
- Winkel Spannung L3 zu Strom L3
- Zähleridentifikationsnummern des Netzbetreibers

Verschlüsselung und Authentifizierung

Die Datenausgabe wird mit individuellen kundenbezogenen Schlüsseln verschlüsselt und
authentisiert. Zur Anwendung kommt dabei die dlms/COSEM Security Suite 0, die entsprechend dem
Datenmodel durch die IEC 62056 Normenreihe spezifiziert ist.

#### Spezifikation Kundenschnittstelle KAIFA MA309

The KAIFA interface defines how the IR interface transmission is defined. The format of the message is different in KAIFA dann in Landis+Gyr.

Source: [Optische Schnittstelle](https://assets.netzburgenland.at/Netz_Burgenland_Beschreibung_Endkundenschnittstelle_02_c72d3973e9.pdf)

Als Kundenschnittstelle wird die optische Schnittstelle des Zählers verwendet. Es wird alle
15 Sekunden eine Nachricht dieser optischen Schnittstelle ausgegeben. Der Aufbau sowie
der Inhalt der Nachricht wird in den nachfolgenden Kapiteln beschrieben. Die
Implementierung erfolgt gemäß IDIS CII.

Die Ausgabe der Push-Nachrichten erfolgt auf der optischen Schnittstelle, welche nach
DIN EN 62056-21 ausgeführt ist.

Jede Push-Nachricht enthält die unten angeführten Daten (in dieser Reihenfolge). Das
Push-Intervall beträgt 15 Sekunden. Es werden immer die aktuellsten Daten ausgegeben.

_*Attention*: this format is not for Ladis+Gyr, but for KAIFA_

1. Datum/Uhrzeit,
2. Logical Device Number,
3. +A: Wirkenergie Bezug,
4. –A: Wirkenergie Lieferung,
5. +P: momentane Wirkleistung Bezug,
6. –P: momentane Wirkleistung Lieferung,
7. +R Blindleistung Bezug,
8. –R Blindleistung Lieferung

Jede Push-Nachricht ist mit einem individuellen Schlüssel verschlüsselt. Der Schlüssel kann
aus der Ferne geändert werden. Die Verschlüsselung basiert auf DLMS/COSEM
Security Suite 0 nach HLS5.

Port Einstellungen
Mit einem beliebigen seriellen Terminal Programm, kann der Datenstrom der PushNachrichten aufgezeichnet werden. Nachfolgend sind die Einstellungen angeführt, mit
denen sich die Daten auslesen lassen.

- COM-Port: je nach lokaler Einstellung
- Baud Rate: 9600
- Parity: None
- Data Bits: 8 Bits
- Stop Bits: 1
- Hardware Flow Control: None
- Anzeige der Daten im hexadezimalen Format
