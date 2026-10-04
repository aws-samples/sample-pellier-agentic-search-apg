"""Every deterministic tool has an owner, or a recorded reason for having none.

The finding this closes
-----------------------

A pre-handoff audit found a fully governed capability bound to no agent: nothing could
call it. It was not broken, it was unreachable, and nothing in the repository said
whether that was a decision or an oversight. A lab author reading `agent_tools.py` would
reasonably write a step against it and find no path. It has since been deleted, on the
grounds that a capability we may want later is cheaper to build then than to carry
unreachable now.

An unreachable tool is worse than a missing one: it reads as shipped, it carries a
security surface that still needs reviewing, and it costs the next team the same
investigation this test now answers in one place.

Writing the check surfaced a second one immediately: `give_store_credit` was bound
to no agent. That one was deliberate, and its wrapper has since been deleted outright:
the Operator reaches the write through `services.governed_execution`, so there is no
`@tool` for an agent to bind and nothing left to waive.

What this asserts
-----------------

For every `@tool` in `services/agent_tools.py`, either a specialist imports it or it
appears in `UNBOUND_BY_DECISION` with a reason. That makes both directions fail loudly:

  * a new tool nobody binds fails until someone decides;
  * a tool listed as deliberately unbound fails the moment an agent binds it, so the
    decision has to be revisited rather than silently reversed.

The scan is import-based rather than runtime-based on purpose. `stock_agent.py` grants
its tool inside the Lab 2B marker region, which is empty until a participant fills it,
but the module-level import names `check_stock` in either state. A runtime check would
report it as orphaned on every unstarted workshop box.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "pellier" / "backend"
AGENT_TOOLS = BACKEND / "services" / "agent_tools.py"
AGENTS_DIR = BACKEND / "agents"

# Tools deliberately reachable by no specialist. Each entry is a decision with a reason,
# not a waiver: removing the reason, or binding the tool, must break this test.
UNBOUND_BY_DECISION: Dict[str, str] = {}

# The eight agent tools, and no others. `give_store_credit` is the ninth store tool
# and has no wrapper here on purpose. Agents are plain Strands Agents over these
# functions; none is wrapped as a tool itself.
EXPECTED_TOOLS: Set[str] = {
    "search_products", "browse_department", "compare_products", "check_stock",
    "get_orders", "get_return_policy", "get_tickets", "ask_a_person",
}


def _decorated_tools(path: Path) -> Set[str]:
    """Names of `@tool`-decorated functions, from the AST rather than a regex."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            name = getattr(target, "attr", None) or getattr(target, "id", None)
            if name == "tool":
                found.add(node.name)
    return found


def _bound_tools() -> Dict[str, Set[str]]:
    """Agent module -> the tool names it imports from `services.agent_tools`."""
    bound: Dict[str, Set[str]] = {}
    for path in sorted(AGENTS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in (
                "services.agent_tools", "agent_tools",
            ):
                names.update(alias.name for alias in node.names)
        if names:
            bound[path.name] = names
    return bound


def test_the_scan_finds_the_tools_and_the_agents() -> None:
    """Guards the assertions below from passing on an empty scan."""
    tools = _decorated_tools(AGENT_TOOLS)
    bound = _bound_tools()
    assert "give_store_credit" not in tools, "the Operator's write grew an agent wrapper"
    assert tools == EXPECTED_TOOLS, f"@tool functions differ from the eight: {sorted(tools ^ EXPECTED_TOOLS)}"
    assert set(bound) == {"shopping_agent.py", "stock_agent.py", "support_agent.py"}


def test_every_tool_is_bound_or_recorded_as_unbound() -> None:
    tools = _decorated_tools(AGENT_TOOLS)
    bound = set().union(*_bound_tools().values())
    orphans = sorted(tools - bound - set(UNBOUND_BY_DECISION))
    assert not orphans, (
        "these tools are reachable by no agent and no decision is recorded:\n  "
        + "\n  ".join(orphans)
        + "\nEither bind one to an agent or add it to UNBOUND_BY_DECISION with the reason."
    )


def test_each_agent_binds_its_documented_tools() -> None:
    """The module docstring of agent_tools.py is the ownership table."""
    bound = _bound_tools()
    assert bound["shopping_agent.py"] == {
        "search_products", "browse_department", "compare_products", "ask_a_person",
    }
    assert bound["stock_agent.py"] == {"check_stock"}
    assert bound["support_agent.py"] == {
        "get_orders", "get_return_policy", "get_tickets", "ask_a_person",
    }


def test_no_recorded_unbound_tool_has_quietly_been_bound() -> None:
    """Reversing the decision must be deliberate, not a side effect of an import."""
    bound = set().union(*_bound_tools().values())
    contradictions = sorted(set(UNBOUND_BY_DECISION) & bound)
    assert not contradictions, (
        f"{contradictions} are listed as deliberately unbound but an agent imports "
        "them. Update UNBOUND_BY_DECISION, and the governance that entry describes."
    )


def test_every_recorded_reason_is_a_reason() -> None:
    """A one-word waiver is not a decision the next team can act on."""
    for name, reason in UNBOUND_BY_DECISION.items():
        assert len(reason) > 120, f"{name}: the recorded reason is too thin to act on"
        assert name not in reason.split()[0], name


def test_every_recorded_unbound_tool_still_exists() -> None:
    """A stale entry hides the fact that the capability is gone."""
    tools = _decorated_tools(AGENT_TOOLS)
    missing = sorted(set(UNBOUND_BY_DECISION) - tools)
    assert not missing, f"UNBOUND_BY_DECISION names tools that no longer exist: {missing}"


def test_no_agent_is_wrapped_as_a_tool() -> None:
    """Agents are not tools: the Router picks one agent, no agent calls another."""
    wrappers: Set[str] = set()
    for path in sorted(AGENTS_DIR.glob("*.py")):
        wrappers |= _decorated_tools(path)
    assert not wrappers, f"@tool wrappers found in agents/: {sorted(wrappers)}"
