# Smart Meter Reader Burgenland - AT

This python program connects your Smart Meter from Netz Burgenland to Home
Assistant via MQTT. It has been tested with a Raspberry Pi Zero W 2 with a
[Weidmann Elektronik IR Schreib/Lesekopf](https://shop.weidmann-elektronik.de/index.php?page=product&info=24) and the
[Landis+Gyr E450](https://www.netzburgenland.at/fileadmin/NB_pdf_NEU/Smart_Meter/Spezifikation_Kundenschnittstelle_E450_korr_2.pdf).

## Quickstart

### Homeassistant Addon

To use this program on the homeassistant raspberry pi as addon follow this steps:

1. Request the [activation of the customer interface](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/kundenschnittstelle.html) and select IR as transport.
2. Connect the IR reader to the smart meter
3. Connect the IR reader to your raspberry pi
4. Open homeassistant web ui and go to Settings -> Add-ons -> Add-on Store
5. Click on the 3 dots on the top right and click on Repositories
6. Add `https://github.com/r00tat/smartmeter_homeassistant_burgenland` as a repository.
7. Reload the page
8. Install the Smartmeter Burgenland MQTT Addon
9. Configure the smartmeter connection in `/config/smartmeter-config.yaml` from the [smartmeter-config-template.yaml](smartmeter-config-template.yaml).
10. start the addon 


### Standalone

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
cp config-template.yaml config.yaml
# now edit the config
sudo ln -s "$(pwd)/smartmeter.service" /etc/systemd/system/smartmeter.service && sudo systemctl enable smartmeter && sudo systemctl start smartmeter
```

To view the status of the service you can use `sudo systemctl status smartmeter` and to restart it `sudo systemctl restart smartmeter`

To follow the output of the program you can use `tail -f /var/log/daemon.log`.

## Development

Initialize virtual environment:

```bash
python3 -m venv .
source bin/activate
pip3 install -r requirements.txt
```

If you install additional pacakges, save the current installed dependencies to `requirements.txt` with:
`pip freeze -l | grep -v flake8 > requirements.txt`

### Addon Development

Building a version and pushing to docker hub:

```bash
ARCH=$(uname -m)
if [[ "$ARCH" =~ "armv7.*" ]]; then
  ARCH="armv7"
fi

VERSION=$(yq -r '.version' config.yaml)
docker build -t paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:$VERSION --build-arg BUILD_FROM=homeassistant/${ARCH}-base:latest .
docker tag paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:$VERSION paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:latest
docker push paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:$VERSION
docker push paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:latest

```

## useful links

- [Netz Burgenland Zählerbeschreibung](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/zaehlerbeschreibung.html)
- [Netz Burgenland Kundenschnittstelle](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/kundenschnittstelle.html)
- [Optische Schnittstelle](https://www.netzburgenland.at/fileadmin/user_upload/Netz_Burgenland_Beschreibung_Endkundenschnittstelle_02.pdf)

### Interface description

#### Landis+Gyr E450

The programm has been tested with the Landis+Gyr E450 Smart Meter, but not with
the wired connection, but with the IR interface. If you order the customer
interface, you can select the optical interface as the desired option.

Source: [Spezifikation Kundenschnittstelle L+G E450](https://www.netzburgenland.at/fileadmin/NB_pdf_NEU/Smart_Meter/Spezifikation_Kundenschnittstelle_E450_korr_2.pdf)

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
- Zähleridentifikationsnummern des Netzbetreibers
  Verschlüsselung und Authentifizierung
  Die Datenausgabe wird mit individuellen kundenbezogenen Schlüsseln verschlüsselt und
  authentisiert. Zur Anwendung kommt dabei die dlms/COSEM Security Suite 0, die entsprechend dem
  Datenmodel durch die IEC 62056 Normenreihe spezifiziert ist.

#### Spezifikation Kundenschnittstelle KAIFA MA309

The KAIFA interface defines how the IR interface transmission is defined. The format of the message is different in KAIFA dann in Landis+Gyr.

Source: [Optische Schnittstelle](https://www.netzburgenland.at/fileadmin/user_upload/Netz_Burgenland_Beschreibung_Endkundenschnittstelle_02.pdf)

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
