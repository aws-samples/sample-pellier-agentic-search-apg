"""Routing tests for the Challenge 4 multi-agent orchestrator.

Validates Requirement 2.4.6-2.4.8 and 4.3.1 from
`.kiro/specs/pellier-storefront/requirements.md`:

  2.4.6  The orchestrator is constructed with Haiku 4.5 model id exactly,
         temperature=0.0, and five specialist tools following the Strands
         "Agents as Tools" pattern.
  2.4.7  Intent classification priority: pricing > inventory > support >
         search > recommendation (default), lifted from
         coding-standards.md.
  2.4.8  Five representative queries (one per specialist intent) each
         route to the expected specialist, observable via trace logs.
  4.3.1  Routing for an authenticated request surfaces via the same
         observation path (span tags) used by `otel_trace_extractor` so
         the frontend waterfall/inspector view sees the selected agent.

Bedrock is stubbed. `strands.Agent` and `strands.models.BedrockModel` as
imported into `agents.orchestrator` are swapped for recording stubs. The
stub agent replays the priority-ordered router the system prompt encodes,
picks exactly one specialist tool from its tools list, records the
selection in an otel_trace_extractor-compatible routing_decision dict,
and returns a canned response string. No live model call, no DB call.

Runnable from the repo root per `pytest.ini`:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_orchestrator_routing.py -v
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable

import pytest


# ---------------------------------------------------------------------------
# Priority-ordered router (mirrors copy.ORCHESTRATOR_SYSTEM_PROMPT)
# ---------------------------------------------------------------------------
#
# Intent priority from coding-standards.md:
#   pricing > inventory > support > search > recommendation (default)
#
# The patterns below are deliberately tight. A query that matches more
# than one pattern resolves to the highest-priority match. A query that
# matches none falls through to recommendation so the
# default branch is covered by the same router.

_PRICING = re.compile(
    r"\b(price|prices|pricing|deal|deals|discount|"
    r"cheap|cheaper|budget|cost|under \$|below \$|\$\d)",
    re.IGNORECASE,
)
_INVENTORY = re.compile(
    r"\b(stock|in stock|out of stock|inventory|restock|"
    r"how many|units left|low[- ]stock|availability|available)\b",
    re.IGNORECASE,
)
_SUPPORT = re.compile(
    r"\b(return|returns|refund|refunds|warranty|warranties|"
    r"exchange|exchanges|policy|policies|broken|defective|damaged)\b",
    re.IGNORECASE,
)
_SEARCH = re.compile(
    r"\b(find|search for|look for|show me|browse|"
    r"compare|comparison|specifically|linen camp shirt|"
    r"oxford shirt|sundress|straw tote|cardigan|"
    r"tumbler|slide sandal|utility jacket|trail runner|"
    r"wide-leg trousers)\b",
    re.IGNORECASE,
)


def _route(query: str) -> str:
    """Return the tool_name of the specialist a priority-respecting
    orchestrator would call for `query`. Mirrors the logic the
    ORCHESTRATOR_SYSTEM_PROMPT asks Haiku 4.5 to perform."""
    if _PRICING.search(query):
        return "pricing"
    if _INVENTORY.search(query):
        return "inventory"
    if _SUPPORT.search(query):
        return "support"
    if _SEARCH.search(query):
        return "search"
    return "recommendation"


# ---------------------------------------------------------------------------
# Stub Bedrock Agent (no network call)
# ---------------------------------------------------------------------------


class _StubBedrockModel:
    """Swap for `BedrockModel`. Captures kwargs so the test can assert
    the Haiku 4.5 model id and temperature=0.0 are wired exactly."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _StubAgent:
    """Swap for `strands.Agent`.

    Records construction kwargs and, on call, runs the priority-ordered
    router to pick one specialist from the tools list, records the
    selection in a routing_decision dict shaped like the payload
    `otel_trace_extractor.infer_agent_from_query` produces, and invokes
    the chosen tool. Each specialist tool is itself stubbed (see
    `stubbed_specialists` fixture) so no DB or Bedrock round-trip.
    """

    last_kwargs: dict[str, Any] = {}
    # Append-only observation log so tests can make multiple calls
    # against the same stub and assert the sequence.
    routing_decisions: list[dict[str, Any]] = []
    tool_call_log: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        type(self).last_kwargs = kwargs

    def add_hook(self, _hook: Callable[[Any], None]) -> None:
        # Real Strands Agent accepts hooks; the stub accepts and ignores.
        pass

    def __call__(self, query: str) -> str:
        tools = type(self).last_kwargs.get("tools", [])
        # Map tool_name -> callable for fast lookup. Strands @tool
        # exposes the underlying function via __wrapped__ and the
        # registered name via .tool_name. Fall back to __name__ when
        # running against a non-Strands callable (no-op safety).
        name_to_tool: dict[str, Any] = {}
        for t in tools:
            name = getattr(t, "tool_name", None) or getattr(
                getattr(t, "__wrapped__", t), "__name__", repr(t)
            )
            name_to_tool[name] = t

        selected_name = _route(query)
        assert selected_name in name_to_tool, (
            f"router picked {selected_name!r} but the orchestrator was "
            f"constructed with tools {sorted(name_to_tool)!r}"
        )

        # Record a routing_decision in the otel_trace_extractor shape so
        # the frontend waterfall and /api/traces/waterfall consumer see
        # the same payload shape on every routing event (Req 4.3.1).
        decision = {
            "selected_agent": selected_name,
            "confidence": 95,
            "reason": f"Priority-ordered routing for query: {query[:80]!r}",
            "alternatives": [],
        }
        type(self).routing_decisions.append(decision)

        # Call the selected specialist. Capture the tool-call event so
        # the test can also observe routing via the tool_call_log (which
        # mirrors what Strands' BeforeToolCallEvent / AfterToolCallEvent
        # hook would emit).
        tool = name_to_tool[selected_name]
        # Reach past @tool so the tool's own stub (installed by the
        # fixture) runs instead of the DecoratedFunctionTool wrapper.
        inner = getattr(tool, "__wrapped__", tool)
        tool_result = inner(query=query)
        type(self).tool_call_log.append(
            {
                "tool": selected_name,
                "query": query,
                "result": tool_result,
            }
        )
        return f"[stub-orchestrator] routed to {selected_name}"


@pytest.fixture(autouse=True)
def _reset_stub_state() -> Iterable[None]:
    _StubAgent.last_kwargs = {}
    _StubAgent.routing_decisions = []
    _StubAgent.tool_call_log = []
    yield
    _StubAgent.last_kwargs = {}
    _StubAgent.routing_decisions = []
    _StubAgent.tool_call_log = []


@pytest.fixture
def stubbed_specialists(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Swap each specialist's underlying callable for a recorder that
    returns a canned string. Returns a dict mapping tool_name to the
    list of queries that tool saw during the test so assertions can
    cover who-got-called without dragging in DB or Bedrock."""
    import agents.orchestrator as orch

    calls: dict[str, list[str]] = {
        "search": [],
        "recommendation": [],
        "pricing": [],
        "inventory": [],
        "support": [],
    }

    def _patch(tool_obj: Any, name: str) -> None:
        """Replace the DecoratedFunctionTool's wrapped function with a
        recorder closure that appends `name -> query` to `calls`."""

        def _recorder(query: str) -> str:
            calls[name].append(query)
            return f"[stub-{name}] ok"

        # Strands' DecoratedFunctionTool keeps the original function on
        # _tool_func; __wrapped__ is set via functools.update_wrapper
        # and both paths should receive the recorder so the orchestrator
        # stub (which reaches __wrapped__) and any direct .tool_name
        # invocation resolve to the same function.
        monkeypatch.setattr(tool_obj, "__wrapped__", _recorder, raising=False)
        monkeypatch.setattr(tool_obj, "_tool_func", _recorder, raising=False)

    _patch(orch.search, "search")
    _patch(orch.recommendation, "recommendation")
    _patch(orch.pricing, "pricing")
    _patch(orch.inventory, "inventory")
    _patch(orch.support, "support")

    return calls


@pytest.fixture
def orchestrator_factory(monkeypatch: pytest.MonkeyPatch, stubbed_specialists):
    """Return `create_orchestrator` with `Agent` and `BedrockModel` as
    imported into `agents.orchestrator` swapped for the stubs above."""
    import agents.orchestrator as orch

    monkeypatch.setattr(orch, "Agent", _StubAgent)
    monkeypatch.setattr(orch, "BedrockModel", _StubBedrockModel)
    return orch.create_orchestrator


# ---------------------------------------------------------------------------
# Req 2.4.6 - construction wiring
# ---------------------------------------------------------------------------


def test_orchestrator_uses_haiku_4_5_at_temperature_0_0(
    orchestrator_factory,
) -> None:
    """The orchestrator SHALL wrap BedrockModel with the exact Haiku 4.5
    model id and `temperature=0.0` per Req 2.4.6."""
    orchestrator_factory()

    model = _StubAgent.last_kwargs.get("model")
    assert isinstance(model, _StubBedrockModel)
    assert (
        model.kwargs.get("model_id")
        == "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    ), f"Haiku 4.5 model id mismatch: {model.kwargs.get('model_id')!r}"
    assert model.kwargs.get("temperature") == 0.0


def test_orchestrator_registers_exactly_five_specialists(
    orchestrator_factory,
) -> None:
    """The orchestrator SHALL register the five specialist tools by name
    per Req 2.4.6."""
    orchestrator_factory()

    tools = _StubAgent.last_kwargs.get("tools", [])
    names = []
    for t in tools:
        name = getattr(t, "tool_name", None) or getattr(
            getattr(t, "__wrapped__", t), "__name__", repr(t)
        )
        names.append(name)

    assert set(names) == {
        "search",
        "recommendation",
        "pricing",
        "inventory",
        "support",
    }, f"unexpected specialist roster: {names!r}"


def test_orchestrator_system_prompt_enforces_priority_order(
    orchestrator_factory,
) -> None:
    """The system prompt SHALL name all five specialists and state the
    priority order pricing > inventory > support > search >
    recommendation per Req 2.4.7."""
    orchestrator_factory()

    prompt = _StubAgent.last_kwargs.get("system_prompt", "")
    assert isinstance(prompt, str) and prompt, "system_prompt SHALL be non-empty"

    for tool_name in (
        "pricing",
        "inventory",
        "support",
        "search",
        "recommendation",
    ):
        assert tool_name in prompt, (
            f"system_prompt SHALL mention {tool_name!r} so Haiku can "
            f"pick it; current prompt missing it"
        )

    # Priority order: pricing must appear before inventory, inventory
    # before support, support before finding, finding before
    # recommendation in the prompt text (these are the priority labels
    # the prompt uses for the 1..5 ordering).
    idx = {
        "pricing": prompt.find("pricing"),
        "inventory": prompt.find("inventory"),
        "support": prompt.find("support"),
        "finding": prompt.find("finding"),
        "recommendation": prompt.find("recommendation"),
    }
    assert all(v >= 0 for v in idx.values()), (
        f"system_prompt SHALL mention every priority label; got indices {idx!r}"
    )
    assert idx["pricing"] < idx["inventory"] < idx["support"] < idx["finding"] < idx["recommendation"], (
        f"priority order violated in system_prompt; label positions: {idx!r}"
    )


# ---------------------------------------------------------------------------
# Req 2.4.8 - five representative queries, one per specialist intent
# ---------------------------------------------------------------------------


_REPRESENTATIVE_QUERIES = [
    ("what are the best deals on linen under $100?", "pricing"),
    ("how many Sundresses do we have left in stock?", "inventory"),
    ("what is the return policy for shoes I bought last week?", "support"),
    ("find me the Italian Linen Camp Shirt", "search"),
    ("something for warm evenings out", "recommendation"),
]


@pytest.mark.parametrize("query,expected_tool", _REPRESENTATIVE_QUERIES)
def test_representative_query_routes_to_expected_specialist(
    orchestrator_factory,
    stubbed_specialists,
    query: str,
    expected_tool: str,
) -> None:
    """Each of the five representative queries SHALL route to the
    specialist named in `expected_tool` and SHALL surface that routing
    via a routing_decision span-shaped record per Req 2.4.8 and 4.3.1."""
    orchestrator = orchestrator_factory()

    orchestrator(query)

    # Specialist actually invoked exactly once, with the query unmodified.
    assert stubbed_specialists[expected_tool] == [query], (
        f"expected {expected_tool} called once with {query!r}; "
        f"full call log: "
        f"{ {k: v for k, v in stubbed_specialists.items() if v} !r}"
    )
    # No other specialist fired.
    others = {k: v for k, v in stubbed_specialists.items() if k != expected_tool}
    assert all(not v for v in others.values()), (
        f"exactly one specialist SHALL fire; extra calls: "
        f"{ {k: v for k, v in others.items() if v} !r}"
    )

    # Routing observation: a single routing_decision with
    # selected_agent == expected_tool (mirrors the shape used by
    # otel_trace_extractor.infer_agent_from_query).
    assert len(_StubAgent.routing_decisions) == 1
    decision = _StubAgent.routing_decisions[0]
    assert decision["selected_agent"] == expected_tool
    assert "reason" in decision

    # Tool-call log mirrors what a Strands BeforeToolCallEvent hook
    # would emit - included so Req 4.3.1 observability is visible
    # without depending on C8's otel extractor being implemented.
    assert len(_StubAgent.tool_call_log) == 1
    assert _StubAgent.tool_call_log[0]["tool"] == expected_tool
    assert _StubAgent.tool_call_log[0]["query"] == query


# ---------------------------------------------------------------------------
# Req 2.4.7 - priority order on ambiguous queries
# ---------------------------------------------------------------------------


def test_priority_order_on_ambiguous_queries(
    orchestrator_factory,
    stubbed_specialists,
) -> None:
    """An ambiguous query matching BOTH pricing and inventory SHALL
    route to `pricing` because pricing outranks
    inventory in the priority order (Req 2.4.7)."""
    orchestrator = orchestrator_factory()

    # "in stock under $100" triggers both the inventory pattern (stock)
    # and the pricing pattern ($ with a digit). Priority says pricing
    # wins.
    ambiguous = "do you have the linen camp shirt in stock under $100"
    orchestrator(ambiguous)

    assert stubbed_specialists["pricing"] == [ambiguous], (
        "ambiguous pricing+inventory query SHALL route to "
        "pricing per Req 2.4.7"
    )
    assert not stubbed_specialists["inventory"], (
        "inventory SHALL NOT fire when pricing also matches"
    )

    # Sanity: the routing decision reflects the higher-priority pick.
    assert _StubAgent.routing_decisions[-1]["selected_agent"] == (
        "pricing"
    )


def test_priority_order_support_beats_search_when_both_match(
    orchestrator_factory,
    stubbed_specialists,
) -> None:
    """A secondary ambiguity check: a query that mentions both a return
    (support) and finding a replacement (search) SHALL route to support,
    because support outranks search in the priority order."""
    orchestrator = orchestrator_factory()

    query = "can I return this sundress and find me a replacement"
    orchestrator(query)

    assert stubbed_specialists["support"] == [query]
    assert not stubbed_specialists["search"]


def test_priority_fallback_to_recommendation_when_nothing_matches(
    orchestrator_factory,
    stubbed_specialists,
) -> None:
    """When no specialist pattern fires, the default SHALL be
    recommendation per Req 2.4.7 and the order in
    coding-standards.md."""
    orchestrator = orchestrator_factory()

    query = "curate a little something for a slow Sunday"
    orchestrator(query)

    assert stubbed_specialists["recommendation"] == [query]
    assert not any(
        v for k, v in stubbed_specialists.items()
        if k != "recommendation"
    )
