"""The per-turn identifier contract on ``POST /api/chat/stream``.

A receipt deep link is only worth shipping if it resolves to the same turn
after a reload. That needs a server-minted id, emitted before any content
and repeated on the terminal event, so the client can capture it even if
the stream fails mid-answer.

The properties pinned here:

  1. ``turn_start`` is the first event and carries ``turn_id``.
  2. The terminal ``complete`` event repeats the same id.
  3. Ids are unique per turn and never positional.
  4. The same contract holds on every real execution rail.
"""

from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Dict, List

import pytest
from fastapi.testclient import TestClient

import app as app_module

_TURN_ID_RE = re.compile(r"^turn-[0-9a-f]{32}$")


def _events(body: str) -> List[Dict[str, Any]]:
    return [json.loads(m) for m in re.findall(r"^data: (.*)$", body, re.M)]


def _first(events: List[Dict[str, Any]], kind: str) -> Dict[str, Any] | None:
    return next((e for e in events if e.get("type") == kind), None)


@pytest.fixture
def live_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Client with a deterministic in-process chat dependency."""

    async def _stream(**kwargs: Any) -> AsyncIterator[Dict[str, Any]]:
        yield {"type": "content", "content": "hello"}
        yield {
            "type": "complete",
            "response": {"response": "hello", "products": [], "suggestions": []},
        }

    class _Svc:
        chat_stream = staticmethod(_stream)

    monkeypatch.setattr(app_module, "chat_service", _Svc())
    return TestClient(app_module.app)


def _post(client: TestClient, session_id: str = "sess-1") -> List[Dict[str, Any]]:
    response = client.post(
        "/api/chat/stream",
        json={"message": "linen", "conversation_history": [], "session_id": session_id},
    )
    assert response.status_code == 200
    return _events(response.text)


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------
def test_new_turn_id_is_prefixed_uuid4_hex() -> None:
    value = app_module.new_turn_id()

    assert _TURN_ID_RE.match(value), value


def test_turn_ids_are_unique() -> None:
    ids = {app_module.new_turn_id() for _ in range(200)}

    assert len(ids) == 200


def test_turn_id_is_not_positional() -> None:
    """A positional id would point at the wrong turn after any reordering."""
    value = app_module.new_turn_id()

    assert value not in {"turn-0", "turn-1", "0", "1"}


# ---------------------------------------------------------------------------
# Live stream
# ---------------------------------------------------------------------------
def test_turn_start_is_the_first_event(live_client: TestClient) -> None:
    events = _post(live_client)

    assert events[0]["type"] == "turn_start"
    assert _TURN_ID_RE.match(events[0]["turn_id"])
    assert events[0]["session_id"] == "sess-1"


def test_complete_repeats_the_same_turn_id(live_client: TestClient) -> None:
    events = _post(live_client)

    start = _first(events, "turn_start")
    complete = _first(events, "complete")

    assert start is not None and complete is not None
    assert complete["response"]["turn_id"] == start["turn_id"]
    assert complete["response"]["session_id"] == "sess-1"


def test_each_request_gets_a_distinct_turn_id(live_client: TestClient) -> None:
    first = _first(_post(live_client), "turn_start")
    second = _first(_post(live_client), "turn_start")

    assert first is not None and second is not None
    assert first["turn_id"] != second["turn_id"]


def test_complete_still_carries_the_rail(live_client: TestClient) -> None:
    """Turn identity must not displace the rail annotation."""
    complete = _first(_post(live_client), "complete")

    assert complete is not None
    assert complete["response"]["rail"] == "in-process"
    assert complete["response"]["railDecision"]["available"] is True


@pytest.mark.parametrize("success, build_required, status, code", [
    (True, False, "complete", None),
    (False, False, "failed", None),
    (False, True, "failed", "workshop_build_required"),
])
def test_transport_completion_records_the_actual_turn_outcome(
    monkeypatch, success, build_required, status, code,
):
    persisted = []

    class Service:
        async def chat_stream(self, **kwargs):
            yield {"type": "complete", "response": {
                "response": "A bounded response", "success": success,
                "agent_execution": {"build_required": build_required},
            }}

    async def persist(**kwargs):
        persisted.append(kwargs)
        return None

    monkeypatch.setattr(app_module.settings, "USE_AGENTCORE_RUNTIME", False)
    monkeypatch.setattr(app_module, "chat_service", Service())
    monkeypatch.setattr(app_module, "_persist_terminal_turn_receipt", persist)
    events = _post(TestClient(app_module.app))
    assert _first(events, "complete")["response"]["success"] is success
    assert len(persisted) == 1
    assert persisted[0]["terminal_status"] == status
    assert persisted[0]["terminal_error_code"] == code


@pytest.mark.parametrize(
    ("verified_user", "requested_customer_id", "expected_customer_id"),
    [
        (
            {
                "sub": "principal-marco",
                "username": "marco",
                "access_token": "jwt-marco",
            },
            "CUST-ANNA",
            "CUST-MARCO",
        ),
        (None, "CUST-ANNA", "CUST-ANNA"),
    ],
)
def test_local_turn_receives_server_resolved_aurora_customer(
    monkeypatch: pytest.MonkeyPatch,
    verified_user: Dict[str, Any] | None,
    requested_customer_id: str,
    expected_customer_id: str,
) -> None:
    """Profile context follows verified identity, then demo persona fallback."""
    captured_users: list[Dict[str, Any] | None] = []

    async def _stream(**kwargs: Any) -> AsyncIterator[Dict[str, Any]]:
        captured_users.append(kwargs.get("user"))
        yield {
            "type": "complete",
            "response": {"response": "hello", "products": [], "suggestions": []},
        }

    class _Svc:
        chat_stream = staticmethod(_stream)

    monkeypatch.setattr(app_module.settings, "USE_AGENTCORE_RUNTIME", False, raising=False)
    monkeypatch.setattr(app_module, "chat_service", _Svc())
    app_module.app.dependency_overrides[app_module.get_current_user] = (
        lambda: verified_user
    )
    try:
        response = TestClient(app_module.app).post(
            "/api/chat/stream",
            json={
                "message": "linen",
                "conversation_history": [],
                "session_id": "sess-local-profile",
                "customer_id": requested_customer_id,
            },
        )
    finally:
        app_module.app.dependency_overrides.pop(app_module.get_current_user, None)

    assert response.status_code == 200
    assert len(captured_users) == 1
    assert captured_users[0] is not None
    assert captured_users[0]["customer_id"] == expected_customer_id
    if verified_user:
        assert captured_users[0]["sub"] == verified_user["sub"]
        assert captured_users[0]["access_token"] == verified_user["access_token"]


def test_managed_storefront_turn_invokes_runtime_not_local_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pellier must execute the rail it reports on a managed turn."""
    import services.agentcore_runtime as runtime_module

    async def _managed_runtime(**kwargs: Any) -> runtime_module.ManagedRuntimeResult:
        assert kwargs["message"] == "linen"
        assert kwargs["session_id"] == "sess-managed"
        assert kwargs["auth_token"] == "jwt-managed"
        assert kwargs["history"] == []
        return runtime_module.ManagedRuntimeResult(
            response="The managed Runtime found the linen edit.",
            products=[
                {
                    "productId": 7,
                    "name": "Italian Linen Camp Shirt",
                    "price": 228,
                }
            ],
            rail="gateway-mcp",
            intent="recommendation",
            specialist="recommendation",
            model="global.anthropic.claude-opus-4-6-v1",
            tool_calls=[
                {
                    "id": "tool-1",
                    "tool": "search_products_hybrid",
                    "status": "success",
                    "duration_ms": 12,
                    "input": {"query": "linen"},
                    "result": {"product_count": 1, "product_ids": [7]},
                }
            ],
        )

    class _Memory:
        writes: list[tuple[str, list[dict[str, Any]]]] = []

        def __init__(self, *, strict: bool = False) -> None:
            assert strict is True

        async def get_session_history(self, namespace: str) -> list[dict[str, Any]]:
            assert namespace == "user-principal-managed-session-sess-managed"
            return []

        async def append_session_turns(
            self, namespace: str, turns: list[dict[str, Any]]
        ) -> None:
            self.writes.append((namespace, turns))

    class _LocalChatMustNotRun:
        async def chat_stream(self, **_: Any) -> AsyncIterator[Dict[str, Any]]:
            raise AssertionError("managed storefront turn called local chat_stream")
            yield {}

    monkeypatch.setattr(app_module.settings, "USE_AGENTCORE_RUNTIME", True, raising=False)
    monkeypatch.setattr(
        app_module.settings,
        "AGENTCORE_RUNTIME_ENDPOINT",
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier",
        raising=False,
    )
    monkeypatch.setattr(app_module, "chat_service", _LocalChatMustNotRun())
    import services.agentcore_memory as memory_module

    monkeypatch.setattr(
        runtime_module, "run_agent_on_runtime_result", _managed_runtime
    )
    monkeypatch.setattr(memory_module, "AgentCoreMemory", _Memory)
    monkeypatch.setattr(
        runtime_module,
        "get_latest_trace",
        lambda _session_id, **_: {
            "rail": "gateway-mcp",
            "traceId": "trace-managed",
            "runtimeRequestId": "request-managed",
        },
    )
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: {
        "sub": "principal-managed",
        "username": "marco",
        "access_token": "jwt-managed",
    }
    try:
        client = TestClient(app_module.app)
        events = _events(
            client.post(
                "/api/chat/stream",
                json={
                    "message": "linen",
                    "conversation_history": [],
                    "session_id": "sess-managed",
                },
            ).text
        )
    finally:
        app_module.app.dependency_overrides.pop(app_module.get_current_user, None)

    complete = _first(events, "complete")
    assert complete is not None
    assert complete["response"]["response"] == "The managed Runtime found the linen edit."
    assert complete["response"]["products"][0]["productId"] == 7
    assert complete["response"]["orchestration"]["pattern"] == "dispatcher"
    assert complete["response"]["rail"] == "gateway-mcp"
    assert complete["response"]["railDecision"]["managedRequested"] is True
    profile = _first(events, "aurora_profile_context")
    assert profile is not None
    assert profile["profile"]["customer_id"] == "CUST-MARCO"
    assert _first(events, "agentcore_memory") is not None
    assert _first(events, "tool_call")["tool"] == "search_products_hybrid"
    assert _first(events, "tool_call")["status"] == "completed"
    assert _first(events, "product")["product"]["productId"] == 7
    assert len(_Memory.writes) == 1


def test_managed_storefront_memory_write_failure_does_not_recast_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed managed action remains complete when Memory append fails."""
    import services.agentcore_memory as memory_module
    import services.agentcore_runtime as runtime_module
    from services.agentcore_memory import ManagedMemoryError

    async def _managed_runtime(**_kwargs: Any) -> runtime_module.ManagedRuntimeResult:
        return runtime_module.ManagedRuntimeResult(
            response="Your return was processed.",
            rail="gateway-mcp",
            intent="returns",
            specialist="experience-guide",
            tool_calls=[{"tool": "initiate_return", "status": "success"}],
        )

    class _Memory:
        def __init__(self, *, strict: bool = False) -> None:
            assert strict is True

        async def get_session_history(self, _namespace: str) -> list[dict[str, Any]]:
            return []

        async def append_session_turns(
            self, _namespace: str, _turns: list[dict[str, Any]]
        ) -> None:
            raise ManagedMemoryError("write failed")

    class _LocalChatMustNotRun:
        async def chat_stream(self, **_: Any) -> AsyncIterator[Dict[str, Any]]:
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
    monkeypatch.setattr(
        runtime_module, "run_agent_on_runtime_result", _managed_runtime
    )
    monkeypatch.setattr(memory_module, "AgentCoreMemory", _Memory)
    monkeypatch.setattr(
        runtime_module,
        "get_latest_trace",
        lambda _session_id, **_: {"rail": "gateway-mcp"},
    )
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: {
        "sub": "principal-managed",
        "username": "marco",
        "access_token": "jwt-managed",
    }
    try:
        events = _events(
            TestClient(app_module.app)
            .post(
                "/api/chat/stream",
                json={
                    "message": "Return order 31",
                    "conversation_history": [],
                    "session_id": "sess-managed-write-failure",
                },
            )
            .text
        )
    finally:
        app_module.app.dependency_overrides.pop(app_module.get_current_user, None)

    assert _first(events, "error") is None
    memory = _first(events, "agentcore_memory")
    assert memory is not None, events
    assert memory["memory"]["write_status"] == "failed"
    assert memory["memory"]["retry_recommended"] is False
    complete = _first(events, "complete")
    assert complete is not None
    assert complete["response"]["success"] is True
    assert complete["response"]["warnings"][0]["retry_recommended"] is False


def test_unexpected_managed_memory_write_failure_preserves_completed_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpected SDK write error cannot make a completed action retryable."""
    import services.agentcore_memory as memory_module
    import services.agentcore_runtime as runtime_module

    async def _managed_runtime(**_kwargs: Any) -> runtime_module.ManagedRuntimeResult:
        return runtime_module.ManagedRuntimeResult(
            response="Your return was processed.",
            rail="gateway-mcp",
            intent="returns",
            specialist="experience-guide",
            tool_calls=[{"tool": "initiate_return", "status": "success"}],
        )

    class _Memory:
        def __init__(self, *, strict: bool = False) -> None:
            assert strict is True

        async def get_session_history(self, _namespace: str) -> list[dict[str, Any]]:
            return []

        async def append_session_turns(
            self, _namespace: str, _turns: list[dict[str, Any]]
        ) -> None:
            raise RuntimeError("unexpected SDK failure")

    class _LocalChatMustNotRun:
        async def chat_stream(self, **_: Any) -> AsyncIterator[Dict[str, Any]]:
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
    monkeypatch.setattr(
        runtime_module, "run_agent_on_runtime_result", _managed_runtime
    )
    monkeypatch.setattr(memory_module, "AgentCoreMemory", _Memory)
    monkeypatch.setattr(
        runtime_module,
        "get_latest_trace",
        lambda _session_id, **_: {"rail": "gateway-mcp"},
    )
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: {
        "sub": "principal-managed",
        "username": "marco",
        "access_token": "jwt-managed",
    }
    try:
        events = _events(
            TestClient(app_module.app)
            .post(
                "/api/chat/stream",
                json={
                    "message": "Return order 31",
                    "conversation_history": [],
                    "session_id": "sess-managed-unexpected-write-failure",
                },
            )
            .text
        )
    finally:
        app_module.app.dependency_overrides.pop(app_module.get_current_user, None)

    assert _first(events, "error") is None
    memory = _first(events, "agentcore_memory")
    assert memory is not None, events
    assert memory["memory"] == {
        "source": "unavailable",
        "turns_loaded": 0,
        "turns_persisted": 0,
        "namespace_scope": "verified-principal",
        "read_status": "succeeded",
        "write_status": "failed",
        "action_status": "completed",
        "retry_recommended": False,
        "error_code": "memory_write_failed",
    }
    complete = _first(events, "complete")
    assert complete is not None
    assert complete["response"]["success"] is True
    assert complete["response"]["warnings"][0]["retry_recommended"] is False


def test_unavailable_managed_storefront_turn_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A governed request never degrades into a local answer without a runtime."""
    class _LocalChatMustNotRun:
        async def chat_stream(self, **_: Any) -> AsyncIterator[Dict[str, Any]]:
            raise AssertionError("unavailable managed turn called local chat_stream")
            yield {}

    monkeypatch.setattr(app_module.settings, "USE_AGENTCORE_RUNTIME", True, raising=False)
    monkeypatch.setattr(app_module.settings, "AGENTCORE_RUNTIME_ENDPOINT", None, raising=False)
    monkeypatch.setattr(app_module, "chat_service", _LocalChatMustNotRun())
    client = TestClient(app_module.app)
    events = _events(
        client.post(
            "/api/chat/stream",
            json={"message": "linen", "conversation_history": [], "session_id": "sess-no-runtime"},
        ).text
    )

    assert events[0]["type"] == "turn_start"
    error = _first(events, "error")
    assert error is not None
    assert error["code"] == "service_unavailable"
