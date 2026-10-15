"""The starter and the solution of each lab region, whatever the live file holds.

A participant edits the live files, so a contract test that read them would
pass or fail with the participant's progress. These helpers build each variant
from its source of truth instead: the starter from ``workshop/starters``, the
solution from its twin under ``solutions/``. The region body runs in the live
module's own namespace, so it sees the same imports and globals it would in
place.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Callable, Dict, List

REPO = Path(__file__).resolve().parents[3]
STARTERS = REPO / "workshop" / "starters"
SOLUTIONS = REPO / "solutions"

STARTER = "starter"
SOLUTION = "solution"

LAB1_RRF = {
    STARTER: STARTERS / "lab-1-fusion.sql",
    SOLUTION: SOLUTIONS / "the-quiet-search" / "sql" / "lab-1-fusion-solution.sql",
}
_PLAN = ("Search plan - preserve requirements",
         STARTERS / "lab-1" / "preserve-requirements.pyfrag",
         SOLUTIONS / "the-quiet-search" / "retrieval" / "search_plan_solution.py")
_VECTOR = ("Vector branch - order by meaning",
           STARTERS / "lab-1" / "vector-branch.pyfrag",
           SOLUTIONS / "the-quiet-search" / "retrieval" / "store_tools_solution.py")
LAB2_FUNCTION = {
    STARTER: STARTERS / "lab-2-check-stock.sql",
    SOLUTION: SOLUTIONS / "closing-marcos-gap" / "sql" / "lab-2-check-stock-solution.sql",
}
_GRANT = ("Stock agent - definition",
          STARTERS / "lab-2" / "stock-agent-definition.pyfrag",
          SOLUTIONS / "waking-the-stock-keeper" / "agents" / "stock_agent_solution.py")
_PUBLISHED = ("Gateway catalogue - published tools",
              STARTERS / "lab-3" / "gateway-published-tools.pyfrag",
              SOLUTIONS / "the-ledger" / "gateway" / "gateway_tool_schemas_solution.py")
_GATEWAY_TOOLS = ("Support agent - Gateway tools",
              STARTERS / "lab-3" / "support-gateway-tools.pyfrag",
              SOLUTIONS / "the-ledger" / "services" / "agentcore_gateway.py")


def region(text: str, label: str) -> str:
    """The lines between one marker pair, without the markers."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if f"WORKSHOP - {label}: START ===" in line)
    end = next(i for i, line in enumerate(lines) if f"WORKSHOP - {label}: END ===" in line)
    return "\n".join(lines[start + 1:end]) + "\n"


def body(spec: tuple, variant: str) -> str:
    label, starter, solution = spec
    if variant == STARTER:
        return starter.read_text(encoding="utf-8")
    return region(solution.read_text(encoding="utf-8"), label)


def _function(source: str, name: str, namespace: Dict[str, Any]) -> Callable[..., Any]:
    scratch: Dict[str, Any] = {}
    exec(compile(source, f"<{name}>", "exec"), namespace, scratch)  # noqa: S102 - repo source
    return scratch[name]


def plan_fallback(variant: str) -> Callable[..., Any]:
    """``SearchPlan._next_attempt`` as the starter or the solution writes it."""
    from services import search_plan

    source = "def _next_attempt(self, relaxations):\n" + textwrap.indent(
        textwrap.dedent(body(_PLAN, variant)), "    ")
    return _function(source, "_next_attempt", vars(search_plan))


def vector_branch(variant: str) -> Callable[..., str]:
    """``store_tools.vector_branch_sql`` as the starter or the solution writes it."""
    from services import store_tools

    source = "def vector_branch_sql(extra_clauses=()):\n" + textwrap.indent(
        textwrap.dedent(body(_VECTOR, variant)), "    ")
    return _function(source, "vector_branch_sql", vars(store_tools))


def check_stock_function(variant: str) -> str:
    """The ``CREATE OR REPLACE FUNCTION pellier.check_stock`` statement the worksheet runs."""
    text = LAB2_FUNCTION[variant].read_text(encoding="utf-8")
    start = text.index("CREATE OR REPLACE FUNCTION pellier.check_stock(")
    end = text.index("$check_stock$;", start) + len("$check_stock$;")
    return text[start:end]


def stock_grant(variant: str) -> List[Any]:
    """The ``_STOCK_TOOLS`` list the Stock agent definition grants."""
    from agents import stock_agent

    scratch: Dict[str, Any] = {}
    exec(compile(body(_GRANT, variant), "<stock-grant>", "exec"),  # noqa: S102 - repo source
         dict(vars(stock_agent)), scratch)
    return scratch["_STOCK_TOOLS"]


def _constants(spec: tuple, variant: str, *names: str) -> tuple:
    scratch: Dict[str, Any] = {}
    exec(compile(body(spec, variant), f"<{spec[0]}>", "exec"), {}, scratch)  # noqa: S102 - repo source
    return tuple(scratch[name] for name in names)


def deferred_tools(variant: str) -> frozenset:
    """The ``UNPUBLISHED_TOOLS`` the Gateway catalogue region names."""
    return _constants(_PUBLISHED, variant, "UNPUBLISHED_TOOLS")[0]


def support_contract(variant: str) -> tuple:
    """``(SUPPORT_GATEWAY_TOOLS, SUPPORT_CALLER_BOUND_TOOLS)`` from the Gateway tools region."""
    return _constants(_GATEWAY_TOOLS, variant, "SUPPORT_GATEWAY_TOOLS",
                      "SUPPORT_CALLER_BOUND_TOOLS")
