"""Generic pipeline for meters that push encrypted DLMS or DSMR telegrams.

Used by the Steiermark, Salzburg, Tirol and Smart Meter 2.0 (H1) profiles::

    serial bytes → framing (M-Bus / HDLC / P1) → general-glo-ciphering
                 → AES-GCM → data-notification (A-XDR) or DSMR text
                 → OBIS registers → ObisMeterData

Every step is a pure function or a small stateful framer, so each layer is
unit-tested without a serial port. The serial shell lives in ``reader``.
"""
