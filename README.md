# Smartmeter Austria für Home Assistant

> **English:** Reads Austrian smart meters (Netz Burgenland, Netz NÖ, Wiener
> Netze, Energienetze Steiermark, Salzburg Netz, TINETZ, Smart Meter 2.0 H1)
> through their customer interface and brings the values into Home Assistant,
> either as a Home Assistant integration (installed via the Marketplace) or as
> a standalone Docker container that publishes via MQTT.
> **[English documentation → README.en.md](README.en.md)**

Liest österreichische Smart Meter über die Kundenschnittstelle aus und bringt
Verbrauch, Einspeisung, Leistung, Spannung und Strom in Home Assistant, auch
ins Energie-Dashboard.

## Unterstützte Zähler

| Netzbetreiber | Zähler | Schnittstelle | Status |
| --- | --- | --- | --- |
| Netz Burgenland | Landis+Gyr E450 | Infrarot (optisch) oder kabelgebunden | getestet |
| Netz NÖ / EVN | Sagemcom T210-D | M-Bus | getestet |
| Wiener Netze | Siemens IM150/IM350/IM351, Iskraemeco AM550, Landis+Gyr E450 | Infrarot | getestet |
| Energienetze Steiermark | Landis+Gyr E450 | M-Bus | nach Spezifikation, ungetestet |
| Energienetze Steiermark | Sagemcom | DSMR P1 | nach Spezifikation, ungetestet |
| Salzburg Netz | Kaifa / Honeywell MA309M | M-Bus | nach Spezifikation, ungetestet |
| TINETZ (Tirol) | Kaifa / Honeywell MA110M / MA309M | M-Bus | nach Spezifikation, ungetestet |
| alle (Smart Meter 2.0) | Kundenschnittstelle H1 | DSMR P1 | nach Spezifikation, ungetestet |

Details zu jedem Zähler, zur Freischaltung und zum Schlüssel:
[docs/zaehler.md](docs/zaehler.md). Du hast einen der ungetesteten Zähler?
[Hilf mit einer Aufzeichnung](docs/zaehler.md#echte-daten-gesucht).

## Was du brauchst

1. **Freigeschaltete Kundenschnittstelle:** Beim Netzbetreiber beantragen und
   den Schlüssel (32 Hex-Zeichen) aus dem Kundenportal holen.
2. **Lesekopf oder Adapter:** einen Infrarot-Lesekopf (USB) für Burgenland und
   Wien, einen M-Bus-Adapter (M-Bus auf USB) oder ein P1-Kabel für die anderen.
3. **Home Assistant.**

## Welcher Weg passt?

| Der Lesekopf hängt … | Weg |
| --- | --- |
| … direkt am Home-Assistant-Gerät | **[Integration über den Marketplace](#integration-über-den-marketplace-empfohlen)** (empfohlen) |
| … an einem anderen Gerät (z.B. Raspberry Pi im Zählerkasten) | **[Standalone Docker-Container](#standalone-docker-container)**, sendet per MQTT |

Weitere Wege (Home-Assistant-Add-on, systemd ohne Docker) beschreibt
[docs/installation.md](docs/installation.md).

### Integration über den Marketplace (empfohlen)

[![Repository im Home Assistant Marketplace öffnen](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=r00tat&repository=smartmeter_homeassistant_burgenland&category=integration)

Liest den Zähler direkt in Home Assistant, ohne MQTT-Broker und ohne Add-on.
Funktioniert mit Home Assistant OS, Container und Core.

1. Auf den Button oben klicken, oder *Einstellungen → Marketplace → Aus Link
   hinzufügen* → `https://github.com/r00tat/smartmeter_homeassistant_burgenland`.
2. *Smartmeter Austria* installieren und Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen →
   Smartmeter Austria*.
4. Netzbetreiber, seriellen Port und Schlüssel eingeben. Die Integration liest
   vor dem Speichern ein Telegramm, ein falscher Schlüssel oder Port fällt also
   sofort auf.

Vor Home Assistant 2026.11 öffnet der Button HACS. Dort das Repository unter
*HACS → ⋮ → Benutzerdefinierte Repositories* (Kategorie *Integration*)
hinzufügen.

Du nutzt bisher das Add-on? Die Integration übernimmt dessen Sensoren samt
Verlauf und Statistik: [docs/umstieg.md](docs/umstieg.md).

### Standalone Docker-Container

Für einen Lesekopf an einem anderen Gerät als Home Assistant. Der Container
liest den Zähler und sendet die Werte per MQTT an Home Assistant, die Sensoren
erscheinen dort automatisch.

Voraussetzung: ein MQTT-Broker (z.B. das Add-on *Mosquitto broker*) und die
MQTT-Integration in Home Assistant.

1. `smartmeter-config.yaml` anlegen:

   ```yaml
   meter_type: burgenland        # siehe docs/zaehler.md
   interface_type: OPTICAL
   mqtt:
     host: homeassistant.local   # Adresse des MQTT-Brokers
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

3. Starten: `docker compose up -d`, Logs: `docker compose logs -f`.

Alle Optionen (TLS, Intervall, serielle Einstellungen) stehen in
[docs/installation.md](docs/installation.md#standalone-docker-container).

## Weitere Dokumentation

- [Installation im Detail](docs/installation.md): Integration, Docker, Add-on, systemd
- [Zähler und Netzbetreiber](docs/zaehler.md): Freischaltung, Schlüssel, technische Details
- [Umstieg vom Add-on auf die Integration](docs/umstieg.md)
- [Fehlerbehebung](docs/fehlerbehebung.md): Fehlermeldungen, Debug-Logs, Verhalten bei Ausfällen
- [Entwicklung](docs/entwicklung.md): Architektur, lokale Testumgebung, neuen Zähler hinzufügen
- [Python-Library `smartmeter-austria`](packages/smartmeter-austria/README.md): der Zähler-Code für eigene Projekte, auf [PyPI](https://pypi.org/project/smartmeter-austria/)

Fragen und Fehler: [GitHub Issues](https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues)
