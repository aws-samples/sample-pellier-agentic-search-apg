"""Theo's remembered taste reaches the agent from AgentCore Memory, on both rails, attributed.

The spec: in his first session Theo tells Pellier his taste; in a new session
the Shopping agent's answer reflects it, and the preferences come from
AgentCore Memory (session events plus the user-preference strategy), never
from a tool. Provisioning writes that first session, so here a fake Memory
answers with the record it extracted.

* Managed rail: the app reads the record with the strict client, keyed on the
  server-resolved customer, and sends it in the Runtime payload. The Router
  step names the record the Runtime reports it put ahead of the prompt. No
  Aurora customer record is sent on this rail, so none is reported.
* In process: the same labelled line goes into the persona context, on a line
  of its own beside the Aurora ``Known about them:`` line.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

import app as app_module
import services.agentcore_memory as memory_module
import services.agentcore_runtime as runtime_module
import services.chat as chat_module
from services.agentcore_runtime import ManagedRuntimeResult
from services.chat import EnhancedChatService
from tests.test_chat_stream_contract import ScriptedAgent

THEO_RECORD = {"record_id": "mem-theo-1",
               "preference": "Prefers hand-thrown ceramics, stoneware and linen throws"}
LABELLED = ("Remembered from earlier conversations (AgentCore Memory, user preference): "
            "Prefers hand-thrown ceramics, stoneware and linen throws")
ARN = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier"


def _events(body: str) -> List[Dict[str, Any]]:
    return [json.loads(line[len("data: "):]) for line in body.splitlines()
            if line.startswith("data: ")]


class _TheoMemory:
    """AgentCore Memory as provisioning left it: one record extracted for CUST-THEO."""

    reads: List[str] = []
    strict_flags: List[bool] = []

    def __init__(self, *, strict: bool = False) -> None:
        self.strict_flags.append(strict)

    async def get_session_history(self, namespace: str) -> list:
        return []

    async def get_semantic_memories(self, customer_id: str) -> List[Dict[str, str]]:
        self.reads.append(customer_id)
        return [dict(THEO_RECORD)] if customer_id == "CUST-THEO" else []

    async def append_session_turns(self, namespace: str, turns: list) -> None:
        return None

    async def append_session_turn(self, namespace: str, turn: dict) -> None:
        return None


@pytest.fixture
def theo_memory(monkeypatch: pytest.MonkeyPatch) -> type:
    _TheoMemory.reads, _TheoMemory.strict_flags = [], []
    monkeypatch.setattr(memory_module, "AgentCoreMemory", _TheoMemory)
    return _TheoMemory


# ---------------------------------------------------------------------------
# Managed rail
# ---------------------------------------------------------------------------


@pytest.fixture
def managed_theo(monkeypatch: pytest.MonkeyPatch, theo_memory: type):
    """Theo signed in on the managed rail; the Runtime reports what it was given."""
    sent: List[Dict[str, Any]] = []
    reported: Dict[str, Optional[List[str]]] = {"ids": None}

    async def _runtime(**kwargs: Any) -> ManagedRuntimeResult:
        sent.append(kwargs)
        ids = reported["ids"]
        if ids is None:
            ids = [item["record_id"] for item in kwargs.get("preferences") or []]
        return ManagedRuntimeResult(
            response="Start with the stoneware.", rail="gateway-mcp", intent="shopping",
            specialist="shopping", model="global.anthropic.claude-opus-5", remembered=ids,
        )

    class _LocalChatMustNotRun:
        async def chat_stream(self, **_: Any):
            raise AssertionError("managed turn called local chat_stream")
            yield {}

    monkeypatch.setattr(app_module.settings, "USE_AGENTCORE_RUNTIME", True, raising=False)
    monkeypatch.setattr(app_module.settings, "AGENTCORE_RUNTIME_ENDPOINT", ARN, raising=False)
    monkeypatch.setattr(app_module, "chat_service", _LocalChatMustNotRun())
    monkeypatch.setattr(app_module, "db_service", None)
    monkeypatch.setattr(runtime_module, "run_agent_on_runtime_result", _runtime)
    monkeypatch.setattr(runtime_module, "get_latest_trace",
                        lambda _session_id, **_: {"rail": "gateway-mcp"})
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: {
        "sub": "principal-theo", "username": "theo", "access_token": "jwt-theo",
    }

    def ask(body: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        response = TestClient(app_module.app).post("/api/chat/stream", json={
            "message": "Something for the table", "conversation_history": [],
            "session_id": "sess-new", **(body or {}),
        })
        assert response.status_code == 200
        return _events(response.text)

    ask.sent, ask.reported = sent, reported
    try:
        yield ask
    finally:
        app_module.app.dependency_overrides.pop(app_module.get_current_user, None)


def _route(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return next(e for e in events if e.get("type") == "step" and e["id"] == "route")


def test_the_managed_payload_carries_theos_preference_and_the_step_names_its_record(
    managed_theo, theo_memory,
) -> None:
    # The body names another customer: the read follows the token, not the body.
    events = managed_theo({"customer_id": "CUST-JESSICA"})

    assert theo_memory.reads == ["CUST-THEO"]
    assert theo_memory.strict_flags == [True]
    (call,) = managed_theo.sent
    assert call["preferences"] == [THEO_RECORD]
    assert call["customer_id"] == "CUST-THEO"

    route = _route(events)
    assert route["builder"]["remembered"] == {
        "source": "agentcore-memory", "strategy": "USER_PREFERENCE", "records": ["mem-theo-1"],
    }
    assert "Memory" in route["tags"]
    # No Aurora customer record went to the Runtime, so none is reported as context.
    assert route["builder"]["memory"] is None
    assert [e for e in events if e.get("type") == "aurora_profile_context"] == []


def test_a_runtime_that_reports_no_record_gets_no_memory_line(managed_theo) -> None:
    """The step names what the Runtime says it sent, never the list the app sent."""
    managed_theo.reported["ids"] = []
    route = _route(managed_theo())

    assert managed_theo.sent[0]["preferences"] == [THEO_RECORD]
    assert route["builder"]["remembered"] is None
    assert "Memory" not in route["tags"]


def test_a_failed_strict_memory_read_ends_the_turn(managed_theo, monkeypatch) -> None:
    """The managed rail never reads a failed Memory read as "nothing remembered"."""
    async def _fails(self: Any, customer_id: str) -> list:
        raise memory_module.ManagedMemoryError("AgentCore semantic memory read failed")

    monkeypatch.setattr(_TheoMemory, "get_semantic_memories", _fails)
    events = managed_theo()

    assert managed_theo.sent == []
    assert any(e.get("type") == "error" for e in events)


def test_the_bridge_sends_the_preferences_and_parses_the_reported_ids(monkeypatch) -> None:
    """Through the real ``run_agent_on_runtime_result``: the payload out, the ids back."""
    bodies: List[Dict[str, Any]] = []

    class _Response:
        headers: Dict[str, str] = {}

        def read(self) -> bytes:
            return json.dumps({
                "response": "Start with the stoneware.", "rail": "gateway-mcp",
                "orchestration": "dispatcher", "remembered": ["mem-theo-1", "", 7],
            }).encode("utf-8")

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *exc: Any) -> bool:
            return False

    def _data_plane(request: Any, timeout: Any = None) -> _Response:
        assert urllib.parse.urlsplit(request.full_url).hostname == (
            "bedrock-agentcore.us-east-1.amazonaws.com")
        bodies.append(json.loads(request.data.decode("utf-8")))
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", _data_plane)
    monkeypatch.setattr(runtime_module.settings, "AWS_DEFAULT_REGION", "us-east-1", raising=False)
    monkeypatch.setattr(runtime_module.settings, "AGENTCORE_RUNTIME_ENDPOINT", ARN, raising=False)
    result = asyncio.run(runtime_module.run_agent_on_runtime_result(
        message="Something for the table", session_id="sess-new", user_id="principal-theo",
        auth_token="jwt-theo", customer_id="CUST-THEO", preferences=[THEO_RECORD],
    ))

    assert bodies[0]["preferences"] == [THEO_RECORD]
    assert result.remembered == ["mem-theo-1"]


# ---------------------------------------------------------------------------
# In process
# ---------------------------------------------------------------------------

THEO_KNOWN = "Ceramics, linen throws, stoneware"
# As the storefront route passes him: the verified token, and the customer it resolved.
THEO_USER = {"sub": "sub-theo", "username": "theo", "customer_id": "CUST-THEO"}


class _SeededTheo:
    """The two Aurora reads the persona context makes, answered from the seed."""

    async def fetch_all(self, sql: str, *params: Any) -> List[Dict[str, Any]]:
        return []

    async def fetch_all_as(self, username: Optional[str], sql: str, *params: Any) -> list:
        if "pellier.orders" in sql and username == "theo":
            return [{"productId": "37", "name": "Wabi-Sabi Bowl", "brand": "Pellier",
                     "color": "Ash", "price": 24, "category": "Home", "imgUrl": "/p.webp",
                     "rating": 4.8, "reviews": 9, "price_paid": 24.0,
                     "placed_at": "2026-08-01"}]
        return []

    async def fetch_one(self, sql: str, *params: Any) -> Optional[Dict[str, Any]]:
        if "pellier.customers" in sql:
            return {"name": "Theo", "preferences_summary": THEO_KNOWN}
        return None


@pytest.fixture
def in_process(monkeypatch: pytest.MonkeyPatch, theo_memory: type):
    service = EnhancedChatService.__new__(EnhancedChatService)
    service.model_id = "test-model"
    service.strands_available = True
    service._agent_stats = {
        "query_count": 0, "products_found": 0, "agent_calls_by_type": {},
        "total_response_time_ms": 0, "avg_response_time_ms": 0,
    }
    monkeypatch.setitem(sys.modules, "services.otel_trace_extractor", types.SimpleNamespace(
        extract_agent_execution_from_otel=lambda **kwargs: {}))
    monkeypatch.setattr(chat_module, "classify_intent", lambda _m: "shopping")
    prompts: List[str] = []

    class _Recording(ScriptedAgent):
        def __call__(self, prompt: str):
            prompts.append(prompt)
            return super().__call__(prompt)

    monkeypatch.setattr(chat_module, "_build_dispatcher_specialist",
                        lambda *_a, **_k: _Recording([], "Start with the stoneware."))

    def run(user: Optional[Dict[str, Any]], db: Any = None) -> List[Dict[str, Any]]:
        service.db_service = db
        prompts.clear()

        async def collect() -> List[Dict[str, Any]]:
            return [event async for event in service.chat_stream(
                message="Something for the table", turn_id="turn-" + "b" * 32,
                session_id="sess-new", user=user)]

        events = asyncio.run(collect())
        return [{"type": "_prompts", "prompts": list(prompts)}, *events]

    return run


def _prompt(events: List[Dict[str, Any]]) -> str:
    return events[0]["prompts"][0]


def test_in_process_the_memory_line_sits_apart_from_the_aurora_line(in_process,
                                                                   theo_memory) -> None:
    events = in_process(THEO_USER, db=_SeededTheo())
    lines = _prompt(events).splitlines()

    assert lines[0] == "PERSONA CONTEXT: Theo (CUST-THEO)"
    assert lines[1] == f"Known about them: {THEO_KNOWN}"
    assert lines[2] == LABELLED
    # Read once, without the strict flag (the turn's Memory write is another client).
    assert theo_memory.reads == ["CUST-THEO"] and not any(theo_memory.strict_flags)
    route = next(e for e in events if e.get("type") == "step" and e["id"] == "route")
    assert route["builder"]["remembered"]["records"] == ["mem-theo-1"]
    assert route["builder"]["memory"]["facts"] == 1


def test_in_process_memory_alone_still_reaches_the_prompt(in_process) -> None:
    """With no Aurora record to read, the remembered preference is still sent, labelled."""
    events = in_process(THEO_USER, db=None)
    prompt = _prompt(events)

    assert LABELLED in prompt
    assert "Known about them" not in prompt


def test_a_signed_out_turn_reads_no_one_from_memory(in_process, theo_memory) -> None:
    events = in_process(None)

    assert theo_memory.reads == []
    assert "AgentCore Memory" not in _prompt(events)
