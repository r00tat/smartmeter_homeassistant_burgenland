# Design: Netz NÖ / EVN Sagemcom T210-D Support

- **Issue:** [#69](https://github.com/r00tat/smartmeter_homeassistant_burgenland/issues/69)
- **Date:** 2026-04-17
- **Status:** Accepted – implementation in progress

## Goal

Extend the add-on so a user with a Sagemcom T210-D (Netz Niederösterreich
/ EVN) M-Bus customer interface can run this add-on alongside the existing
Landis+Gyr E450 / Kaifa MA309 flows.

## Why a second code path is unavoidable

The two meters are similar on paper (both DLMS/COSEM, AES-GCM), but the
framing and data model are different enough that the current
`MeterReader` cannot parse T210-D output:

| Aspect | Burgenland L+G E450 (current) | Netz NÖ Sagemcom T210-D |
|---|---|---|
| Physical interface | IR optical head / wired DLMS | M-Bus (RJ12), 20–30 V |
| Baud rate | 9600 8N1 | 2400 8N1 |
| Framing | DLMS HDLC (`InterfaceType.HDLC`) | M-Bus long frame `68 LL LL 68 … 16` |
| Decryption entry point | `GXDLMSSecureClient.getData()` | raw AES-GCM, nonce = system title + frame counter extracted from M-Bus payload |
| APDU parsing | Positional DLMS structure | `GXDLMSTranslator.pduToXml` + OBIS dictionary |
| Provided values | U/I L1–L3, ±P, ±A, angles, meter id | U/I L1–L3, ±P, ±A, **power factor** (no angles) |
| Value scaling | divide current by 100 | voltage ·0.1, current ·0.01, pf ·0.001, energy /1000 (to kWh then ·1000 to Wh for HA) |

Reference implementation: [greenMikeEU/SmartMeterEVN](https://github.com/greenMikeEU/SmartMeterEVN).

## Architecture

Introduce a **meter profile** abstraction. A profile bundles:

- The reader strategy (HDLC/optical serial loop vs. M-Bus long-frame loop)
- The parser (positional DLMS list vs. OBIS-code dictionary)
- The `MeterData` payload (fields, scaling, `to_dict`)
- The MQTT sensor catalog (which HA sensors to publish)
- Device metadata (manufacturer/model for HA auto-discovery)

Profiles live next to their data models:

```
smartmeter/meter/
  bgld/                 # existing profile – unchanged behaviour
    data.py
    read.py
  noe/                  # NEW profile
    __init__.py
    mbus.py             # M-Bus long-frame parser (pure, testable)
    decrypt.py          # AES-GCM decrypt (pure, testable)
    obis.py             # OBIS dictionary + gurux XML → dict parser
    data.py             # MeterData for NOE (incl. power_factor)
    read.py             # NoeMeterReader – owns the serial loop
  profile.py            # NEW: profile registry / dispatch
```

The top-level `SmartMqttMeter` selects a profile from
`meter_type` in config (default `burgenland` for backward compat). It
hands the reader its callback and hands the MQTT device its sensor
catalog and device metadata; nothing else in `smartmeter.py` changes.

## Config surface

New top-level option:

```yaml
meter_type: burgenland        # or: noe_evn
```

Defaults per profile are applied when the user leaves them empty:

- `burgenland`: baudrate 9600, interface_type OPTICAL (unchanged)
- `noe_evn`: baudrate 2400, parity NONE, stopbits 1, bytesize 8

`config_validation.validate_config` grows a check: reject unknown
`meter_type` values; all other validation stays provider-agnostic.

The Home Assistant add-on `config.yaml` schema adds the `meter_type`
dropdown and documents the NOE-specific defaults.

## Data flow (NOE profile)

```
serial (2400 8N1)
  → NoeMeterReader: read bytes until a complete `68 LL LL 68 … 16` frame arrives
  → MBusFrame.parse(hex): extract system_title, frame_counter, ciphertext
  → aes_gcm_decrypt(ciphertext, key, system_title + frame_counter): APDU hex
  → GXDLMSTranslator.pduToXml(APDU)
  → obis.parse_xml(xml): OBIS→int dict
  → noe.MeterData(obis_values): applies scaling, exposes to_dict()
  → callback → SmartMeterDevice.publish_status
```

Decryption uses `pycryptodomex` (already transitively available as a
gurux_dlms dep on some platforms – we list it explicitly). Nonce is the
12-byte `system_title (8 bytes) || frame_counter (4 bytes)`, matching
DLMS Security Suite 0.

## Error handling

Two failure modes that are new for the NOE profile:

1. **Frame sync loss on M-Bus**: the read loop accumulates bytes until
   a `68 LL LL 68` start is found, then reads `LL + 6` bytes, then
   validates the trailing `16`. Out-of-sync data is discarded; the
   existing `MAX_CONSECUTIVE_FAILURES` counter is reused.
2. **Unknown APDU tag**: the reference script silently skips frames
   whose APDU does not start with `0f 80` (general-glo-ciphering). We
   do the same and log at DEBUG.

## Home Assistant sensors

Reuse `SensorSpec`/`SENSOR_SPECS` but make the catalog profile-specific:

- `bgld` profile: current catalog (incl. angles)
- `noe_evn` profile: voltage/current/power/energy + **power factor**;
  no angles

Device metadata also becomes profile-specific (`mf: "Sagemcom"`,
`mdl: "T210-D"`).

## Testing strategy

The transport layer cannot be unit-tested without hardware, but every
pure function can. TDD-testable pieces:

- OBIS dictionary (static mapping)
- M-Bus frame parser (hex in → header fields + ciphertext out)
- AES-GCM decrypt (pycryptodome round-trip with synthetic frame)
- OBIS XML parser (gurux XML fixture → dict)
- NOE MeterData (OBIS dict → scaled fields + to_dict)
- Config validation (meter_type accepted/rejected)
- Profile factory (returns NOE bundle for `noe_evn`)
- Sensor catalog (NOE catalog includes power_factor, not angles)

The `NoeMeterReader` serial loop is covered by a focused unit test that
feeds a pre-encrypted M-Bus frame through a stubbed `serial.Serial`
object.

## Out of scope

- Wien Netze / Kaifa on other grids – the profile abstraction makes
  this possible later but we do not add a third profile now.
- UI configuration flow (Home Assistant add-on schema is enough).
- Backfilling power-factor into the BGLD profile.

## Risks

- **No real hardware for validation.** The issue author offered debug
  logs; we ship the first cut behind the explicit opt-in
  `meter_type: noe_evn` and ask the reporter to verify. Unit tests
  cover the deterministic parsing/crypto layers so regressions are
  caught.
- **M-Bus frame size varies with firmware.** Reference implementation
  hard-codes 282 bytes; we instead read the length byte from the
  M-Bus header, which is the standards-compliant approach.
