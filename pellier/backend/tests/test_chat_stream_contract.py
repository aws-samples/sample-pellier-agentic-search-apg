"""The Ask Pellier stream: status from real events, steps with findings, stable failures.

Every test drives the real ``chat_stream`` with a scripted agent that fires
the same hooks and callback a Strands agent would. No model, no database, no
network: the conftest guard makes any AWS call fail loudly.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
import types
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import services.chat as chat_module
from services import tool_evidence
from services.chat import EnhancedChatService

TURN = "turn-" + "a" * 32

SEARCH_RESULT = json.dumps({
    "status": "success",
    "count": 2,
    "products": [
        {"productId": "65", "name": "Stoneware Mugs, Set of 2", "price": 38, "quantity": 9},
        {"productId": "22", "name": "Linen Napkins, Set of 4", "price": 44, "quantity": 4},
    ],
    "search_plan": {
        "hard_constraints": {"price_max_usd": 100, "in_stock_only": True, "categories": []},
        "exclusions": ["candle"],
    },
})
RANKING = {"available": True, "rail": "in-process", "rows": [{"product_id": "65", "after": 1}]}


class _Answer:
    def __init__(self, text: str) -> None:
        self.text = text

    def __str__(self) -> str:
        return self.text


class ScriptedAgent:
    """Replays tool calls and text through the hooks ``chat_stream`` attaches."""

    trace_attributes: Dict[str, Any] = {}

    def __init__(self, calls: List[Dict[str, Any]], answer: str, *, fail: Optional[Exception] = None) -> None:
        self.calls = calls
        self.answer = answer
        self.fail = fail
        self.hooks: List[Any] = []
        self.callback_handler = None

    def add_hook(self, hook: Any) -> None:
        self.hooks.append(hook)

    def _fire(self, event: Any, phase: str) -> None:
        # Strands dispatches by the callback's annotated event type.
        for hook in self.hooks:
            annotation = str(next(iter(inspect.signature(hook).parameters.values())).annotation)
            if phase in annotation:
                hook(event)

    def __call__(self, prompt: str) -> _Answer:
        if self.fail is not None:
            raise self.fail
        for index, call in enumerate(self.calls):
            tool_use = {"name": call["tool"], "toolUseId": f"use-{index}", "input": call.get("input", {})}
            self._fire(SimpleNamespace(tool_use=tool_use, result=None), "BeforeToolCall")
            for publish in call.get("publish", []):
                tool_evidence.publish(call["tool"], publish)
            result = {"status": "success", "content": [{"text": call["result"]}]}
            self._fire(SimpleNamespace(tool_use=tool_use, result=result), "AfterToolCall")
        for piece in self.answer.split(" "):
            self.callback_handler(data=piece + " ")
        return _Answer(self.answer)


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
    monkeypatch.setitem(
        sys.modules,
        "services.otel_trace_extractor",
        types.SimpleNamespace(extract_agent_execution_from_otel=lambda **kwargs: {}),
    )
    monkeypatch.setattr(chat_module, "classify_intent", lambda _m: "shopping")
    return svc


def _run(service: EnhancedChatService, agent: ScriptedAgent, monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> List[Dict[str, Any]]:
    seen: Dict[str, Any] = {}

    def build(intent: str, allow_handoff: bool, skill_mode: str = "fixed") -> ScriptedAgent:
        seen["skill_mode"] = skill_mode
        return agent

    monkeypatch.setattr(chat_module, "_build_dispatcher_specialist", build)

    async def collect() -> List[Dict[str, Any]]:
        return [
            event
            async for event in service.chat_stream(
                message=kwargs.pop("message", "a housewarming gift under $100, in stock, no candles"),
                turn_id=TURN,
                **kwargs,
            )
        ]

    events = asyncio.run(collect())
    events.append({"type": "_seen", **seen})
    return events


def _of(events: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    return [event for event in events if event.get("type") == kind]


def _anna_agent() -> ScriptedAgent:
    return ScriptedAgent(
        [
            {
                "tool": "search_products",
                "input": {"query": "housewarming gift"},
                "result": SEARCH_RESULT,
                "publish": [{"ranking": RANKING, "receipt_id": 412}],
            }
        ],
        "Start with the Stoneware Mugs, Set of 2 at $38. The Linen Napkins, Set of 4 at $44 pair well.",
    )


def test_status_and_steps_come_from_real_events_in_order(service, monkeypatch) -> None:
    events = _run(service, _anna_agent(), monkeypatch)
    kinds = [event["type"] for event in events]

    assert kinds.index("intent_signal") < kinds.index("status")
    statuses = [event["label"] for event in _of(events, "status")]
    assert statuses == ["Understanding your request", "Writing your answer"]

    steps = _of(events, "step")
    assert [(step["id"], step["status"]) for step in steps] == [
        ("route", "done"), ("step-1", "running"), ("step-1", "done"),
    ]
    route = steps[0]
    assert route["finding"] == "Sent to the Shopping agent"
    assert route["tags"] == ["Router", "Skills"]
    assert [skill["loaded"] for skill in route["builder"]["skills"]] == ["fixed"] * 4

    running, done = steps[1], steps[2]
    assert running["label"] == "Searching the catalog in Aurora" and running["tags"] == ["Aurora"]
    assert done["finding"] == "2 found under $100 and in stock, candles left out"
    assert done["builder"]["ranking"] == RANKING
    assert done["builder"]["requirements"] == {
        "applied": ["under $100", "in stock", "no candles"], "carried": [],
    }
    assert done["builder"]["receipt_id"] == 412
    assert done["builder"]["audit_id"] is None

    # The writing status precedes the first delta, and the delta stream still flows.
    first_delta = kinds.index("content_delta")
    assert kinds.index("status", kinds.index("status") + 1) < first_delta
    assert "Stoneware Mugs" in "".join(event["delta"] for event in _of(events, "content_delta"))

    complete = _of(events, "complete")[0]["response"]
    assert complete["orchestration"]["skill_mode"] == "fixed"
    assert [skill["name"] for skill in complete["orchestration"]["skills"]] == [
        "the-gift-table", "the-makers-shelf", "the-packing-list", "the-proof-counter",
    ]
    assert [product["id"] for product in complete["products"]] == ["65", "22"]
    assert events[-2]["type"] == "complete"


def test_shopper_steps_carry_no_tool_ids_or_raw_json_outside_builder(service, monkeypatch) -> None:
    events = _run(service, _anna_agent(), monkeypatch)
    for step in _of(events, "step"):
        shopper_view = {key: value for key, value in step.items() if key != "builder"}
        assert "search_products" not in json.dumps(shopper_view)
        assert "productId" not in json.dumps(shopper_view)


def test_the_request_field_switches_the_skill_mode_and_defaults_to_fixed(service, monkeypatch) -> None:
    default = _run(service, _anna_agent(), monkeypatch)
    on_demand = _run(service, _anna_agent(), monkeypatch, skill_mode="on_demand")
    assert default[-1]["skill_mode"] == "fixed"
    assert on_demand[-1]["skill_mode"] == "on_demand"
    route = _of(on_demand, "step")[0]
    assert route["builder"]["skill_mode"] == "on_demand"
    assert route["builder"]["skills"] == []
    assert route["tags"] == ["Router", "Skills (on demand)"]
    assert "opens the ones it needs" in route["builder"]["note"]


def test_a_follow_up_search_says_which_limits_it_kept_from_earlier(service, monkeypatch) -> None:
    """The finding and the Builder payload show carried limits plainly."""
    agent = ScriptedAgent(
        [
            {
                "tool": "search_products",
                "input": {"query": "small kitchen"},
                "result": SEARCH_RESULT,
                "publish": [
                    {"ranking": {**RANKING, "filters": {"kept": 64, "of": 100, "removed": {}}}},
                    {"requirements": {"carried": ["budget", "stock", "exclusions"]}},
                ],
            }
        ],
        "The Stoneware Mugs, Set of 2 suit a small kitchen.",
    )
    events = _run(
        service, agent, monkeypatch,
        message="Which of those would you pick for a small kitchen?",
        conversation_history=[
            {"role": "user", "content": "a housewarming gift under $100, in stock, no candles"},
            {"role": "assistant", "content": "Start with the mugs."},
        ],
    )
    done = [step for step in _of(events, "step") if step["builder"]["tool"] == "search_products"][-1]
    assert done["finding"] == (
        "2 found from 64 that fit. Kept your limits from earlier: under $100, in stock, no candles"
    )
    assert done["builder"]["requirements"]["carried"] == ["under $100", "in stock", "no candles"]


def test_on_demand_loads_are_one_step_no_tool_call_and_in_the_receipt(service, monkeypatch) -> None:
    agent = ScriptedAgent(
        [
            {"tool": "skills", "input": {"skill_name": "the-gift-table"}, "result": "# The Gift Table\n..."},
            {"tool": "skills", "input": {"skill_name": "the-proof-counter"}, "result": "# The Proof Counter"},
            {"tool": "search_products", "input": {"query": "gift"}, "result": SEARCH_RESULT},
        ],
        "Start with the Stoneware Mugs, Set of 2 at $38.",
    )
    events = _run(service, agent, monkeypatch, skill_mode="on_demand")

    steps = _of(events, "step")
    skill_steps = [step for step in steps if step["builder"]["tool"] == "skills"]
    assert skill_steps[0]["label"] == "Opening The Gift Table"
    assert skill_steps[1]["finding"] == "Loaded The Gift Table from skills/the-gift-table/SKILL.md"
    assert skill_steps[-1]["finding"] == "Loaded The Gift Table and The Proof Counter from skills/"
    assert skill_steps[-1]["tags"] == ["Skills"]
    assert len({step["id"] for step in steps}) == 3
    assert [event["tool"] for event in _of(events, "tool_call")] == ["search_products", "search_products"]

    receipt = _of(events, "complete")[0]["response"]["orchestration"]
    assert receipt["skill_mode"] == "on_demand"
    assert [(skill["name"], skill["loaded"]) for skill in receipt["skills"]] == [
        ("the-gift-table", "on demand"), ("the-proof-counter", "on demand"),
    ]


def test_a_skill_opened_twice_is_one_load_in_the_step_and_the_receipt(service, monkeypatch) -> None:
    agent = ScriptedAgent(
        [
            {"tool": "skills", "input": {"skill_name": "the-gift-table"}, "result": "# The Gift Table"},
            {"tool": "skills", "input": {"skill_name": "the-gift-table"}, "result": "# The Gift Table"},
        ],
        "A gift.",
    )
    events = _run(service, agent, monkeypatch, skill_mode="on_demand")
    last = [step for step in _of(events, "step") if step["builder"]["tool"] == "skills"][-1]
    assert last["finding"] == "Loaded The Gift Table from skills/the-gift-table/SKILL.md"
    receipt = _of(events, "complete")[0]["response"]["orchestration"]
    assert [skill["name"] for skill in receipt["skills"]] == ["the-gift-table"]


def test_a_turn_never_shows_more_than_four_steps(service, monkeypatch) -> None:
    calls = [
        {"tool": tool, "result": json.dumps({"status": "success", "count": 0, "products": []})}
        for tool in ("search_products", "browse_department", "compare_products", "check_stock", "get_return_policy")
    ]
    events = _run(service, ScriptedAgent(calls, "Nothing fits all of that."), monkeypatch)
    assert len({step["id"] for step in _of(events, "step")}) == 4


def test_a_failed_tool_is_a_failed_step_with_the_calm_template(service, monkeypatch) -> None:
    agent = ScriptedAgent(
        [{"tool": "check_stock", "input": {"product_query": "bowl"}, "result": json.dumps({"error": "psycopg.OperationalError"})}],
        "I could not check that just now.",
    )
    events = _run(service, agent, monkeypatch)
    done = [step for step in _of(events, "step") if step["builder"]["tool"] == "check_stock" and step["status"] != "running"]
    assert done[0]["status"] == "failed"
    assert done[0]["finding"] == "The stock check did not complete"


def test_failures_end_the_stream_with_a_stable_code_not_exception_text(service, monkeypatch) -> None:
    throttled = ScriptedAgent([], "", fail=RuntimeError("An error occurred (ThrottlingException) when calling the ConverseStream operation"))
    events = _run(service, throttled, monkeypatch)
    error = _of(events, "error")[0]
    assert error["code"] == "rate_limited"
    assert "ThrottlingException" not in json.dumps(error)
    assert error["retryable"] is True
    assert not _of(events, "complete")


def test_chat_collects_the_stable_code(service, monkeypatch) -> None:
    failing = ScriptedAgent([], "", fail=RuntimeError("ServiceUnavailableException: Bedrock is unavailable"))
    monkeypatch.setattr(chat_module, "_build_dispatcher_specialist", lambda *a, **k: failing)
    result = asyncio.run(service.chat(message="a linen shirt"))
    assert result["success"] is False
    assert result["error"] == "service_unavailable"


def test_the_greeting_is_answered_by_the_router_in_the_same_contract(service, monkeypatch) -> None:
    events = _run(service, _anna_agent(), monkeypatch, message="hello")
    assert [event["label"] for event in _of(events, "status")] == [
        "Understanding your request", "Writing your answer",
    ]
    route = _of(events, "step")[0]
    assert route["builder"]["agent"] == "Router"
    assert route["finding"] == "Answered by the Router, no agent needed"
    assert "Triage" not in json.dumps(events)
    assert events[-2]["type"] == "complete"
