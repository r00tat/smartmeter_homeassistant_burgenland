# Meters and grid operators

[Deutsche Version](../zaehler.md) · [Back to the README](../../README.en.md)

Every meter type (`meter_type`) brings its serial settings, push interval,
decryption and sensors. In the integration you pick it as *Grid operator /
meter*, in the add-on and the container as `meter_type`.

| `meter_type` | Grid operator | Interface | Serial | Interval |
| --- | --- | --- | --- | --- |
| `burgenland` | Netz Burgenland | IR or wired, DLMS/HDLC | 9600 8N1 | 5 s |
| `noe_evn` | Netz NÖ / EVN | M-Bus | 2400 8E1 | 5 s |
| `wien` | Wiener Netze | IR, DLMS/HDLC | 9600 8N1 | 1 s |
| `steiermark` | Energienetze Steiermark (Landis+Gyr) | M-Bus | 2400 8E1 | 10 s |
| `steiermark_sagemcom` | Energienetze Steiermark (Sagemcom) | DSMR P1 | 115200 8N1 | 10 s |
| `salzburg` | Salzburg Netz | M-Bus | 2400 8E1 | 5 s |
| `tirol` | TINETZ | M-Bus | 2400 8E1 | 5 s |
| `h1` | Smart Meter 2.0 (all) | DSMR P1 | 115200 8N1 | 1 s |

Values a meter does not send (e.g. L2/L3 on single-phase meters) show up as
*unknown* in Home Assistant.

## Netz Burgenland – Landis+Gyr E450

- [Request the customer interface](https://www.netzburgenland.at/kundenservice/smart-metering/smart-metering/kundenschnittstelle.html)
  and select *IR (optical)* as transport. The key is in the customer portal.
- Tested with the optical interface (`interface_type: OPTICAL`); the wired
  one (`PHYSICAL`) is implemented but less proven.
- One telegram every 5 seconds, encrypted and authenticated with DLMS/COSEM
  Security Suite 0 (IEC 62056) and a customer-specific key.

Contents of a telegram: timestamp, instantaneous voltage L1–L3, instantaneous
current L1–L3, active power +P and −P, total active energy +A and −A, angle
between voltage and current per phase, and the meter identification number.

Sources: [Customer interface specification L+G E450](https://assets.netzburgenland.at/Spezifikation_Kundenschnittstelle_E450_korr_2_009418889e.pdf),
[Netz Burgenland smart meter](https://www.netzburgenland.at/smart-meter/),
[End customer interface description](https://assets.netzburgenland.at/Netz_Burgenland_Beschreibung_Endkundenschnittstelle_02_c72d3973e9.pdf).

**Kaifa MA309 in Burgenland:** According to Netz Burgenland, Kaifa meters send
a different format on the optical interface every 15 seconds (date/time,
logical device number, ±A, ±P, ±R; IDIS CII, 9600 8N1). The `burgenland`
profile is built for the E450; captures from a Kaifa meter are
[welcome](#real-data-wanted).

## Netz NÖ / EVN – Sagemcom T210-D

- Request the M-Bus customer interface and the AES key in the Netz NÖ customer
  portal. Needs an M-Bus adapter (M-Bus to USB).
- Roughly every 5 seconds an M-Bus long frame (`68 LL LL 68 … CS 16`) wrapping
  a DLMS/COSEM data notification, encrypted with AES-128-GCM (Security
  Suite 0). The nonce is the system title (8 bytes) plus the frame counter
  (4 bytes) from the M-Bus header.
- Values: voltage L1–L3, current L1–L3, active power ±P, energy consumed and
  fed in, power factor. The T210-D does not send phase angles.

Sources: [Netz NÖ customer interface specification (PDF)](https://www.netz-noe.at/Download-(1)/Smart-Meter/218_9_SmartMeter_Kundenschnittstelle_Lastenheft2-0.aspx),
[greenMikeEU/SmartMeterEVN](https://github.com/greenMikeEU/SmartMeterEVN).

## Wiener Netze – Siemens IM150/IM350/IM351, Iskraemeco AM550, Landis+Gyr E450

- Activate the customer interface and copy the key in the
  [Wiener Netze smart meter portal](https://smartmeter-web.wienernetze.at/).
- Every second a DLMS/COSEM data notification on the infrared interface in an
  HDLC frame (`7E A0 …`), encrypted with AES-128-GCM without authentication
  tag. Same transport as in Burgenland, hence the same reader.
- The message has no OBIS codes but a fixed order: optionally the serial
  number (not every meter sends it), timestamp, +A, −A, +R, −R (Wh/varh) and
  +P, −P, +Q, −Q (W/var). The meter sends no voltage or current. The reactive
  values are disabled by default.

Sources: [Wiener Netze customer interface](https://www.wienernetze.at/smart-meter-kundenschnittstelle),
[bernikr/esphome-wienernetze-smartmeter](https://github.com/bernikr/esphome-wienernetze-smartmeter),
[tofuSCHNITZEL/wiener-netze-smartmeter-serial](https://github.com/tofuSCHNITZEL/wiener-netze-smartmeter-serial).

## Steiermark, Salzburg, Tirol and H1

These meters name every value by its OBIS code and therefore share one
pipeline:

```text
serial bytes → framing → general-glo-ciphering (AES-128-GCM)
             → data notification (A-XDR) or DSMR text → OBIS registers
```

They follow the published specifications and are tested with telegrams built
to them, **but not yet with a real meter** (see
[Real data wanted](#real-data-wanted)).

- **Salzburg Netz and TINETZ (Kaifa, Honeywell):** wired M-Bus on RJ12 pins
  3/4, 2400 baud 8E1, every 5 s. Messages above 250 bytes are split into
  several M-Bus frames. Values carry scaler and unit. Activate the interface
  and get the key in the [Salzburg Netz portal](https://portal.salzburgnetz.at/)
  or the TINETZ customer portal (the key is sent to you).
  Specifications: [Salzburg Netz](https://www.salzburgnetz.at/content/dam/salzburgnetz/dokumente/stromnetz/Technische-Beschreibung-Kundenschnittstelle.pdf),
  [TINETZ](https://www.tinetz.at/uploads/tx_bh/101/tinetz_smart-meter_beschreibung-kundenschnittstelle_001.pdf).
- **Energienetze Steiermark, Landis+Gyr E450 (`steiermark`):** wired M-Bus on
  RJ12 pins 3/4, 2400 baud, every 10 s. Community reports show three HDLC
  frames per push carrying DLMS general-block-transfer blocks, with the clock
  and 16 OBIS values (energy and power ±A/±R, tariffs 1 and 2). M-Bus frames
  are accepted as well. Use the GUEK from the
  [Energienetze portal](https://portal.e-netze.at/) as key; the GAK is not
  needed.
- **Energienetze Steiermark, Sagemcom (`steiermark_sagemcom`):** DSMR 5.0.2 P1
  on RJ12, 115200 baud, every 10 s, encrypted with the GUEK.
  Specification: [Energienetze Steiermark](https://www.e-netze.at/downloads-data/pdf.aspx?pdf=EN_Update+Kundenschnittstelle+Smart+Meter+%2803_2024%29_WEB_RGB.pdf).
- **Smart Meter 2.0, customer interface H1 (`h1`):** the Oesterreichs Energie
  Companion Standard 2026 defines H1 as DSMR P1 at 115200 baud, one push per
  second, DLMS Security Suite 0 (AES-GCM-128), with voltage, current, ±P, ±Q,
  ±A and ±R. The exact format is not public yet, so `h1` accepts encrypted and
  plain DSMR telegrams as well as DLMS notifications (raw or in HDLC frames).
  Specification: [OE Companion Standard Smart Meter 2.0](https://oesterreichsenergie.at/fileadmin/user_upload/Oesterreichs_Energie/Publikationsdatenbank/Diverses/2026/OE_Companion_Standard_V1.0.pdf),
  chapter C.6.

The M-Bus interfaces need an M-Bus slave adapter (M-Bus to USB), the DSMR P1
interfaces a P1 cable.

## Real data wanted

No telegram from a real meter has been decoded yet with `steiermark`,
`steiermark_sagemcom`, `salzburg`, `tirol` and `h1`. Meters do not always
behave as documented (Salzburg Netz, for example, documents AES-CBC while
community projects report AES-GCM). How you can help:

1. Enable debug logs (see [troubleshooting.md](troubleshooting.md#debug-logs))
   and let the matching meter type run for a minute.
2. Open an [issue](https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues)
   with grid operator, meter model, the `raw bytes:` / `telegram (…):` log
   lines and whether values showed up in Home Assistant.
3. If you can, attach the capture together with its key so it can become a
   test. The key only decrypts the customer interface of your own meter, and
   you can have your grid operator issue a new one afterwards. Without the key,
   the decoded values from the log or the values on the meter display at that
   moment help as well.

Not supported yet: Netz Oberösterreich (AMIS, OMS M-Bus with AES mode 5),
Vorarlberg Netz (AES-CBC with CMAC) and Kärnten Netz (no public specification
found). Captures for these are welcome too.
