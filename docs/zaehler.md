# Zähler und Netzbetreiber

[English version](en/meters.md) · [Zurück zum README](../README.md)

Jeder Zählertyp (`meter_type`) bringt seine seriellen Einstellungen, das
Sendeintervall, die Entschlüsselung und die Sensoren mit. In der Integration
wählst du ihn als *Netzbetreiber / Zähler*, im Add-on und im Container als
`meter_type`.

| `meter_type` | Netzbetreiber | Schnittstelle | Seriell | Intervall |
| --- | --- | --- | --- | --- |
| `burgenland` | Netz Burgenland | IR oder kabelgebunden, DLMS/HDLC | 9600 8N1 | 5 s |
| `noe_evn` | Netz NÖ / EVN | M-Bus | 2400 8E1 | 5 s |
| `wien` | Wiener Netze | IR, DLMS/HDLC | 9600 8N1 | 1 s |
| `steiermark` | Energienetze Steiermark (Landis+Gyr) | M-Bus | 2400 8E1 | 10 s |
| `steiermark_sagemcom` | Energienetze Steiermark (Sagemcom) | DSMR P1 | 115200 8N1 | 10 s |
| `salzburg` | Salzburg Netz | M-Bus | 2400 8E1 | 5 s |
| `tirol` | TINETZ | M-Bus | 2400 8E1 | 5 s |
| `h1` | Smart Meter 2.0 (alle) | DSMR P1 | 115200 8N1 | 1 s |

Werte, die ein Zähler nicht sendet (z.B. L2/L3 bei einphasigen Zählern),
erscheinen in Home Assistant als *unbekannt*.

## Netz Burgenland – Landis+Gyr E450

- Kundenschnittstelle [beim Netzbetreiber beantragen](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/kundenschnittstelle.html),
  als Übertragung *IR (optisch)* wählen. Den Schlüssel gibt es im Kundenportal.
- Getestet mit der optischen Schnittstelle (`interface_type: OPTICAL`); die
  kabelgebundene (`PHYSICAL`) ist implementiert, aber weniger erprobt.
- Alle 5 Sekunden ein Telegramm, verschlüsselt und authentisiert mit
  DLMS/COSEM Security Suite 0 (IEC 62056) und kundenindividuellem Schlüssel.

Inhalt eines Telegramms: Zeitstempel, Momentanspannung L1–L3, Momentanstrom
L1–L3, Wirkleistung +P und −P, Wirkenergie total +A und −A, Winkel Spannung zu
Strom je Phase und die Zähleridentifikationsnummer.

Quellen: [Spezifikation Kundenschnittstelle L+G E450](https://assets.netzburgenland.at/Spezifikation_Kundenschnittstelle_E450_korr_2_009418889e.pdf),
[Netz Burgenland Smart Meter](https://www.netzburgenland.at/smart-meter/),
[Beschreibung Endkundenschnittstelle](https://assets.netzburgenland.at/Netz_Burgenland_Beschreibung_Endkundenschnittstelle_02_c72d3973e9.pdf).

**Kaifa MA309 im Burgenland:** Laut Netz Burgenland senden Kaifa-Zähler auf der
optischen Schnittstelle alle 15 Sekunden ein anderes Format (Datum/Uhrzeit,
Logical Device Number, ±A, ±P, ±R; IDIS CII, 9600 8N1). Das Profil
`burgenland` ist für den E450 gebaut; Aufzeichnungen eines Kaifa-Zählers sind
[willkommen](#echte-daten-gesucht).

## Netz NÖ / EVN – Sagemcom T210-D

- M-Bus-Kundenschnittstelle im Kundenportal von Netz NÖ beantragen und den
  AES-Schlüssel anfordern. Benötigt einen M-Bus-Adapter (M-Bus auf USB).
- Etwa alle 5 Sekunden ein M-Bus-Long-Frame (`68 LL LL 68 … CS 16`) mit einer
  DLMS/COSEM-Data-Notification, verschlüsselt mit AES-128-GCM (Security
  Suite 0). Der Nonce besteht aus System-Title (8 Byte) und Frame-Counter
  (4 Byte) aus dem M-Bus-Header.
- Werte: Spannung L1–L3, Strom L1–L3, Wirkleistung ±P, Energie Bezug und
  Einspeisung, Leistungsfaktor. Phasenwinkel sendet der T210-D nicht.

Quellen: [Netz NÖ Lastenheft Kundenschnittstelle (PDF)](https://www.netz-noe.at/Download-(1)/Smart-Meter/218_9_SmartMeter_Kundenschnittstelle_Lastenheft2-0.aspx),
[greenMikeEU/SmartMeterEVN](https://github.com/greenMikeEU/SmartMeterEVN).

## Wiener Netze – Siemens IM150/IM350/IM351, Iskraemeco AM550, Landis+Gyr E450

- Kundenschnittstelle aktivieren und Schlüssel kopieren im
  [Smart-Meter-Webportal von Wiener Netze](https://smartmeter-web.wienernetze.at/).
- Jede Sekunde eine DLMS/COSEM-Data-Notification auf der Infrarot-Schnittstelle
  in einem HDLC-Frame (`7E A0 …`), verschlüsselt mit AES-128-GCM ohne
  Authentisierungs-Tag. Dasselbe Transportformat wie im Burgenland, deshalb
  derselbe Leser.
- Die Nachricht hat keine OBIS-Codes, sondern eine feste Reihenfolge:
  optional die Seriennummer (nicht jeder Zähler sendet sie), Zeitstempel,
  +A, −A, +R, −R (Wh/varh) und +P, −P, +Q, −Q (W/var). Spannung und Strom
  sendet der Zähler nicht. Die Blindwerte sind standardmäßig deaktiviert.

Quellen: [Wiener Netze Kundenschnittstelle](https://www.wienernetze.at/smart-meter-kundenschnittstelle),
[bernikr/esphome-wienernetze-smartmeter](https://github.com/bernikr/esphome-wienernetze-smartmeter),
[tofuSCHNITZEL/wiener-netze-smartmeter-serial](https://github.com/tofuSCHNITZEL/wiener-netze-smartmeter-serial).

## Steiermark, Salzburg, Tirol und H1

Diese Zähler benennen jeden Wert mit seinem OBIS-Code und teilen sich deshalb
eine gemeinsame Verarbeitung:

```text
serielle Bytes → Framing → general-glo-ciphering (AES-128-GCM)
               → Data-Notification (A-XDR) oder DSMR-Text → OBIS-Register
```

Sie sind nach den veröffentlichten Spezifikationen umgesetzt und mit danach
gebauten Telegrammen getestet, **aber noch nicht mit einem echten Zähler**
(siehe [Echte Daten gesucht](#echte-daten-gesucht)).

- **Salzburg Netz und TINETZ (Kaifa, Honeywell):** kabelgebundener M-Bus an
  RJ12 Pin 3/4, 2400 Baud 8E1, alle 5 s. Nachrichten über 250 Byte kommen in
  mehreren M-Bus-Frames. Die Werte enthalten Skalierung und Einheit.
  Schnittstelle aktivieren und Schlüssel holen im
  [Salzburg-Netz-Portal](https://portal.salzburgnetz.at/) bzw. im
  TINETZ-Kundenportal (der Schlüssel wird zugeschickt).
  Spezifikationen: [Salzburg Netz](https://www.salzburgnetz.at/content/dam/salzburgnetz/dokumente/stromnetz/Technische-Beschreibung-Kundenschnittstelle.pdf),
  [TINETZ](https://www.tinetz.at/uploads/tx_bh/101/tinetz_smart-meter_beschreibung-kundenschnittstelle_001.pdf).
- **Energienetze Steiermark, Landis+Gyr E450 (`steiermark`):** kabelgebundener
  M-Bus an RJ12 Pin 3/4, 2400 Baud, alle 10 s. Laut Community-Berichten drei
  HDLC-Frames pro Sendung mit DLMS-General-Block-Transfer; enthalten sind Uhr
  und 16 OBIS-Werte (Energie und Leistung ±A/±R, Tarif 1 und 2). M-Bus-Frames
  werden ebenfalls akzeptiert. Als Schlüssel den GUEK aus dem
  [Energienetze-Portal](https://portal.e-netze.at/) verwenden; der GAK wird
  nicht gebraucht.
- **Energienetze Steiermark, Sagemcom (`steiermark_sagemcom`):** DSMR 5.0.2 P1
  an RJ12, 115200 Baud, alle 10 s, verschlüsselt mit dem GUEK.
  Spezifikation: [Energienetze Steiermark](https://www.e-netze.at/downloads-data/pdf.aspx?pdf=EN_Update+Kundenschnittstelle+Smart+Meter+%2803_2024%29_WEB_RGB.pdf).
- **Smart Meter 2.0, Kundenschnittstelle H1 (`h1`):** Der Companion Standard
  2026 von Oesterreichs Energie definiert H1 als DSMR P1 mit 115200 Baud,
  einer Sendung pro Sekunde und DLMS Security Suite 0 (AES-GCM-128), mit
  Spannung, Strom, ±P, ±Q, ±A und ±R. Das genaue Format ist noch nicht
  öffentlich; `h1` akzeptiert daher verschlüsselte und unverschlüsselte
  DSMR-Telegramme sowie DLMS-Notifications (roh oder in HDLC-Frames).
  Spezifikation: [OE Companion Standard Smart Meter 2.0](https://oesterreichsenergie.at/fileadmin/user_upload/Oesterreichs_Energie/Publikationsdatenbank/Diverses/2026/OE_Companion_Standard_V1.0.pdf),
  Kapitel C.6.

Die M-Bus-Schnittstellen brauchen einen M-Bus-Slave-Adapter (M-Bus auf USB),
die DSMR-P1-Schnittstellen ein P1-Kabel.

## Echte Daten gesucht

Für `steiermark`, `steiermark_sagemcom`, `salzburg`, `tirol` und `h1` wurde
noch kein Telegramm eines echten Zählers entschlüsselt. Zähler verhalten sich
nicht immer wie dokumentiert (Salzburg Netz dokumentiert z.B. AES-CBC,
Community-Projekte berichten von AES-GCM). So kannst du helfen:

1. Debug-Logs einschalten (siehe [fehlerbehebung.md](fehlerbehebung.md#debug-logs))
   und den passenden Zählertyp eine Minute laufen lassen.
2. Ein [Issue](https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues)
   anlegen mit Netzbetreiber, Zählermodell, den Logzeilen `rx +…s … bytes: …`
   (Logger `meter.serial.raw`) und der Info, ob Werte in Home Assistant
   ankamen. Diese Zeilen enthalten alle empfangenen Bytes samt Zeitabstand;
   daraus lässt sich der Datenstrom exakt nachspielen.
3. Wenn möglich die Aufzeichnung samt Schlüssel anhängen, damit daraus ein
   Test werden kann. Der Schlüssel entschlüsselt nur die Kundenschnittstelle
   deines eigenen Zählers, und du kannst danach beim Netzbetreiber einen neuen
   anfordern. Ohne Schlüssel helfen die entschlüsselten Werte aus dem Log oder
   die Werte am Zählerdisplay zum selben Zeitpunkt.

Noch nicht unterstützt: Netz Oberösterreich (AMIS, OMS-M-Bus mit AES Mode 5),
Vorarlberg Netz (AES-CBC mit CMAC) und Kärnten Netz (keine öffentliche
Spezifikation gefunden). Aufzeichnungen dieser Zähler sind ebenfalls
willkommen.
