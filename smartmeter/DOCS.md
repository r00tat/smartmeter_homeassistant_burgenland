# Smartmeter Burgenland (AT) MQTT Addon

This Addon connects your Austrian Smart Meter to Home Assistant via MQTT.
It has been tested with a Raspberry Pi Zero W 2 and a
[Weidmann Elektronik IR Schreib/Lesekopf](https://shop.weidmann-elektronik.de/index.php?page=product&info=24).

Supported meters (select via `meter_type`):

- `burgenland` *(default)* — Netz Burgenland
  [Landis+Gyr E450](https://www.netzburgenland.at/fileadmin/NB_pdf_NEU/Smart_Meter/Spezifikation_Kundenschnittstelle_E450_korr_2.pdf)
  over DLMS/HDLC at 9600 baud. The IR customer interface must be unlocked
  by Netz Burgenland and the AES key obtained from the customer portal.
- `noe_evn` — Netz Niederösterreich / EVN
  [Sagemcom T210-D](https://www.netz-noe.at/Download-(1)/Smart-Meter/218_9_SmartMeter_Kundenschnittstelle_Lastenheft2-0.aspx)
  over DLMS via M-Bus framing at 2400 baud (8E1). The M-Bus customer
  interface must be activated and the AES key requested via the Netz NÖ
  customer portal.

You can read more about the underlying python program at the [github page](https://github.com/r00tat/smartmeter_homeassistant_burgenland).

## Meter selection

Set the top-level `meter_type` option to switch between providers. When
omitted, the addon behaves exactly as before and uses the `burgenland`
profile. Changing the profile also switches the default serial baudrate
(9600 for `burgenland`, 2400 for `noe_evn`) and the Home Assistant
device manufacturer/model metadata.

The `noe_evn` profile publishes the subset of OBIS registers emitted by
the Sagemcom T210-D: instantaneous voltages (L1–L3), currents (L1–L3),
active power in/out, power factor, and cumulative import/export energy.
Phase-angle sensors (which the E450 exposes) are omitted because the
T210-D does not publish them.

## Optional MQTT TLS

To connect to an MQTT broker over TLS, set any of the `tls_ca`, `tls_cert`, `tls_key`, or `tls_insecure` options under `mqtt`. `tls_ca` points to a CA certificate (PEM) the broker is trusted against; `tls_cert` and `tls_key` enable mutual TLS with a client certificate and key. Set `tls_insecure: true` to skip hostname verification for testing only. Paths must be readable from within the addon container (e.g. mounted via `share:ro` or `config:ro`). If none of these options are set, MQTT connects without TLS.
