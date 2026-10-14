"""Carry the turns a shopper sends from the terminal to their own Ask Pellier panel.

``scripts/lab_run.py send`` marks each workshop request ``source: "terminal"``. The
chat route passes that turn's SSE chunks through :func:`relay_turn_chunks`, which
copies every event into the relay under the verified Cognito ``sub``;
``GET /api/chat/watch`` streams the same shopper's channel with
:func:`watch_stream`: the recent turns first, then each new one live.

The backend runs as one uvicorn worker, so one process holds every turn and every
watcher. A restart empties the relay; each lab sends its requests after its
restart, so the labs' turns survive. Nothing here can change or delay a turn: a
relay failure is logged and the turn's own stream continues untouched.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Deque, Dict, Iterator, List, Optional, Set

logger = logging.getLogger(__name__)

KEEP_TURNS = 3
KEEP_SECONDS = 30 * 60
MAX_TURN_BYTES = 2 * 1024 * 1024
MAX_SUBSCRIBERS = 5
QUEUE_SIZE = 1000
HEARTBEAT_SECONDS = 15.0
HEARTBEAT = ": keep-alive\n\n"
TOO_MANY_WATCHERS = ": too many watchers\n\n"

# A watcher's queue carries frames, or None: "you were dropped, reconnect".
Frame = Optional[Dict[str, Any]]


@dataclass
class _Turn:
    header: Dict[str, Any]
    events: List[Dict[str, Any]] = field(default_factory=list)
    size: int = 0
    full: bool = False
    outcome: Optional[str] = None
    ended_at: Optional[float] = None

    @property
    def turn_id(self) -> str:
        return str(self.header["turn_id"])


class TurnRelay:
    """Per-shopper channels of terminal-sent turns, keyed by the verified ``sub``."""

    def __init__(self, *, keep_turns: int = KEEP_TURNS, keep_seconds: float = KEEP_SECONDS,
                 max_turn_bytes: int = MAX_TURN_BYTES, max_subscribers: int = MAX_SUBSCRIBERS,
                 queue_size: int = QUEUE_SIZE,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._keep_turns = keep_turns
        self._keep_seconds = keep_seconds
        self._max_turn_bytes = max_turn_bytes
        self._max_subscribers = max_subscribers
        self._queue_size = queue_size
        self._clock = clock
        self._turns: Dict[str, Deque[_Turn]] = {}
        self._watchers: Dict[str, Set["asyncio.Queue[Frame]"]] = {}

    # -- publishing ---------------------------------------------------------

    def start_turn(self, sub: str, *, turn_id: str, session_id: Optional[str], message: str,
                   started_at: str) -> None:
        header = {"type": "relay_turn", "turn_id": turn_id, "session_id": session_id,
                  "message": message, "source": "terminal", "started_at": started_at}
        turns = self._turns.setdefault(sub, deque())
        turns.append(_Turn(header=header))
        self._prune(sub)
        self._push(sub, header)

    def add_event(self, sub: str, turn_id: str, event: Dict[str, Any]) -> None:
        turn = self._find(sub, turn_id)
        if turn is None:
            return
        size = len(json.dumps(event, ensure_ascii=False, default=str))
        if not turn.full and turn.size + size <= self._max_turn_bytes:
            turn.events.append(event)
            turn.size += size
        else:
            turn.full = True
        self._push(sub, {"type": "relay_event", "turn_id": turn_id, "event": event})

    def end_turn(self, sub: str, turn_id: str, outcome: str) -> None:
        turn = self._find(sub, turn_id)
        if turn is None:
            return
        turn.outcome = outcome
        turn.ended_at = self._clock()
        self._push(sub, {"type": "relay_end", "turn_id": turn_id, "outcome": outcome})

    # -- watching -----------------------------------------------------------

    def subscribe(self, sub: str) -> "Optional[asyncio.Queue[Frame]]":
        """A queue of this shopper's live frames, or None when they have the most watchers."""
        watchers = self._watchers.setdefault(sub, set())
        if len(watchers) >= self._max_subscribers:
            return None
        queue: "asyncio.Queue[Frame]" = asyncio.Queue(maxsize=self._queue_size)
        watchers.add(queue)
        return queue

    def unsubscribe(self, sub: str, queue: "asyncio.Queue[Frame]") -> None:
        self._watchers.get(sub, set()).discard(queue)

    def watchers(self, sub: str) -> int:
        return len(self._watchers.get(sub, set()))

    def replay(self, sub: str) -> List[Dict[str, Any]]:
        """The retained turns as frames, oldest first, each ``relay_turn`` marked ``replay``."""
        self._prune(sub)
        frames: List[Dict[str, Any]] = []
        for turn in self._turns.get(sub, ()):
            frames.append({**turn.header, "replay": True})
            frames.extend({"type": "relay_event", "turn_id": turn.turn_id, "event": event}
                          for event in _replayable(turn.events))
            if turn.outcome is not None:
                frames.append({"type": "relay_end", "turn_id": turn.turn_id,
                               "outcome": turn.outcome})
        return frames

    # -- internals ----------------------------------------------------------

    def _find(self, sub: str, turn_id: str) -> Optional[_Turn]:
        for turn in reversed(self._turns.get(sub, ())):
            if turn.turn_id == turn_id:
                return turn
        return None

    def _prune(self, sub: str) -> None:
        turns = self._turns.get(sub)
        if not turns:
            return
        now = self._clock()
        kept = [turn for turn in turns
                if turn.ended_at is None or now - turn.ended_at <= self._keep_seconds]
        self._turns[sub] = deque(kept[-self._keep_turns:])

    def _push(self, sub: str, frame: Dict[str, Any]) -> None:
        for queue in list(self._watchers.get(sub, ())):
            try:
                queue.put_nowait(frame)
            except asyncio.QueueFull:
                # A watcher that cannot keep up is dropped, never waited for: it
                # empties, learns to reconnect, and the replay brings it back.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
                self.unsubscribe(sub, queue)


def _replayable(events: List[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    """A turn's events for a late watcher: the deltas go once the final content is there."""
    final = any(event.get("type") == "content" for event in events)
    return (event for event in events if not (final and event.get("type") == "content_delta"))


RELAY = TurnRelay()


def terminal_sub(source: Optional[str], user: Optional[Dict[str, Any]]) -> Optional[str]:
    """The verified shopper whose terminal turn this is; None when the turn is not relayed."""
    if source != "terminal" or not user or not user.get("sub"):
        return None
    return str(user["sub"])


def _sse(frame: Dict[str, Any]) -> str:
    return f"data: {json.dumps(frame, ensure_ascii=False, default=str)}\n\n"


def _events(chunk: str) -> Iterator[Dict[str, Any]]:
    for line in chunk.splitlines():
        if line.startswith("data: "):
            try:
                event = json.loads(line[len("data: "):])
            except ValueError:
                continue
            if isinstance(event, dict):
                yield event


async def relay_turn_chunks(chunks: AsyncIterator[str], *, sub: Optional[str],
                            session_id: Optional[str], message: str,
                            relay: Optional[TurnRelay] = None) -> AsyncIterator[str]:
    """Yield the chat route's chunks unchanged, copying a terminal turn's events to the relay."""
    if sub is None:
        async for chunk in chunks:
            yield chunk
        return
    relay = relay or RELAY
    turn_id: Optional[str] = None
    outcome = "complete"
    warned = False
    try:
        async for chunk in chunks:
            try:
                for event in _events(chunk):
                    if turn_id is None and event.get("type") == "turn_start" and event.get("turn_id"):
                        turn_id = str(event["turn_id"])
                        relay.start_turn(sub, turn_id=turn_id, session_id=session_id,
                                         message=message,
                                         started_at=datetime.now(timezone.utc).isoformat())
                    if turn_id is None:
                        continue
                    if event.get("type") == "error":
                        outcome = "error"
                    relay.add_event(sub, turn_id, event)
            except Exception as exc:  # noqa: BLE001 - the relay never changes the turn
                if not warned:
                    logger.warning("Relaying terminal turn %s failed: %s", turn_id, exc)
                    warned = True
            yield chunk
    finally:
        if turn_id is not None:
            try:
                relay.end_turn(sub, turn_id, outcome)
            except Exception as exc:  # noqa: BLE001 - the relay never changes the turn
                logger.warning("Ending relayed terminal turn %s failed: %s", turn_id, exc)


async def watch_stream(sub: str, *, relay: Optional[TurnRelay] = None,
                       heartbeat_seconds: float = HEARTBEAT_SECONDS) -> AsyncIterator[str]:
    """One shopper's channel as SSE: a heartbeat at once, the replay, then live frames."""
    relay = relay or RELAY
    # Subscribe and snapshot the replay with no await between them, so no frame
    # is published in the gap: none is missed and none arrives twice.
    queue = relay.subscribe(sub)
    if queue is None:
        yield TOO_MANY_WATCHERS
        return
    backlog = relay.replay(sub)
    try:
        yield HEARTBEAT
        for frame in backlog:
            yield _sse(frame)
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                yield HEARTBEAT
                continue
            if frame is None:
                return
            yield _sse(frame)
    finally:
        relay.unsubscribe(sub, queue)
