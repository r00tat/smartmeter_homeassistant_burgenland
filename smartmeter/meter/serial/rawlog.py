"""Raw serial capture in the debug log, and turning it back into bytes.

With debug logging on, the transport logs every chunk the serial port
delivers on the logger ``meter.serial.raw``::

    rx +12.345s 24 bytes: 7ea08bceff0313ee...

``+12.345s`` is the time since the port was opened. Bytes and timing are
enough to replay exactly what the meter sent, including what a reader
dropped while looking for the start of a telegram. ``parse`` turns such
log lines back into ``(seconds, bytes)`` chunks, e.g. to build a test from
a bug report.
"""

from __future__ import annotations

import re

LOGGER_NAME = "meter.serial.raw"

_LINE = re.compile(r"rx \+(?P<at>\d+(?:\.\d+)?)s \d+ bytes: (?P<hex>[0-9a-fA-F]+)")


def format_chunk(seconds: float, data: bytes) -> str:
    """The log message for one received chunk."""
    return f"rx +{seconds:.3f}s {len(data)} bytes: {data.hex()}"


def parse(text: str) -> list[tuple[float, bytes]]:
    """Every ``rx`` chunk found in ``text`` (other lines are ignored).

    Works on whole log files: prefixes such as timestamps or logger names
    before ``rx`` do not matter.
    """
    return [
        (float(match["at"]), bytes.fromhex(match["hex"]))
        for match in _LINE.finditer(text)
    ]
