"""The managed rail speaks the same step contract, ignores the skill mode field,
and shows only the skills the Runtime reported."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

import app as app_module
import services.agentcore_memory as memory_module
import services.agentcore_runtime as runtime_module
from services.agentcore_runtime import ManagedRuntimeResult


def _events(body: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


# What the Runtime reports it loaded. The app renders this; it asserts nothing.
RUNTIME_SKILLS = [
    {"name": "the-care-card", "display_name": "The Care Card",
     "path": "skills/the-care-card/SKILL.md", "loaded": "fixed"},
    {"name": "the-proof-counter", "display_name": "The Proof Counter",
     "path": "skills/the-proof-counter/SKILL.md", "loaded": "fixed"},
]


def _support_result(skills: List[Dict[str, Any]]) -> ManagedRuntimeResult:
    return ManagedRuntimeResult(
        response="Your ticket about the chipped bowl is open.",
        products=[],
        rail="gateway-mcp",
        intent="support",
        specialist="support",
        model="global.anthropic.claude-opus-5",
        tool_calls=[
            {
                "id": "tool-1",
                "tool": "get_tickets",
                "status": "success",
                "duration_ms": 90,
                "input": {"limit": 5},
                "result": {"product_count": 0, "status": "success", "count": 2},
                "finding": "1 open ticket, 1 closed",
                "customer_scope": "server",
                "requested_other_customer": True,
                "requested_customer": "CUST-JESSICA",
                "bound_customer": "CUST-THEO",
                "binding": "overwritten",
            }
        ],
        skills=skills,
        stop_reason="end_turn",
    )


# One raw Runtime response, as the entrypoint returns it over the data plane.
RAW_RUNTIME_RESPONSE = {
    "response": "Your ticket about the chipped bowl is open.",
    "products": [],
    "rail": "gateway-mcp",
    "intent": "support",
    "specialist": "support",
    "model": "global.anthropic.claude-opus-5",
    "gateway_tools": ["get_tickets", "get_orders"],
    "tool_calls": [{"id": "tool-1", "tool": "get_tickets", "status": "success", "duration_ms": 90,
                    "input": {"limit": 5}, "result": {"count": 2}, "finding": "1 open ticket, 1 closed"}],
    # What the Runtime reports it carried, plus two entries the parser must drop.
    "skills": [*RUNTIME_SKILLS, {"display_name": "No name"}, "not-a-receipt"],
    "stop_reason": "end_turn",
    "orchestration": "dispatcher",
    "build_fingerprint": "abc123",
}


def test_the_bridge_parses_skills_and_stop_reason_from_the_raw_runtime_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The response goes through ``run_agent_on_runtime_result``, not a hand-built result."""

    class _Response:
        headers = {"x-amzn-requestid": "req-1"}

        def read(self) -> bytes:
            return json.dumps(RAW_RUNTIME_RESPONSE).encode("utf-8")

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *exc: Any) -> bool:
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout=None: _Response())
    monkeypatch.setattr(
        runtime_module.settings,
        "AGENTCORE_RUNTIME_ENDPOINT",
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier",
        raising=False,
    )
    result = asyncio.run(runtime_module.run_agent_on_runtime_result(
        message="any news on my chipped bowl?",
        session_id="sess-theo",
        user_id="principal-theo",
        auth_token="jwt-theo",
    ))
    assert result.skills == RUNTIME_SKILLS
    assert result.stop_reason == "end_turn"
    assert result.tool_calls[0]["finding"] == "1 open ticket, 1 closed"


@pytest.fixture
def managed_app(monkeypatch: pytest.MonkeyPatch):
    async def _managed_runtime(**kwargs: Any) -> ManagedRuntimeResult:
        return _support_result(RUNTIME_SKILLS)

    class _Memory:
        def __init__(self, *, strict: bool = False) -> None:
            pass

        async def get_session_history(self, namespace: str) -> list:
            return []

        async def append_session_turns(self, namespace: str, turns: list) -> None:
            return None

    class _LocalChatMustNotRun:
        async def chat_stream(self, **_: Any):
            raise AssertionError("managed turn called local chat_stream")
            yield {}

    monkeypatch.setattr(app_module.settings, "USE_AGENTCORE_RUNTIME", True, raising=False)
    monkeypatch.setattr(
        app_module.settings,
        "AGENTCORE_RUNTIME_ENDPOINT",
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier",
        raising=False,
    )
    monkeypatch.setattr(app_module, "chat_service", _LocalChatMustNotRun())
    monkeypatch.setattr(app_module, "db_service", None)
    monkeypatch.setattr(runtime_module, "run_agent_on_runtime_result", _managed_runtime)
    monkeypatch.setattr(memory_module, "AgentCoreMemory", _Memory)
    monkeypatch.setattr(
        runtime_module,
        "get_latest_trace",
        lambda _session_id, **_: {"rail": "gateway-mcp", "traceId": "trace-1"},
    )
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: {
        "sub": "principal-theo",
        "username": "theo",
        "access_token": "jwt-theo",
    }
    try:
        yield TestClient(app_module.app)
    finally:
        app_module.app.dependency_overrides.pop(app_module.get_current_user, None)


def test_the_managed_rail_ignores_the_skill_mode_field_and_says_so(managed_app: TestClient) -> None:
    body = managed_app.post(
        "/api/chat/stream",
        json={
            "message": "any news on my chipped bowl?",
            "conversation_history": [],
            "session_id": "sess-theo",
            "skill_mode": "on_demand",
        },
    ).text
    events = _events(body)

    statuses = [event["label"] for event in events if event.get("type") == "status"]
    assert statuses == ["Understanding your request", "Writing your answer"]

    steps = [event for event in events if event.get("type") == "step"]
    route = steps[0]
    assert route["id"] == "route" and route["builder"]["rail"] == "gateway-mcp"
    assert route["builder"]["skill_mode"] == "fixed"
    # Exactly what the Runtime reported, never a list the app assembled itself.
    assert route["builder"]["skills"] == RUNTIME_SKILLS
    assert "Skills" in route["tags"]
    assert route["builder"]["note"] == (
        "On-demand skill loading runs in the in-process app only; "
        "the Runtime loaded its fixed skills"
    )
    assert route["builder"]["stop_reason"] == "end_turn"

    tickets = steps[1]
    assert tickets["id"] == "step-1" and tickets["status"] == "done"
    assert tickets["label"] == "Reading your tickets"
    assert tickets["finding"] == "1 open ticket, 1 closed"
    assert tickets["tags"] == ["Aurora", "Identity"]
    assert tickets["builder"]["identity"] == {
        "binding": "overwritten",
        "requested_customer": "CUST-JESSICA",
        "bound_customer": "CUST-THEO",
        "authorized_customer": "CUST-THEO",
    }
    shopper_view = {key: value for key, value in tickets.items() if key != "builder"}
    assert "CUST-" not in json.dumps(shopper_view)

    # The Builder fields travel on the step alone: the tool_call event and the
    # execution envelope carry the execution facts only.
    tool_call = [event for event in events if event.get("type") == "tool_call"][0]
    assert tool_call["tool"] == "get_tickets" and tool_call["status"] == "completed"
    for field in ("requested_customer", "bound_customer", "finding", "ranking"):
        assert field not in tool_call
    complete = [event for event in events if event.get("type") == "complete"][0]
    assert complete["response"]["rail"] == "gateway-mcp"
    assert complete["response"]["orchestration"]["stop_reason"] == "end_turn"
    executed = complete["response"]["agent_execution"]["tool_calls"][0]
    assert "requested_customer" not in executed and "finding" not in executed
    assert executed["binding"] == "overwritten"


def test_a_runtime_that_reports_no_skills_shows_none(
    managed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bundle without skill files reports none, and the Builder view says so."""
    async def _bare_runtime(**kwargs: Any) -> ManagedRuntimeResult:
        return _support_result([])

    monkeypatch.setattr(runtime_module, "run_agent_on_runtime_result", _bare_runtime)
    for skill_mode, note in (
        ("fixed", "The Runtime reported no skills"),
        ("on_demand", "On-demand skill loading runs in the in-process app only; "
                      "the Runtime reported no skills"),
    ):
        body = managed_app.post(
            "/api/chat/stream",
            json={"message": "any news on my chipped bowl?", "conversation_history": [],
                  "session_id": "sess-theo", "skill_mode": skill_mode},
        ).text
        route = [event for event in _events(body) if event.get("type") == "step"][0]
        assert route["builder"]["skills"] == []
        assert "Skills" not in route["tags"]
        assert route["builder"]["note"] == note


def test_a_managed_search_without_a_readable_receipt_says_ranking_is_unavailable(
    managed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _managed_search(**kwargs: Any) -> ManagedRuntimeResult:
        return ManagedRuntimeResult(
            response="Start with the Stoneware Mugs, Set of 2.",
            products=[{"productId": "65", "name": "Stoneware Mugs, Set of 2", "price": 38}],
            rail="gateway-mcp",
            intent="shopping",
            specialist="shopping",
            model="global.anthropic.claude-opus-5",
            tool_calls=[
                {
                    "id": "tool-1",
                    "tool": "search_products",
                    "status": "success",
                    "duration_ms": 300,
                    "input": {"query": "mugs"},
                    "result": {"product_count": 1, "status": "success", "count": 1},
                    "finding": "1 found",
                }
            ],
        )

    monkeypatch.setattr(runtime_module, "run_agent_on_runtime_result", _managed_search)
    body = managed_app.post(
        "/api/chat/stream",
        json={"message": "stoneware mugs", "conversation_history": [], "session_id": "sess-anna"},
    ).text
    search = [event for event in _events(body) if event.get("type") == "step"][1]
    assert search["builder"]["tool"] == "search_products"
    assert search["builder"]["ranking"] == {
        "available": False,
        "rail": "gateway-mcp",
        "reason": "No database connection to read the receipt",
    }
