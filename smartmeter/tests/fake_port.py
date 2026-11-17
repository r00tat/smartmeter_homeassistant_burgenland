"""A scripted serial port for the async readers.

``FakePort`` is a ``StreamOpener``: every ``open`` plays the next session.
A session is a list of steps:

- ``bytes``: the meter sends these bytes,
- ``float``: nothing arrives for that many seconds,
- ``EOF``: the port is closed underneath the reader,
- an ``Exception`` instance: the port fails with it.

After the last step the line stays silent. A session that is an exception
instance makes ``open`` itself fail (e.g. the port does not exist).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any

from meter.serial.transport import ByteStream, SerialSettings

EOF = object()

Step = bytes | float | object
Session = Sequence[Step] | BaseException

SETTINGS = SerialSettings(
    port="/dev/ttyFAKE", baudrate=9600, bytesize=8, parity="N", stopbits=1
)


class FakePort:
    def __init__(self, *sessions: Session) -> None:
        self.sessions = list(sessions)
        self.opened: list[SerialSettings] = []
        self.closed = 0
        self.is_open = False

    def __call__(self, settings: SerialSettings):
        return self._open(settings)

    @asynccontextmanager
    async def _open(self, settings: SerialSettings) -> AsyncIterator[ByteStream]:
        self.opened.append(settings)
        session = self.sessions.pop(0) if self.sessions else []
        if isinstance(session, BaseException):
            raise session
        stream = asyncio.StreamReader()
        feeder = asyncio.create_task(_feed(stream, session))
        self.is_open = True
        try:
            yield stream
        finally:
            feeder.cancel()
            await asyncio.wait({feeder})
            self.is_open = False
            self.closed += 1
            if not feeder.cancelled() and feeder.exception() is not None:
                raise AssertionError("bad FakePort script") from feeder.exception()


async def _feed(stream: asyncio.StreamReader, steps: Sequence[Step]) -> None:
    for step in steps:
        if isinstance(step, bytes):
            stream.feed_data(step)
            await asyncio.sleep(0)
        elif isinstance(step, float | int):
            await asyncio.sleep(step)
        elif step is EOF:
            stream.feed_eof()
        elif isinstance(step, BaseException):
            stream.set_exception(step)
        else:
            raise TypeError(f"unknown step {step!r}")


def chunks(data: bytes, size: int, pause: float = 0.0) -> list[Step]:
    """``data`` in pieces of ``size`` bytes, ``pause`` seconds apart."""
    steps: list[Step] = []
    for i in range(0, len(data), size):
        if steps and pause:
            steps.append(pause)
        steps.append(data[i : i + size])
    return steps


async def run_until(
    run: Callable[[], Any],
    done: Callable[[], bool],
    timeout: float = 3.0,
) -> asyncio.Task[Any]:
    """Run the coroutine ``run()`` until ``done()`` or it ends; return its task.

    The task is cancelled if it is still running, so the caller can check
    ``task.cancelled()`` (still running) or ``task.exception()`` (it failed).
    """
    task = asyncio.create_task(run())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not done() and not task.done():
        if loop.time() > deadline:
            task.cancel()
            await asyncio.wait({task})
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.005)
    if not task.done():
        task.cancel()
    await asyncio.wait({task})
    if not task.cancelled():
        task.exception()  # mark as retrieved; callers inspect it if they care
    return task
