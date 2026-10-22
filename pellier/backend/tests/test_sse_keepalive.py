"""``with_heartbeat`` keeps a quiet SSE stream open through CloudFront and nginx.

CloudFront closes an origin response that sends nothing for its read timeout (60
seconds here), and it does not retry an interrupted POST. A managed chat turn
waits on the Runtime and an investigation on a model call, each longer than
that at worst, so a comment frame goes out whenever the stream is quiet.
"""
from __future__ import annotations

import asyncio
import contextvars
from typing import AsyncIterator, List

import pytest

from services import sse_keepalive
from services.sse_keepalive import HEARTBEAT, with_heartbeat


async def _collect(chunks: AsyncIterator[str]) -> List[str]:
    return [chunk async for chunk in chunks]


@pytest.mark.asyncio
async def test_a_quiet_gap_becomes_heartbeats_between_whole_frames() -> None:
    async def source() -> AsyncIterator[str]:
        yield "data: 1\n\n"
        await asyncio.sleep(0.35)
        yield "data: 2\n\n"

    out = await _collect(with_heartbeat(source(), seconds=0.1))
    assert out[0] == "data: 1\n\n" and out[-1] == "data: 2\n\n"
    assert set(out[1:-1]) == {HEARTBEAT} and len(out[1:-1]) >= 2


@pytest.mark.asyncio
async def test_a_busy_stream_gets_no_heartbeat() -> None:
    async def source() -> AsyncIterator[str]:
        for index in range(3):
            yield f"data: {index}\n\n"

    assert await _collect(with_heartbeat(source(), seconds=5)) == [
        "data: 0\n\n", "data: 1\n\n", "data: 2\n\n"]


@pytest.mark.asyncio
async def test_a_source_error_reaches_the_reader_after_its_frames() -> None:
    async def source() -> AsyncIterator[str]:
        yield "data: 1\n\n"
        raise RuntimeError("boom")

    seen: List[str] = []
    with pytest.raises(RuntimeError, match="boom"):
        async for chunk in with_heartbeat(source(), seconds=5):
            seen.append(chunk)
    assert seen == ["data: 1\n\n"]


@pytest.mark.asyncio
async def test_a_reader_that_leaves_closes_the_source() -> None:
    closed = asyncio.Event()

    async def source() -> AsyncIterator[str]:
        try:
            yield "data: 1\n\n"
            await asyncio.sleep(30)
            yield "data: 2\n\n"
        finally:
            closed.set()

    stream = with_heartbeat(source(), seconds=5)
    assert await stream.__anext__() == "data: 1\n\n"
    await stream.aclose()
    await asyncio.wait_for(closed.wait(), timeout=2)


@pytest.mark.asyncio
async def test_context_set_inside_the_source_can_be_reset_after_a_yield() -> None:
    """The chat generator sets its turn context, yields, then resets it: one task runs it."""
    turn: contextvars.ContextVar[str] = contextvars.ContextVar("turn", default="")

    async def source() -> AsyncIterator[str]:
        token = turn.set("turn-1")
        try:
            yield "data: 1\n\n"
            await asyncio.sleep(0.25)
            yield f"data: {turn.get()}\n\n"
        finally:
            turn.reset(token)

    out = await _collect(with_heartbeat(source(), seconds=0.1))
    assert out[0] == "data: 1\n\n" and out[-1] == "data: turn-1\n\n"


def test_the_default_gap_is_well_inside_cloudfronts_read_timeout() -> None:
    assert sse_keepalive.HEARTBEAT_SECONDS <= 20
