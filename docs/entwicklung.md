# Entwicklung

[English version](en/development.md) · [Zurück zum README](../README.md)

## Aufbau des Repositorys

| Pfad | Inhalt |
| --- | --- |
| `smartmeter/meter/` | Kern: serieller Transport, Leser pro Zählertyp, Supervisor, MQTT |
| `smartmeter/` | Add-on und Standalone-Image (Dockerfiles, `config.yaml`, Tests in `tests/`) |
| `custom_components/smartmeter_at/` | Home-Assistant-Integration, Tests in `tests_integration/` |
| `docs/` | Dokumentation (Deutsch, englisch unter `docs/en/`) |

Die Integration hat keine eigene Kopie des Kerns: `meter/` und
`fix_source_encoding.py` sind Symlinks nach `smartmeter/`.

## Architektur

Add-on und Integration teilen sich den Kern. Alles läuft auf einer
asyncio-Event-Loop, ohne Threads:

```text
serieller Port ──(pyserial-asyncio-fast)──> reader.run() ──Callback──> Supervisor
                                                                      │
                Add-on: SmartMeterDevice (aiomqtt) <── on_data ───────┤
         Integration: SmartMeterCoordinator        <── on_error ──────┘
```

- `meter/serial/transport.py` öffnet den Port in einem Executor und liefert
  Bytes, sobald sie ankommen. Leser warten auf Daten statt mit Timeouts
  abzufragen; ein abgesteckter Adapter beendet den Datenstrom sofort mit
  einem Fehler.
- Ein Leser (`MeterReaderLike`) hat eine Methode, `async run()`: Er liest, bis
  er abgebrochen wird, und wirft bei jedem Fehler. Leser versuchen nie selbst
  neu.
- `meter/supervisor.py` (`ReaderSupervisor`) ist die einzige Stelle für
  Wiederherstellung: Er ersetzt einen fehlgeschlagenen Leser nach einer Pause,
  meldet einen stillen Zähler (`stale_after`) und öffnet den Port neu, wenn er
  still bleibt (`restart_after`). Ihn abzubrechen stoppt den Leser und
  schließt den Port.
- Das Parsen (gurux, etwa 1–2 ms pro Telegramm) läuft auf der Loop; bei einem
  Telegramm alle 1–5 Sekunden ist das weit unter 1 % der Loop-Zeit.

## Tests

Die Tests brauchen weder Hardware noch einen Broker: ein geskripteter Port
(`smartmeter/tests/fake_port.py`), ein kleiner MQTT-Broker
(`smartmeter/tests/fake_broker.py`) und Pseudo-Terminals für den echten
seriellen Transport.

Add-on und Kern (Python 3.15):

```bash
cd smartmeter
uv venv && source .venv/bin/activate
uv pip install -r requirements-dev.txt
python3 fix_source_encoding.py gurux_dlms gurux_common
ruff check && pytest tests
cd .. && mypy --config-file mypy.ini
```

Integration (Python-Version aus `tests_integration/.python-version`):

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements-ha-test.txt ruff
python3 smartmeter/fix_source_encoding.py gurux_dlms gurux_common
ruff check custom_components tests_integration && pytest tests_integration
```

## Integration lokal testen

Immer mit dem ganzen Repository arbeiten: Wer nur
`custom_components/smartmeter_at/` kopiert, hat kaputte Symlinks. Entweder das
Verzeichnis aus einem Klon verlinken oder beim Kopieren die Links auflösen (wie
die Release-Zip).

**Testinstanz in Docker:** `./dev.sh` spiegelt die Integration (Links
aufgelöst) nach `config/` und startet Home Assistant im Container
`smartmeter-ha-dev` auf <http://localhost:8124>. Nach einer Änderung erneut
ausführen, um zu synchronisieren und neu zu starten. `HTTP_PORT` ändert den
Port, `--recreate` erzeugt den Container neu, `--no-logs` lässt ihn im
Hintergrund laufen. Auf einem Linux-Host reicht
`SERIAL_DEVICE=/dev/ttyUSB0 ./dev.sh` den Lesekopf durch; Docker Desktop auf
macOS/Windows kann keine USB-Seriell-Geräte durchreichen.

### Auf einem echten Home Assistant

Das Repository nach `/config` klonen (z.B. mit dem Add-on *Terminal & SSH*)
und die Integration nach `custom_components` verlinken. Aktualisieren ist dann
ein `git pull`:

```bash
cd /config
git clone https://github.com/r00tat/smartmeter_homeassistant_burgenland.git smartmeter-src
# Branch testen, der noch nicht veröffentlicht ist:
# git clone -b <branch> https://github.com/r00tat/smartmeter_homeassistant_burgenland.git smartmeter-src
mkdir -p /config/custom_components
rm -rf /config/custom_components/smartmeter_at
ln -s ../smartmeter-src/custom_components/smartmeter_at /config/custom_components/smartmeter_at
```

Home Assistant neu starten und die Integration hinzufügen. Aktualisieren mit
`cd /config/smartmeter-src && git pull` und danach Home Assistant neu starten;
die Integration nur neu zu laden reicht nicht, weil Python den alten Code
geladen hält. Branches wechseln geht genauso mit `git checkout <branch>`.

Hinweise zum Symlink:

- Den Klon in `/config` lassen und den Link relativ setzen. Home Assistant OS
  und Container sehen nur `/config`; ein Link nach außen oder ein absoluter
  Host-Pfad ist im Container kaputt.
- Nicht gleichzeitig über den Marketplace installieren, beide nutzen
  `custom_components/smartmeter_at`. Vor dem Wechsel zum Marketplace den Link
  entfernen.
- Der Klon landet in den Home-Assistant-Backups. Ausschließen oder entfernen,
  wenn er nicht mehr gebraucht wird.

Ohne `git` auf dem Home-Assistant-Host das Verzeichnis mit aufgelösten Links
kopieren, z.B. `cp -rL`, oder von einem anderen Rechner
`rsync -aL --delete --exclude __pycache__ custom_components/smartmeter_at/ root@homeassistant.local:/config/custom_components/smartmeter_at/`
(das SSH-Add-on braucht `rsync`; `scp -r` folgt Links ebenfalls).

## Add-on-Images bauen

```bash
cd smartmeter
DOCKERHUB_USER=… DOCKERHUB_PASSWORD=… ./build_images.sh
```

baut die Add-on-Images für alle Architekturen mit dem Home-Assistant-Builder
und lädt sie auf Docker Hub hoch. Die Version kommt aus `config.yaml`.

## Einen neuen Zähler hinzufügen

Alles, was die Kundenschnittstelle eines Zählers ausmacht, steht in seinem
Profil in `smartmeter/meter/profile.py`: serielle Einstellungen,
Sendeintervall, welcher Leser die Leitung verarbeitet, wie aus einem
Telegramm ein `MeterData`-Objekt wird, sowie Gerätedaten und Sensoren für Home
Assistant.

- `MeterProfile` ist die abstrakte Basisklasse. `HdlcDlmsProfile` (DLMS in
  HDLC-Frames, Burgenland und Wien), `MBusDlmsProfile` (DLMS in M-Bus-Frames,
  Netz NÖ) und `ObisProfile` (die OBIS-Verarbeitung) implementieren
  `create_reader`, das einen Leser mit `async run()` zurückgibt.
- Ein Zähler mit OBIS-Codes braucht meist nur eine neue `ObisProfile`-Instanz
  mit den passenden Transporten und Feldern.
- Ein Zähler mit festem Aufbau ohne OBIS-Codes, der eine bestehende
  Schnittstelle nutzt, braucht eine neue Profil-Instanz, eine
  `MeterData`-Unterklasse von `BaseMeterData` und einen Sensorkatalog.
- Den Namen auch in `smartmeter/config.yaml` und
  `smartmeter/config.schema.json` eintragen; ein Test prüft, dass die Listen
  übereinstimmen.

Technische Details zu den bestehenden Zählern: [zaehler.md](zaehler.md).
