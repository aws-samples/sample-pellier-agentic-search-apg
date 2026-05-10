"""Graph Pattern (Pattern II) contract tests.

Scope:
  * ``_extract_route`` normalizes noisy LLM output to a valid route key.
  * ``GraphAgentAdapter`` forwards the callback/hook/trace/session
    attributes that ``services/chat.py`` relies on to every specialist.
  * The adapter returns an object whose ``str()`` yields specialist
    prose, not a GraphResult dataclass repr.

We stub the Strands ``Agent`` + ``Graph`` layers so the tests can run
without AWS credentials. The adapter is intentionally thin — most of
the value is in the build/wire-up, which is exactly what these tests
exercise.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _stub_agent_result(text: str) -> SimpleNamespace:
    """Produce an object that mimics Strands' ``AgentResult`` just
    enough for ``str()`` to yield the expected text.
    """
    class _Stub:
        def __str__(self) -> str:
            return text
    return _Stub()


# ---------------------------------------------------------------------
# _extract_route
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("search", "search"),
        ("Pricing.", "pricing"),
        ("  Inventory  ", "inventory"),
        ("RECOMMENDATION", "recommendation"),
        ("support\nplease", "support"),
        ("gibberish", "search"),
        ("", "search"),
        ("   ", "search"),
    ],
)
def test_extract_route_normalization(raw, expected):
    """Router outputs are normalized to the five valid routes with a
    safe fallback to ``search``."""
    from agents.graph_pattern import _extract_route
    assert _extract_route(raw) == expected


# ---------------------------------------------------------------------
# GraphAgentAdapter — attribute forwarding
# ---------------------------------------------------------------------

def _patched_adapter():
    """Build an adapter with stubbed specialists + router + graph.

    We replace the factory functions and ``GraphBuilder`` so no AWS /
    Strands model code runs. The returned adapter has real
    ``_specialists`` dict and real attribute-forwarding behavior.
    """
    from agents import graph_pattern

    router = MagicMock(name="router")
    specialists = {
        "search": MagicMock(name="search"),
        "recommendation": MagicMock(name="recommendation"),
        "pricing": MagicMock(name="pricing"),
        "inventory": MagicMock(name="inventory"),
        "support": MagicMock(name="support"),
    }

    # Stub the five factory imports that __init__ pulls in. Keep them
    # scoped to this call so parallel tests stay isolated.
    with patch.object(graph_pattern, "_build_router_agent", return_value=router), \
         patch("agents.search_agent.build_search_agent", return_value=specialists["search"]), \
         patch("agents.recommendation_agent.build_recommendation_agent", return_value=specialists["recommendation"]), \
         patch("agents.pricing_agent.build_pricing_agent", return_value=specialists["pricing"]), \
         patch("agents.inventory_agent.build_inventory_agent", return_value=specialists["inventory"]), \
         patch("agents.customer_support_agent.build_support_agent", return_value=specialists["support"]):
        # Also stub GraphBuilder so its internal validation (which
        # rejects MagicMocks) doesn't kick in.
        fake_graph = MagicMock(name="graph")
        fake_builder = MagicMock(name="builder")
        fake_builder.build.return_value = fake_graph
        with patch("strands.multiagent.GraphBuilder", return_value=fake_builder):
            adapter = graph_pattern.GraphAgentAdapter()

    return adapter, router, specialists, fake_graph


def test_callback_handler_assignment_forwards_to_specialists():
    """Setting ``callback_handler`` on the adapter must propagate to
    every specialist agent — the chat pipeline assigns this once and
    expects tokens to stream from whichever specialist runs."""
    adapter, _router, specialists, _g = _patched_adapter()

    cb = lambda **k: None  # noqa: E731 — marker sentinel
    adapter.callback_handler = cb

    for spec in specialists.values():
        assert spec.callback_handler is cb


def test_trace_attributes_assignment_forwards_to_specialists():
    """trace_attributes propagation keeps OTEL spans consistent across
    the router + specialist execution surface."""
    adapter, _router, specialists, _g = _patched_adapter()

    attrs = {"session.id": "test-session", "pattern": "graph"}
    adapter.trace_attributes = attrs

    for spec in specialists.values():
        assert spec.trace_attributes == attrs


def test_session_manager_assignment_forwards_to_specialists():
    """session_manager assignment reaches every specialist so STM
    persists whichever specialist ran."""
    adapter, _router, specialists, _g = _patched_adapter()

    sm = MagicMock(name="session_manager")
    adapter.session_manager = sm

    for spec in specialists.values():
        assert spec.session_manager is sm


def test_add_hook_registers_on_every_specialist():
    """Tool lifecycle hooks need to fire regardless of which specialist
    the router picks, so ``add_hook`` is forwarded to all of them."""
    adapter, _router, specialists, _g = _patched_adapter()

    hook = lambda event: None  # noqa: E731
    adapter.add_hook(hook)

    for spec in specialists.values():
        spec.add_hook.assert_called_once_with(hook)


# ---------------------------------------------------------------------
# GraphAgentAdapter — invocation shape
# ---------------------------------------------------------------------

def test_call_returns_specialist_agent_result():
    """After the graph runs, ``adapter(message)`` returns the winning
    specialist's AgentResult — the object whose ``str()`` is the
    specialist's prose, matching the Agent single-agent contract the
    chat pipeline depends on."""
    adapter, _router, specialists, fake_graph = _patched_adapter()

    # Build a fake GraphResult where the 'pricing' specialist ran.
    pricing_result = _stub_agent_result("Our top deals right now: …")
    pricing_node_result = MagicMock()
    pricing_node_result.get_agent_results.return_value = [pricing_result]
    router_node_result = MagicMock()
    router_node_result.get_agent_results.return_value = [_stub_agent_result("pricing")]

    pricing_node = SimpleNamespace(node_id="pricing")
    router_node = SimpleNamespace(node_id="router")

    fake_graph_result = MagicMock()
    fake_graph_result.execution_order = [router_node, pricing_node]
    fake_graph_result.results = {
        "router": router_node_result,
        "pricing": pricing_node_result,
    }
    fake_graph.return_value = fake_graph_result

    result = adapter("Any deals on headphones?")

    assert str(result) == "Our top deals right now: …"
    assert adapter.last_route == "pricing"


def test_call_falls_back_to_router_when_no_specialist_ran():
    """If conditional edges somehow all miss (shouldn't happen with
    the fallback in ``_extract_route``, but defensive), the adapter
    returns the router's result rather than raising — the pipeline's
    own empty-response guard picks up the rest."""
    adapter, _router, _specialists, fake_graph = _patched_adapter()

    router_result = _stub_agent_result("search")
    router_node_result = MagicMock()
    router_node_result.get_agent_results.return_value = [router_result]

    router_node = SimpleNamespace(node_id="router")
    fake_graph_result = MagicMock()
    fake_graph_result.execution_order = [router_node]
    fake_graph_result.results = {"router": router_node_result}
    fake_graph.return_value = fake_graph_result

    result = adapter("anything")
    assert str(result) == "search"
    assert adapter.last_route == "router"
