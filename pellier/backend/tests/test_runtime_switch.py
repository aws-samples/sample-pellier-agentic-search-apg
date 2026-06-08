"""Runtime-switch tests for the Challenge 5 dispatcher.

Validates Requirement 2.5.1 from
`.kiro/specs/pellier-storefront/requirements.md` and Design
"Runtime selection switch":

  2.5.1  When ``settings.USE_AGENTCORE_RUNTIME`` is ``False`` (the
         default), ``services.agentcore_runtime.run_agent`` SHALL
         dispatch to the in-process Strands orchestrator produced by
         ``agents.orchestrator.create_orchestrator`` (Challenge 4).
         When flipped to ``True`` the same call SHALL forward the
         request to ``run_agent_on_runtime`` so a single env var flip
         migrates ``/api/agent/chat`` from local execution to the
         managed AgentCore Runtime without any other code change.

Both execution paths are mocked:

  - The in-process path stubs ``create_orchestrator`` so no Bedrock /
    Strands agent is actually constructed.
  - The runtime path stubs ``run_agent_on_runtime`` so no boto3 /
    AgentCore SDK call is actually performed.

Runnable from the repo root per ``pytest.ini``:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_runtime_switch.py -v
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# In-process orchestrator stub (Challenge 4 path)
# ---------------------------------------------------------------------------


class _StubOrchestrator:
    """Stand-in for the Strands ``Agent`` returned by
    ``create_orchestrator``. Records the prompt it receives and the
    trace attributes the dispatcher attaches, returns a canned string.
    """

    instances: list["_StubOrchestrator"] = []

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.trace_attributes: dict[str, Any] = {}
        type(self).instances.append(self)

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        return f"[stub-inprocess] {prompt}"


@pytest.fixture(autouse=True)
def _reset_stub_state() -> None:
    _StubOrchestrator.instances = []


@pytest.fixture
def stub_create_orchestrator(monkeypatch: pytest.MonkeyPatch):
    """Patch ``agents.orchestrator.create_orchestrator`` to return a
    recording stub so the in-process path never touches Bedrock."""
    import agents.orchestrator as orch

    def _factory() -> _StubOrchestrator:
        return _StubOrchestrator()

    monkeypatch.setattr(orch, "create_orchestrator", _factory)
    return _factory


@pytest.fixture
def stub_runtime_call(monkeypatch: pytest.MonkeyPatch):
    """Patch ``run_agent_on_runtime`` so the runtime path never calls
    boto3. Records each invocation's kwargs for assertion."""
    import services.agentcore_runtime as rt

    calls: list[dict[str, Any]] = []

    async def _fake_run_agent_on_runtime(
        message: str,
        session_id: str,
        user_id: Any = None,
        auth_token: Any = None,
    ) -> str:
        calls.append(
            {
                "message": message,
                "session_id": session_id,
                "user_id": user_id,
                "auth_token": auth_token,
            }
        )
        return f"[stub-runtime] {message}"

    monkeypatch.setattr(rt, "run_agent_on_runtime", _fake_run_agent_on_runtime)
    return calls


# ---------------------------------------------------------------------------
# Default (USE_AGENTCORE_RUNTIME=false) — in-process Strands path
# ---------------------------------------------------------------------------


def test_use_agentcore_runtime_defaults_to_false() -> None:
    """The feature flag SHALL default to False so existing labs run
    against the in-process orchestrator without any env setup."""
    from config import Settings

    # Construct a fresh Settings with no env override (the test
    # environment may have DB_* etc. already set; that's fine).
    s = Settings()
    assert s.USE_AGENTCORE_RUNTIME is False


def test_run_agent_dispatches_to_inprocess_when_flag_false(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
    stub_runtime_call: list[dict[str, Any]],
) -> None:
    """When ``USE_AGENTCORE_RUNTIME`` is False, ``run_agent`` SHALL
    call the in-process orchestrator and SHALL NOT call
    ``run_agent_on_runtime``."""
    import asyncio

    import services.agentcore_runtime as rt

    monkeypatch.setattr(rt.settings, "USE_AGENTCORE_RUNTIME", False)

    result = asyncio.run(
        rt.run_agent(
            message="show me linen pieces",
            session_id="sess-1",
            user_id="user-abc",
        )
    )

    # In-process stub fired exactly once with the unmodified prompt.
    assert len(_StubOrchestrator.instances) == 1
    stub = _StubOrchestrator.instances[0]
    assert stub.calls == ["show me linen pieces"]
    assert result == "[stub-inprocess] show me linen pieces"

    # Runtime path was not taken.
    assert stub_runtime_call == []

    # Dispatcher attached trace attributes so the otel extractor (C8)
    # sees the session + user context on the in-process path too.
    assert stub.trace_attributes == {
        "session.id": "sess-1",
        "user.id": "user-abc",
        "runtime": "in-process",
        "workshop": "pellier",
    }


def test_run_agent_inprocess_defaults_anonymous_user_id(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
    stub_runtime_call: list[dict[str, Any]],
) -> None:
    """When no ``user_id`` is passed, the dispatcher SHALL tag traces
    as ``anonymous`` on the in-process path."""
    import asyncio

    import services.agentcore_runtime as rt

    monkeypatch.setattr(rt.settings, "USE_AGENTCORE_RUNTIME", False)

    asyncio.run(
        rt.run_agent(
            message="hello",
            session_id="sess-anon",
        )
    )

    assert len(_StubOrchestrator.instances) == 1
    assert _StubOrchestrator.instances[0].trace_attributes["user.id"] == "anonymous"


# ---------------------------------------------------------------------------
# Flipped (USE_AGENTCORE_RUNTIME=true) — AgentCore Runtime path
# ---------------------------------------------------------------------------


def test_run_agent_dispatches_to_runtime_when_flag_true(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
    stub_runtime_call: list[dict[str, Any]],
) -> None:
    """When ``USE_AGENTCORE_RUNTIME`` is True, ``run_agent`` SHALL call
    ``run_agent_on_runtime`` with the caller's message, session_id,
    and user_id, and SHALL NOT invoke the in-process orchestrator."""
    import asyncio

    import services.agentcore_runtime as rt

    monkeypatch.setattr(rt.settings, "USE_AGENTCORE_RUNTIME", True)

    result = asyncio.run(
        rt.run_agent(
            message="something for warm evenings out",
            session_id="sess-runtime",
            user_id="cognito-sub-xyz",
            auth_token="jwt-123",
        )
    )

    # Runtime path fired exactly once with the full invocation context.
    assert stub_runtime_call == [
        {
            "message": "something for warm evenings out",
            "session_id": "sess-runtime",
            "user_id": "cognito-sub-xyz",
            "auth_token": "jwt-123",
        }
    ]
    assert result == "[stub-runtime] something for warm evenings out"

    # In-process path was not taken.
    assert _StubOrchestrator.instances == []


def test_run_agent_runtime_passes_none_user_id_through(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
    stub_runtime_call: list[dict[str, Any]],
) -> None:
    """Anonymous requests SHALL reach the runtime path with
    ``user_id=None`` so the runtime entrypoint can fall back to
    ``"anonymous"`` itself (C5 contract in ``agentcore_runtime.py``)."""
    import asyncio

    import services.agentcore_runtime as rt

    monkeypatch.setattr(rt.settings, "USE_AGENTCORE_RUNTIME", True)

    asyncio.run(rt.run_agent(message="hi", session_id="sess-none"))

    assert stub_runtime_call == [
        {
            "message": "hi",
            "session_id": "sess-none",
            "user_id": None,
            "auth_token": None,
        }
    ]


# ---------------------------------------------------------------------------
# Runtime implementation — missing endpoint falls back to in-process
# ---------------------------------------------------------------------------


def test_run_agent_on_runtime_falls_back_when_endpoint_missing(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
) -> None:
    """If the flag is flipped but ``AGENTCORE_RUNTIME_ENDPOINT`` is not
    configured, ``run_agent_on_runtime`` SHALL emit a warning and fall
    back to the in-process orchestrator so a misconfigured environment
    never breaks the storefront."""
    import asyncio

    import services.agentcore_runtime as rt

    monkeypatch.setattr(rt.settings, "AGENTCORE_RUNTIME_ENDPOINT", None)

    result = asyncio.run(
        rt.run_agent_on_runtime(
            message="fallback case",
            session_id="sess-fb",
            user_id="user-abc",
        )
    )

    # In-process stub fired as the fallback.
    assert len(_StubOrchestrator.instances) == 1
    assert _StubOrchestrator.instances[0].calls == ["fallback case"]
    assert result == "[stub-inprocess] fallback case"


def test_run_agent_on_runtime_falls_back_when_auth_token_missing(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
) -> None:
    """The managed Runtime is Cognito JWT-protected. Anonymous calls keep
    the route usable by falling back to the in-process orchestrator."""
    import asyncio

    import services.agentcore_runtime as rt

    monkeypatch.setattr(rt.settings, "AGENTCORE_RUNTIME_ENDPOINT", "runtime-id-123")

    result = asyncio.run(
        rt.run_agent_on_runtime(
            message="anonymous fallback",
            session_id="sess-anon",
            user_id=None,
            auth_token=None,
        )
    )

    assert len(_StubOrchestrator.instances) == 1
    assert _StubOrchestrator.instances[0].calls == ["anonymous fallback"]
    assert result == "[stub-inprocess] anonymous fallback"


def test_run_agent_on_runtime_invokes_agentcore_runtime_with_jwt(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
) -> None:
    """The live Runtime path SHALL use the AgentCore Runtime client,
    runtime id, and caller JWT shape validated by the provisioning smoke test."""
    import asyncio

    import services.agentcore_runtime as rt

    calls: list[dict[str, Any]] = []

    class _Body:
        def read(self) -> bytes:
            return b'{"response":"runtime ok"}'

    class _RuntimeClient:
        def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"body": _Body()}

    def _client(service_name: str, region_name: str) -> _RuntimeClient:
        calls.append({"service_name": service_name, "region_name": region_name})
        return _RuntimeClient()

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=_client))
    monkeypatch.setattr(
        rt.settings,
        "AGENTCORE_RUNTIME_ENDPOINT",
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:agent-runtime/pellier-abc",
    )
    monkeypatch.setattr(rt.settings, "AWS_REGION", "us-east-1", raising=False)

    result = asyncio.run(
        rt.run_agent_on_runtime(
            message="runtime invoke",
            session_id="sess-runtime",
            user_id="user-123",
            auth_token="jwt-abc",
        )
    )

    assert result == "runtime ok"
    assert calls[0] == {
        "service_name": "bedrock-agentcore-runtime",
        "region_name": "us-east-1",
    }
    assert calls[1] == {
        "agentRuntimeId": "pellier-abc",
        "payload": '{"prompt": "runtime invoke", "session_id": "sess-runtime", "user_id": "user-123"}',
        "authToken": "jwt-abc",
    }
