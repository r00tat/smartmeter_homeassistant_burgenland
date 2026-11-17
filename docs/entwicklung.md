# Entwicklung

[English version](en/development.md) · [Zurück zum README](../README.md)

## Aufbau des Repositorys

| Pfad | Inhalt |
| --- | --- |
| `smartmeter/smartmeter-austria/` | Library [`smartmeter-austria`](https://pypi.org/project/smartmeter-austria/) (Import `smartmeter_austria`): serieller Transport, Leser pro Zählertyp, Supervisor; Tests in `tests/` |
| `smartmeter/` | Add-on und Standalone-Image: MQTT-Bridge in `meter/`, Dockerfiles, `config.yaml`, Tests in `tests/` |
| `custom_components/smartmeter_at/` | Home-Assistant-Integration, Tests in `tests_integration/` |
| `docs/` | Dokumentation (Deutsch, englisch unter `docs/en/`) |

Wie von Home Assistant
[empfohlen](https://contributors.home-assistant.io/core/integrations/api-library/) enthält
die Integration keinen Protokoll-Code: Sie installiert die Library als
Requirement (`manifest.json`) von PyPI. Das Add-on installiert sie beim
Image-Build aus demselben Commit. Library, Integration und Add-on haben eine
gemeinsame Versionsnummer, siehe [Release](#release).

## Architektur

Add-on und Integration teilen sich den Kern. Alles läuft auf einer
asyncio-Event-Loop, ohne Threads:

```text
serieller Port ──(pyserial-asyncio-fast)──> reader.run() ──Callback──> Supervisor
                                                                      │
                Add-on: SmartMeterDevice (aiomqtt) <── on_data ───────┤
         Integration: SmartMeterCoordinator        <── on_error ──────┘
```

- `smartmeter_austria/serial/transport.py` öffnet den Port in einem Executor und liefert
  Bytes, sobald sie ankommen. Leser warten auf Daten statt mit Timeouts
  abzufragen; ein abgesteckter Adapter beendet den Datenstrom sofort mit
  einem Fehler.
- Ein Leser (`MeterReaderLike`) hat eine Methode, `async run()`: Er liest, bis
  er abgebrochen wird, und wirft bei jedem Fehler. Leser versuchen nie selbst
  neu.
- `smartmeter_austria/supervisor.py` (`ReaderSupervisor`) ist die einzige Stelle für
  Wiederherstellung: Er ersetzt einen fehlgeschlagenen Leser nach einer Pause,
  meldet einen stillen Zähler (`stale_after`) und öffnet den Port neu, wenn er
  still bleibt (`restart_after`). Ihn abzubrechen stoppt den Leser und
  schließt den Port.
- Das Parsen (gurux, etwa 1–2 ms pro Telegramm) läuft auf der Loop; bei einem
  Telegramm alle 1–5 Sekunden ist das weit unter 1 % der Loop-Zeit.

## Tests

Die Tests brauchen weder Hardware noch einen Broker: ein geskripteter Port
(`smartmeter/smartmeter-austria/tests/fake_port.py`), ein kleiner MQTT-Broker
(`smartmeter/tests/fake_broker.py`) und Pseudo-Terminals für den echten
seriellen Transport.

Library und Add-on (Python 3.15, im Repository-Root):

```bash
uv venv && source .venv/bin/activate
uv pip install -r smartmeter/requirements-dev.txt -e smartmeter/smartmeter-austria
python3 -m smartmeter_austria.fix_source_encoding gurux_dlms gurux_common
ruff check smartmeter && mypy --config-file mypy.ini
(cd smartmeter/smartmeter-austria && pytest tests)
(cd smartmeter && pytest tests)
```

Integration (Python-Version aus `tests_integration/.python-version`, eigene
venv); die Library kommt editierbar aus dem Repository:

```bash
uv venv .venv-ha && source .venv-ha/bin/activate
uv pip install -r requirements-ha-test.txt -e smartmeter/smartmeter-austria ruff
python3 -m smartmeter_austria.fix_source_encoding gurux_dlms gurux_common
python3 .github/scripts/check_requirements_sync.py
ruff check custom_components tests_integration && pytest tests_integration
```

### Aus einem Debug-Log einen Test machen

Die Zeilen von `smartmeter_austria.serial.raw` (siehe
[fehlerbehebung.md](fehlerbehebung.md#debug-logs)) lassen sich direkt
nachspielen, mitsamt den Pausen:

```python
from smartmeter_austria.serial import rawlog
from tests.fake_port import EOF, FakePort, run_until, steps_from_capture

captured = rawlog.parse(open("bericht.log").read())
reader = get_profile("noe_evn").create_reader({"dlms": {"key": KEY}}, received.append)
reader._open_stream = FakePort([*steps_from_capture(captured), 0.3, EOF])
await run_until(reader.run, lambda: False)
```

`tests/test_rawlog.py` zeigt das vollständig: Ein echtes Pseudo-Terminal wird
gelesen, das Log mitgeschnitten und wieder eingespielt, mit denselben
Messwerten als Ergebnis.

## Integration lokal testen

Die Integration verlangt in `manifest.json` die Library in genau der Version
aus `smartmeter/smartmeter-austria/pyproject.toml`. Home Assistant installiert
sie von PyPI. Änderungen an der Library in einem Branch sieht Home Assistant
deshalb erst nach einem Release, außer die Library wird wie bei `./dev.sh`
selbst installiert.

**Testinstanz in Docker:** `./dev.sh` spiegelt die Integration und die
Library nach `config/`, installiert die Library bei jedem Start des
Containers aus dieser Kopie und startet Home Assistant im Container
`smartmeter-ha-dev` auf <http://localhost:8124>. Nach einer Änderung erneut
ausführen, um zu synchronisieren und neu zu starten. `HTTP_PORT` ändert den
Port, `--recreate` erzeugt den Container neu, `--no-logs` lässt ihn im
Hintergrund laufen. Auf einem Linux-Host reicht
`SERIAL_DEVICE=/dev/ttyUSB0 ./dev.sh` den Lesekopf durch; Docker Desktop auf
macOS/Windows kann keine USB-Seriell-Geräte durchreichen.

### Auf einem echten Home Assistant

Das Repository nach `/config` klonen (z.B. mit dem Add-on *Terminal & SSH*)
und die Integration nach `custom_components` verlinken. Aktualisieren ist dann
ein `git pull`. Home Assistant installiert dabei die Library-Version aus
`manifest.json` von PyPI; ein Branch, der die Library ändert, lässt sich so
nur mit `./dev.sh` testen.

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

Ohne `git` auf dem Home-Assistant-Host das Verzeichnis kopieren, z.B. von
einem anderen Rechner
`rsync -a --delete --exclude __pycache__ custom_components/smartmeter_at/ root@homeassistant.local:/config/custom_components/smartmeter_at/`
(das SSH-Add-on braucht `rsync`) oder mit `scp -r`.

## Add-on und Standalone lokal testen

Alle Varianten verwenden die Library aus `smartmeter/smartmeter-austria/` des
Arbeitsstands, nicht die Version von PyPI:

| Variante | Testen mit |
| --- | --- |
| Integration | `./dev.sh`, siehe [oben](#integration-lokal-testen) |
| Add-on | Klon in `/addons` auf dem Home-Assistant-Host, siehe [unten](#add-on) |
| Standalone-Container | `build:`-Block in `smartmeter/docker-compose.standalone.yml` |
| Standalone ohne Docker | `smartmeter/smartmeter.sh`, siehe [Installation](installation.md#systemd-ohne-docker) |

### Add-on

Den Klon auf dem Home-Assistant-Host nach `/addons` legen, z.B. mit dem
Add-on *Terminal & SSH*, und `image:` deaktivieren. Ohne `image:` baut der
Supervisor das Add-on selbst aus `smartmeter/`; die Library liegt in
`smartmeter/smartmeter-austria/` und kommt so aus demselben Stand.

```bash
cd /addons
git clone https://github.com/r00tat/smartmeter_homeassistant_burgenland.git smartmeter-src
# für einen Branch: git clone -b <branch> …
sed -i 's/^image:/# image:/' smartmeter-src/smartmeter/config.yaml
```

1. Unter *Einstellungen → Add-ons → Add-on-Store* über *⋮ → Nach Updates
   suchen* den Store neu laden. Das Add-on erscheint unter *Lokale Add-ons*;
   installieren und konfigurieren.
2. Nach einer Änderung `git pull --autostash` (behält das auskommentierte
   `image:`) und im Add-on auf *Neu erstellen* klicken, oder
   `ha addons rebuild local_smartmeter_bgld_mqtt`. Hat sich `version` in
   `config.yaml` geändert, bietet der Supervisor stattdessen ein Update an.

Das lokale Add-on (`local_smartmeter_bgld_mqtt`) steht neben dem
veröffentlichten. Nicht beide gleichzeitig mit demselben Lesekopf starten.

### Images ohne Supervisor bauen

Build-Kontext ist `smartmeter/`, wie beim Supervisor:

```bash
docker build -t smartmeter-addon smartmeter
docker build -f smartmeter/Dockerfile.standalone -t smartmeter-standalone smartmeter
```

Die Release-Pipeline baut und veröffentlicht die Images.
`cd smartmeter && DOCKERHUB_USER=… DOCKERHUB_PASSWORD=… ./build_images.sh`
baut sie bei Bedarf manuell mit dem Home-Assistant-Builder für alle
Architekturen und lädt sie auf Docker Hub.

## Release

Ein GitHub-Release mit dem Tag `X.Y.Z` (ohne `v`) startet
`.github/workflows/release.yml`:

1. Die Version wird in `smartmeter/config.yaml`, `manifest.json` (Version und
   Pin `smartmeter-austria==X.Y.Z`) und `smartmeter/smartmeter-austria/pyproject.toml`
   gesetzt und auf `main` committet.
2. Die Library wird gebaut und per
   [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) auf PyPI
   veröffentlicht, ohne API-Token.
3. Add-on- und Standalone-Images werden gebaut und auf Docker Hub geladen.
4. Erst nach dem PyPI-Upload hängt der Workflow `smartmeter_at.zip` für HACS
   an das Release; sonst könnte Home Assistant die gepinnte Version nicht
   installieren.

Einmalig auf pypi.org einrichten: unter *Publishing* einen *pending
publisher* für das Projekt `smartmeter-austria` anlegen, mit Owner `r00tat`,
Repository `smartmeter_homeassistant_burgenland`, Workflow `release.yml` und
Environment `pypi`. Im GitHub-Repository das Environment `pypi` anlegen
(Settings → Environments), optional mit Freigabe durch einen Reviewer.

## Einen neuen Zähler hinzufügen

Alles, was die Kundenschnittstelle eines Zählers ausmacht, steht in seinem
Profil in `smartmeter/smartmeter-austria/src/smartmeter_austria/profile.py`: serielle Einstellungen,
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
