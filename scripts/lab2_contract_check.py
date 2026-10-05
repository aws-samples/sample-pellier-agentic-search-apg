#!/usr/bin/env python3
"""Lab 2's checks: the Stock agent's numbers come from one SELECT on warehouse_inventory.

Task 2A runs your ``check_stock`` body through the same ``@tool`` wrapper the
Stock agent calls, once per case, and compares each answer with the catalog
and the warehouse rows read directly:

    not carried   a piece the catalog does not carry  -> not_found, no count
    several       a query that names several pieces   -> ambiguous, no count
    sold out      a carried piece with no units       -> success, total_units 0
    in stock      the Hadley Linen Shirt              -> success, the warehouse rows

You choose the first three queries; a query that is not what it claims to be
fails as a test input, so a weak test cannot pass. A blank choice uses the
default and the report says so.

Task 2B reads Marco's latest turn from ``pellier.tool_audit`` (his session is
the one choosing Marco on the home page starts, ``persona-marco-...``) and the
Stock agent's grant from ``agents/stock_agent.py``. The agent may call only
``check_stock``, and every count it was given must equal the warehouse rows.

    python3 scripts/lab2_contract_check.py
    python3 scripts/lab2_contract_check.py --unknown "..." --ambiguous "..." --sold-out "..."
    python3 scripts/lab2_contract_check.py --task 2B
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workshop_check as check  # noqa: E402  (sibling module)

REPO = check.REPO
BACKEND = REPO / "pellier" / "backend"
STOCK_AGENT = BACKEND / "agents" / "stock_agent.py"
MARCO_SESSION_PREFIX = "persona-marco-"

CASES = ("unknown", "several", "sold_out", "in_stock")
CHOSEN = ("unknown", "several", "sold_out")
DEFAULT_INPUTS = {
    "unknown": "Velvet Opera Cape",
    "several": "Linen shirt",
    "sold_out": "Quilted Silk Vest",
    "in_stock": "Hadley Linen Shirt",
}
_CASE_LABEL = {"unknown": "not carried", "several": "several", "sold_out": "sold out",
               "in_stock": "in stock"}
EXPECTED_2A = ("not carried -> not_found with no count; several -> ambiguous with the "
                "candidates; sold out -> success with 0 units; in stock -> success with "
                "the warehouse rows")
_NEXT_2A = ("open the Stock agent - check_stock block in pellier/backend/services/agent_tools.py: "
            "it must return the shared implementation's answer unchanged, so not_found stays "
            "not_found. Restart, then rerun this check.")

# The catalog's own answer to "which pieces does this query name?": every word
# of the query in the name, the matching rule check_stock documents.
_MATCH_SQL = """
    SELECT "productId" AS product_id, name
      FROM pellier.product_catalog
     WHERE {tokens}
     ORDER BY "productId"::int
"""
_STOCK_SQL = """
    SELECT warehouse_code, quantity
      FROM pellier.warehouse_inventory
     WHERE product_id = %s
     ORDER BY warehouse_code
"""
_LATEST_TURN = """
SELECT args->>'turn_id' AS turn_id
  FROM pellier.tool_audit
 WHERE session_id LIKE %s
 ORDER BY audit_id DESC
 LIMIT 1
"""
_TURN_ROWS = """
SELECT audit_id, tool, args, result
  FROM pellier.tool_audit
 WHERE session_id LIKE %s AND args->>'turn_id' = %s
 ORDER BY audit_id
"""


# ---------------------------------------------------------------------------
# Reading the catalog and the warehouse rows
# ---------------------------------------------------------------------------


def catalog_answer(conn: Any, query: str) -> Dict[str, Any]:
    """The products ``query`` names and, for exactly one, its warehouse rows."""
    tokens = [token.lower() for token in str(query or "").split() if token]
    if not tokens:
        return {"matches": [], "stock": []}
    clause = " AND ".join(["strpos(lower(name), %s) > 0"] * len(tokens))
    with conn.cursor() as cur:
        cur.execute(_MATCH_SQL.format(tokens=clause), tokens)
        matches = [dict(row) for row in cur.fetchall()]
        stock: List[Dict[str, Any]] = []
        if len(matches) == 1:
            cur.execute(_STOCK_SQL, (str(matches[0]["product_id"]),))
            stock = [dict(row) for row in cur.fetchall()]
    return {"matches": matches, "stock": stock}


def classify(catalog: Dict[str, Any]) -> str:
    """Which case a query belongs to, from the catalog alone."""
    matches, stock = catalog.get("matches") or [], catalog.get("stock") or []
    if not matches:
        return "unknown"
    if len(matches) > 1:
        return "several"
    if stock and all(int(row.get("quantity") or 0) == 0 for row in stock):
        return "sold_out"
    return "in_stock" if stock else "no_warehouse_rows"


def _counts(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    return {str(row.get("warehouse_code")): int(row.get("quantity") or 0) for row in rows}


def _counts_text(counts: Dict[str, int]) -> str:
    return ", ".join(f"{code} {quantity}" for code, quantity in sorted(counts.items())) or "no rows"


def describe_catalog(catalog: Dict[str, Any]) -> str:
    matches = catalog.get("matches") or []
    if not matches:
        return "not_found: no product matches"
    if len(matches) > 1:
        return f"ambiguous: {len(matches)} products match"
    counts = _counts(catalog.get("stock") or [])
    return f"success, {sum(counts.values())} units ({_counts_text(counts)})"


def describe_envelope(envelope: Dict[str, Any]) -> str:
    status = envelope.get("status") or ("error" if envelope.get("error") else "no status")
    if status == "ambiguous":
        return f"ambiguous: {len(envelope.get('candidates') or [])} candidates"
    if status == "success":
        counts = _counts(envelope.get("warehouses") or [])
        return f"success, {envelope.get('total_units')} units ({_counts_text(counts)})"
    if status == "not_found":
        return "not_found" + (", with a count" if "total_units" in envelope else "")
    return str(envelope.get("error") or status)[:60]


def keeps_contract(case: str, envelope: Dict[str, Any], catalog: Dict[str, Any]) -> bool:
    """Whether the tool's answer is the catalog's answer for this case."""
    ids = {str(row["product_id"]) for row in catalog.get("matches") or []}
    no_count = "total_units" not in envelope and "warehouses" not in envelope
    if case == "unknown":
        return envelope.get("status") == "not_found" and no_count
    if case == "several":
        candidates = envelope.get("candidates")
        return (envelope.get("status") == "ambiguous" and no_count
                and isinstance(candidates, list) and len(candidates) >= 2
                and all(isinstance(c, dict) and str(c.get("productId")) in ids
                        for c in candidates))
    product = envelope.get("product") or {}
    return (envelope.get("status") == "success"
            and str(product.get("productId")) in ids
            and _counts(envelope.get("warehouses") or []) == _counts(catalog.get("stock") or [])
            and envelope.get("total_units") == sum(_counts(catalog.get("stock") or []).values()))


# ---------------------------------------------------------------------------
# Task 2A
# ---------------------------------------------------------------------------


def judge_2a(
    conn: Any, tool: Callable[..., str], inputs: Dict[str, Tuple[str, str]]
) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Run ``tool`` once per case and judge each answer against the catalog."""
    rows: List[Sequence[Any]] = []
    evidence: List[str] = []
    bad_inputs: List[str] = []
    differs: List[str] = []
    for case in CASES:
        query, chosen_by = inputs[case]
        catalog = catalog_answer(conn, query)
        actual_case = classify(catalog)
        try:
            envelope = json.loads(tool(product_query=query))
        except (TypeError, ValueError):
            envelope = {"error": "the tool did not return JSON"}
        if not isinstance(envelope, dict):
            envelope = {"error": "the tool did not return an object"}
        if actual_case != case:
            verdict = f"not a {_CASE_LABEL[case]} query (it is {actual_case.replace('_', ' ')})"
            actual = actual_case.replace("_", " ")
            bad_inputs.append(f"{_CASE_LABEL[case]}: \"{query}\" is {actual}")
        elif keeps_contract(case, envelope, catalog):
            verdict = "matches"
        else:
            verdict = "differs"
            answer = describe_envelope(envelope)
            differs.append(f"{_CASE_LABEL[case]}: \"{query}\" came back {answer}")
        rows.append((_CASE_LABEL[case], query[:24], chosen_by, describe_catalog(catalog),
                     describe_envelope(envelope), verdict))
        evidence.append(_catalog_evidence(query, catalog))
    title = "check_stock keeps not carried, several and sold out apart"
    matched = sum(1 for row in rows if row[-1] == "matches")
    observed = f"{matched} of {len(CASES)} cases match" + (
        "; " + "; ".join(differs + bad_inputs) if differs or bad_inputs else "")
    if bad_inputs:
        return check.Finding("2A", title, check.NOT_YET, EXPECTED_2A, observed, evidence,
                             "choose a query that is what its case says: run the check again "
                             "with another --unknown, --ambiguous or --sold-out."), rows
    if differs:
        return check.Finding("2A", title, check.CONTRADICTED, EXPECTED_2A, observed,
                             evidence, _NEXT_2A), rows
    return check.Finding("2A", title, check.PROVED, EXPECTED_2A, observed, evidence), rows


def _catalog_evidence(query: str, catalog: Dict[str, Any]) -> str:
    matches = catalog.get("matches") or []
    if len(matches) != 1:
        names = ", ".join(f"{row['product_id']} {row['name']}" for row in matches[:4])
        listed = f": {names}" if names else ""
        return f"product_catalog: \"{query}\" matches {len(matches)}{listed}"
    product = matches[0]
    return (f"warehouse_inventory for {product['product_id']} {product['name']}: "
            f"{_counts_text(_counts(catalog.get('stock') or []))}")


# ---------------------------------------------------------------------------
# Task 2B
# ---------------------------------------------------------------------------


def granted_tools(path: Optional[pathlib.Path] = None) -> Optional[List[str]]:
    """The tool names ``_STOCK_TOOLS`` grants, read from the source, or None."""
    try:
        tree = ast.parse((path or STOCK_AGENT).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_STOCK_TOOLS"
                and isinstance(node.value, (ast.List, ast.Tuple))):
            return [item.attr if isinstance(item, ast.Attribute) else getattr(item, "id", "?")
                    for item in node.value.elts]
    return None


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _judge_stock_row(conn: Any, row: Dict[str, Any]) -> Tuple[bool, str]:
    args, result = _as_dict(row.get("args")), _as_dict(row.get("result"))
    query = str(args.get("product_query") or "")
    catalog = catalog_answer(conn, query)
    status = result.get("status")
    if status == "not_found":
        ok = not catalog["matches"]
        return ok, (f"audit {row['audit_id']}: check_stock(\"{query}\") said not carried; "
                    f"the catalog matches {len(catalog['matches'])}")
    if status == "ambiguous":
        return len(catalog["matches"]) > 1, (
            f"audit {row['audit_id']}: check_stock(\"{query}\") asked which; "
            f"the catalog matches {len(catalog['matches'])}")
    product = result.get("product") or {}
    product_id = str(product.get("productId") or "")
    real: Dict[str, int] = {}
    if product_id:
        with conn.cursor() as cur:
            cur.execute(_STOCK_SQL, (product_id,))
            real = _counts([dict(r) for r in cur.fetchall()])
    told = _counts(result.get("warehouses") or [])
    ok = bool(product_id) and told == real
    return ok, (f"audit {row['audit_id']}: check_stock(\"{query}\") gave "
                f"{_counts_text(told) if told else str(result.get('total_units')) + ' units'}; "
                + (f"warehouse_inventory for {product_id}: {_counts_text(real)}" if product_id
                   else "no catalog product carries that name"))


def judge_2b(conn: Any, grant: Optional[List[str]]) -> check.Finding:
    """Marco's latest turn: only check_stock ran, and its counts equal the warehouse rows."""
    title = "the Stock agent's numbers equal one SELECT on warehouse_inventory"
    expected = ("the Stock agent is granted check_stock only; Marco's latest turn called "
                "check_stock and nothing else; every count equals warehouse_inventory")
    grant_text = ", ".join(grant) if grant is not None else "unreadable"
    evidence = [f"agents/stock_agent.py grants: {grant_text}"]
    pattern = MARCO_SESSION_PREFIX + "%"
    with conn.cursor() as cur:
        cur.execute(_LATEST_TURN, (pattern,))
        latest = cur.fetchone()
        rows = []
        if latest and latest.get("turn_id"):
            cur.execute(_TURN_ROWS, (pattern, latest["turn_id"]))
            rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        return check.Finding("2B", title, check.NOT_YET, expected,
                             "no tool call in a session of Marco's yet", evidence,
                             "choose Marco on the home page, ask his stock question, then "
                             "rerun this check.")
    evidence.append(f"pellier.tool_audit turn {check.short(latest['turn_id'], 20)}: "
                    + ", ".join(f"{row['tool']} (audit {row['audit_id']})" for row in rows))
    grant_problems: List[str] = []
    if grant != ["check_stock"]:
        grant_problems.append(f"the agent is granted {grant_text}")
    others = sorted({row["tool"] for row in rows if row["tool"] != "check_stock"})
    if others:
        grant_problems.append("the turn called " + ", ".join(others)
                              + ", which read the catalog, not warehouse_inventory")
    stock_rows = [row for row in rows if row["tool"] == "check_stock"]
    if not stock_rows:
        grant_problems.append("the turn never called check_stock")
    count_problems: List[str] = []
    for row in stock_rows:
        ok, line = _judge_stock_row(conn, row)
        evidence.append(line)
        if not ok:
            count_problems.append(f"audit {row['audit_id']} does not match the catalog")
    if grant_problems:
        return check.Finding("2B", title, check.CONTRADICTED, expected,
                             "; ".join(grant_problems + count_problems), evidence,
                             "grant the Stock agent check_stock alone in the Stock agent - "
                             "definition block of agents/stock_agent.py; restart, ask Marco's "
                             "question again, then rerun this check.")
    if count_problems:
        return check.Finding("2B", title, check.CONTRADICTED, expected, "; ".join(count_problems),
                             evidence, "check_stock reported something warehouse_inventory does "
                             "not hold: finish Task 2A, restart, ask again, then rerun this check.")
    return check.Finding("2B", title, check.PROVED, expected,
                         f"{len(stock_rows)} check_stock call(s), every count matches", evidence)


# ---------------------------------------------------------------------------
# Running against the box's database
# ---------------------------------------------------------------------------


class _RowsOn:
    """The pool interface ``agent_tools`` calls, answered on one psycopg connection."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def fetch_all(self, sql: str, *params: Any) -> List[Dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


def participant_tool(conn: Any, cfg: Dict[str, str]) -> Callable[..., str]:
    """Your check_stock, through its ``@tool`` wrapper, on this connection."""
    for key, value in cfg.items():
        os.environ.setdefault(key, value)
    sys.path.insert(0, str(BACKEND))
    from services import agent_tools

    agent_tools.set_db_service(_RowsOn(conn))
    return agent_tools.check_stock


def _inputs(args: argparse.Namespace) -> Dict[str, Tuple[str, str]]:
    chosen = {"unknown": args.unknown, "several": args.ambiguous, "sold_out": args.sold_out}
    inputs = {case: ((value.strip(), "you") if value and value.strip()
                     else (DEFAULT_INPUTS[case], "default"))
              for case, value in chosen.items()}
    inputs["in_stock"] = (DEFAULT_INPUTS["in_stock"], "fixed")
    return inputs


def run(task: str, inputs: Dict[str, Tuple[str, str]],
        env_path: pathlib.Path = check.DEFAULT_ENV) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Connect with the backend's settings and run one task's check; never raises."""
    cfg = check.db_config(env_path)
    title = f"Lab 2 Task {task}"
    if cfg is None:
        return check.Finding(task, title, check.UNCHECKED, "a reachable database",
                             "the check could not look",
                             [check.missing_settings_reason(env_path)]), []
    try:
        with check.connect(cfg) as conn:
            conn.autocommit = True
            if task == "2B":
                return judge_2b(conn, granted_tools()), []
            return judge_2a(conn, participant_tool(conn, cfg), inputs)
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return check.Finding(task, title, check.UNCHECKED, "a reachable database",
                             "the check could not look",
                             [f"{type(exc).__name__}: {str(exc)[:160]}"],
                             "check that the database in pellier/backend/.env is reachable."), []


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task", choices=("2A", "2B"), default="2A")
    parser.add_argument("--unknown", help="A piece Pellier does not carry")
    parser.add_argument("--ambiguous", help="A query that names several pieces")
    parser.add_argument("--sold-out", dest="sold_out", help="A carried piece with no units")
    args = parser.parse_args(argv)
    finding, rows = run(args.task, _inputs(args))
    if args.task == "2A":
        print("Lab 2A: check_stock answers from the catalog and warehouse_inventory")
        if rows:
            print(check.table(("case", "query", "chosen by", "expected (catalog)",
                               "observed (your check_stock)", "verdict"), rows))
    else:
        print("Lab 2B: Marco's latest answer comes from warehouse_inventory alone")
    print(check.render(finding))
    passed = finding.state == check.PROVED
    print(f"Lab {args.task} check {'passed' if passed else 'failed'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
