#!/usr/bin/env python3
"""Prepare the retrieval SQL, warehouse SQL, and agent-grant exercises."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


AGENT_GRANT_START = "# === WORKSHOP: Stock Keeper agent grant: START ==="
AGENT_GRANT_END = "# === WORKSHOP: Stock Keeper agent grant: END ==="
TOOL_BODY_START = "# === WORKSHOP: warehouse inventory SQL: START ==="
TOOL_BODY_END = "# === WORKSHOP: warehouse inventory SQL: END ==="
TOOL_STUB_MARKER = "WORKSHOP_INVENTORY_SQL_STUB"
RETRIEVAL_BLOCKS = {
    "eligibility": (
        "      -- WORKSHOP_RETRIEVAL_FILTER_STUB\n"
        "      -- Require price at or below :'max_price'::numeric and quantity above zero.\n"
        "      AND TRUE",
        "      AND price <= :'max_price'::numeric\n      AND quantity > 0",
    ),
    "rank fusion": (
        "           -- WORKSHOP_RETRIEVAL_RANK_STUB\n"
        "           -- Sum 1 / (60 + rank) for each branch. Use decimal division.\n"
        "           0.0::numeric AS rrf_score",
        "           sum(1.0 / (60 + rank)) AS rrf_score",
    ),
}
INVENTORY_STARTER = '''    # WORKSHOP_INVENTORY_SQL_STUB
    # Return (query, arguments). Keep the function signature and docstring.
    # Join wi to w, select the six fields above, and filter with wi.product_id = %s.
    # Sort by quantity descending, then warehouse ID. Bind (product_id,).
    raise NotImplementedError("Complete the warehouse inventory SQL")
'''
INVENTORY_RECOVERY = '''    query = """
        SELECT w.id AS warehouse_id,
               w.display_name AS warehouse_name,
               w.city,
               w.ship_window_min,
               w.ship_window_max,
               wi.quantity
        FROM pellier.warehouse_inventory wi
        JOIN pellier.warehouses w ON w.id = wi.warehouse_id
        WHERE wi.product_id = %s
        ORDER BY wi.quantity DESC, w.id ASC
    """
    return query, (product_id,)
'''

STARTER_AGENT_GRANT = """# === WORKSHOP: Stock Keeper agent grant: START ===
# WORKSHOP_AGENT_GRANT_STUB
# Add floor_check to this list after its implementation passes step 1.
INVENTORY_AGENT_TOOLS = [restock_shelf, running_low]
# === WORKSHOP: Stock Keeper agent grant: END ==="""

COMPLETE_AGENT_GRANT = """# === WORKSHOP: Stock Keeper agent grant: START ===
INVENTORY_AGENT_TOOLS = [floor_check, restock_shelf, running_low]
# === WORKSHOP: Stock Keeper agent grant: END ==="""


def _paths(repo: Path) -> dict[str, Path]:
    return {
        "inventory_sql": repo / "pellier/backend/services/inventory_sql.py",
        "retrieval_sql": repo / "workshop/retrieval.sql",
        "stock_keeper": repo / "pellier/backend/agents/stock_keeper.py",
    }


def _replace_marked_block(path: Path, replacement: str) -> None:
    source = path.read_text(encoding="utf-8")
    if source.count(AGENT_GRANT_START) != 1 or source.count(AGENT_GRANT_END) != 1:
        raise RuntimeError(
            f"{path} must contain exactly one Stock Keeper agent-grant block"
        )
    before, remainder = source.split(AGENT_GRANT_START, 1)
    _current, after = remainder.split(AGENT_GRANT_END, 1)
    path.write_text(
        f"{before}{replacement}{after}",
        encoding="utf-8",
    )


def _inventory_tool_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name)
            and target.id == "INVENTORY_AGENT_TOOLS"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            raise RuntimeError("INVENTORY_AGENT_TOOLS must be a literal list")
        names = {
            item.id
            for item in node.value.elts
            if isinstance(item, ast.Name)
        }
        if len(names) != len(node.value.elts):
            raise RuntimeError(
                "INVENTORY_AGENT_TOOLS may contain only imported tool names"
            )
        return names
    raise RuntimeError("INVENTORY_AGENT_TOOLS assignment was not found")


def inspect_state(repo: Path) -> dict[str, object]:
    paths = _paths(repo)
    for label, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"Missing {label}: {path}")

    tool_source = paths["inventory_sql"].read_text(encoding="utf-8")
    tool_is_stub = TOOL_STUB_MARKER in tool_source
    inventory_tools = _inventory_tool_names(paths["stock_keeper"])
    return {
        "floor_check": "exercise" if tool_is_stub else "shipped",
        "Stock Keeper": (
            "shipped"
            if not tool_is_stub and "floor_check" in inventory_tools
            else "exercise"
        ),
        "inventoryTools": sorted(inventory_tools),
        "retrieval": (
            "exercise" if "WORKSHOP_RETRIEVAL_" in
            paths["retrieval_sql"].read_text(encoding="utf-8") else "shipped"
        ),
    }


def apply_starter(repo: Path) -> dict[str, object]:
    paths = _paths(repo)
    for label in ("inventory_sql", "retrieval_sql", "stock_keeper"):
        if not paths[label].is_file():
            raise RuntimeError(f"Missing {label}: {paths[label]}")

    _replace_inventory_body(paths["inventory_sql"], INVENTORY_STARTER)
    _replace_retrieval_blocks(paths["retrieval_sql"], complete=False)
    _replace_marked_block(paths["stock_keeper"], STARTER_AGENT_GRANT)
    return verify_state(repo, "starter")


def _replace_inventory_body(path: Path, body: str) -> None:
    source = path.read_text(encoding="utf-8")
    if source.count(TOOL_BODY_START) != 1 or source.count(TOOL_BODY_END) != 1:
        raise RuntimeError(
            f"{path} must contain exactly one warehouse SQL block"
        )
    before, remainder = source.split(TOOL_BODY_START, 1)
    _current, after = remainder.split(TOOL_BODY_END, 1)
    path.write_text(
        f"{before}{TOOL_BODY_START}\n{body.rstrip()}\n    {TOOL_BODY_END}{after}",
        encoding="utf-8",
    )


def _replace_retrieval_blocks(path: Path, *, complete: bool) -> None:
    source = path.read_text(encoding="utf-8")
    for label, alternatives in RETRIEVAL_BLOCKS.items():
        start = f"-- === WORKSHOP: {label}: START ==="
        end = f"-- === WORKSHOP: {label}: END ==="
        if source.count(start) != 1 or source.count(end) != 1:
            raise RuntimeError(f"{path} must contain one {label} block")
        before, rest = source.split(start, 1)
        _, after = rest.split(end, 1)
        indent = "      " if label == "eligibility" else "           "
        source = f"{before}{start}\n{alternatives[int(complete)]}\n{indent}{end}{after}"
    path.write_text(source, encoding="utf-8")


def complete_retrieval(repo: Path) -> dict[str, object]:
    _replace_retrieval_blocks(_paths(repo)["retrieval_sql"], complete=True)
    return inspect_state(repo)


def complete_tool(repo: Path) -> dict[str, object]:
    _replace_inventory_body(_paths(repo)["inventory_sql"], INVENTORY_RECOVERY)
    return verify_state(repo, "tool-wired")


def complete_agent(repo: Path) -> dict[str, object]:
    _replace_marked_block(_paths(repo)["stock_keeper"], COMPLETE_AGENT_GRANT)
    return verify_state(repo, "complete")


def verify_state(repo: Path, expected: str) -> dict[str, object]:
    state = inspect_state(repo)
    expected_states = {
        "starter": ("exercise", "exercise"),
        "tool-wired": ("shipped", "exercise"),
        "complete": ("shipped", "shipped"),
    }
    expected_tool, expected_agent = expected_states[expected]
    actual = (state["floor_check"], state["Stock Keeper"])
    wanted = (expected_tool, expected_agent)
    if actual != wanted:
        raise RuntimeError(
            f"Expected builders state {expected!r} {wanted}, found {actual}"
        )
    return state


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("apply")
    commands.add_parser("complete-tool")
    commands.add_parser("complete-retrieval")

    verify = commands.add_parser("verify")
    verify.add_argument(
        "--expect",
        choices=("starter", "tool-wired", "complete"),
        required=True,
    )

    commands.add_parser("complete-agent")
    return root


def main() -> int:
    args = parser().parse_args()
    repo = args.repo.resolve()
    try:
        if args.command == "apply":
            state = apply_starter(repo)
        elif args.command == "complete-tool":
            state = complete_tool(repo)
        elif args.command == "complete-retrieval":
            state = complete_retrieval(repo)
        elif args.command == "complete-agent":
            state = complete_agent(repo)
        else:
            state = verify_state(repo, args.expect)
    except (OSError, RuntimeError, SyntaxError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
