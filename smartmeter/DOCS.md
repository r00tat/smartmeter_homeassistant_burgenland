# Smartmeter Burgenland (AT) MQTT Addon

This Addon connects your Smart Meter from Netz Burgenland to Home
Assistant via MQTT. It has been tested with a Raspberry Pi Zero W 2 with a
[Weidmann Elektronik IR Schreib/Lesekopf](https://shop.weidmann-elektronik.de/index.php?page=product&info=24) and the
[Landis+Gyr E450](https://www.netzburgenland.at/fileadmin/NB_pdf_NEU/Smart_Meter/Spezifikation_Kundenschnittstelle_E450_korr_2.pdf).

You can read more about the underlying python program at the [github page](https://github.com/r00tat/smartmeter_homeassistant_burgenland).

## Optional MQTT TLS

To connect to an MQTT broker over TLS, set any of the `tls_ca`, `tls_cert`, `tls_key`, or `tls_insecure` options under `mqtt`. `tls_ca` points to a CA certificate (PEM) the broker is trusted against; `tls_cert` and `tls_key` enable mutual TLS with a client certificate and key. Set `tls_insecure: true` to skip hostname verification for testing only. Paths must be readable from within the addon container (e.g. mounted via `share:ro` or `config:ro`). If none of these options are set, MQTT connects without TLS.
