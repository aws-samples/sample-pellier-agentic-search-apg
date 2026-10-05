"""Executable contract tests for the managed AgentCore Runtime entrypoint."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest

import services.agentcore_gateway as gateway_module
from services.conversation_context import build_conversation_prompt


ENTRYPOINT = Path(__file__).resolve().parents[1] / "agentcore_runtime.py"


class _RuntimeApp:
    def __init__(self) -> None:
        self.handler = None

    def entrypoint(self, handler):
        self.handler = handler
        return handler


class _Context:
    request_headers = {"Authorization": "Bearer verified-jwt"}


class _Response:
    def __init__(self, text: str, stop_reason: str = "end_turn") -> None:
        self.text = text
        self.stop_reason = stop_reason

    def __str__(self) -> str:
        return self.text


class _Dispatcher:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls: list[str] = []
        self.trace_attributes: dict[str, str] = {}
        self.last_products = [
            {
                "productId": 7,
                "name": "Italian Linen Camp Shirt",
                "price": 228,
            }
        ]
        self.last_tool_events = [
            {
                "id": "tool-1",
                "tool": "search_products",
                "status": "success",
            }
        ]
        self.last_intent = "recommendation"
        self.last_specialist = "recommendation"
        self.last_model_id = "global.anthropic.claude-opus-5"
        self.last_tool_names = ["search_products"]
        self.last_unpublished_tools = ("get_tickets",)
        self.last_skills = [
            {
                "name": "the-gift-table",
                "display_name": "The Gift Table",
                "path": "skills/the-gift-table/SKILL.md",
                "loaded": "fixed",
            }
        ]

    def __call__(self, prompt: str) -> _Response:
        self.calls.append(prompt)
        return self.response


def _load_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response: _Response,
) -> tuple[Any, _Dispatcher, list[dict[str, Any]]]:
    runtime_sdk = types.ModuleType("bedrock_agentcore.runtime")
    runtime_sdk.BedrockAgentCoreApp = _RuntimeApp
    runtime_sdk.BedrockAgentCoreContext = type(
        "_BedrockAgentCoreContext",
        (),
        {"get_request_headers": staticmethod(lambda: {})},
    )
    package = types.ModuleType("bedrock_agentcore")
    package.runtime = runtime_sdk
    monkeypatch.setitem(sys.modules, "bedrock_agentcore", package)
    monkeypatch.setitem(sys.modules, "bedrock_agentcore.runtime", runtime_sdk)
    monkeypatch.setenv(
        "AGENTCORE_GATEWAY_URL",
        "https://gateway.example.test/mcp",
    )

    dispatcher = _Dispatcher(response)
    factory_calls: list[dict[str, Any]] = []

    def _factory(**kwargs: Any) -> _Dispatcher:
        factory_calls.append(kwargs)
        return dispatcher

    monkeypatch.setattr(gateway_module, "create_gateway_dispatcher", _factory)

    spec = importlib.util.spec_from_file_location(
        "test_managed_agentcore_entrypoint",
        ENTRYPOINT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.app is not None
    assert module.app.handler is not None
    return module.app.handler, dispatcher, factory_calls


def test_entrypoint_runs_fixed_dispatcher_and_returns_observed_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler, dispatcher, factory_calls = _load_entrypoint(
        monkeypatch,
        response=_Response("A grounded resort edit."),
    )

    result = handler(
        {
            "prompt": "Build a resort edit",
            "session_id": "session-123",
            "turn_id": "turn-123",
            "user_id": "cognito-sub-123",
            "customer_id": "CUST-MARCO",
            "history": [{"role": "user", "content": "I prefer linen."}],
        },
        _Context(),
    )

    assert factory_calls == [
        {
            "access_token": "verified-jwt",
            "customer_id": "CUST-MARCO",
            "routing_query": "Build a resort edit",
        }
    ]
    assert dispatcher.calls == [
        build_conversation_prompt(
            "Build a resort edit",
            [{"role": "user", "content": "I prefer linen."}],
        )
    ]
    assert dispatcher.trace_attributes == {
        "session.id": "session-123",
        "turn.id": "turn-123",
        "user.id": "cognito-sub-123",
        "runtime": "agentcore-managed",
        "workshop": "pellier",
    }
    assert result == {
        "response": "A grounded resort edit.",
        "products": dispatcher.last_products,
        "rail": "gateway-mcp",
        "intent": "recommendation",
        "specialist": "recommendation",
        "model": "global.anthropic.claude-opus-5",
        "gateway_tools": ["search_products"],
        "unpublished_tools": ["get_tickets"],
        "tool_calls": dispatcher.last_tool_events,
        # The skills the agent's prompt carried, from the source: the app
        # renders this list and never assembles one of its own.
        "skills": dispatcher.last_skills,
        # How the agent's turn ended, for the receipt.
        "stop_reason": "end_turn",
        "orchestration": "dispatcher",
        # Echoed on every response so the caller can prove which revision
        # Runtime executed; empty here because the test process carries no
        # injected digest, which is the same honest answer a runtime deployed
        # before this mechanism gives.
        "build_fingerprint": "",
    }


def test_entrypoint_rejects_truncated_model_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler, dispatcher, _ = _load_entrypoint(
        monkeypatch,
        response=_Response("Partial answer", stop_reason="max_tokens"),
    )

    result = handler(
        {
            "prompt": "Build a resort edit",
            "session_id": "session-123",
            "user_id": "cognito-sub-123",
            "customer_id": "CUST-MARCO",
        },
        _Context(),
    )

    assert result == {
        "error": "runtime_output_truncated",
        "products": dispatcher.last_products,
        "rail": "gateway-mcp",
        "tool_calls": dispatcher.last_tool_events,
        # Present on the failure path too: which revision produced a truncated
        # answer is exactly as worth knowing as which produced a good one.
        "build_fingerprint": "",
    }


@pytest.mark.parametrize("payload_session", [None, "different-payload-session"])
def test_entrypoint_correlates_with_the_actual_runtime_session(monkeypatch, payload_session):
    handler, dispatcher, _ = _load_entrypoint(monkeypatch, response=_Response("A linen item."))
    context = _Context()
    context.session_id = "actual-runtime-session"
    handler({"prompt": "Find linen", "session_id": payload_session}, context)
    assert dispatcher.trace_attributes["session.id"] == "actual-runtime-session"


def test_entrypoint_installs_model_content_redaction_before_the_tracer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The managed rail must withhold prompts and completions like app.py does.

    Strands' tracer reads OTEL_SEMCONV_STABILITY_OPT_IN once, when it is
    constructed. The Runtime container never runs app.py's lifespan, so unless
    the entrypoint installs the redact-all token itself, every agent span the
    platform exports carries the shopper's words in clear text.
    """
    from services.otel_content_redaction import SEMCONV_ENV, redaction_already_configured

    monkeypatch.delenv(SEMCONV_ENV, raising=False)
    monkeypatch.delenv("OTEL_REDACT_MODEL_CONTENT", raising=False)

    _load_entrypoint(monkeypatch, response=_Response("Linen for Goa"))

    assert redaction_already_configured(os.environ.get(SEMCONV_ENV, ""))

    # Order matters: the token must be in place before any Strands-importing
    # module can construct a tracer.
    source = ENTRYPOINT.read_text(encoding="utf-8")
    assert source.index("apply_model_content_redaction(") < source.index(
        "from bedrock_agentcore.runtime import BedrockAgentCoreApp"
    )


def test_entrypoint_leaves_redaction_off_only_when_told_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.otel_content_redaction import SEMCONV_ENV, redaction_already_configured

    monkeypatch.delenv(SEMCONV_ENV, raising=False)
    monkeypatch.setenv("OTEL_REDACT_MODEL_CONTENT", "false")

    _load_entrypoint(monkeypatch, response=_Response("Linen for Goa"))

    assert not redaction_already_configured(os.environ.get(SEMCONV_ENV, ""))
