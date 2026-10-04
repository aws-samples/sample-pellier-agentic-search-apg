"""Factory-shape contract test.

The Router builds every agent from a uniform factory function. This test
enforces that contract so future changes to ``agents/`` get flagged before
they ship.

Scope, per agent (shopping, stock, support):
  1. ``build_<name>_agent()`` exists and returns a real Strands Agent
  2. The Agent has exactly the tools the design grants it
  3. Anonymous build leaves the ``<persona-preamble>`` wrapper OFF
  4. Setting the persona_preamble_var ContextVar injects the wrapper
  5. No agent is wrapped as a ``@tool`` for another agent to call

Also enforces:
  - ``EXA_API_KEY`` is gone from ``config.settings``
  - the Support agent module has no residual Exa references
"""
from __future__ import annotations

import inspect

import pytest

from strands import Agent

from agents import shopping_agent as shopping_module
from agents import stock_agent as stock_module
from agents import support_agent as support_module
from agents.shopping_agent import build_shopping_agent
from agents.stock_agent import build_stock_agent
from agents.support_agent import build_support_agent
from pellier_copy import SHOPPING_SYSTEM_PROMPT
from services.persona_context import persona_preamble_var, set_persona_preamble


# Exact tool names bound to each agent. If you rename a tool in
# ``services/agent_tools.py`` you have to update this list.
AGENT_SPECS = [
    ("shopping", build_shopping_agent,
     {"search_products", "browse_department", "compare_products", "ask_a_person"}),
    ("stock", build_stock_agent, {"check_stock"}),
    ("support", build_support_agent,
     {"get_orders", "get_return_policy", "get_tickets", "ask_a_person"}),
]

PERSONA_WRAPPER = "<persona-preamble source=\"aurora-ltm\">"


def _tool_names(agent: Agent) -> set[str]:
    """Extract the set of bound tool names from an Agent's tool registry."""
    registry = getattr(agent.tool_registry, "registry", None) or {}
    return set(registry.keys()) if isinstance(registry, dict) else set()


def _is_governed_stock_scaffold(name: str) -> bool:
    """The governed workshop ships the Stock agent as a definition exercise."""
    return name == "stock" and bool(getattr(stock_module, "_STOCK_AGENT_STUBBED", False))


# ---------------------------------------------------------------------------
# Factory contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,factory,expected_tools", AGENT_SPECS, ids=[s[0] for s in AGENT_SPECS])
def test_factory_returns_real_agent(name: str, factory, expected_tools: set[str]) -> None:
    if _is_governed_stock_scaffold(name):
        with pytest.raises(RuntimeError, match="Stock agent definition"):
            factory()
        return

    agent = factory()
    assert isinstance(agent, Agent), f"{name}: factory must return a Strands Agent"
    assert agent.name == name, (
        f"{name}: factory must set Agent.name so OTEL specialistRoute is stable"
    )
    assert _tool_names(agent) == expected_tools


def test_the_shopping_agent_drops_the_handoff_on_an_ordinary_catalog_turn() -> None:
    agent = build_shopping_agent(allow_handoff=False)
    assert "ask_a_person" not in _tool_names(agent)
    assert "<turn-policy>" in (agent.system_prompt or "")
    assert "<turn-policy>" not in (build_shopping_agent().system_prompt or "")


def test_the_shopping_prompt_merges_the_search_and_personalization_rules() -> None:
    for required in (
        "search_products", "browse_department", "compare_products", "ask_a_person",
        "constraint_notice", "search_notice", "PERSONA CONTEXT",
    ):
        assert required in SHOPPING_SYSTEM_PROMPT, required
    retired = ("boutique",) + tuple(
        "_".join(parts) for parts in (
            ("get", "related", "products"), ("search", "products", "hybrid"),
            ("escalate", "to", "human"), ("browse", "category"),
        )
    )
    for word in retired:
        assert word not in SHOPPING_SYSTEM_PROMPT, word


@pytest.mark.parametrize("name,factory,_tools", AGENT_SPECS, ids=[s[0] for s in AGENT_SPECS])
def test_factory_anonymous_has_no_persona_wrapper(name: str, factory, _tools: set[str]) -> None:
    """Anonymous build (empty ContextVar) must not include the persona wrapper."""
    assert persona_preamble_var.get() == "", (
        "persona ContextVar leaked into a later test; an earlier test forgot to reset"
    )
    if _is_governed_stock_scaffold(name):
        with pytest.raises(RuntimeError, match="Stock agent definition"):
            factory()
        return

    prompt = factory().system_prompt or ""
    assert PERSONA_WRAPPER not in prompt, (
        f"{name}: anonymous prompt unexpectedly contains the persona wrapper"
    )


@pytest.mark.parametrize("name,factory,_tools", AGENT_SPECS, ids=[s[0] for s in AGENT_SPECS])
def test_factory_honors_persona_contextvar(name: str, factory, _tools: set[str]) -> None:
    """Setting the persona preamble ContextVar injects the wrapper into the system prompt."""
    token = set_persona_preamble(
        "PERSONA CONTEXT - TestShopper (CUST-TEST)\nKnown: likes linen\n---"
    )
    try:
        if _is_governed_stock_scaffold(name):
            with pytest.raises(RuntimeError, match="Stock agent definition"):
                factory()
            return

        prompt = factory().system_prompt or ""
        assert PERSONA_WRAPPER in prompt, (
            f"{name}: factory did not inject persona wrapper when ContextVar was set"
        )
    finally:
        persona_preamble_var.reset(token)


# ---------------------------------------------------------------------------
# No agents-as-tools: the Router builds one agent per turn and nothing else
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", [shopping_module, stock_module, support_module],
                         ids=["shopping", "stock", "support"])
def test_no_agent_module_exports_a_tool_wrapper(module) -> None:
    wrappers = [
        name for name, value in vars(module).items()
        if hasattr(value, "tool_spec") and hasattr(value, "tool_name")
        and not name.startswith("_") and name not in (
            "search_products", "browse_department", "compare_products", "ask_a_person",
            "check_stock", "get_orders", "get_return_policy", "get_tickets",
        )
    ]
    assert not wrappers, f"{module.__name__} exports agent-as-tool wrappers: {wrappers}"


def test_the_stock_definition_is_the_only_scaffold() -> None:
    """The Router reports the Stock agent as unbuilt while its definition is the lab."""
    from services.chat import _unbuilt_dispatcher_specialist

    assert _unbuilt_dispatcher_specialist("shopping") is None
    assert _unbuilt_dispatcher_specialist("support") is None
    expected = "stock" if getattr(stock_module, "_STOCK_AGENT_STUBBED", False) else None
    assert _unbuilt_dispatcher_specialist("stock") == expected


# ---------------------------------------------------------------------------
# Exa removal, defensive checks so the integration doesn't sneak back
# ---------------------------------------------------------------------------


def test_exa_api_key_removed_from_settings() -> None:
    from config import settings

    assert not hasattr(settings, "EXA_API_KEY"), (
        "settings.EXA_API_KEY reappeared; the Exa MCP integration was removed"
    )


def test_support_agent_has_no_exa_references() -> None:
    """The Support agent's module carries no residual Exa symbols in its code."""
    import ast

    src = inspect.getsource(support_module)
    tree = ast.parse(src)
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
            f"support_agent.py contains forbidden token {forbidden!r} in executable code"
        )
