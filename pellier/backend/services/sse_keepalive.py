"""Keep a quiet server-sent-event stream open through CloudFront and nginx.

CloudFront closes an origin response that sends nothing for its read timeout,
60 seconds on the workshop's distribution, and does not retry an interrupted
POST. Some streams wait longer than that between frames: a managed chat turn
waits for the whole Runtime answer, and an Operator investigation for one model
call. ``with_heartbeat`` sends an SSE comment whenever the stream has been quiet
for ``HEARTBEAT_SECONDS``; every reader of these streams ignores comment lines.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

HEARTBEAT_SECONDS = 15.0
HEARTBEAT = ": keep-alive\n\n"

_DONE = object()


class _Failed:
    def __init__(self, error: BaseException) -> None:
        self.error = error


async def with_heartbeat(
    chunks: AsyncIterator[str], *, seconds: Optional[float] = None
) -> AsyncIterator[str]:
    """Yield ``chunks`` unchanged, with a heartbeat between them while the source is quiet.

    The source runs whole in one task, so context it sets before a yield is
    still its own after it, and a heartbeat only ever falls between two whole
    frames. A source error reaches the reader after the frames before it; a
    reader that leaves closes the source.

    Args:
        chunks: The SSE frames to relay, each a complete frame.
        seconds: The longest quiet gap; ``HEARTBEAT_SECONDS`` when omitted.
    """
    gap = HEARTBEAT_SECONDS if seconds is None else seconds
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)

    async def pump() -> None:
        iterator = chunks.__aiter__()
        try:
            async for chunk in iterator:
                await queue.put(chunk)
            await queue.put(_DONE)
        except Exception as error:  # noqa: BLE001 - handed to the reader, not swallowed
            await queue.put(_Failed(error))
        finally:
            close = getattr(iterator, "aclose", None)
            if close is not None:
                await close()

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=gap)
            except asyncio.TimeoutError:
                yield HEARTBEAT
                continue
            if item is _DONE:
                return
            if isinstance(item, _Failed):
                raise item.error
            yield item
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
