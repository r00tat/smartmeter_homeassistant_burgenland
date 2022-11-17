# Smart Meter Reader Burgenland - AT

## Development

Initialize virtual environment:

```bash
python3 -m venv .
source bin/activate
pip3 install -r requirements.txt
```

If you install additional pacakges, save the current installed dependencies to `requirements.txt` with:
`pip freeze -l | grep -v flake8 > requirements.txt`

## useful links

- [Netz Burgenland Zählerbeschreibung](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/zaehlerbeschreibung.html)
- [Netz Burgenland Kundenschnittstelle](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/kundenschnittstelle.html)
- [Optische Schnittstelle](https://www.netzburgenland.at/fileadmin/user_upload/Netz_Burgenland_Beschreibung_Endkundenschnittstelle_02.pdf)

### Interface description

Source: [Optische Schnittstelle](https://www.netzburgenland.at/fileadmin/user_upload/Netz_Burgenland_Beschreibung_Endkundenschnittstelle_02.pdf)

Als Kundenschnittstelle wird die optische Schnittstelle des Zählers verwendet. Es wird alle
15 Sekunden eine Nachricht dieser optischen Schnittstelle ausgegeben. Der Aufbau sowie
der Inhalt der Nachricht wird in den nachfolgenden Kapiteln beschrieben. Die
Implementierung erfolgt gemäß IDIS CII.

Die Ausgabe der Push-Nachrichten erfolgt auf der optischen Schnittstelle, welche nach
DIN EN 62056-21 ausgeführt ist.

Jede Push-Nachricht enthält die unten angeführten Daten (in dieser Reihenfolge). Das
Push-Intervall beträgt 15 Sekunden. Es werden immer die aktuellsten Daten ausgegeben.

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
