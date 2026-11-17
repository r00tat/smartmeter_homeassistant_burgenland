"""Reader for DLMS data notifications in HDLC frames (Burgenland, Wien).

Two interfaces:

- **optical** (IR head): the meter pushes one telegram every few seconds
  and is silent in between. A telegram is complete once the line has been
  idle for ``OPTICAL_IDLE_GAP_SECONDS``.
- **physical** (wired customer interface): read until at least
  ``hdlc_frame_size`` bytes arrived.

Bytes are awaited, not polled: the reader wakes up when data arrives and
the idle gap is measured from the last byte, so a telegram cannot be cut
in two by the phase between a polling loop and the meter (#128).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ..bgld.data import MeterData
from ..dlms.read import parse_dlms_data, parse_pyhiscal_dlms_data, parse_xml
from ..meter_data import BaseMeterData
from .transport import ByteStream, SerialSettings, StreamOpener, open_serial, read_some

MAX_CONSECUTIVE_FAILURES = 10
# At 9600 baud a byte takes ~1 ms, USB-serial adapters add <= 16 ms.
OPTICAL_IDLE_GAP_SECONDS = 0.2
# Upper bound for collecting one telegram, so a constantly chattering line
# cannot keep the reader from ever handing data to the parser.
OPTICAL_MAX_FRAME_SECONDS = 3.0

# gurux reports some decoding problems with a bare ``Exception`` (e.g. a
# corrupted telegram on the optical head raises ``Exception("Wrong CRC.")``),
# so a single garbled telegram must not end the reader. Repeated failures
# still abort after MAX_CONSECUTIVE_FAILURES.
PARSE_ERRORS: tuple[type[Exception], ...] = (Exception,)

log = logging.getLogger("meter.serial.read")


class MeterReader:
    """Read DLMS/HDLC telegrams and hand the decoded values to ``data_factory``.

    ``data_factory`` maps the list of values in a data notification onto the
    meter profile's ``MeterData`` class (Burgenland by default).
    """

    def __init__(
        self,
        key: str,
        settings: SerialSettings,
        interface_type: str = "OPTICAL",
        hdlc_frame_size: int = 120,
        callback: Callable[[BaseMeterData], None] | None = None,
        data_factory: Callable[[list[Any]], BaseMeterData] = MeterData,
        open_stream: StreamOpener = open_serial,
    ) -> None:
        self.key = key
        self.settings = settings
        self.is_optical_interface = str(interface_type).upper() == "OPTICAL"
        self.hdlc_frame_size = hdlc_frame_size
        self.callback = callback
        self.data_factory = data_factory
        self._open_stream = open_stream

    async def run(self) -> None:
        """Read until cancelled; raise on a port error or repeated parse failures."""
        async with self._open_stream(self.settings) as stream:
            if self.is_optical_interface:
                await self._read_loop(
                    lambda: self.read_optical_frame(stream), self._handle_optical_frame
                )
            else:
                await self._read_loop(
                    lambda: self.read_physical_frame(stream), self._handle_physical_frame
                )

    async def read_optical_frame(self, stream: ByteStream) -> bytes:
        """Collect one telegram: everything until the line is idle."""
        loop = asyncio.get_running_loop()
        received = bytearray(await read_some(stream))
        deadline = loop.time() + OPTICAL_MAX_FRAME_SECONDS
        while True:
            left = deadline - loop.time()
            if left <= 0:
                log.warning(
                    "optical telegram exceeded %.1fs, parsing %d bytes received so far",
                    OPTICAL_MAX_FRAME_SECONDS,
                    len(received),
                )
                break
            try:
                async with asyncio.timeout(min(OPTICAL_IDLE_GAP_SECONDS, left)):
                    received += await read_some(stream)
            except TimeoutError:
                if left > OPTICAL_IDLE_GAP_SECONDS:
                    break  # line idle: telegram complete
        return bytes(received)

    async def read_physical_frame(self, stream: ByteStream) -> bytes:
        """Read at least ``hdlc_frame_size`` bytes."""
        received = bytearray()
        while len(received) < self.hdlc_frame_size:
            received += await read_some(stream)
        return bytes(received)

    async def _read_loop(
        self,
        read_frame: Callable[[], Awaitable[bytes]],
        handle: Callable[[bytes], None],
    ) -> None:
        failures = 0
        while True:
            received_data = await read_frame()
            log.debug("received: %s", received_data.hex())
            try:
                handle(received_data)
                failures = 0
            except PARSE_ERRORS as err:
                failures += 1
                log.exception("failed to parse data from serial port: %s", err)
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    log.error(
                        "exceeded %d consecutive parse failures, aborting",
                        MAX_CONSECUTIVE_FAILURES,
                    )
                    raise

    def _publish(self, values: list[Any]) -> None:
        data = self.data_factory(values)
        log.debug("received meter data: %s", data)
        if self.callback is not None:
            self.callback(data)

    def _handle_optical_frame(self, received_data: bytes) -> None:
        decrypted_data = parse_dlms_data(received_data, self.key)
        log.debug("values: %s", decrypted_data.value)
        if decrypted_data.value:
            self._publish(decrypted_data.value)

    def _handle_physical_frame(self, received_data: bytes) -> None:
        parsed_xml = parse_pyhiscal_dlms_data(received_data, self.key)
        log.debug("XML Result:\n%s", parsed_xml)
        if parsed_xml:
            values = parse_xml(parsed_xml)
            if values:
                self._publish(values)
