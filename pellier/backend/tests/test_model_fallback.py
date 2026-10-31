"""The Catalog and Support agents' model falls back to Sonnet when Bedrock cannot serve Opus."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from botocore.exceptions import ClientError, EventStreamError
from strands.models.bedrock import BedrockModel
from strands.types.exceptions import ModelThrottledException

from services import model_fallback
from services.model_fallback import (
    FallbackBedrockModel,
    answered_with,
    bedrock_unavailable,
    run_turn,
)

OPUS, SONNET = "global.anthropic.claude-opus-5-5", "global.anthropic.claude-sonnet-5-5"
TEXT = {"contentBlockDelta": {"delta": {"text": "ok"}}}


def _unavailable() -> EventStreamError:
    return EventStreamError(
        {"Error": {"Code": "serviceUnavailableException",
                   "Message": "Bedrock is unable to process your request."}},
        "ConverseStream")


def _model(script: dict[str, list[Any]]) -> FallbackBedrockModel:
    """A fallback model whose Bedrock calls follow ``script`` per model id."""
    model = FallbackBedrockModel(model_id=OPUS, max_tokens=1200,
                                 fallback_model_id=SONNET, fallback_max_tokens=2048)

    async def fake_stream(self: BedrockModel, *args: Any, **kwargs: Any):
        for item in script[self.config["model_id"]]:
            if isinstance(item, BaseException):
                raise item
            yield item

    model._parent_stream = fake_stream  # type: ignore[attr-defined]
    return model


def _run(model: FallbackBedrockModel) -> list[Any]:
    async def collect() -> list[Any]:
        return [event async for event in model.stream([], None, None)]
    return asyncio.run(collect())


@pytest.fixture(autouse=True)
def parent_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    async def delegate(self: Any, *args: Any, **kwargs: Any):
        async for event in self._parent_stream(self, *args, **kwargs):
            yield event
    monkeypatch.setattr(BedrockModel, "stream", delegate)


def test_an_unavailable_opus_hands_the_turn_to_sonnet_and_says_so() -> None:
    model = _model({OPUS: [{"messageStart": {"role": "assistant"}}, _unavailable()],
                    SONNET: [{"messageStart": {"role": "assistant"}}, TEXT]})
    switches: list[tuple[str, str]] = []
    model.on_fallback = lambda primary, used: switches.append((primary, used))

    events = _run(model)

    assert events == [{"messageStart": {"role": "assistant"}}, TEXT], "Opus's held start is dropped"
    assert switches == [(OPUS, SONNET)]
    assert model.fell_back_from == OPUS
    assert answered_with(model, OPUS) == SONNET
    assert model.config["max_tokens"] == 2048


def test_a_turn_that_fell_back_stays_on_sonnet() -> None:
    model = _model({OPUS: [_unavailable()], SONNET: [TEXT]})
    _run(model)
    model._parent_stream = None  # type: ignore[attr-defined]
    calls: list[str] = []

    async def record(self: Any, *args: Any, **kwargs: Any):
        calls.append(self.config["model_id"])
        yield TEXT

    model._parent_stream = record  # type: ignore[attr-defined]
    _run(model)
    assert calls == [SONNET]


def test_a_refusal_after_content_is_not_retried() -> None:
    model = _model({OPUS: [TEXT, _unavailable()], SONNET: [TEXT]})
    with pytest.raises(EventStreamError):
        _run(model)
    assert model.fell_back_from is None


def test_a_refusal_for_the_request_is_not_retried() -> None:
    invalid = ClientError({"Error": {"Code": "ValidationException", "Message": "bad"}}, "Converse")
    model = _model({OPUS: [invalid], SONNET: [TEXT]})
    with pytest.raises(ClientError):
        _run(model)
    assert answered_with(model, OPUS) == OPUS


def test_throttling_also_moves_to_sonnet() -> None:
    model = _model({OPUS: [ModelThrottledException("slow down")], SONNET: [TEXT]})
    assert _run(model) == [TEXT]
    assert bedrock_unavailable(ModelThrottledException("x"))


def test_sonnet_has_no_fallback_and_opus_has_sonnet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_fallback, "specialist_model",
                        lambda tier: (SONNET, 2048) if tier == "sonnet" else (OPUS, 1200))
    assert type(model_fallback.specialist_bedrock_model(SONNET, 2048)) is BedrockModel
    opus = model_fallback.specialist_bedrock_model(OPUS, 1200)
    assert isinstance(opus, FallbackBedrockModel) and opus.fallback_model_id == SONNET


def test_the_catalog_and_support_agents_use_the_fallback_model() -> None:
    from agents.catalog_agent import build_catalog_agent
    from agents.support_agent import build_support_agent

    for agent in (build_catalog_agent(), build_support_agent()):
        assert isinstance(agent.model, FallbackBedrockModel), agent.name


def test_the_builder_view_names_the_model_that_answered() -> None:
    from types import SimpleNamespace

    from services.chat import _report_model_fallback

    model = _model({OPUS: [_unavailable()], SONNET: [TEXT]})
    steps = SimpleNamespace(model_id=OPUS)
    route_facts: dict[str, Any] = {"model_id": OPUS, "note": None}
    _report_model_fallback(SimpleNamespace(model=model), steps, route_facts)

    _run(model)

    assert steps.model_id == SONNET, "tool steps after the switch name Sonnet"
    assert route_facts["model_id"] == SONNET
    assert OPUS in route_facts["note"] and SONNET in route_facts["note"]


def _answer(text: str) -> list[Any]:
    return [{"messageStart": {"role": "assistant"}},
            {"contentBlockDelta": {"delta": {"text": text}}},
            {"contentBlockStop": {}},
            {"messageStop": {"stopReason": "end_turn"}}]


def _agent(model: BedrockModel) -> Any:
    from strands import Agent

    return Agent(model=model, callback_handler=None)


def test_a_runtime_turn_refused_mid_answer_continues_on_sonnet_without_rerunning_tools(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from strands import Agent, tool

    reads: list[str] = []

    @tool
    def get_tickets() -> str:
        """Read the caller's tickets."""
        reads.append("get_tickets")
        return "1 open ticket"

    calls = {OPUS: [
        [{"messageStart": {"role": "assistant"}},
         {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "t1", "name": "get_tickets"}}}},
         {"contentBlockDelta": {"delta": {"toolUse": {"input": "{}"}}}},
         {"contentBlockStop": {}},
         {"messageStop": {"stopReason": "tool_use"}}],
        [{"messageStart": {"role": "assistant"}},
         {"contentBlockDelta": {"delta": {"text": "Your ticket is"}}}, _unavailable()],
    ], SONNET: [_answer("Your ticket is open.")]}

    async def by_call(self: Any, *args: Any, **kwargs: Any):
        for item in calls[self.config["model_id"]].pop(0):
            if isinstance(item, BaseException):
                raise item
            yield item

    model = FallbackBedrockModel(model_id=OPUS, max_tokens=1200,
                                 fallback_model_id=SONNET, fallback_max_tokens=2048)
    model._parent_stream = by_call  # type: ignore[attr-defined]
    switches: list[tuple[str, str]] = []
    model.on_fallback = lambda primary, used: switches.append((primary, used))
    agent = Agent(model=model, tools=[get_tickets], callback_handler=None)

    response = run_turn(agent, "Where is my ticket?")

    assert str(response).strip() == "Your ticket is open."
    assert reads == ["get_tickets"], "the tool Opus called ran once, not again on Sonnet"
    assert switches == [(OPUS, SONNET)]
    assert answered_with(model, OPUS) == SONNET
    assert [message["role"] for message in agent.messages] == \
        ["user", "assistant", "user", "assistant"], "one prompt, one tool round, one answer"


def test_a_runtime_turn_already_on_sonnet_is_not_run_again() -> None:
    model = _model({OPUS: _answer("unused"), SONNET: [TEXT, _unavailable()]})
    model.update_config(model_id=SONNET)
    with pytest.raises(EventStreamError):
        run_turn(_agent(model), "hello")


def test_a_runtime_turn_refused_for_the_request_is_not_run_again() -> None:
    invalid = ClientError({"Error": {"Code": "ValidationException", "Message": "bad"}}, "Converse")
    model = _model({OPUS: [TEXT, invalid], SONNET: _answer("unused")})
    with pytest.raises(ClientError):
        run_turn(_agent(model), "hello")
    assert answered_with(model, OPUS) == OPUS


def test_a_runtime_turn_without_a_fallback_is_not_run_again() -> None:
    calls: list[str] = []

    async def refuse(self: Any, *args: Any, **kwargs: Any):
        calls.append(self.config["model_id"])
        yield TEXT
        raise _unavailable()

    model = BedrockModel(model_id=SONNET, max_tokens=2048)
    model._parent_stream = refuse  # type: ignore[attr-defined]
    with pytest.raises(EventStreamError):
        run_turn(_agent(model), "hello")
    assert calls == [SONNET]


def test_the_runtime_dispatcher_runs_its_turn_through_run_turn() -> None:
    import inspect

    from services.agentcore_gateway import ManagedGatewayDispatcher

    source = inspect.getsource(ManagedGatewayDispatcher.__call__)
    assert "run_turn(agent, prompt)" in source and "agent(prompt)" not in source.replace(
        "run_turn(agent, prompt)", "")
