"""The relay that carries a shopper's terminal-sent turns to their own Ask Pellier panel.

``scripts/lab_run.py send`` marks each workshop request ``source: "terminal"``; the
chat route copies that turn's events into the relay under the verified Cognito
``sub``, and ``GET /api/chat/watch`` streams them to the same shopper. These
tests pin the channel boundary, the replay a late panel gets, what is retained,
and that a slow watcher never holds up a turn.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List

from services import turn_relay
from services.turn_relay import TurnRelay


def _start(relay: TurnRelay, sub: str, turn_id: str, message: str = "a gift") -> None:
    relay.start_turn(sub, turn_id=turn_id, session_id="persona-anna-1", message=message,
                     started_at="2026-10-14T12:00:00+00:00")


def _drain(queue: "asyncio.Queue[Any]") -> List[Any]:
    frames = []
    while not queue.empty():
        frames.append(queue.get_nowait())
    return frames


def test_a_watcher_gets_only_its_own_shoppers_turns() -> None:
    relay = TurnRelay()
    anna = relay.subscribe("sub-anna")
    marco = relay.subscribe("sub-marco")
    _start(relay, "sub-anna", "turn-1")
    relay.add_event("sub-anna", "turn-1", {"type": "status", "label": "Understanding your request"})
    relay.end_turn("sub-anna", "turn-1", "complete")

    frames = _drain(anna)
    assert [frame["type"] for frame in frames] == ["relay_turn", "relay_event", "relay_end"]
    assert frames[0] == {"type": "relay_turn", "turn_id": "turn-1", "session_id": "persona-anna-1",
                         "message": "a gift", "source": "terminal",
                         "started_at": "2026-10-14T12:00:00+00:00"}
    assert frames[1] == {"type": "relay_event", "turn_id": "turn-1",
                         "event": {"type": "status", "label": "Understanding your request"}}
    assert frames[2] == {"type": "relay_end", "turn_id": "turn-1", "outcome": "complete"}
    assert _drain(marco) == []


def test_replay_gives_a_late_panel_the_recent_turns_marked_as_replay() -> None:
    relay = TurnRelay()
    _start(relay, "sub-anna", "turn-1")
    relay.add_event("sub-anna", "turn-1", {"type": "step", "id": "route", "status": "done"})
    relay.end_turn("sub-anna", "turn-1", "complete")

    frames = relay.replay("sub-anna")
    assert [frame["type"] for frame in frames] == ["relay_turn", "relay_event", "relay_end"]
    assert frames[0]["replay"] is True
    assert relay.replay("sub-marco") == []


def test_a_turn_still_running_replays_what_it_has_and_no_end() -> None:
    relay = TurnRelay()
    _start(relay, "sub-anna", "turn-1")
    relay.add_event("sub-anna", "turn-1", {"type": "status", "label": "Writing your answer"})

    assert [frame["type"] for frame in relay.replay("sub-anna")] == ["relay_turn", "relay_event"]


def test_replay_drops_the_deltas_once_the_final_content_arrived() -> None:
    relay = TurnRelay()
    _start(relay, "sub-anna", "turn-1")
    for event in ({"type": "content_delta", "delta": "Hel"}, {"type": "content_delta", "delta": "lo"},
                  {"type": "content", "content": "Hello"}):
        relay.add_event("sub-anna", "turn-1", event)
    relay.end_turn("sub-anna", "turn-1", "complete")

    kinds = [frame["event"]["type"] for frame in relay.replay("sub-anna") if frame["type"] == "relay_event"]
    assert kinds == ["content"]


def test_replay_keeps_the_deltas_when_no_final_content_arrived() -> None:
    relay = TurnRelay()
    _start(relay, "sub-anna", "turn-1")
    relay.add_event("sub-anna", "turn-1", {"type": "content_delta", "delta": "Hel"})

    kinds = [frame["event"]["type"] for frame in relay.replay("sub-anna") if frame["type"] == "relay_event"]
    assert kinds == ["content_delta"]


def test_only_the_last_three_turns_are_kept() -> None:
    relay = TurnRelay(keep_turns=3)
    for index in range(5):
        _start(relay, "sub-anna", f"turn-{index}")
        relay.end_turn("sub-anna", f"turn-{index}", "complete")

    kept = [frame["turn_id"] for frame in relay.replay("sub-anna") if frame["type"] == "relay_turn"]
    assert kept == ["turn-2", "turn-3", "turn-4"]


def test_an_ended_turn_expires_after_thirty_minutes() -> None:
    now = [1000.0]
    relay = TurnRelay(keep_seconds=1800, clock=lambda: now[0])
    _start(relay, "sub-anna", "turn-old")
    relay.end_turn("sub-anna", "turn-old", "complete")
    now[0] += 1799
    assert relay.replay("sub-anna")
    now[0] += 2
    assert relay.replay("sub-anna") == []


def test_a_turn_over_its_byte_cap_keeps_streaming_live_but_stops_storing() -> None:
    relay = TurnRelay(max_turn_bytes=200)
    queue = relay.subscribe("sub-anna")
    _start(relay, "sub-anna", "turn-1")
    big = {"type": "content_delta", "delta": "x" * 300}
    relay.add_event("sub-anna", "turn-1", big)

    live = _drain(queue)
    assert live[-1] == {"type": "relay_event", "turn_id": "turn-1", "event": big}
    stored = [frame for frame in relay.replay("sub-anna") if frame["type"] == "relay_event"]
    assert stored == []


def test_a_full_watcher_is_dropped_and_told_to_reconnect_without_slowing_the_turn() -> None:
    relay = TurnRelay(queue_size=2)
    queue = relay.subscribe("sub-anna")
    _start(relay, "sub-anna", "turn-1")
    for _ in range(5):
        relay.add_event("sub-anna", "turn-1", {"type": "status", "label": "working"})

    assert _drain(queue) == [None]
    assert relay.watchers("sub-anna") == 0


def test_a_shopper_has_at_most_five_watchers() -> None:
    relay = TurnRelay(max_subscribers=5)
    queues = [relay.subscribe("sub-anna") for _ in range(5)]
    assert all(queue is not None for queue in queues)
    assert relay.subscribe("sub-anna") is None
    relay.unsubscribe("sub-anna", queues[0])
    assert relay.subscribe("sub-anna") is not None


def test_events_for_an_unknown_turn_are_ignored() -> None:
    relay = TurnRelay()
    queue = relay.subscribe("sub-anna")
    relay.add_event("sub-anna", "turn-never-started", {"type": "status", "label": "x"})
    relay.end_turn("sub-anna", "turn-never-started", "complete")
    assert _drain(queue) == []


def _data(chunks: List[str]) -> List[Dict[str, Any]]:
    return [json.loads(line[len("data: "):]) for chunk in chunks for line in chunk.splitlines()
            if line.startswith("data: ")]


def test_the_watch_stream_opens_at_once_replays_then_streams_live_then_heartbeats() -> None:
    relay = TurnRelay()
    _start(relay, "sub-anna", "turn-1")
    relay.end_turn("sub-anna", "turn-1", "complete")

    async def run() -> List[str]:
        stream = turn_relay.watch_stream("sub-anna", relay=relay, heartbeat_seconds=0.05)
        chunks = [await stream.__anext__()]
        chunks += [await stream.__anext__(), await stream.__anext__()]
        _start(relay, "sub-anna", "turn-2", message="live one")
        chunks.append(await stream.__anext__())
        chunks.append(await stream.__anext__())
        await stream.aclose()
        return chunks

    chunks = asyncio.run(run())
    assert chunks[0] == ": keep-alive\n\n"
    frames = _data(chunks[1:4])
    assert [(frame["type"], frame.get("replay")) for frame in frames] == [
        ("relay_turn", True), ("relay_end", None), ("relay_turn", None)]
    assert frames[2]["message"] == "live one"
    assert chunks[4] == ": keep-alive\n\n"
    assert relay.watchers("sub-anna") == 0


def test_the_watch_stream_ends_when_the_watcher_was_dropped() -> None:
    relay = TurnRelay(queue_size=1)

    async def run() -> List[str]:
        stream = turn_relay.watch_stream("sub-anna", relay=relay, heartbeat_seconds=5)
        chunks = [await stream.__anext__()]
        _start(relay, "sub-anna", "turn-1")
        relay.add_event("sub-anna", "turn-1", {"type": "status", "label": "x"})
        chunks += [chunk async for chunk in stream]
        return chunks

    assert asyncio.run(run()) == [": keep-alive\n\n"]


def test_the_watch_stream_says_so_when_the_shopper_has_too_many_watchers() -> None:
    relay = TurnRelay(max_subscribers=1)
    relay.subscribe("sub-anna")

    async def run() -> List[str]:
        return [chunk async for chunk in turn_relay.watch_stream("sub-anna", relay=relay)]

    assert asyncio.run(run()) == [": too many watchers\n\n"]


async def _chunks(*events: Dict[str, Any]) -> AsyncIterator[str]:
    for event in events:
        yield f"data: {json.dumps(event)}\n\n"


def _collect(stream: AsyncIterator[str]) -> List[str]:
    async def run() -> List[str]:
        return [chunk async for chunk in stream]
    return asyncio.run(run())


def test_relaying_a_terminal_turn_copies_every_event_and_changes_nothing_it_streams() -> None:
    relay = TurnRelay()
    queue = relay.subscribe("sub-anna")
    source = [{"type": "turn_start", "turn_id": "turn-1"}, {"type": "content", "content": "Hi"},
              {"type": "complete", "response": {"response": "Hi"}}]

    out = _collect(turn_relay.relay_turn_chunks(_chunks(*source), sub="sub-anna", relay=relay,
                                                session_id="persona-anna-1", message="a gift"))

    assert out == [f"data: {json.dumps(event)}\n\n" for event in source]
    frames = _drain(queue)
    assert [frame["type"] for frame in frames] == ["relay_turn", "relay_event", "relay_event",
                                                   "relay_event", "relay_end"]
    assert [frame["event"] for frame in frames if frame["type"] == "relay_event"] == source
    assert frames[-1]["outcome"] == "complete"


def test_an_error_event_ends_the_relayed_turn_as_an_error() -> None:
    relay = TurnRelay()
    queue = relay.subscribe("sub-anna")
    _collect(turn_relay.relay_turn_chunks(
        _chunks({"type": "turn_start", "turn_id": "turn-1"}, {"type": "error", "code": "x"}),
        sub="sub-anna", relay=relay, session_id=None, message="a gift"))
    assert _drain(queue)[-1] == {"type": "relay_end", "turn_id": "turn-1", "outcome": "error"}


def test_events_before_turn_start_and_unparseable_chunks_pass_through_unrelayed() -> None:
    relay = TurnRelay()
    queue = relay.subscribe("sub-anna")

    async def source() -> AsyncIterator[str]:
        yield 'data: {"type": "guardrail_decision"}\n\n'
        yield "data: not json\n\n"
        yield 'data: {"type": "turn_start", "turn_id": "turn-1"}\n\n'

    out = _collect(turn_relay.relay_turn_chunks(source(), sub="sub-anna", relay=relay,
                                                session_id=None, message="a gift"))
    assert out[1] == "data: not json\n\n"
    assert [frame["type"] for frame in _drain(queue)] == ["relay_turn", "relay_event", "relay_end"]


def test_without_a_terminal_sub_the_stream_passes_through_untouched() -> None:
    relay = TurnRelay()
    queue = relay.subscribe("sub-anna")
    out = _collect(turn_relay.relay_turn_chunks(_chunks({"type": "turn_start", "turn_id": "t"}),
                                                sub=None, relay=relay, session_id=None, message="m"))
    assert out == ['data: {"type": "turn_start", "turn_id": "t"}\n\n']
    assert _drain(queue) == []


def test_terminal_sub_is_the_verified_sub_of_a_terminal_request_only() -> None:
    assert turn_relay.terminal_sub("terminal", {"sub": "sub-anna"}) == "sub-anna"
    assert turn_relay.terminal_sub(None, {"sub": "sub-anna"}) is None
    assert turn_relay.terminal_sub("terminal", None) is None
    assert turn_relay.terminal_sub("terminal", {"email": "anna@example.com"}) is None
