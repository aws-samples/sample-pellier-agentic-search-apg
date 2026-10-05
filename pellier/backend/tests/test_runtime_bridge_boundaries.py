"""The in-process Runtime bridge keeps scope, writes Memory once and fails loudly.

Three boundary reproductions from the 2026-10-04 external review, each
hermetic: no database, no model, no managed service. The identity case drives
the real greeting turn through the real chat entry. The Memory and failure
cases stand in for the specialist stream behind the real ``chat()`` collector,
the real bridge, the real route generator and the real namespace builder, with
a recording Memory.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from typing import Any, Dict, List

import pytest

import services.agentcore_memory as memory_module
import services.agentcore_runtime as rt
from routes.agent import _stream_agent_response
from services.agentcore_identity import AgentCoreIdentityService, UserContext
from services.chat import EnhancedChatService, _append_pellier_stm_turn
from services.turn_identity import TurnIdentity, authorized_customer_id_var, principal_sub_var


class _RecordingMemory:
    def __init__(self) -> None:
        self.rows: List[tuple[str, Dict[str, Any]]] = []

    async def get_session_history(self, namespace: str) -> list:
        return []

    async def append_session_turn(self, namespace: str, turn: Dict[str, Any]) -> str:
        return await self.append_session_turns(namespace, [turn])

    async def append_session_turns(self, namespace: str, turns: list) -> str:
        self.rows.extend((namespace, dict(turn)) for turn in turns)
        return "process-local"


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> EnhancedChatService:
    svc = EnhancedChatService.__new__(EnhancedChatService)
    svc.model_id = "test-model"
    svc.strands_available = True
    svc.db_service = None
    svc._agent_stats = {
        "query_count": 0, "products_found": 0, "agent_calls_by_type": {},
        "total_response_time_ms": 0, "avg_response_time_ms": 0,
    }
    monkeypatch.setattr(rt.settings, "USE_AGENTCORE_RUNTIME", False, raising=False)
    monkeypatch.setitem(sys.modules, "app", types.SimpleNamespace(chat_service=svc))
    monkeypatch.setitem(
        sys.modules,
        "services.otel_trace_extractor",
        types.SimpleNamespace(extract_agent_execution_from_otel=lambda **kwargs: {}),
    )
    return svc


@pytest.fixture
def memory(monkeypatch: pytest.MonkeyPatch) -> _RecordingMemory:
    recording = _RecordingMemory()
    monkeypatch.setattr(memory_module, "AgentCoreMemory", lambda *args, **kwargs: recording)
    return recording


def _context() -> UserContext:
    return UserContext(
        user_id="review-sub",
        session_id="review-session",
        namespace=AgentCoreIdentityService.build_namespace("review-sub", "review-session"),
        customer_id="CUST-THEO",
    )


def _stream(message: str, memory: _RecordingMemory) -> List[str]:
    async def collect() -> List[str]:
        return [
            event
            async for event in _stream_agent_response(
                message=message, context=_context(), memory=memory
            )
        ]

    return asyncio.run(collect())


def _event_types(events: List[str]) -> List[str]:
    return [event.splitlines()[0] for event in events]


def _data(event: str) -> Dict[str, Any]:
    return json.loads(event.split("data: ", 1)[1])


# ---------------------------------------------------------------------------
# 1. Verified scope survives the bridge
# ---------------------------------------------------------------------------

def test_the_bridge_keeps_the_verified_customer_scope(service: EnhancedChatService) -> None:
    """The greeting runs the real chat entry with no model; the scope must survive it."""
    seen: Dict[str, Any] = {}

    async def run() -> None:
        await rt.run_agent(
            message="hello", session_id="review-session",
            user_id="review-sub", customer_id="CUST-THEO",
        )
        seen["scope"] = authorized_customer_id_var.get()
        seen["principal"] = principal_sub_var.get()

    asyncio.run(run())
    assert seen == {"scope": "CUST-THEO", "principal": "review-sub"}


def test_the_bridge_hands_chat_a_verified_turn_identity(service: EnhancedChatService) -> None:
    """Not a bare ``{sub}`` for chat to re-resolve into nothing."""
    seen: Dict[str, Any] = {}

    async def record(**kwargs: Any):
        seen.update(kwargs)
        yield {"type": "complete", "response": {"response": "ok", "success": True}}

    service.chat_stream = record
    asyncio.run(rt.run_agent(
        message="what did I buy", session_id="s-1", user_id="review-sub", customer_id="CUST-THEO",
        principal_username="theo",
    ))
    identity = seen["turn_identity"]
    assert isinstance(identity, TurnIdentity)
    assert identity.principal_sub == "review-sub"
    assert identity.shopper_customer_id == "CUST-THEO"
    # The name row-level security binds, so the customer's own reads see rows.
    assert identity.principal_username == "theo"
    assert identity.authenticated is True and identity.persona_is_simulated is False
    assert seen["user"] == {"sub": "review-sub"}

    seen.clear()
    asyncio.run(rt.run_agent(message="hello", session_id="s-2", principal_username="theo"))
    assert seen["turn_identity"] == TurnIdentity(), "a name with no verified subject binds nothing"
    assert seen["user"] is None


# ---------------------------------------------------------------------------
# 2. One Memory write per logical turn
# ---------------------------------------------------------------------------

def test_a_local_turn_is_written_to_memory_once(
    service: EnhancedChatService, memory: _RecordingMemory
) -> None:
    """The route owns the Memory receipt, so it tells the shared chat not to mirror."""
    seen: Dict[str, Any] = {}

    async def completed_turn(**kwargs: Any):
        seen.update(kwargs)
        if kwargs["persist_memory"]:
            await _append_pellier_stm_turn(
                kwargs["session_id"], kwargs["message"], "one answer", user=kwargs.get("user"),
            )
        yield {"type": "complete", "response": {"response": "one answer", "success": True}}

    service.chat_stream = completed_turn
    events = _stream("one question", memory)

    assert seen["persist_memory"] is False
    assert _event_types(events) == ["event: session", "event: memory", "event: chunk", "event: done"]
    assert [row for _namespace, row in memory.rows] == [
        {"role": "user", "content": "one question"},
        {"role": "assistant", "content": "one answer"},
    ]
    assert _data(events[-1])["memory"]["turns_persisted"] == 2


def test_chat_stream_honours_the_persist_memory_argument(
    service: EnhancedChatService, memory: _RecordingMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared stream's own guard, driven through a stubbed specialist, no model."""
    import services.chat as chat_module

    # Nothing here may reach Bedrock: the specialist is a plain callable, which
    # is all `chat_stream` asks of one.

    class _Answer:
        def __str__(self) -> str:
            return "one answer"

    class _Specialist:
        trace_attributes: Dict[str, Any] = {}

        def add_hook(self, hook: Any) -> None:
            return None

        def __call__(self, prompt: str) -> _Answer:
            return _Answer()

    monkeypatch.setattr(chat_module, "_build_dispatcher_specialist", lambda *a, **k: _Specialist())
    monkeypatch.setattr(chat_module, "classify_intent", lambda _m: "shopping")

    async def run(persist: bool) -> None:
        async for _event in service.chat_stream(
            message="a linen shirt", session_id="s-3", user={"sub": "review-sub"},
            turn_id="turn-" + "a" * 32, persist_memory=persist,
        ):
            pass

    asyncio.run(run(False))
    assert memory.rows == []
    asyncio.run(run(True))
    assert [row["role"] for _namespace, row in memory.rows] == ["user", "assistant"]


# ---------------------------------------------------------------------------
# 3. Failure is failure
# ---------------------------------------------------------------------------

async def _failed_turn(**kwargs: Any):
    yield {"type": "error", "error": "upstream_model_failed"}


def test_the_bridge_raises_a_typed_failure(service: EnhancedChatService) -> None:
    service.chat_stream = _failed_turn
    with pytest.raises(rt.AgentTurnError) as exc_info:
        asyncio.run(rt.run_agent(message="one question", session_id="s-4", user_id="review-sub"))
    assert exc_info.value.code == "upstream_model_failed"


def test_a_failed_turn_ends_the_stream_in_an_error_event(
    service: EnhancedChatService, memory: _RecordingMemory
) -> None:
    service.chat_stream = _failed_turn
    events = _stream("one question", memory)

    assert _event_types(events) == ["event: session", "event: error"]
    assert _data(events[-1]) == {"code": "upstream_model_failed"}
    assert memory.rows == [], "error text was stored as the assistant's answer"


def test_a_missing_chat_service_is_an_unavailable_error(
    monkeypatch: pytest.MonkeyPatch, memory: _RecordingMemory
) -> None:
    monkeypatch.setattr(rt.settings, "USE_AGENTCORE_RUNTIME", False, raising=False)
    monkeypatch.setitem(sys.modules, "app", types.SimpleNamespace(chat_service=None))
    events = _stream("one question", memory)

    assert _event_types(events) == ["event: session", "event: error"]
    assert _data(events[-1]) == {"code": "chat_service_unavailable"}
    assert memory.rows == []
