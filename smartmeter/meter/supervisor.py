"""Run a meter reader in a background thread and restart it after failures.

Used by the Home Assistant integration, which cannot let a reader fault end
the process the way the add-on does. Nothing in here depends on Home
Assistant; the integration passes thread-safe callbacks.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from .profile import MeterDataCallback, MeterReaderLike

log = logging.getLogger("meter.supervisor")

ReaderFactory = Callable[[MeterDataCallback], MeterReaderLike]


class ReaderSupervisor:
    """Keep one reader running until ``stop()``.

    ``on_data`` receives every ``every``-th reading, ``on_error`` every
    reader failure (including a reader that returns without being stopped).
    Both are called from the reader thread.
    """

    def __init__(
        self,
        reader_factory: ReaderFactory,
        on_data: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        every: int = 1,
        retry_seconds: float = 10.0,
    ) -> None:
        if every < 1:
            raise ValueError("every must be >= 1")
        self._factory = reader_factory
        self._on_data = on_data
        self._on_error = on_error
        self._every = every
        self._retry_seconds = retry_seconds
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._reader: MeterReaderLike | None = None
        self._thread: threading.Thread | None = None
        self._count = 0
        self._restart_reason: str | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("supervisor already started")
        self._thread = threading.Thread(
            target=self._run, name="smartmeter-reader", daemon=True
        )
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the reader and wait for the thread. Safe to call twice.

        Blocks for up to ``timeout`` seconds, so do not call it on an asyncio
        event loop (use an executor). A stopped supervisor cannot be
        restarted; create a new one.
        """
        self._stop.set()
        with self._lock:
            reader = self._reader
        if reader is not None:
            reader.stop()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                log.warning("reader thread did not exit within %.0fs", timeout)

    def restart(self, reason: str) -> None:
        """Stop the current reader so the loop opens the port again.

        For a reader that runs but delivers nothing (e.g. a hung USB
        adapter); the next reader starts after ``retry_seconds``.
        """
        with self._lock:
            reader = self._reader
            if reader is None or self._stop.is_set():
                return
            self._restart_reason = reason
        log.warning("restarting meter reader: %s", reason)
        reader.stop()

    def _run(self) -> None:
        while not self._stop.is_set():
            error: Exception | None = None
            try:
                with self._lock:
                    if self._stop.is_set():
                        break
                    self._count = 0
                    reader = self._factory(self._handle)
                    self._reader = reader
                reader.start()
                if not self._stop.is_set() and self._restart_reason is None:
                    error = RuntimeError("meter reader stopped unexpectedly")
            except Exception as err:  # any reader fault must lead to a restart
                log.warning("meter reader failed: %s", err, exc_info=True)
                error = err
            finally:
                with self._lock:
                    self._reader = None
                    self._restart_reason = None
            if error is not None and not self._stop.is_set():
                try:
                    self._on_error(error)
                except Exception:
                    log.exception("on_error callback failed")
            self._stop.wait(self._retry_seconds)

    def _handle(self, data: Any) -> None:
        if self._stop.is_set():
            return
        if self._count % self._every == 0:
            try:
                self._on_data(data)
            except Exception:
                # Must not reach the reader, which counts exceptions as parse failures.
                log.exception("on_data callback failed")
        self._count += 1


def probe(reader_factory: ReaderFactory, timeout: float) -> Any | None:
    """Run a reader until the first reading or ``timeout`` seconds.

    Returns the first reading, ``None`` on timeout, and re-raises the
    reader's exception if it failed before delivering anything (e.g. the
    serial port does not exist).

    Blocks for up to ``timeout`` plus a few seconds, so do not call it on an
    asyncio event loop (use an executor).
    """
    received: list[Any] = []
    errors: list[Exception] = []
    done = threading.Event()

    def on_data(data: Any) -> None:
        if not received:
            received.append(data)
        done.set()

    reader = reader_factory(on_data)

    def run() -> None:
        try:
            reader.start()
        except Exception as err:  # reported to the caller below
            errors.append(err)
        finally:
            done.set()

    thread = threading.Thread(target=run, name="smartmeter-probe", daemon=True)
    thread.start()
    done.wait(timeout)
    reader.stop()
    thread.join(timeout=5.0)
    if thread.is_alive():
        log.warning("probe thread did not exit after stop()")
    if received:
        return received[0]
    if errors:
        raise errors[0]
    return None
