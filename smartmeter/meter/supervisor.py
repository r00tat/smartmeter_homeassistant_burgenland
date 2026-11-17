"""Keep a meter reader running on the event loop.

``ReaderSupervisor.run`` is the one place that decides what happens when a
reader fails or goes quiet, for the add-on and the Home Assistant
integration alike:

- a reader that raises (port gone, too many garbled telegrams) or returns
  is reported through ``on_error`` and replaced after ``retry_seconds``;
- no telegram for ``stale_after`` seconds is reported once through
  ``on_error`` (the readings are outdated, the sensors go unavailable);
- no telegram for ``restart_after`` seconds reopens the port, for a USB
  adapter that hangs without closing the port.

Cancelling ``run`` stops the reader and closes the port. Nothing in here
depends on Home Assistant; all callbacks run on the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from .profile import MeterDataCallback, MeterReaderLike

log = logging.getLogger("meter.supervisor")

ReaderFactory = Callable[[MeterDataCallback], MeterReaderLike]


class ReaderSilentError(TimeoutError):
    """No telegram arrived within the configured time."""


async def cancel_and_wait(task: asyncio.Task[Any]) -> None:
    """Cancel ``task`` and wait until it finished.

    Unlike ``await task`` this does not swallow a cancellation of the
    caller itself, and it retrieves the task's exception so asyncio does
    not log it as never retrieved.
    """
    task.cancel()
    await asyncio.wait({task})
    if not task.cancelled():
        task.exception()


class ReaderSupervisor:
    """Run one reader at a time until cancelled.

    ``on_data`` receives every ``every``-th reading (the count starts again
    with each new reader and after a silence), ``on_skipped`` the readings in
    between (e.g. to log them), ``on_error`` every failure.
    """

    def __init__(
        self,
        reader_factory: ReaderFactory,
        on_data: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        every: int = 1,
        retry_seconds: float = 10.0,
        stale_after: float | None = None,
        restart_after: float | None = None,
        on_skipped: Callable[[Any], None] | None = None,
    ) -> None:
        if every < 1:
            raise ValueError("every must be >= 1")
        self._factory = reader_factory
        self._on_data = on_data
        self._on_error = on_error
        self._on_skipped = on_skipped
        self._every = every
        self._retry_seconds = retry_seconds
        self._stale_after = stale_after
        self._restart_after = restart_after
        self._count = 0
        self._last_data = 0.0
        self._reader_started = 0.0
        self._stale = False
        # Set when data ends a silence, so the watchdog arms its timer again.
        self._resumed = asyncio.Event()

    async def run(self) -> None:
        """Supervise readers until cancelled."""
        loop = asyncio.get_running_loop()
        self._last_data = loop.time()
        while True:
            error = await self._run_reader()
            if error is not None:
                self._report(error)
            await asyncio.sleep(self._retry_seconds)

    async def _run_reader(self) -> Exception | None:
        """Run one reader; return the error to report (``None`` for a restart)."""
        self._count = 0
        self._reader_started = asyncio.get_running_loop().time()
        try:
            reader = self._factory(self._handle)
        except Exception as err:
            log.warning("cannot create meter reader: %s", err, exc_info=True)
            return err
        task = asyncio.create_task(reader.run(), name="smartmeter-reader")
        try:
            await self._watch(task)
        except ReaderSilentError as err:
            log.warning("restarting meter reader: %s", err)
            return None
        except Exception as err:  # any reader fault leads to a new reader
            log.warning("meter reader failed: %s", err, exc_info=True)
            return err
        finally:
            await cancel_and_wait(task)
        return RuntimeError("meter reader stopped unexpectedly")

    async def _watch(self, task: asyncio.Task[None]) -> None:
        """Wait for ``task``, report silence and raise when the port must reopen."""
        loop = asyncio.get_running_loop()
        while True:
            self._resumed.clear()
            resumed = asyncio.create_task(self._resumed.wait())
            try:
                await asyncio.wait(
                    {task, resumed},
                    timeout=self._next_check(loop.time()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                await cancel_and_wait(resumed)
            if task.done():
                if task.cancelled():
                    raise RuntimeError("meter reader was cancelled")
                task.result()
                return
            now = loop.time()
            silent = now - self._last_data
            if (
                self._stale_after is not None
                and not self._stale
                and silent >= self._stale_after
            ):
                self._stale = True
                self._report(ReaderSilentError(f"no telegram for {silent:.1f} s"))
            if (
                self._restart_after is not None
                and now - max(self._last_data, self._reader_started) >= self._restart_after
            ):
                raise ReaderSilentError(f"no telegram for {silent:.1f} s")

    def _next_check(self, now: float) -> float | None:
        """Seconds until the watchdog has something to decide, ``None`` if never."""
        deadlines = []
        if self._stale_after is not None and not self._stale:
            deadlines.append(self._last_data + self._stale_after)
        if self._restart_after is not None:
            deadlines.append(max(self._last_data, self._reader_started) + self._restart_after)
        if not deadlines:
            return None
        return max(0.0, min(deadlines) - now)

    def _report(self, error: Exception) -> None:
        try:
            self._on_error(error)
        except Exception:
            log.exception("on_error callback failed")

    def _handle(self, data: Any) -> None:
        self._last_data = asyncio.get_running_loop().time()
        if self._stale:
            # Forward the first reading after a silence right away, so the
            # sensors do not stay unavailable until the next n-th reading.
            self._stale = False
            self._count = 0
            self._resumed.set()
        callback = self._on_data if self._count % self._every == 0 else self._on_skipped
        self._count += 1
        if callback is None:
            return
        try:
            callback(data)
        except Exception:
            # Must not reach the reader, which counts exceptions as parse failures.
            log.exception("meter data callback failed")


async def probe(reader_factory: ReaderFactory, timeout: float) -> Any | None:
    """Run a reader until the first reading or ``timeout`` seconds.

    Returns the first reading, ``None`` on timeout, and re-raises the
    reader's exception if it failed before delivering anything (e.g. the
    serial port does not exist). The port is closed when this returns.
    """
    first: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

    def on_data(data: Any) -> None:
        if not first.done():
            first.set_result(data)

    reader = reader_factory(on_data)
    task = asyncio.create_task(reader.run(), name="smartmeter-probe")
    try:
        await asyncio.wait({task, first}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
    finally:
        first.cancel()
        await cancel_and_wait(task)
    if first.done() and not first.cancelled():
        return first.result()
    error = None if task.cancelled() else task.exception()
    if error is not None:
        raise error
    return None
