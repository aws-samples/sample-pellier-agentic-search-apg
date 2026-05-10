"""Factory-shape contract test.

The three-pattern model (Storefront dispatcher, Atelier Agents-as-Tools,
Atelier Graph) depends on every specialist exposing a uniform factory
function alongside its ``@tool``-decorated version. This test enforces
that contract so future changes to ``agents/`` get flagged before they
ship.

Scope, per specialist (search, recommendation, pricing, inventory, support):
  1. ``build_<name>_agent()`` exists and returns a real Strands Agent
  2. The Agent has the correct tools bound
  3. Anonymous build leaves the ``<persona-preamble>`` wrapper OFF
  4. Setting the persona_preamble_var ContextVar injects the wrapper
  5. The ``@tool``-decorated wrapper still exposes Strands tool metadata
     so the Pattern I orchestrator keeps discovering it

Also enforces:
  - ``EXA_API_KEY`` is gone from ``config.settings`` (removed in
    the three-pattern refactor alongside the Exa MCP integration)
  - ``customer_support_agent`` has no residual Exa references
  - ``create_orchestrator()`` still exposes all five @tool specialists
    (Pattern I byte-compatibility gate)
"""
from __future__ import annotations

import inspect

import pytest

from strands import Agent

from agents.customer_support_agent import build_support_agent, support
from agents.inventory_agent import build_inventory_agent, inventory
from agents.pricing_agent import build_pricing_agent, pricing
from agents.recommendation_agent import build_recommendation_agent, recommendation
from agents.search_agent import build_search_agent, search
from services.persona_context import persona_preamble_var, set_persona_preamble


# Expected tool names bound to each specialist's Agent. If you rename a
# tool in ``services/agent_tools.py`` you have to update this list.
SPECIALIST_SPECS = [
    ("search", build_search_agent, {"find_pieces", "explore_collection", "side_by_side"}),
    ("recommendation", build_recommendation_agent,
     {"find_pieces", "whats_trending", "side_by_side", "explore_collection"}),
    ("pricing", build_pricing_agent,
     {"price_intelligence", "explore_collection", "find_pieces"}),
    ("inventory", build_inventory_agent,
     {"floor_check", "restock_shelf", "running_low"}),
    ("support", build_support_agent,
     {"returns_and_care", "find_pieces"}),
]

SPECIALIST_WRAPPERS = [
    ("search", search),
    ("recommendation", recommendation),
    ("pricing", pricing),
    ("inventory", inventory),
    ("support", support),
]

PERSONA_WRAPPER = "<persona-preamble source=\"aurora-ltm\">"


def _tool_names(agent: Agent) -> set[str]:
    """Extract the set of bound tool names from an Agent's tool registry."""
    registry = getattr(agent.tool_registry, "registry", None) or {}
    return set(registry.keys()) if isinstance(registry, dict) else set()


# ---------------------------------------------------------------------------
# Factory contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,factory,expected_tools", SPECIALIST_SPECS, ids=[s[0] for s in SPECIALIST_SPECS])
def test_factory_returns_real_agent(name: str, factory, expected_tools: set[str]) -> None:
    agent = factory()
    assert isinstance(agent, Agent), f"{name}: factory must return a Strands Agent"
    tools = _tool_names(agent)
    assert expected_tools.issubset(tools), (
        f"{name}: missing tools {expected_tools - tools}; got {sorted(tools)}"
    )


@pytest.mark.parametrize("name,factory,_tools", SPECIALIST_SPECS, ids=[s[0] for s in SPECIALIST_SPECS])
def test_factory_anonymous_has_no_persona_wrapper(name: str, factory, _tools: set[str]) -> None:
    """Anonymous build (empty ContextVar) must not include the persona wrapper."""
    # Ensure the ContextVar is empty before we check — if a prior test
    # leaked a value, this reset is idempotent.
    assert persona_preamble_var.get() == "", (
        "persona ContextVar leaked into a later test — earlier test forgot to reset"
    )
    prompt = factory().system_prompt or ""
    assert PERSONA_WRAPPER not in prompt, (
        f"{name}: anonymous prompt unexpectedly contains the persona wrapper"
    )


@pytest.mark.parametrize("name,factory,_tools", SPECIALIST_SPECS, ids=[s[0] for s in SPECIALIST_SPECS])
def test_factory_honors_persona_contextvar(name: str, factory, _tools: set[str]) -> None:
    """Setting the persona preamble ContextVar injects the wrapper into the system prompt."""
    token = set_persona_preamble(
        "PERSONA CONTEXT — TestShopper (CUST-TEST)\nKnown: likes linen\n---"
    )
    try:
        prompt = factory().system_prompt or ""
        assert PERSONA_WRAPPER in prompt, (
            f"{name}: factory did not inject persona wrapper when ContextVar was set"
        )
    finally:
        persona_preamble_var.reset(token)


# ---------------------------------------------------------------------------
# @tool wrapper contract — Pattern I (Agents-as-Tools) needs these
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,wrapper", SPECIALIST_WRAPPERS, ids=[s[0] for s in SPECIALIST_WRAPPERS])
def test_tool_wrapper_has_strands_metadata(name: str, wrapper) -> None:
    """Each specialist's @tool-decorated function must still expose the
    Strands metadata the orchestrator uses for tool discovery."""
    assert hasattr(wrapper, "tool_spec"), f"{name}: @tool wrapper missing tool_spec"
    assert hasattr(wrapper, "tool_name"), f"{name}: @tool wrapper missing tool_name"
    assert wrapper.tool_name == name, (
        f"{name}: @tool wrapper tool_name is {wrapper.tool_name!r}"
    )


# ---------------------------------------------------------------------------
# Pattern I byte-compatibility gate
# ---------------------------------------------------------------------------


def test_orchestrator_exposes_all_five_specialists() -> None:
    """create_orchestrator() must still wire all five @tool specialists
    so Pattern I (Atelier Agents-as-Tools) keeps working."""
    from agents.orchestrator import create_orchestrator

    orch = create_orchestrator()
    assert isinstance(orch, Agent)
    tools = _tool_names(orch)
    expected = {"search", "recommendation", "pricing", "inventory", "support"}
    assert expected.issubset(tools), (
        f"orchestrator missing specialist tools {expected - tools}; got {sorted(tools)}"
    )


def test_guarded_orchestrator_appends_guardrails() -> None:
    """create_guarded_orchestrator() must add guardrails copy to the
    orchestrator's system prompt."""
    from agents.orchestrator import create_guarded_orchestrator

    guarded = create_guarded_orchestrator()
    assert isinstance(guarded, Agent)
    assert "GUARDRAILS" in (guarded.system_prompt or ""), (
        "guarded orchestrator did not append GUARDRAILS suffix"
    )


# ---------------------------------------------------------------------------
# Exa removal — defensive checks so the integration doesn't sneak back
# ---------------------------------------------------------------------------


def test_exa_api_key_removed_from_settings() -> None:
    """EXA_API_KEY was deleted in the three-pattern refactor."""
    from config import settings

    assert not hasattr(settings, "EXA_API_KEY"), (
        "settings.EXA_API_KEY reappeared — Exa MCP integration was removed, "
        "see .kiro/specs/customer-support-agent/requirements.md §5"
    )


def test_support_agent_has_no_exa_references() -> None:
    """The support specialist's module should carry no residual Exa symbols
    in its *code*. The module docstring is allowed to mention Exa because
    it documents the removal — we check the source with the docstring
    stripped so the "we removed Exa" note isn't treated as a regression.
    """
    import ast

    from agents import customer_support_agent as mod

    src = inspect.getsource(mod)
    tree = ast.parse(src)

    # Remove the module-level docstring from the AST and regenerate
    # source from the remaining nodes. That leaves imports, factory,
    # @tool — real code — without the removal-note prose.
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        tree.body = tree.body[1:]

    code_only = ast.unparse(tree)
    for forbidden in ("exa_client", "MCPClient", "from mcp", "EXA_API_KEY"):
        assert forbidden not in code_only, (
            f"customer_support_agent.py contains forbidden token {forbidden!r} "
            f"in executable code (module docstring is excluded from this check)"
        )
