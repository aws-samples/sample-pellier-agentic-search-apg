"""The starter and the solution of each Lab 1 and Lab 2 region, whatever the live file holds.

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
    STARTER: STARTERS / "lab-1-rrf.sql",
    SOLUTION: SOLUTIONS / "the-quiet-search" / "sql" / "lab-1-rrf-solution.sql",
}
_PLAN = ("Search plan - preserve requirements",
         STARTERS / "lab-1" / "preserve-requirements.pyfrag",
         SOLUTIONS / "the-quiet-search" / "retrieval" / "search_plan_solution.py")
_CHECK_STOCK = ("Stock agent - check_stock",
                STARTERS / "lab-2" / "check-stock-tool.pyfrag",
                SOLUTIONS / "closing-marcos-gap" / "services"
                / "agent_tools_check_stock_solution.py")
_GRANT = ("Stock agent - definition",
          STARTERS / "lab-2" / "stock-agent-definition.pyfrag",
          SOLUTIONS / "waking-the-stock-keeper" / "agents" / "stock_agent_solution.py")


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
    """``SearchPlan._with_relaxations`` as the starter or the solution writes it."""
    from services import search_plan

    source = "def _with_relaxations(self, relaxations):\n" + textwrap.indent(
        textwrap.dedent(body(_PLAN, variant)), "    ")
    return _function(source, "_with_relaxations", vars(search_plan))


def check_stock_body(variant: str) -> Callable[..., str]:
    """The ``check_stock`` tool body, run in ``services.agent_tools``."""
    from services import agent_tools

    source = "def check_stock(product_query):\n" + textwrap.indent(
        textwrap.dedent(body(_CHECK_STOCK, variant)), "    ")
    return _function(source, "check_stock", vars(agent_tools))


def stock_grant(variant: str) -> List[Any]:
    """The ``_STOCK_TOOLS`` list the Stock agent definition grants."""
    from agents import stock_agent

    scratch: Dict[str, Any] = {}
    exec(compile(body(_GRANT, variant), "<stock-grant>", "exec"),  # noqa: S102 - repo source
         dict(vars(stock_agent)), scratch)
    return scratch["_STOCK_TOOLS"]
