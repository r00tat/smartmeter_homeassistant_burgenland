"""Tests for ``meter.supervisor``."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from meter.supervisor import ReaderSupervisor, probe


class FakeReader:
    """Emits ``items``, then raises ``fail`` or blocks until stopped."""

    def __init__(
        self,
        callback: Callable[[Any], None],
        items: list[Any] | None = None,
        fail: Exception | None = None,
        block: bool = True,
    ) -> None:
        self.callback = callback
        self.items = items or []
        self.fail = fail
        self.block = block
        self.stopped = threading.Event()
        self.started = threading.Event()

    def start(self) -> None:
        self.started.set()
        for item in self.items:
            self.callback(item)
        if self.fail is not None:
            raise self.fail
        if self.block:
            self.stopped.wait(5)

    def stop(self) -> None:
        self.stopped.set()


def wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_forwards_every_nth_reading() -> None:
    data: list[Any] = []
    supervisor = ReaderSupervisor(
        lambda cb: FakeReader(cb, items=[0, 1, 2, 3, 4, 5]),
        on_data=data.append,
        on_error=lambda err: None,
        every=2,
    )
    supervisor.start()
    assert wait_for(lambda: len(data) == 3)
    supervisor.stop()
    assert data == [0, 2, 4]


def test_restarts_reader_after_failure() -> None:
    data: list[Any] = []
    errors: list[Exception] = []
    readers = iter(
        [
            lambda cb: FakeReader(cb, fail=OSError("port gone")),
            lambda cb: FakeReader(cb, items=["ok"]),
        ]
    )
    supervisor = ReaderSupervisor(
        lambda cb: next(readers)(cb),
        on_data=data.append,
        on_error=errors.append,
        retry_seconds=0.01,
    )
    supervisor.start()
    assert wait_for(lambda: data == ["ok"])
    supervisor.stop()
    assert [str(err) for err in errors] == ["port gone"]


def test_reader_that_returns_on_its_own_is_reported() -> None:
    errors: list[Exception] = []
    supervisor = ReaderSupervisor(
        lambda cb: FakeReader(cb, block=False),
        on_data=lambda data: None,
        on_error=errors.append,
        retry_seconds=0.01,
    )
    supervisor.start()
    assert wait_for(lambda: len(errors) >= 1)
    supervisor.stop()
    assert isinstance(errors[0], RuntimeError)


def test_stop_ends_thread_without_reporting_an_error() -> None:
    errors: list[Exception] = []
    created: list[FakeReader] = []

    def factory(cb: Callable[[Any], None]) -> FakeReader:
        reader = FakeReader(cb)
        created.append(reader)
        return reader

    supervisor = ReaderSupervisor(factory, on_data=lambda data: None, on_error=errors.append)
    supervisor.start()
    assert wait_for(lambda: bool(created) and created[0].started.is_set())
    began = time.monotonic()
    supervisor.stop()
    assert time.monotonic() - began < 1.0
    assert not supervisor.is_running()
    assert created[0].stopped.is_set()
    assert errors == []


def test_every_must_be_positive() -> None:
    with pytest.raises(ValueError):
        ReaderSupervisor(lambda cb: FakeReader(cb), lambda d: None, lambda e: None, every=0)


def test_probe_returns_first_reading() -> None:
    assert probe(lambda cb: FakeReader(cb, items=["a", "b"]), timeout=1.0) == "a"


def test_probe_raises_reader_error() -> None:
    with pytest.raises(OSError, match="no port"):
        probe(lambda cb: FakeReader(cb, fail=OSError("no port")), timeout=1.0)


def test_probe_returns_none_on_timeout() -> None:
    created: list[FakeReader] = []

    def factory(cb: Callable[[Any], None]) -> FakeReader:
        reader = FakeReader(cb)
        created.append(reader)
        return reader

    assert probe(factory, timeout=0.05) is None
    assert created[0].stopped.is_set()


def test_factory_failure_is_reported_and_retried() -> None:
    errors: list[Exception] = []
    calls: list[int] = []

    def factory(cb: Callable[[Any], None]) -> FakeReader:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("cannot build")
        return FakeReader(cb)

    supervisor = ReaderSupervisor(
        factory, on_data=lambda d: None, on_error=errors.append, retry_seconds=0.01
    )
    supervisor.start()
    assert wait_for(lambda: len(calls) >= 2)
    supervisor.stop()
    assert [str(err) for err in errors] == ["cannot build"]


def test_failing_on_error_does_not_kill_the_supervisor() -> None:
    calls: list[int] = []

    def factory(cb: Callable[[Any], None]) -> FakeReader:
        calls.append(1)
        return FakeReader(cb, fail=OSError("boom"))

    def on_error(err: Exception) -> None:
        raise RuntimeError("event loop closed")

    supervisor = ReaderSupervisor(
        factory, on_data=lambda d: None, on_error=on_error, retry_seconds=0.01
    )
    supervisor.start()
    assert wait_for(lambda: len(calls) >= 2)
    assert supervisor.is_running()
    supervisor.stop()


def test_failing_on_data_does_not_reach_the_reader() -> None:
    seen: list[Any] = []
    errors: list[Exception] = []

    def on_data(data: Any) -> None:
        seen.append(data)
        raise RuntimeError("callback bug")

    supervisor = ReaderSupervisor(
        lambda cb: FakeReader(cb, items=[1, 2, 3]), on_data=on_data, on_error=errors.append
    )
    supervisor.start()
    assert wait_for(lambda: seen == [1, 2, 3])
    assert supervisor.is_running()
    supervisor.stop()
    assert errors == []


def test_counter_resets_for_every_new_reader() -> None:
    data: list[Any] = []
    readers = iter(
        [
            lambda cb: FakeReader(cb, items=["first"], fail=OSError("gone")),
            lambda cb: FakeReader(cb, items=["second"]),
        ]
    )
    supervisor = ReaderSupervisor(
        lambda cb: next(readers)(cb),
        on_data=data.append,
        on_error=lambda err: None,
        every=3,
        retry_seconds=0.01,
    )
    supervisor.start()
    assert wait_for(lambda: len(data) == 2)
    supervisor.stop()
    assert data == ["first", "second"]


def test_no_data_forwarded_after_stop() -> None:
    data: list[Any] = []
    callbacks: list[Callable[[Any], None]] = []

    def factory(cb: Callable[[Any], None]) -> FakeReader:
        callbacks.append(cb)
        return FakeReader(cb)

    supervisor = ReaderSupervisor(factory, on_data=data.append, on_error=lambda err: None)
    supervisor.start()
    assert wait_for(lambda: bool(callbacks))
    supervisor.stop()
    callbacks[0]("late")
    assert data == []
