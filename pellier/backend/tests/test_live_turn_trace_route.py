"""The chat route relays a terminal turn, and ``GET /api/chat/watch`` serves it to its shopper.

``scripts/lab_run.py send`` posts with ``source: "terminal"``. Only that turn, by a
verified shopper, is copied to the relay; the stream the caller reads is the same
either way. The watch endpoint needs a verified shopper and reads their own
channel, with no parameter that could name another.
"""
from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

import app as app_module
from services import turn_relay
from services.turn_relay import TurnRelay


def _shopper(username: str) -> Dict[str, Any]:
    return {"sub": f"sub-{username}", "username": username, "access_token": f"jwt-{username}"}


@pytest.fixture
def relay(monkeypatch: pytest.MonkeyPatch) -> TurnRelay:
    fresh = TurnRelay()
    monkeypatch.setattr(turn_relay, "RELAY", fresh)
    return fresh


@pytest.fixture
def post(monkeypatch: pytest.MonkeyPatch):
    """POST one turn as ``user`` with an optional ``source``; returns the streamed body."""

    async def _stream(**_kwargs: Any) -> AsyncIterator[Dict[str, Any]]:
        yield {"type": "status", "label": "Understanding your request"}
        yield {"type": "content", "content": "hello"}
        yield {"type": "complete", "response": {"response": "hello", "products": [], "suggestions": []}}

    class _Svc:
        chat_stream = staticmethod(_stream)

    monkeypatch.setattr(app_module.settings, "USE_AGENTCORE_RUNTIME", False, raising=False)
    monkeypatch.setattr(app_module, "chat_service", _Svc())

    def send(user: Optional[Dict[str, Any]], source: Optional[str]) -> str:
        app_module.app.dependency_overrides[app_module.get_current_user] = lambda: user
        body: Dict[str, Any] = {"message": "a gift", "conversation_history": [],
                                "session_id": "persona-anna-1"}
        if source is not None:
            body["source"] = source
        try:
            response = TestClient(app_module.app).post("/api/chat/stream", json=body)
        finally:
            app_module.app.dependency_overrides.pop(app_module.get_current_user, None)
        assert response.status_code == 200
        return response.text

    return send


def _types(body: str) -> List[str]:
    return [json.loads(m)["type"] for m in re.findall(r"^data: (.*)$", body, re.M)]


def test_a_verified_terminal_turn_is_relayed_whole(relay: TurnRelay, post) -> None:
    body = post(_shopper("anna"), "terminal")

    frames = relay.replay("sub-anna")
    assert frames[0]["type"] == "relay_turn"
    assert frames[0]["message"] == "a gift"
    assert frames[0]["session_id"] == "persona-anna-1"
    relayed = [frame["event"]["type"] for frame in frames if frame["type"] == "relay_event"]
    assert relayed == _types(body)
    assert frames[-1] == {"type": "relay_end", "turn_id": frames[0]["turn_id"], "outcome": "complete"}
    assert relay.replay("sub-marco") == []


def test_relaying_does_not_change_what_the_caller_reads(relay: TurnRelay, post) -> None:
    def shape(body: str) -> List[str]:
        return [re.sub(r"turn-[0-9a-f]{32}", "turn-x", line) for line in body.splitlines()]

    assert shape(post(_shopper("anna"), "terminal")) == shape(post(_shopper("anna"), None))


def test_a_browser_turn_is_not_relayed(relay: TurnRelay, post) -> None:
    post(_shopper("anna"), None)
    assert relay.replay("sub-anna") == []


def test_an_anonymous_terminal_turn_is_not_relayed(relay: TurnRelay, post) -> None:
    post(None, "terminal")
    assert relay.replay("sub-anna") == []


def test_only_terminal_is_a_source() -> None:
    response = TestClient(app_module.app).post("/api/chat/stream", json={
        "message": "a gift", "conversation_history": [], "source": "browser"})
    assert response.status_code == 422


def test_watching_needs_a_verified_shopper() -> None:
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: None
    try:
        response = TestClient(app_module.app).get("/api/chat/watch")
    finally:
        app_module.app.dependency_overrides.pop(app_module.get_current_user, None)
    assert response.status_code == 401


def test_watching_streams_the_callers_own_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    watched: List[str] = []

    async def finite(sub: str, **_kwargs: Any) -> AsyncIterator[str]:
        watched.append(sub)
        yield ": keep-alive\n\n"
        yield 'data: {"type": "relay_turn", "turn_id": "turn-1"}\n\n'

    monkeypatch.setattr(turn_relay, "watch_stream", finite)
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: _shopper("anna")
    try:
        response = TestClient(app_module.app).get("/api/chat/watch?sub=sub-marco")
    finally:
        app_module.app.dependency_overrides.pop(app_module.get_current_user, None)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert watched == ["sub-anna"]
    assert _types(response.text) == ["relay_turn"]
