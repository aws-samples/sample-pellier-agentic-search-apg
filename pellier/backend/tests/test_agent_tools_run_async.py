"""``agent_tools._run_async``: a sync bridge that never blocks a loop on itself."""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading

import pytest

from services import agent_tools


def test_calling_from_a_running_loop_raises_instead_of_deadlocking(monkeypatch) -> None:
    monkeypatch.setattr(agent_tools, "_main_loop", None)

    async def inner() -> int:
        return 1

    async def caller() -> None:
        coro = inner()
        try:
            agent_tools._run_async(coro)
        finally:
            coro.close()

    with pytest.raises(RuntimeError, match="running event loop"):
        asyncio.run(asyncio.wait_for(caller(), timeout=5))


def test_a_timed_out_main_loop_call_is_cancelled(monkeypatch) -> None:
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    cancelled = threading.Event()

    async def never() -> None:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(agent_tools, "_main_loop", loop)
    monkeypatch.setattr(agent_tools, "_RUN_ASYNC_TIMEOUT_SECONDS", 0.2)
    try:
        with pytest.raises(concurrent.futures.TimeoutError):
            agent_tools._run_async(never())
        assert cancelled.wait(2.0), "the timed-out coroutine kept running"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(2.0)
        loop.close()
