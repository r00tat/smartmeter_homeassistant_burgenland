# Smart Meter Reader Burgenland – AT

Dieses Python-Programm verbindet deinen österreichischen Smart Meter über
MQTT mit Home Assistant. Es liest die Kundenschnittstelle des Zählers aus,
entschlüsselt die Daten und veröffentlicht die Messwerte (Spannung, Strom,
Wirkleistung, Energie usw.) als Sensoren in Home Assistant.

Getestet wurde es auf einem Raspberry Pi Zero 2 W als eigenständiges Gerät
sowie auf einem Raspberry Pi 4 als Home-Assistant-Add-on. Als Lesekopf eignet
sich z. B. ein [Weidmann Elektronik IR Schreib-/Lesekopf](https://shop.weidmann-elektronik.de/index.php?page=product&info=24).

## Was du auswählen musst

Vor der Inbetriebnahme legst du über zwei Optionen fest, welcher Zähler und
welche Schnittstelle verwendet werden.

### 1. Netzbetreiber / Zähler (`meter_type`)

| `meter_type` | Netzbetreiber | Region | Zähler | Baudrate |
| --- | --- | --- | --- | --- |
| `burgenland` *(Standard)* | Netz Burgenland | Burgenland (BGLD) | Landis+Gyr E450 | 9600 |
| `noe_evn` | Netz Niederösterreich / EVN | Niederösterreich (NÖ) | Sagemcom T210-D | 2400 (8E1) |

Die Baudrate und die Geräte-Metadaten (Hersteller/Modell) werden automatisch
passend zum gewählten `meter_type` gesetzt – du musst sie normalerweise nicht
selbst angeben.

### 2. Art der Schnittstelle (`interface_type`)

| `interface_type` | Beschreibung | Wann verwenden |
| --- | --- | --- |
| `OPTICAL` *(Standard)* | **Optische (IR-)Schnittstelle.** Daten werden mit einem IR-Schreib-/Lesekopf abgegriffen. | Wenn du beim Netzbetreiber die optische Schnittstelle freischalten lässt (häufigster Fall). |
| `PHYSICAL` | **Physische (verkabelte) Schnittstelle.** Daten werden direkt über die kabelgebundene Kundenschnittstelle gelesen (HDLC-Rahmen). | Wenn dein Zähler eine kabelgebundene Datenschnittstelle bereitstellt. |

> **Tipp:** Bei der Bestellung der Kundenschnittstelle gibst du an, ob du die
> optische (IR) oder die physische Variante möchtest. Wähle `interface_type`
> entsprechend.

In allen Fällen brauchst du vom Netzbetreiber den **individuellen AES-Schlüssel**
(`dlms.key`), mit dem die Daten entschlüsselt werden.

---

## Quick Start

Wähle einen der drei Betriebsmodi. Alle Wege haben dieselben Vorbedingungen:

**Vorbereitung (für alle Varianten):**

1. [Freischaltung der Kundenschnittstelle beantragen](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/kundenschnittstelle.html)
   (bei Netz NÖ über das Netz-NÖ-Portal) und als Übertragung die optische
   (IR) bzw. physische Schnittstelle wählen.
2. Den **AES-Schlüssel** vom Netzbetreiber besorgen (Kundenportal).
3. Den Lesekopf am Smart Meter und am Host (Raspberry Pi o. Ä.) anschließen.

### Variante A: Home-Assistant-Add-on (empfohlen)

Für den Betrieb direkt auf einem Home-Assistant-Gerät (z. B. Raspberry Pi):

1. In Home Assistant: **Einstellungen → Add-ons → Add-on Store** öffnen.
2. `Mosquitto broker` installieren und starten (richtet den MQTT-Server ein).
3. Unter **Einstellungen → Geräte & Dienste** die **Mosquitto-MQTT**-Integration
   hinzufügen.
4. Zurück im Add-on Store oben rechts auf die drei Punkte → **Repositories**
   klicken und folgendes Repository hinzufügen:
   `https://github.com/r00tat/smartmeter_homeassistant_burgenland`
5. Seite neu laden und das **Smartmeter Burgenland MQTT**-Add-on installieren.
6. Im Add-on die Konfiguration setzen (siehe [Konfiguration](#konfiguration)):
   - `meter_type` und `interface_type` passend zu deinem Zähler.
   - Unter `mqtt`: als `host` die Home-Assistant-Adresse, als `user`/`password`
     einen Home-Assistant-Benutzer (oder im Mosquitto broker hinterlegte
     Zugangsdaten).
   - Unter `dlms`: den `port` (Geräteknoten des Lesekopfs) und den `key`
     (AES-Schlüssel).
7. Das Add-on starten.

### Variante B: Standalone mit Docker

Das Add-on-Image benötigt den Home Assistant Supervisor und läuft nicht auf
einem normalen Docker-Host. Dafür gibt es ein separates Standalone-Image
(Multi-Arch, amd64/arm64,
[#101](https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues/101)):

```text
docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone
```

1. Beispielkonfiguration kopieren und anpassen:

   ```bash
   cd smartmeter/
   cp smartmeter-config.example.yaml smartmeter-config.yaml
   # smartmeter-config.yaml bearbeiten: meter_type, interface_type,
   # mqtt.host, dlms.key, dlms.port, …
   ```

2. Mit Docker Compose starten (aus dem Verzeichnis `smartmeter/`):

   ```bash
   docker compose -f docker-compose.standalone.yml up -d
   ```

   Oder direkt mit `docker run` (ebenfalls aus `smartmeter/`):

   ```bash
   docker run -d --restart unless-stopped \
     --device /dev/ttyUSB0:/dev/ttyUSB0 \
     -v "$(pwd)/smartmeter-config.yaml:/config/smartmeter-config.yaml:ro" \
     docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone:latest
   ```

   Passe `/dev/ttyUSB0` an, falls dein Lesekopf an einem anderen Geräteknoten
   hängt.

### Variante C: Standalone mit systemd / uv

Für einen eigenständigen Raspberry Pi ohne Home Assistant bzw. Docker:

```bash
git clone https://github.com/r00tat/smartmeter_homeassistant_burgenland.git smartmeter
cd smartmeter
cp smartmeter-config.example.yaml smartmeter-config.yaml
# jetzt smartmeter-config.yaml bearbeiten (meter_type, interface_type, mqtt, dlms)

# uv installieren (z. B. unter Debian), falls noch nicht vorhanden:
curl -LsSf https://astral.sh/uv/install.sh | sh

# systemd-Service einrichten und starten:
sudo ln -s "$(pwd)/smartmeter.service" /etc/systemd/system/smartmeter.service \
  && sudo systemctl enable smartmeter \
  && sudo systemctl start smartmeter
```

Service verwalten:

- Status anzeigen: `sudo systemctl status smartmeter`
- Neu starten: `sudo systemctl restart smartmeter`
- Ausgabe verfolgen: `tail -f /var/log/daemon.log`

---

## Konfiguration

Alle Varianten verwenden dieselben Optionen (im Add-on über die UI, sonst in
`smartmeter-config.yaml`). Vorlage: `smartmeter/smartmeter-config.example.yaml`.

```yaml
logging: INFO            # INFO | WARNING | ERROR | CRITICAL | DEBUG
meter_type: burgenland   # burgenland | noe_evn  (siehe oben)
interface_type: OPTICAL  # OPTICAL | PHYSICAL    (siehe oben)

mqtt:
  host: "homeassistant.local"  # Adresse des MQTT-Brokers
  # port: 1883                 # bei TLS i. d. R. 8883
  user: ""
  password: ""
  # device_id: "smartmeter"
  # name: "Smart Meter"
  # prefix: ""
  # publish_interval: 30       # Veröffentlichungsintervall in Sekunden

dlms:
  port: "/dev/ttyUSB0"         # Geräteknoten des Lesekopfs
  key: "012345678901234567890123456789ab"  # AES-Schlüssel (32 Hex-Zeichen)
  # baudrate: 9600             # Standard ergibt sich aus meter_type
  # bytesize: 8
  # parity: "NONE"
  # stopbits: 1
```

### Veröffentlichte Sensoren

- **`burgenland`** (Landis+Gyr E450): Spannungen L1–L3, Ströme L1–L3,
  Wirkleistung +P/−P, Wirkenergie +A/−A sowie Phasenwinkel.
- **`noe_evn`** (Sagemcom T210-D): Spannungen L1–L3, Ströme L1–L3,
  Wirkleistung +P/−P, Wirkenergie Import/Export und Leistungsfaktor.
  Phasenwinkel-Sensoren entfallen, da der T210-D diese nicht ausgibt.

### MQTT über TLS (optional)

TLS ist standardmäßig deaktiviert. Zum Verbinden mit einem TLS-Broker unter
`mqtt` `tls: true` setzen und `port` anpassen (TLS-Broker nutzen meist `8883`).
Wirksam nur bei `tls: true`:

- `tls_ca`: Pfad zu einem CA-Zertifikat (PEM). Leer = System-CA-Store.
- `tls_cert` / `tls_key`: Client-Zertifikat und -Schlüssel für mutual TLS.
- `tls_insecure: true`: Host-/Zertifikatsprüfung überspringen (nur zum Testen).

Zertifikatspfade müssen aus dem Add-on-Container lesbar sein (z. B. via
`share:ro` oder `config:ro` gemountet).

---

## Technische Details

### Schnittstellenbeschreibung

#### Landis+Gyr E450 (Netz Burgenland)

Getestet wurde der Landis+Gyr E450 über die **optische (IR-)Schnittstelle**
(nicht über die kabelgebundene Verbindung). Bei der Bestellung der
Kundenschnittstelle kann die optische Schnittstelle als gewünschte Option
gewählt werden.

Quelle: [Spezifikation Kundenschnittstelle L+G E450](https://assets.netzburgenland.at/Spezifikation_Kundenschnittstelle_E450_korr_2_009418889e.pdf)

##### Datenausgabe und Zeitintervall

Die Datenausgabe und das Zeitintervall sind durch den Netzbetreiber festgelegt.
Entsprechend der vorliegenden Konfiguration des Zählers werden die nachstehenden
Daten in einem periodischen Zeitintervall von 5 Sekunden ausgegeben:

- Zeitstempel
- Momentanspannung L1, L2, L3
- Momentanstrom L1, L2, L3
- Wirkleistung +P
- Wirkleistung –P
- Wirkenergietotal +A
- Wirkenergietotal –A
- Winkel Spannung L1 zu Strom L1
- Winkel Spannung L2 zu Strom L2
- Winkel Spannung L3 zu Strom L3
- Zähleridentifikationsnummern des Netzbetreibers

Die Datenausgabe wird mit individuellen kundenbezogenen Schlüsseln verschlüsselt
und authentisiert. Zur Anwendung kommt die DLMS/COSEM Security Suite 0, die
entsprechend dem Datenmodell durch die IEC-62056-Normenreihe spezifiziert ist.

#### KAIFA MA309 (optische Schnittstelle, Netz Burgenland)

Die KAIFA-Schnittstelle definiert die Übertragung über die optische
Schnittstelle. Der Aufbau der Nachricht unterscheidet sich von jenem bei
Landis+Gyr. Als Kundenschnittstelle wird die optische Schnittstelle des Zählers
verwendet; alle 15 Sekunden wird eine Nachricht ausgegeben. Die Implementierung
erfolgt gemäß IDIS CII, die Ausgabe der Push-Nachrichten auf der optischen
Schnittstelle nach DIN EN 62056-21.

Quelle: [Optische Schnittstelle](https://assets.netzburgenland.at/Netz_Burgenland_Beschreibung_Endkundenschnittstelle_02_c72d3973e9.pdf)

Jede Push-Nachricht enthält die folgenden Daten (in dieser Reihenfolge), das
Push-Intervall beträgt 15 Sekunden:

1. Datum/Uhrzeit
2. Logical Device Number
3. +A: Wirkenergie Bezug
4. –A: Wirkenergie Lieferung
5. +P: momentane Wirkleistung Bezug
6. –P: momentane Wirkleistung Lieferung
7. +R: Blindleistung Bezug
8. –R: Blindleistung Lieferung

> **Achtung:** Dieses Format gilt für KAIFA, **nicht** für Landis+Gyr.

Jede Push-Nachricht ist mit einem individuellen Schlüssel verschlüsselt (aus
der Ferne änderbar). Die Verschlüsselung basiert auf DLMS/COSEM Security Suite 0
nach HLS5.

**Port-Einstellungen** (z. B. zum Mitschneiden mit einem seriellen Terminal):

- COM-Port: je nach lokaler Einstellung
- Baudrate: 9600
- Parity: None
- Data Bits: 8
- Stop Bits: 1
- Hardware Flow Control: None
- Anzeige der Daten im hexadezimalen Format

#### Sagemcom T210-D (Netz NÖ / EVN)

Der Sagemcom T210-D stellt eine **M-Bus-Kundenschnittstelle** bereit (kein
DLMS/HDLC). Rahmen werden ca. alle 5 Sekunden bei **2400 Baud, 8E1**
ausgegeben. Jeder Rahmen ist ein M-Bus-Long-Frame (`68 LL LL 68 … CS 16`), der
eine DLMS/COSEM-Data-Notification-APDU kapselt. Die APDU ist mit **AES-128-GCM**
verschlüsselt (DLMS/COSEM Security Suite 0). Der 12-Byte-Nonce ist die
Verkettung aus 8-Byte-System-Title und 4-Byte-Frame-Counter aus dem M-Bus-Header.

Die M-Bus-Kundenschnittstelle wird über das Netz-NÖ-Portal bestellt und der
AES-Schlüssel dort angefordert. In der Konfiguration `meter_type: noe_evn`
setzen.

Veröffentlichte OBIS-Register: Spannungen L1–L3, Ströme L1–L3, Wirkleistung
+P/−P, kumulierte Import-/Export-Energie und Leistungsfaktor (keine
Phasenwinkel – der T210-D gibt diese nicht aus).

Weiterführend: [Netz NÖ Kundenschnittstelle Lastenheft (PDF)](https://www.netz-noe.at/Download-(1)/Smart-Meter/218_9_SmartMeter_Kundenschnittstelle_Lastenheft2-0.aspx),
[greenMikeEU/SmartMeterEVN](https://github.com/greenMikeEU/SmartMeterEVN).

---

## Entwicklung

Virtuelle Umgebung initialisieren:

```bash
uv venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

Wenn du zusätzliche Pakete installierst, die aktuell installierten
Abhängigkeiten in `requirements.txt` speichern:

```bash
pip freeze -l | grep -v flake8 > requirements.txt
```

### Add-on-Entwicklung

Image bauen und nach Docker Hub pushen:

```bash
./smartmeter/build_images.sh
```

---

## Nützliche Links

- [Netz Burgenland – Smart Meter](https://www.netzburgenland.at/smart-meter/)
- [Netz Burgenland – Kundenschnittstelle](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/kundenschnittstelle.html)
- [Optische Schnittstelle (Beschreibung Endkundenschnittstelle, PDF)](https://assets.netzburgenland.at/Netz_Burgenland_Beschreibung_Endkundenschnittstelle_02_c72d3973e9.pdf)
- [Spezifikation Kundenschnittstelle L+G E450 (PDF)](https://assets.netzburgenland.at/Spezifikation_Kundenschnittstelle_E450_korr_2_009418889e.pdf)
- [Netz NÖ – Kundenschnittstelle Lastenheft (PDF)](https://www.netz-noe.at/Download-(1)/Smart-Meter/218_9_SmartMeter_Kundenschnittstelle_Lastenheft2-0.aspx)
