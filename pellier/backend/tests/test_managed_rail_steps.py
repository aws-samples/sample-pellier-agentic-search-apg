"""The managed rail speaks the same step contract and ignores the skill mode field."""

from __future__ import annotations

import json
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


@pytest.fixture
def managed_app(monkeypatch: pytest.MonkeyPatch):
    async def _managed_runtime(**kwargs: Any) -> ManagedRuntimeResult:
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
        )

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
    assert [skill["loaded"] for skill in route["builder"]["skills"]] == ["fixed", "fixed"]
    assert "in-process app only" in route["builder"]["note"]

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

    complete = [event for event in events if event.get("type") == "complete"][0]
    assert complete["response"]["rail"] == "gateway-mcp"


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
