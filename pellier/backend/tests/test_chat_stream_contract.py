"""The Ask Pellier stream: status from real events, steps with findings, stable failures.

Every test drives the real ``chat_stream`` with a scripted agent that fires
the same hooks and callback a Strands agent would. No model, no database, no
network: the conftest guard makes any AWS call fail loudly.
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import json
import sys
import threading
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
# What the storefront grid draws from: the search's own order, limits and counts.
RESULTS = {
    "available": True,
    "rail": "in-process",
    "product_ids": ["65", "22", "31"],
    "limits": [{"kind": "budget", "label": "Under $100", "origin": "stated"}],
    "filters": {"kept": 64, "of": 100, "removed": {"budget": 31}, "excluded": []},
}


class _Answer:
    def __init__(self, text: str, stop_reason: Optional[str] = None) -> None:
        self.text = text
        if stop_reason is not None:
            self.stop_reason = stop_reason

    def __str__(self) -> str:
        return self.text


class ScriptedAgent:
    """Replays tool calls and text through the hooks ``chat_stream`` attaches."""

    trace_attributes: Dict[str, Any] = {}

    def __init__(
        self,
        calls: List[Dict[str, Any]],
        answer: str,
        *,
        fail: Optional[Exception] = None,
        stop_reason: Optional[str] = None,
    ) -> None:
        self.calls = calls
        self.answer = answer
        self.fail = fail
        self.stop_reason = stop_reason
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
        return _Answer(self.answer, self.stop_reason)


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
                "publish": [{"ranking": RANKING, "receipt_id": 412, "results": RESULTS}],
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
    # The page grid's result rides the done step beside builder, never in it.
    assert done["results"] == RESULTS and "results" not in done["builder"]
    assert "results" not in running

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


class ParallelAgent(ScriptedAgent):
    """Runs its calls the way Strands' concurrent executor does.

    Each tool use gets its own context, as each runs in its own asyncio task:
    the before-tool hook runs in it, the tool body runs in a thread that
    copies it (``asyncio.to_thread``), and the after-tool hook runs in it
    again. Both bodies publish before either hook takes, and the second call
    finishes first.
    """

    def __call__(self, prompt: str) -> _Answer:
        uses = [
            (
                {"name": call["tool"], "toolUseId": f"use-{index}", "input": call.get("input", {})},
                call,
            )
            for index, call in enumerate(self.calls)
        ]
        contexts = [contextvars.copy_context() for _ in uses]
        for context, (tool_use, _) in zip(contexts, uses):
            before = SimpleNamespace(tool_use=tool_use, result=None)
            context.run(self._fire, before, "BeforeToolCall")
        published = threading.Barrier(len(uses))

        def body(call: Dict[str, Any]) -> None:
            for publish in call.get("publish", []):
                tool_evidence.publish(call["tool"], publish)
            published.wait(timeout=5)

        threads = [
            threading.Thread(target=context.copy().run, args=(body, call))
            for context, (_, call) in zip(contexts, uses)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        for context, (tool_use, call) in reversed(list(zip(contexts, uses))):
            result = {"status": "success", "content": [{"text": call["result"]}]}
            after = SimpleNamespace(tool_use=tool_use, result=result)
            context.run(self._fire, after, "AfterToolCall")
        for piece in self.answer.split(" "):
            self.callback_handler(data=piece + " ")
        return _Answer(self.answer, self.stop_reason)


def test_two_searches_at_once_are_two_steps_each_with_its_own_evidence(
    service, monkeypatch
) -> None:
    """Evidence is keyed by tool use: neither search shows the other's ranking or result."""
    ranking_b = {**RANKING, "rows": [{"product_id": "90", "after": 1}]}
    results_b = {**RESULTS, "product_ids": ["90", "28"], "count": 2}
    agent = ParallelAgent(
        [
            {"tool": "search_products", "input": {"query": "housewarming gift"},
             "result": SEARCH_RESULT,
             "publish": [{"ranking": RANKING, "receipt_id": 412, "results": RESULTS}]},
            {"tool": "search_products", "input": {"query": "morning run"},
             "result": SEARCH_RESULT,
             "publish": [{"ranking": ranking_b, "receipt_id": 413, "results": results_b}]},
        ],
        "Start with the Stoneware Mugs, Set of 2 at $38.",
    )
    events = _run(service, agent, monkeypatch)
    steps = [step for step in _of(events, "step") if step["id"] != "route"]
    assert [(step["id"], step["status"]) for step in steps] == [
        ("step-1", "running"), ("step-2", "running"), ("step-2", "done"), ("step-1", "done"),
    ]
    done = {step["id"]: step for step in steps if step["status"] == "done"}
    assert done["step-1"]["builder"]["ranking"] == RANKING
    assert done["step-1"]["builder"]["receipt_id"] == 412
    assert done["step-1"]["results"] == RESULTS
    assert done["step-2"]["builder"]["ranking"] == ranking_b
    assert done["step-2"]["builder"]["receipt_id"] == 413
    assert done["step-2"]["results"] == results_b


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


def test_six_tool_uses_are_six_steps_each_with_its_own_evidence(service, monkeypatch) -> None:
    """The live two-request turn: four searches and two browses, run at once.

    No step budget folds the later calls together: each tool use keeps its own
    step, ranking, receipt and result, so the Builder view shows all six.
    """
    browse = json.dumps({"status": "success", "count": 1, "department": "Home", "products": []})
    calls = [
        {
            "tool": tool,
            "input": {"query": f"request {index}"},
            "result": SEARCH_RESULT if tool == "search_products" else browse,
            "publish": [{
                "ranking": {**RANKING, "rows": [{"product_id": str(index), "after": 1}]},
                "receipt_id": 600 + index,
                "results": {**RESULTS, "product_ids": [str(index)], "count": 1},
            }],
        }
        for index, tool in enumerate(("search_products",) * 4 + ("browse_department",) * 2)
    ]
    events = _run(service, ParallelAgent(calls, "Two answers, one turn."), monkeypatch)
    done = {
        step["id"]: step for step in _of(events, "step")
        if step["id"] != "route" and step["status"] == "done"
    }
    assert sorted(done) == [f"step-{index}" for index in range(1, 7)]
    payloads = [
        (step["builder"]["receipt_id"], step["builder"]["ranking"]["rows"][0]["product_id"],
         step["results"]["product_ids"])
        for step in (done[f"step-{index + 1}"] for index in range(6))
    ]
    assert payloads == [(600 + index, str(index), [str(index)]) for index in range(6)]


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


def test_the_receipt_and_the_router_step_record_how_the_turn_ended(service, monkeypatch, caplog) -> None:
    """Thinking and the answer share one budget; a turn that stops at max_tokens says so."""
    agent = ScriptedAgent(_anna_agent().calls, "Start with the Stoneware Mugs, Set of 2 at", stop_reason="max_tokens")
    with caplog.at_level("WARNING", logger="services.chat"):
        events = _run(service, agent, monkeypatch)
    routes = [step for step in _of(events, "step") if step["id"] == "route"]
    assert routes[0]["builder"]["stop_reason"] is None
    assert routes[-1]["builder"]["stop_reason"] == "max_tokens"
    assert routes[-1]["finding"] == routes[0]["finding"]
    assert _of(events, "complete")[0]["response"]["orchestration"]["stop_reason"] == "max_tokens"
    assert "answer cut short at max_tokens" in caplog.text

    caplog.clear()
    with caplog.at_level("WARNING", logger="services.chat"):
        events = _run(service, ScriptedAgent(_anna_agent().calls, "Start with the mugs.", stop_reason="end_turn"), monkeypatch)
    assert _of(events, "complete")[0]["response"]["orchestration"]["stop_reason"] == "end_turn"
    assert [step for step in _of(events, "step") if step["id"] == "route"][-1]["builder"]["stop_reason"] == "end_turn"
    assert "cut short" not in caplog.text


@pytest.mark.parametrize("fail", [None, RuntimeError("ServiceUnavailableException: Bedrock is unavailable")])
def test_the_requirements_scope_is_released_with_the_evidence_channel(service, monkeypatch, fail) -> None:
    from services import active_requirements

    seen: Dict[str, Any] = {}

    class _Agent(ScriptedAgent):
        def __call__(self, prompt: str) -> _Answer:
            scope = active_requirements.current_turn()
            seen["bound"] = (scope.session_id, scope.principal) if scope else None
            seen["channel"] = tool_evidence.is_open()
            return super().__call__(prompt)

    agent = _Agent(_anna_agent().calls, "Start with the mugs.", fail=fail)
    monkeypatch.setattr(chat_module, "_build_dispatcher_specialist", lambda *a, **k: agent)

    async def collect() -> Dict[str, Any]:
        events = [event async for event in service.chat_stream(
            message="a housewarming gift under $100", turn_id=TURN, session_id="sess-anna",
        )]
        return {"events": events, "after": active_requirements.current_turn(), "open": tool_evidence.is_open()}

    outcome = asyncio.run(collect())
    kinds = [event["type"] for event in outcome["events"]]
    assert ("complete" in kinds) is (fail is None) and ("error" in kinds) is (fail is not None)
    if fail is None:
        assert seen["bound"] == ("sess-anna", None) and seen["channel"] is True
    assert outcome["after"] is None, "bind_turn's token is reset in the same finally as the channel"
    assert outcome["open"] is False


def test_the_tools_read_the_shoppers_latest_message_only(service, monkeypatch) -> None:
    """Earlier limits are carried server-side, so the reading never re-states them."""
    from services.turn_identity import shopper_words_var

    seen: Dict[str, Any] = {}

    class _Agent(ScriptedAgent):
        def __call__(self, prompt: str) -> _Answer:
            seen["words"] = shopper_words_var.get()
            return super().__call__(prompt)

    history = [
        {"role": "user", "content": "a housewarming gift under $100, in stock, no candles"},
        {"role": "assistant", "content": "Start with the Stoneware Mugs, Set of 2 at $38."},
    ]
    _run(
        service, _Agent(_anna_agent().calls, "The mugs."), monkeypatch,
        message="which of those would you pick for a small kitchen?",
        conversation_history=history, session_id="sess-anna",
    )
    assert seen["words"] == "which of those would you pick for a small kitchen?"


# Anna, as ``scripts/migrations/003_persona_seed.sql`` seeds her.
ANNA_FACTS = [
    {"summary_text": "Past orders skew gift-shaped across varied price bands.", "ts_offset_days": -50},
    {"summary_text": "Recent searches mention milestone occasions and ready-to-give packaging.",
     "ts_offset_days": -20},
    {"summary_text": "Responds well to pairings under a clear budget.", "ts_offset_days": -9},
]
ANNA_ORDERS = [
    {"productId": "7", "name": "Jute Placemats, Set of 4", "brand": "Pellier", "color": "Natural",
     "price": 40, "category": "Kitchen and table", "imgUrl": "/p.webp", "rating": 4.8, "reviews": 12,
     "price_paid": 68.0, "placed_at": "2026-08-01"},
    {"productId": "27", "name": "Ceramic Bud Vase", "brand": "NestWell", "color": "Oat",
     "price": 24, "category": "Home", "imgUrl": "/p.webp", "rating": 4.7, "reviews": 9,
     "price_paid": 22.0, "placed_at": "2026-07-14"},
]


class _SeededAnna:
    """The three reads the preamble makes, answered from the seed."""

    async def fetch_all(self, sql: str, *params: Any) -> List[Dict[str, Any]]:
        if "customer_episodic_seed" in sql:
            return list(ANNA_FACTS)
        if "pellier.orders" in sql:
            return list(ANNA_ORDERS)
        return []

    async def fetch_one(self, sql: str, *params: Any) -> Optional[Dict[str, Any]]:
        return {"name": "Anna"} if "pellier.customers" in sql else None


def test_the_persona_preamble_and_every_agent_prompt_carry_no_em_dash_or_middle_dot(
    service, monkeypatch,
) -> None:
    """The preamble is prepended to the message on every persona turn and appended to
    each agent's system prompt, so it is a model prompt and follows the voice."""
    from agents import stock_agent as stock_module
    from agents.shopping_agent import build_shopping_agent
    from agents.stock_agent import build_stock_agent
    from agents.support_agent import build_support_agent
    from services.persona_context import get_persona_preamble, persona_preamble_var

    seen: Dict[str, Any] = {}

    class _Agent(ScriptedAgent):
        def __call__(self, prompt: str) -> _Answer:
            seen["preamble"] = get_persona_preamble()
            seen["prompt"] = prompt
            return super().__call__(prompt)

    service.db_service = _SeededAnna()
    _run(
        service, _Agent(_anna_agent().calls, "The placemats."), monkeypatch,
        user={"customer_id": "CUST-ANNA"}, session_id="sess-anna",
    )
    preamble = seen["preamble"]
    assert preamble.startswith("PERSONA CONTEXT: Anna (CUST-ANNA)\n")
    assert "  - Responds well to pairings under a clear budget." in preamble
    assert "  - Jute Placemats, Set of 4 (paid $68, Kitchen and table)" in preamble
    assert seen["prompt"].startswith(preamble)

    monkeypatch.setattr(stock_module, "_STOCK_AGENT_STUBBED", False)
    token = persona_preamble_var.set(preamble)
    try:
        prompts = {
            "shopping": build_shopping_agent().system_prompt,
            "stock": build_stock_agent().system_prompt,
            "support": build_support_agent().system_prompt,
        }
    finally:
        persona_preamble_var.reset(token)
    for name, prompt in prompts.items():
        assert preamble.strip() in prompt, name
        for mark in ("—", "·"):
            assert mark not in preamble, mark
            assert mark not in prompt, (name, mark)
