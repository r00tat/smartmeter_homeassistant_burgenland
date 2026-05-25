# Implementation Plan: Netz NÖ Sagemcom T210-D Support

Companion to [design doc](2026-04-17-netz-noe-sagemcom-t210d-design.md).

TDD discipline: every production file listed below is created RED → GREEN → REFACTOR. No production code without a failing test first.

## Sequence

### Phase 1 – pure logic (fully test-driven, fully testable)

1. **OBIS dictionary** – `meter/noe/obis.py::OBIS_TO_FIELD`
   - Test: dictionary contains the 11 codes the T210-D publishes and maps each to the expected field name.

2. **M-Bus frame parser** – `meter/noe/mbus.py::MBusFrame.parse(hex)`
   - Test (happy path): known hex → system_title, frame_counter, ciphertext extracted at documented offsets.
   - Test (bad start): hex not starting with `68` raises `MBusFrameError`.
   - Test (trailer missing): hex missing `16` trailer raises `MBusFrameError`.
   - Test (length mismatch): declared length byte inconsistent with payload raises.

3. **AES-GCM decrypt** – `meter/noe/decrypt.py::aes_gcm_decrypt(ciphertext, key, nonce)`
   - Test: round-trip – encrypt a known plaintext with pycryptodomex GCM and the helper decrypts it back.
   - Test: wrong key raises `DecryptionError`.

4. **OBIS XML parser** – `meter/noe/obis.py::parse_obis_xml(xml)`
   - Test: synthetic gurux-style XML (`<OctetString … /><UInt32 …/>`) with a subset of OBIS codes returns the expected `{field: int}` dict.
   - Test: unknown OBIS codes ignored.

5. **MeterData (NOE)** – `meter/noe/data.py::MeterData`
   - Test: to_dict applies voltage ·0.1, current ·0.01, pf ·0.001 scaling; energy stays in Wh.
   - Test: partial input (some OBIS missing) defaults to 0.
   - Test: to_json round-trips.

### Phase 2 – end-to-end fixture (explicit user request)

6. **Integration test** – `tests/test_noe_pipeline.py`
   - Build a known DLMS APDU (with `0f 80` general-glo-ciphering header and several OBIS octet strings encoding voltages, currents, power, energy, power factor).
   - AES-GCM-encrypt it with a known test key and nonce (system_title + frame_counter).
   - Wrap the ciphertext in a valid M-Bus long frame (`68 LL LL 68 … checksum 16`).
   - Feed the hex through the chain: `MBusFrame.parse` → `aes_gcm_decrypt` → `GXDLMSTranslator.pduToXml` → `parse_obis_xml` → `noe.MeterData`.
   - Assert the final `MeterData` fields match the plaintext values used to build the fixture.
   - Serialize the fixture hex into `tests/fixtures/noe_sample_frame.hex` so it is human-inspectable and regressable.

### Phase 3 – config + wiring (mixed TDD / integration)

7. **Config validation** – extend `meter/config_validation.py`
   - Test: `meter_type: noe_evn` accepted; unknown values rejected; missing `meter_type` defaults to `burgenland`.

8. **Profile registry** – `meter/profile.py`
   - Test: `get_profile("burgenland")` returns BGLD bundle; `get_profile("noe_evn")` returns NOE bundle; unknown raises.

9. **Sensor catalog split** – refactor `meter/mqtt/device.py`
   - Move BGLD-specific specs behind a profile-provided list; add NOE catalog with power_factor, voltage, current, power, energy (no angles).
   - Test: NOE catalog has a `_power_factor` suffix; has no `_angle_*` suffix. BGLD catalog keeps angles.

10. **Wire into `SmartMqttMeter`** – `meter/smartmeter.py`
    - Dispatch reader construction via profile.
    - Test: with `meter_type: noe_evn`, the reader is a `NoeMeterReader` and the device metadata has manufacturer `Sagemcom`, model `T210-D`.

### Phase 4 – serial loop (write test with stubbed Serial, accept hardware verification needed)

11. **NoeMeterReader** – `meter/noe/read.py`
    - Test: fed a `FakeSerial` that yields a pre-encrypted M-Bus frame in chunks, the reader assembles it, decrypts, parses, and invokes the callback with the expected `MeterData`.
    - Document in the reader that fault recovery (sleep/reopen) mirrors the reference implementation but cannot be unit-tested.

### Phase 5 – add-on surface

12. **Addon `config.yaml`**: add `meter_type` option + schema.
13. **Config template** (`smartmeter-config-template.yaml`): document `meter_type` and NOE defaults.
14. **README.md + DOCS.md**: new section "Netz NÖ / EVN Sagemcom T210-D".
15. **requirements.txt**: add `pycryptodomex` (AES-GCM).

### Phase 6 – verification

16. `pytest smartmeter/tests -q` (all green).
17. `ruff check smartmeter`.
18. `mypy` against `smartmeter/meter`.
19. Commit on current branch with a single descriptive commit message.

## Files created

```
docs/plans/2026-04-17-netz-noe-sagemcom-t210d-design.md    # (this commit)
docs/plans/2026-04-17-netz-noe-sagemcom-t210d-plan.md      # (this commit)
smartmeter/meter/noe/__init__.py
smartmeter/meter/noe/mbus.py
smartmeter/meter/noe/decrypt.py
smartmeter/meter/noe/obis.py
smartmeter/meter/noe/data.py
smartmeter/meter/noe/read.py
smartmeter/meter/profile.py
smartmeter/tests/fixtures/__init__.py
smartmeter/tests/fixtures/noe_sample_frame.py              # helper to (re)build the test frame
smartmeter/tests/fixtures/noe_sample_frame.hex             # the generated hex (committed)
smartmeter/tests/test_noe_mbus.py
smartmeter/tests/test_noe_decrypt.py
smartmeter/tests/test_noe_obis.py
smartmeter/tests/test_noe_data.py
smartmeter/tests/test_noe_pipeline.py
smartmeter/tests/test_noe_reader.py
smartmeter/tests/test_profile.py
```

## Files modified

```
smartmeter/meter/smartmeter.py        # profile dispatch
smartmeter/meter/config_validation.py # meter_type validation
smartmeter/meter/mqtt/device.py       # accept sensor catalog + device meta from profile
smartmeter/tests/test_config_validation.py
smartmeter/tests/test_sensor_catalog.py
smartmeter/config.yaml                # addon schema
smartmeter/smartmeter-config-template.yaml
smartmeter/requirements.txt
README.md
smartmeter/DOCS.md
```

## Rollback strategy

The `meter_type` default stays `burgenland`, so existing deployments
see identical behaviour. If the NOE profile misbehaves, a hotfix
can make `get_profile("noe_evn")` raise a clear "not yet supported"
error without touching the burgenland code path.
