"""Tests for ``meter.supervisor``."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from meter.supervisor import ReaderSilentError, ReaderSupervisor, cancel_and_wait, probe
from tests.fake_port import run_until


class FakeReader:
    """Emits ``items`` (``float`` items are pauses), then fails or runs on."""

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
        self.started = False
        self.cancelled = False

    async def run(self) -> None:
        self.started = True
        try:
            for item in self.items:
                if isinstance(item, float):
                    await asyncio.sleep(item)
                else:
                    self.callback(item)
            if self.fail is not None:
                raise self.fail
            if self.block:
                await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class Readers:
    """Factory handing out readers built from ``specs`` (last one repeats)."""

    def __init__(self, *specs: dict[str, Any]) -> None:
        self.specs = list(specs) or [{}]
        self.created: list[FakeReader] = []

    def __call__(self, callback: Callable[[Any], None]) -> FakeReader:
        spec = self.specs[min(len(self.created), len(self.specs) - 1)]
        reader = FakeReader(callback, **spec)
        self.created.append(reader)
        return reader


def supervisor(readers: Readers, **kwargs: Any) -> tuple[ReaderSupervisor, list, list]:
    data: list[Any] = []
    errors: list[Exception] = []
    kwargs.setdefault("retry_seconds", 0.01)
    sup = ReaderSupervisor(readers, on_data=data.append, on_error=errors.append, **kwargs)
    return sup, data, errors


async def test_forwards_every_nth_reading() -> None:
    sup, data, errors = supervisor(Readers({"items": [0, 1, 2, 3, 4, 5]}), every=2)

    await run_until(sup.run, lambda: len(data) == 3)

    assert data == [0, 2, 4]
    assert errors == []


async def test_restarts_reader_after_failure() -> None:
    readers = Readers({"fail": OSError("port gone")}, {"items": ["ok"]})
    sup, data, errors = supervisor(readers)

    await run_until(sup.run, lambda: data == ["ok"])

    assert [str(err) for err in errors] == ["port gone"]
    assert len(readers.created) == 2


async def test_reader_that_returns_on_its_own_is_reported() -> None:
    sup, _, errors = supervisor(Readers({"block": False}))

    await run_until(sup.run, lambda: len(errors) >= 1)

    assert isinstance(errors[0], RuntimeError)


async def test_cancel_stops_the_reader_without_reporting_an_error() -> None:
    readers = Readers()
    sup, _, errors = supervisor(readers)
    task = asyncio.create_task(sup.run())
    while not (readers.created and readers.created[0].started):
        await asyncio.sleep(0)

    await cancel_and_wait(task)

    assert task.cancelled()
    assert readers.created[0].cancelled
    assert errors == []


def test_every_must_be_positive() -> None:
    with pytest.raises(ValueError):
        ReaderSupervisor(Readers(), lambda d: None, lambda e: None, every=0)


async def test_factory_failure_is_reported_and_retried() -> None:
    calls: list[int] = []

    def factory(cb: Callable[[Any], None]) -> FakeReader:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("cannot build")
        return FakeReader(cb)

    errors: list[Exception] = []
    sup = ReaderSupervisor(
        factory, on_data=lambda d: None, on_error=errors.append, retry_seconds=0.01
    )

    await run_until(sup.run, lambda: len(calls) >= 2)

    assert [str(err) for err in errors] == ["cannot build"]


async def test_failing_on_error_does_not_kill_the_supervisor() -> None:
    readers = Readers({"fail": OSError("boom")})

    def on_error(err: Exception) -> None:
        raise RuntimeError("callback bug")

    sup = ReaderSupervisor(readers, on_data=lambda d: None, on_error=on_error, retry_seconds=0.01)

    task = await run_until(sup.run, lambda: len(readers.created) >= 3)

    assert task.cancelled()  # still running, cancelled by the test


async def test_failing_on_data_does_not_reach_the_reader() -> None:
    seen: list[Any] = []
    errors: list[Exception] = []

    def on_data(data: Any) -> None:
        seen.append(data)
        raise RuntimeError("callback bug")

    readers = Readers({"items": [1, 2, 3]})
    sup = ReaderSupervisor(readers, on_data=on_data, on_error=errors.append)

    await run_until(sup.run, lambda: seen == [1, 2, 3])

    assert errors == []
    assert len(readers.created) == 1


async def test_counter_resets_for_every_new_reader() -> None:
    readers = Readers({"items": ["first"], "fail": OSError("gone")}, {"items": ["second"]})
    sup, data, _ = supervisor(readers, every=3)

    await run_until(sup.run, lambda: len(data) == 2)

    assert data == ["first", "second"]


async def test_silent_meter_is_reported_once_and_recovers() -> None:
    readers = Readers({"items": ["a", 0.15, "b"]})
    sup, data, errors = supervisor(readers, stale_after=0.05)

    await run_until(sup.run, lambda: data == ["a", "b"])

    assert len(errors) == 1
    assert isinstance(errors[0], ReaderSilentError)
    assert len(readers.created) == 1  # silence alone does not reopen the port


async def test_first_reading_after_silence_is_forwarded_right_away() -> None:
    readers = Readers({"items": ["a", "b", 0.1, "c", "d", "e", "f"]})
    sup, data, _ = supervisor(readers, stale_after=0.05, every=3)

    await run_until(sup.run, lambda: len(data) == 3)

    assert data == ["a", "c", "f"]


async def test_silence_is_reported_again_after_data_resumed() -> None:
    readers = Readers({"items": ["a", 0.1, "b", 0.1, "c"]})
    sup, data, errors = supervisor(readers, stale_after=0.05)

    await run_until(sup.run, lambda: data == ["a", "b", "c"])

    assert len(errors) == 2


async def test_hung_reader_is_restarted_without_an_error() -> None:
    readers = Readers({"items": ["a"]}, {"items": ["b"]})
    sup, data, errors = supervisor(readers, restart_after=0.05)

    await run_until(sup.run, lambda: data == ["a", "b"])

    assert readers.created[0].cancelled
    assert errors == []


async def test_restart_window_starts_again_with_each_reader() -> None:
    """A silent meter is reopened every ``restart_after``, not in a tight loop."""
    readers = Readers({})  # never delivers anything
    sup, _, _ = supervisor(readers, restart_after=0.05, retry_seconds=0.0)
    loop = asyncio.get_running_loop()
    end = loop.time() + 0.27

    await run_until(sup.run, lambda: loop.time() >= end)

    assert 3 <= len(readers.created) <= 6


async def test_stale_and_restart_together() -> None:
    readers = Readers({}, {}, {"items": ["late"]})
    sup, data, errors = supervisor(readers, stale_after=0.03, restart_after=0.06)

    await run_until(sup.run, lambda: data == ["late"])

    # Reported once while silent, not again for every reopened port.
    assert [type(err) for err in errors] == [ReaderSilentError]
    assert len(readers.created) == 3


async def test_probe_returns_first_reading() -> None:
    readers = Readers({"items": ["a", "b"]})

    assert await probe(readers, timeout=1.0) == "a"
    assert readers.created[0].cancelled


async def test_probe_raises_reader_error() -> None:
    with pytest.raises(OSError, match="no port"):
        await probe(Readers({"fail": OSError("no port")}), timeout=1.0)


async def test_probe_returns_none_on_timeout() -> None:
    readers = Readers()

    assert await probe(readers, timeout=0.05) is None
    assert readers.created[0].cancelled


async def test_probe_returns_none_when_reader_ends_without_data() -> None:
    assert await probe(Readers({"block": False}), timeout=1.0) is None


async def test_cancel_and_wait_does_not_swallow_the_callers_cancellation() -> None:
    inner = asyncio.create_task(asyncio.sleep(10))

    async def outer() -> None:
        await cancel_and_wait(inner)
        await asyncio.sleep(10)

    task = asyncio.create_task(outer())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.wait({task})

    assert inner.cancelled()
    assert task.cancelled()
