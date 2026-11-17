# Troubleshooting

[Deutsche Version](../fehlerbehebung.md) · [Back to the README](../../README.en.md)

## Error messages when setting up the integration

| Message | Cause |
| --- | --- |
| *The serial port cannot be opened.* | The port does not exist, or another program (often the add-on) holds it. |
| *No valid telegram received.* | The port opens, but no readable telegram arrived. Is the reading head on the IR window? Is the interface activated? Are meter type and key right? A key with the right format but the wrong value ends up here as well. |
| *The key must be exactly 32 hex characters.* | Typo in the key. |
| *This port is already used by another smart meter entry.* | Only one entry per port is possible. |
| *Unexpected error* | The log has the details. |

When you report a problem, the diagnostics file from the device page helps;
the key is redacted in it.

## No or outdated values

The integration, the add-on and the container recover on their own, no
restart automation is needed:

- **Port fails** (e.g. USB adapter unplugged): the sensors become
  *unavailable*, the port is reopened every 10 seconds.
- **Meter goes silent** (e.g. reading head slipped off): after about a minute
  without a telegram (six missed telegrams, at least 60 seconds) the sensors
  become *unavailable* until the next telegram.
- **Port open but no data** (e.g. hung USB adapter): after 5 minutes of
  silence the port is closed and reopened.
- **MQTT broker gone** (add-on and container): reconnect every 10 seconds,
  then the device is announced again. Values from the meantime are buffered,
  only the latest per topic.
- **Add-on or container crashes**: the MQTT last will marks the sensors
  *unavailable*.

If values are still missing, the [debug logs](#debug-logs) show at which layer
it hangs. For Netz NÖ, Steiermark, Salzburg, Tirol and H1 the reader also logs
a heartbeat every 30 seconds that names the likely cause: no bytes (wiring,
port, baudrate), bytes without a recognisable telegram (baudrate, parity,
meter type) or telegrams that cannot be decrypted (key).

## Debug logs

**Integration** – in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.smartmeter_at: debug
    smartmeter_austria: debug
```

**Add-on and container** – `logging: DEBUG` in the configuration.

With debug logs the serial transport writes every received chunk as its own
line, for every meter type:

```text
DEBUG:smartmeter_austria.serial.raw:rx +12.345s 24 bytes: 7ea08bceff0313ee…
```

`+12.345s` is the time since the port was opened. These lines hold every
byte, including what a reader drops (e.g. while looking for the start of a
telegram, or a broken frame). Please include them when you report a problem.
The readers additionally log every recognised telegram and the decoded
values.
