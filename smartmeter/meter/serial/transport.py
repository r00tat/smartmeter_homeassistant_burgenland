"""Open a serial port as an asyncio byte stream.

Every reader gets its bytes through ``open_serial``: the port is opened in
an executor (opening and configuring a tty can block), then the event
loop is told to call us back whenever bytes arrive. There is no read
timeout and no polling; a reader simply awaits the next chunk.

A port that disappears (USB adapter unplugged) ends the stream with an
error right away instead of after the next read timeout.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

import serial_asyncio_fast

log = logging.getLogger("meter.serial.transport")

# Upper bound for one ``read`` call; the meters push a few hundred bytes.
READ_CHUNK = 4096
# How long closing the port may take before we give up waiting.
CLOSE_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class SerialSettings:
    """Effective serial line settings: profile defaults plus user overrides."""

    port: str
    baudrate: int
    bytesize: int
    parity: str  # pyserial letter, e.g. "N" or "E"
    stopbits: int

    def describe(self) -> str:
        return f"{self.port} {self.baudrate} {self.bytesize}{self.parity}{self.stopbits}"


class ByteStream(Protocol):
    """The part of ``asyncio.StreamReader`` the readers use."""

    async def read(self, n: int = -1) -> bytes: ...

    async def readexactly(self, n: int) -> bytes: ...


StreamOpener = Callable[[SerialSettings], AbstractAsyncContextManager[ByteStream]]


class PortClosedError(ConnectionError):
    """The serial port delivered end-of-file: it was closed underneath us."""


async def read_some(stream: ByteStream, size: int = READ_CHUNK) -> bytes:
    """Wait for the next bytes on ``stream``; raise if the port went away."""
    chunk = await stream.read(size)
    if not chunk:
        raise PortClosedError("serial port closed")
    return chunk


async def read_exactly(stream: ByteStream, size: int) -> bytes:
    """Wait for exactly ``size`` bytes; raise if the port went away first."""
    try:
        return await stream.readexactly(size)
    except asyncio.IncompleteReadError as err:
        raise PortClosedError("serial port closed") from err


async def _close(writer: asyncio.StreamWriter) -> None:
    writer.close()
    # The transport closes the tty in an executor; wait for it so a reader
    # that is started right after (reload, restart) finds the port free.
    with contextlib.suppress(Exception):
        async with asyncio.timeout(CLOSE_TIMEOUT_SECONDS):
            await writer.wait_closed()


async def _open(settings: SerialSettings) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    return await serial_asyncio_fast.open_serial_connection(
        url=settings.port,
        baudrate=settings.baudrate,
        bytesize=settings.bytesize,
        parity=settings.parity,
        stopbits=settings.stopbits,
    )


@asynccontextmanager
async def open_serial(settings: SerialSettings) -> AsyncIterator[ByteStream]:
    """Open the port described by ``settings`` and close it on exit."""
    log.info("opening serial port %s", settings.describe())
    opening = asyncio.ensure_future(_open(settings))
    try:
        # Shielded: a cancelled open must still close the port the executor
        # thread opens anyway, otherwise the next attempt finds it busy.
        reader, writer = await asyncio.shield(opening)
    except asyncio.CancelledError:
        opening.add_done_callback(_close_when_opened)
        raise
    try:
        yield reader
    finally:
        log.debug("closing serial port %s", settings.port)
        await _close(writer)


@asynccontextmanager
async def periodically(interval: float, callback: Callable[[], None]) -> AsyncIterator[None]:
    """Call ``callback`` every ``interval`` seconds while the block runs."""

    async def loop() -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                callback()
            except Exception:
                log.exception("periodic callback failed")

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.wait({task})


def _close_when_opened(
    opening: asyncio.Future[tuple[asyncio.StreamReader, asyncio.StreamWriter]],
) -> None:
    if opening.cancelled() or opening.exception() is not None:
        return
    _, writer = opening.result()
    writer.close()
