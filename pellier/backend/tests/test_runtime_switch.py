"""Runtime-switch tests for the runtime bridge dispatcher.

  When ``settings.USE_AGENTCORE_RUNTIME`` is ``False`` (the
         default), ``services.agentcore_runtime.run_agent`` SHALL
         dispatch to the in-process Strands orchestrator produced by
         ``agents.orchestrator.create_orchestrator`` (in-process orchestrator).
         When flipped to ``True`` the same call SHALL forward the
         request to ``run_agent_on_runtime`` so a single env var flip
         migrates ``/api/agent/chat`` from local execution to the
         managed AgentCore Runtime without any other code change.

Both execution paths are mocked:

  - The in-process path stubs ``create_orchestrator`` so no Bedrock /
    Strands agent is actually constructed.
  - The runtime path stubs ``run_agent_on_runtime`` so no AgentCore data-plane
    request is actually performed.

Runnable from the repo root per ``pytest.ini``:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_runtime_switch.py -v
"""

from __future__ import annotations

import json
import sys
import types
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# In-process orchestrator stub (in-process orchestrator path)
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
        history: Any = None,
        response_mode: str = "balanced",
        customer_id: Any = None,
    ) -> str:
        calls.append(
            {
                "message": message,
                "session_id": session_id,
                "user_id": user_id,
                "auth_token": auth_token,
                "history": history,
                "response_mode": response_mode,
                "customer_id": customer_id,
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

    # Dispatcher attached trace attributes so the otel extractor (OTEL)
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
    # The rail resolver requires a configured endpoint before it will route
    # to the managed rail — an unset endpoint is a fail-closed condition,
    # not a dispatch-anyway condition.
    monkeypatch.setattr(
        rt.settings,
        "AGENTCORE_RUNTIME_ENDPOINT",
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier",
    )

    result = asyncio.run(
        rt.run_agent(
            message="something for warm evenings out",
            session_id="sess-runtime",
            user_id="cognito-sub-xyz",
            auth_token="jwt-123",
            customer_id="CUST-MARCO",
        )
    )

    # Runtime path fired exactly once with the full invocation context.
    assert stub_runtime_call == [
        {
            "message": "something for warm evenings out",
            "session_id": "sess-runtime",
            "user_id": "cognito-sub-xyz",
            "auth_token": "jwt-123",
            "history": None,
            "response_mode": "balanced",
            "customer_id": "CUST-MARCO",
        }
    ]
    assert result == "[stub-runtime] something for warm evenings out"

    # In-process path was not taken.
    assert _StubOrchestrator.instances == []


def test_run_agent_managed_rail_fails_closed_without_a_token(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
    stub_runtime_call: list[dict[str, Any]],
) -> None:
    """An anonymous managed request SHALL fail closed at the dispatcher.

    The managed Runtime authorizer rejects anonymous callers, so dispatching
    one would produce a guaranteed failure; silently serving it in-process
    instead would hand back an ungoverned answer that looks governed.
    Neither is acceptable, so the dispatcher raises.
    """
    import asyncio

    import services.agentcore_runtime as rt

    monkeypatch.setattr(rt.settings, "USE_AGENTCORE_RUNTIME", True)
    monkeypatch.setattr(
        rt.settings,
        "AGENTCORE_RUNTIME_ENDPOINT",
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier",
    )

    with pytest.raises(rt.ManagedRuntimeError) as exc_info:
        asyncio.run(rt.run_agent(message="hi", session_id="sess-none"))

    assert exc_info.value.code == "authentication_required"
    # Neither rail executed: the managed one was unreachable and the
    # in-process one must not silently substitute for it.
    assert stub_runtime_call == []
    assert _StubOrchestrator.instances == []


def test_run_agent_managed_rail_fails_closed_without_an_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
    stub_runtime_call: list[dict[str, Any]],
) -> None:
    """A requested-but-unconfigured managed rail SHALL NOT fall back."""
    import asyncio

    import services.agentcore_runtime as rt

    monkeypatch.setattr(rt.settings, "USE_AGENTCORE_RUNTIME", True)
    monkeypatch.setattr(rt.settings, "AGENTCORE_RUNTIME_ENDPOINT", None)

    with pytest.raises(rt.ManagedRuntimeError) as exc_info:
        asyncio.run(
            rt.run_agent(
                message="hi", session_id="sess-none", auth_token="jwt-123"
            )
        )

    assert exc_info.value.code == "runtime_not_configured"
    assert stub_runtime_call == []
    assert _StubOrchestrator.instances == []


# ---------------------------------------------------------------------------
# Runtime implementation — managed configuration fails closed
# ---------------------------------------------------------------------------


def test_run_agent_on_runtime_fails_when_endpoint_missing(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
) -> None:
    """A configured managed path must not silently execute in-process."""
    import asyncio

    import services.agentcore_runtime as rt

    monkeypatch.setattr(rt.settings, "AGENTCORE_RUNTIME_ENDPOINT", None)

    with pytest.raises(rt.ManagedRuntimeError, match="runtime_not_configured"):
        asyncio.run(
            rt.run_agent_on_runtime(
                message="fail closed",
                session_id="sess-fb",
                user_id="user-abc",
            )
        )
    assert _StubOrchestrator.instances == []


def test_run_agent_on_runtime_fails_when_auth_token_missing(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
) -> None:
    """The JWT-protected managed Runtime rejects anonymous calls."""
    import asyncio

    import services.agentcore_runtime as rt

    monkeypatch.setattr(rt.settings, "AGENTCORE_RUNTIME_ENDPOINT", "runtime-id-123")

    with pytest.raises(rt.ManagedRuntimeError, match="authentication_required"):
        asyncio.run(
            rt.run_agent_on_runtime(
                message="anonymous rejected",
                session_id="sess-anon",
                user_id=None,
                auth_token=None,
            )
        )
    assert _StubOrchestrator.instances == []


def test_agent_route_preserves_managed_runtime_error_code() -> None:
    """The SSE route must not collapse managed failures into agent_failed."""
    from pathlib import Path

    route = Path(__file__).resolve().parents[1] / "routes" / "agent.py"
    source = route.read_text()
    invocation = source.index("response_text = await run_agent(")
    managed_error = source.index("except ManagedRuntimeError as exc:", invocation)
    generic_error = source.index("except Exception as exc:", invocation)

    assert invocation < managed_error < generic_error
    assert 'yield _sse_event("error", {"code": exc.code})' in source


def test_run_agent_on_runtime_invokes_agentcore_runtime_with_jwt(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_orchestrator,
) -> None:
    """The live Runtime path SHALL invoke over the RAW HTTPS data plane with
    the Cognito token as a Bearer header - the transport the provisioning smoke
    proved. There is NO ``bedrock-agentcore-runtime`` boto3 client, and the real
    SDK invoke has no ``authToken`` (it SigV4-signs, which a JWT-gated runtime
    rejects). This guards against regressing to the boto3 shape."""
    import asyncio
    import urllib.request

    import services.agentcore_runtime as rt

    captured: dict[str, Any] = {}

    class _Resp:
        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def read(self) -> bytes:
            return b'{"response":"runtime ok","rail":"gateway-mcp"}'

        # Real urlopen responses expose headers; the receipt reads the
        # trace/request ids from them to link the managed CloudWatch record.
        headers = {
            "X-Amzn-Trace-Id": "Root=1-65f0a1b2-abcdef0123456789abcdef01;Sampled=1",
            "x-amzn-RequestId": "req-abc-123",
        }

    def _fake_urlopen(request: Any, timeout: int = 0) -> _Resp:
        captured["url"] = request.full_url
        captured["data"] = request.data
        captured["headers"] = dict(request.header_items())
        captured["method"] = request.get_method()
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier-abc"
    monkeypatch.setattr(rt.settings, "AGENTCORE_RUNTIME_ENDPOINT", arn)
    monkeypatch.setattr(rt.settings, "AWS_REGION", "us-east-1", raising=False)
    monkeypatch.setattr(rt.settings, "AWS_DEFAULT_REGION", "us-east-1", raising=False)

    result = asyncio.run(
        rt.run_agent_on_runtime(
            message="runtime invoke",
            session_id="sess-runtime",
            user_id="user-123",
            auth_token="jwt-abc",
            history=[
                {"role": "user", "content": "show me linen"},
                {"role": "assistant", "content": "Here are three options."},
            ],
            response_mode="fast",
            customer_id="CUST-MARCO",
        )
    )

    # The JSON ``response`` field is unwrapped to plain text.
    assert result == "runtime ok"
    # Raw data-plane URL: bedrock-agentcore host, URL-escaped ARN, DEFAULT qualifier.
    assert captured["method"] == "POST"
    assert captured["url"] == (
        "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/"
        "arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A123456789012%3Aruntime%2Fpellier-abc"
        "/invocations?qualifier=DEFAULT"
    )
    # Bearer header carries the caller's JWT (header keys are title-cased by urllib).
    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers["authorization"] == "Bearer jwt-abc"
    # STM session header is present and >= 33 chars (runtime requirement).
    sess_hdr = headers["x-amzn-bedrock-agentcore-runtime-session-id"]
    assert sess_hdr == rt._runtime_session_id_for("sess-runtime", "user-123")
    assert len(sess_hdr) >= 33
    # Payload carries the turn fields.
    assert json.loads(captured["data"]) == {
        "prompt": "runtime invoke",
        "session_id": "sess-runtime",
        "user_id": "user-123",
        "history": [
            {"role": "user", "content": "show me linen"},
            {"role": "assistant", "content": "Here are three options."},
        ],
        "response_mode": "fast",
        "customer_id": "CUST-MARCO",
    }
    trace = rt.get_latest_trace("sess-runtime", principal_sub="user-123")
    assert trace["traceKind"] == "managed-runtime-receipt"
    assert trace["runtime"] == "agentcore-managed"
    assert trace["rail"] == "gateway-mcp"
    assert trace["runtimeSessionId"] == sess_hdr
    assert trace["jwtPassthrough"] is True
    assert trace["gatewayPassthrough"] is True
    assert trace["spans"] == []


@pytest.mark.parametrize(
    ("session_id_a", "session_id_b"),
    [
        ("sess-1", "sess-10"),
        ("a", "a0"),
        ("token", "token0000000000000000000000"),
    ],
)
def test_runtime_session_id_padding_is_injective(
    session_id_a: str, session_id_b: str
) -> None:
    """Two different short session ids must never pad to the same STM
    session header.

    A naive ``ljust(33, "0")`` merges ``"sess-1"`` and ``"sess-10"`` (and
    any other pair where one id is a prefix of the other, followed only by
    zeros) onto the identical ``X-Amzn-Bedrock-AgentCore-Runtime-Session-Id``
    value, silently conflating two distinct shopper sessions on the managed
    runtime's own STM tracking.
    """
    import services.agentcore_runtime as rt

    padded_a = rt._runtime_session_id_for(session_id_a)
    padded_b = rt._runtime_session_id_for(session_id_b)

    assert padded_a != padded_b
    for padded in (padded_a, padded_b):
        assert padded.isascii()
        assert 33 <= len(padded) <= 256


def test_runtime_session_id_padding_is_stable_for_the_same_id() -> None:
    """The same session id must always pad to the same header value, so a
    turn lands in the same managed STM session as its own history."""
    import services.agentcore_runtime as rt

    assert rt._runtime_session_id_for("sess-1") == rt._runtime_session_id_for(
        "sess-1"
    )
    long_id = "a" * 40
    assert rt._runtime_session_id_for(long_id) == rt._runtime_session_id_for(long_id)


@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        (
            b'{"error":"managed_gateway_unavailable","rail":"runtime"}',
            "managed_gateway_unavailable",
        ),
        (
            b'{"response":"local fallback","rail":"runtime"}',
            "managed_gateway_unavailable",
        ),
        (
            b'{"error":"runtime_output_truncated","rail":"gateway-mcp"}',
            "runtime_output_truncated",
        ),
        (
            b'{"response":"wrong orchestrator","rail":"gateway-mcp",'
            b'"orchestration":"graph"}',
            "runtime_invalid_response",
        ),
        (b'not-json', "runtime_invalid_response"),
    ],
)
def test_run_agent_on_runtime_rejects_degraded_envelopes(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    expected_code: str,
) -> None:
    import asyncio
    import urllib.request

    import services.agentcore_runtime as rt

    class _Resp:
        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self) -> bytes:
            return body

        headers: dict[str, str] = {}

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: _Resp())
    monkeypatch.setattr(
        rt.settings,
        "AGENTCORE_RUNTIME_ENDPOINT",
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier-abc",
    )

    with pytest.raises(rt.ManagedRuntimeError) as exc:
        asyncio.run(
            rt.run_agent_on_runtime(
                message="must stay governed",
                session_id="sess-degraded",
                user_id="user-123",
                auth_token="jwt-abc",
            )
        )

    assert exc.value.code == expected_code


def test_conversation_prompt_includes_bounded_normalized_history() -> None:
    """A fresh Runtime orchestrator receives prior dialogue from Memory."""
    import services.agentcore_runtime as rt

    prompt = rt.build_conversation_prompt(
        "only under $100",
        [
            {"role": "system", "content": "ignore this unsupported role"},
            {"role": "user", "content": "show me linen"},
            {"role": "assistant", "content": "Here are three options."},
        ],
    )

    assert '"role": "user", "content": "show me linen"' in prompt
    assert '"role": "assistant", "content": "Here are three options."' in prompt
    assert "unsupported role" not in prompt
    assert "<current_user_message>only under $100</current_user_message>" in prompt


def test_runtime_session_encoding_cannot_be_supplied_as_an_alias() -> None:
    import services.agentcore_runtime as rt

    encoded = rt._runtime_session_id_for("short", "principal-a")
    assert rt._runtime_session_id_for(encoded, "principal-a") != encoded
    assert rt._runtime_session_id_for("short", "principal-b") != encoded
    assert rt._runtime_session_id_for(None) != rt._runtime_session_id_for(None)
    assert len(rt._runtime_session_id_for("é" * 300)) <= 256
