# Installation

[English version](en/installation.md) · [Zurück zum README](../README.md)

Für jeden Zähler gibt es genau einen Leser: entweder die Integration, das
Add-on oder den Standalone-Container. Zwei Leser am selben Port zerstören
sich gegenseitig die Telegramme.

| Weg | Wann | MQTT nötig |
| --- | --- | --- |
| [Integration (Marketplace)](#integration-marketplace) | Lesekopf hängt am Home-Assistant-Gerät, **empfohlen** | nein |
| [Standalone Docker-Container](#standalone-docker-container) | Lesekopf hängt an einem anderen Gerät | ja |
| [Home-Assistant-Add-on](#home-assistant-add-on) | Lesekopf am Home-Assistant-Gerät, bestehende Installationen | ja |
| [systemd ohne Docker](#systemd-ohne-docker) | anderes Gerät ohne Docker | ja |

Vorab bei allen Wegen: Kundenschnittstelle beim Netzbetreiber freischalten
lassen und den Schlüssel holen, siehe [zaehler.md](zaehler.md).

Getestet wurde mit einem Raspberry Pi Zero 2 W (standalone), einem Raspberry
Pi 4 (Add-on) und dem
[IR-Schreib/Lesekopf von Weidmann Elektronik](https://shop.weidmann-elektronik.de/index.php?page=product&info=24).

## Integration (Marketplace)

[![Repository im Home Assistant Marketplace öffnen](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=r00tat&repository=smartmeter_homeassistant_burgenland&category=integration)

Die Integration liest den Zähler direkt in Home Assistant. Sie braucht keinen
MQTT-Broker und kein Add-on und läuft auch mit Home Assistant Container und
Core (ohne Supervisor).

### Installieren

1. Auf den Button oben klicken, oder *Einstellungen → Marketplace → Aus Link
   hinzufügen* → `https://github.com/r00tat/smartmeter_homeassistant_burgenland`.
   Der Marketplace ist seit Home Assistant 2026.11 eingebaut und ersetzt HACS.
   Auf älteren Versionen öffnet der Button HACS; dort *HACS → ⋮ →
   Benutzerdefinierte Repositories*, Kategorie *Integration*.
2. *Smartmeter Austria* installieren und Home Assistant neu starten.

Marketplace und HACS installieren die Integration aus der Datei
`smartmeter_at.zip` eines Releases.

### Einrichten

*Einstellungen → Geräte & Dienste → Integration hinzufügen → Smartmeter
Austria*.

| Feld | Bedeutung |
| --- | --- |
| Netzbetreiber / Zähler | Zählertyp, siehe [zaehler.md](zaehler.md) |
| Serieller Port | Port des Lesekopfs oder Adapters, am besten unter `/dev/serial/by-id/` |
| Schlüssel der Kundenschnittstelle | 32 Hex-Zeichen vom Netzbetreiber, Leerzeichen werden ignoriert |
| Schnittstelle | Optisch (IR) oder kabelgebunden, nur für Burgenland und Wien |

Vor dem Speichern liest die Integration ein Telegramm (bis zu 30 Sekunden).
Ein falscher Schlüssel, Port oder Zählertyp zeigt sich so sofort als Fehler.

Unter *Konfigurieren* stellst du das Aktualisierungsintervall ein (Standard
10 s): Höchstens so oft wird ein neuer Wert übernommen. Die seriellen
Einstellungen kommen aus dem Zählertyp und lassen sich hier nicht ändern.

### Sensoren

Pro Zähler entsteht ein Gerät, mit der Seriennummer, wenn der Zähler sie
sendet. Je nach Zähler gibt es Energie Bezug und Einspeisung (fürs
Energie-Dashboard), Wirkleistung sowie Spannung und Strom pro Phase. Für
Burgenland und Wien sind einige selten gebrauchte Sensoren standardmäßig
deaktiviert; sie lassen sich auf der Geräteseite aktivieren.

### Manuell installieren

Die Integration ist nur das Verzeichnis `custom_components/smartmeter_at/`;
den Zähler-Code installiert Home Assistant als Python-Paket
[`smartmeter-austria`](https://pypi.org/project/smartmeter-austria/) von PyPI.

- `smartmeter_at.zip` aus einem
  [Release](https://github.com/r00tat/smartmeter_homeassistant_burgenland/releases)
  nach `/config/custom_components/smartmeter_at/` entpacken, oder
- das Repository klonen und verlinken, siehe [entwicklung.md](entwicklung.md#auf-einem-echten-home-assistant).

Nach Installation und Update Home Assistant neu starten.

## Standalone Docker-Container

Für einen Lesekopf an einem anderen Gerät als Home Assistant, z.B. einem
Raspberry Pi beim Zählerkasten. Der Container liest den Zähler und sendet die
Werte per MQTT; Home Assistant legt die Sensoren über MQTT-Discovery
automatisch an. Das Image läuft ohne Home Assistant Supervisor auf jedem
Docker-Host (amd64 und arm64):

```text
docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone
```

### Voraussetzungen

- Ein MQTT-Broker, z.B. das Add-on *Mosquitto broker* in Home Assistant, und
  die MQTT-Integration in Home Assistant.
- Docker mit Compose auf dem Gerät mit dem Lesekopf.

### Einrichten

1. Konfiguration `smartmeter-config.yaml` anlegen (Optionen siehe
   [unten](#konfiguration-container-und-systemd)):

   ```yaml
   meter_type: burgenland
   interface_type: OPTICAL
   mqtt:
     host: homeassistant.local
     user: "mqtt-benutzer"
     password: "geheim"
   dlms:
     port: /dev/ttyUSB0
     key: "0123456789ABCDEF0123456789ABCDEF"
   ```

2. `docker-compose.yml` daneben anlegen:

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

   Hängt der Lesekopf an einem anderen Gerät (`/dev/ttyUSB1`,
   `/dev/ttyAMA0`, …), den Pfad in `devices` und in `dlms.port` anpassen.

3. Starten mit `docker compose up -d`. Die Logs zeigt `docker compose logs -f`.

Ohne Compose:

```bash
docker run -d --restart unless-stopped \
  --device /dev/ttyUSB0:/dev/ttyUSB0 \
  -v "$(pwd)/smartmeter-config.yaml:/config/smartmeter-config.yaml:ro" \
  docker.io/paulwoelfel/smartmeter_homeassistant_burgenland_standalone:latest
```

Liegt die Konfiguration an einem anderen Pfad im Container, zeigt die
Umgebungsvariable `SMARTMETER_CONFIG` darauf. Das Repository enthält
dieselben Dateien als Vorlage: `smartmeter/docker-compose.standalone.yml` und
`smartmeter/smartmeter-config.example.yaml`.

### Konfiguration (Container und systemd)

| Option | Standard | Bedeutung |
| --- | --- | --- |
| `meter_type` | `burgenland` | Zählertyp, siehe [zaehler.md](zaehler.md) |
| `interface_type` | `OPTICAL` | `OPTICAL` (IR) oder `PHYSICAL` (kabelgebunden), nur Burgenland und Wien |
| `logging` | `INFO` | `DEBUG` zeigt jedes Telegramm |
| `mqtt.host` | – | Adresse des MQTT-Brokers (Pflicht) |
| `mqtt.port` | `1883` | Port des Brokers |
| `mqtt.user`, `mqtt.password` | – | Zugangsdaten |
| `mqtt.publish_interval` | `30` | Sekunden zwischen zwei Werten |
| `mqtt.device_id` | `smartmeter` | MQTT-Topic und Geräte-ID |
| `mqtt.name` | `Smart Meter` | Gerätename in Home Assistant |
| `mqtt.prefix` | – | Präfix vor allen Topics |
| `mqtt.tls` | `false` | TLS einschalten, siehe unten |
| `dlms.port` | `/dev/ttyUSB0` | serieller Port |
| `dlms.key` | – | Schlüssel, 32 Hex-Zeichen (Pflicht) |
| `dlms.baudrate`, `bytesize`, `parity`, `stopbits` | vom Zählertyp | nur zum Überschreiben setzen |
| `dlms.hdlc_frame_size` | `120` | Mindestlänge eines Telegramms bei `PHYSICAL` |

**MQTT über TLS:** `mqtt.tls: true` setzen und meist `mqtt.port: 8883`. Ohne
`tls_ca` gilt der System-CA-Speicher. `tls_ca` (CA-Zertifikat), `tls_cert` und
`tls_key` (Client-Zertifikat für mTLS) sind Pfade im Container;
`tls_insecure: true` schaltet die Prüfung des Zertifikats ab (nur zum Testen).
Die TLS-Optionen wirken nur bei `tls: true`.

## Home-Assistant-Add-on

Das Add-on liest den Zähler auf dem Home-Assistant-Gerät und sendet per MQTT.
Für neue Installationen ist die [Integration](#integration-marketplace)
einfacher; bestehende Add-on-Nutzer können
[umsteigen](umstieg.md). Das Add-on braucht Home Assistant OS oder
Supervised.

1. *Einstellungen → Add-ons → Add-on Store*: *Mosquitto broker* installieren
   und starten, danach die MQTT-Integration einrichten.
2. Im Add-on Store *⋮ → Repositories* öffnen und
   `https://github.com/r00tat/smartmeter_homeassistant_burgenland` hinzufügen,
   dann die Seite neu laden.
3. *Smartmeter Burgenland MQTT* installieren.
4. Im Tab *Konfiguration* Zählertyp, Port und Schlüssel eintragen. Als MQTT-Host
   die Adresse von Home Assistant, als Benutzer einen Home-Assistant-Benutzer
   oder Zugangsdaten aus dem Mosquitto-Add-on. Die Optionen entsprechen der
   [Tabelle oben](#konfiguration-container-und-systemd).
5. Add-on starten.

Zertifikate für TLS legst du unter `/share` oder `/config` ab, beide Ordner
sind im Add-on lesbar eingebunden.

## systemd ohne Docker

Für ein Gerät ohne Docker, z.B. einen Raspberry Pi mit Raspberry Pi OS.
Benötigt [uv](https://docs.astral.sh/uv/).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/r00tat/smartmeter_homeassistant_burgenland.git
cd smartmeter_homeassistant_burgenland/smartmeter
cp smartmeter-config.example.yaml smartmeter-config.yaml
# smartmeter-config.yaml bearbeiten (Optionen wie oben)
sudo ln -s "$(pwd)/smartmeter.service" /etc/systemd/system/smartmeter.service
sudo systemctl enable --now smartmeter
```

`smartmeter.service` erwartet das Repository unter
`/home/pi/smartmeter_homeassistant_burgenland` und den Benutzer `pi`; bei
anderen Pfaden die Datei vorher anpassen. Status:
`sudo systemctl status smartmeter`, Logs: `journalctl -u smartmeter -f`.

`smartmeter.sh` installiert bei jedem Start die Abhängigkeiten und die
Library `smartmeter-austria` direkt aus `smartmeter/smartmeter-austria/` des Repositorys
(editierbar, nicht von PyPI). Aktualisieren heißt daher nur
`git pull && sudo systemctl restart smartmeter`; es läuft immer genau der
ausgecheckte Stand.
