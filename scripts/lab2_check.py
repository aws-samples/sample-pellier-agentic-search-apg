#!/usr/bin/env python3
"""Lab 2's checks: the Stock agent holds one tool, and that tool answers from the rows.

Task 2A reads Marco's latest Stock-agent turn from ``pellier.tool_audit`` (his
session is the one ``uv run scripts/lab_run.py send --lab 2`` starts,
``persona-marco-...``). Each in-process audit row records the agent that called
the tool and the store tools that running agent held (``args->>'agent'``,
``args->'grant'``), so the check reads the grant the answering Stock agent
actually had, never the source: a saved definition counts once Marco's requests
have run on it. As shipped, the Stock agent holds only the catalog tools, so its
call to ``check_stock`` is refused and does not run. Once connected, that agent
may hold only ``check_stock``, the turn may call nothing else, and the count it
was given for every piece Pellier carries must equal the warehouse rows. What it
was told about a piece Pellier does not carry is Task 2B's to judge.

Task 2B judges ``pellier.check_stock``, the database function both rails call,
as it is live. It runs four cases through ``services.store_tools.check_stock``
on this connection and compares each answer with the catalog and the warehouse
rows read directly:

    not carried   a piece the catalog does not carry  -> not_found, no count
    several       a query that names several pieces   -> ambiguous, no count
    sold out      a carried piece with no units       -> success, total_units 0
    in stock      the Hadley Linen Shirt              -> success, the warehouse rows

It also reads the live function's source: it must be the one
``workshop/lab-2-check-stock.sql`` committed. You choose the first three queries;
a query that is not what it claims to be fails as a test input, so a weak test
cannot pass. A blank choice uses the default and the report says so.

The evidence export judges 2B from the rows Marco's turns left
(:func:`judge_recorded_2b`): his latest ``check_stock`` call for each case, as
recorded, against the catalog.

    uv run scripts/lab2_check.py --task 2A
    uv run scripts/lab2_check.py --task 2B
    uv run scripts/lab2_check.py --task 2B --unknown "..." --ambiguous "..." --sold-out "..."
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workshop_check as check  # noqa: E402  (sibling module)

REPO = check.REPO
BACKEND = REPO / "pellier" / "backend"
MARCO_SESSION_PREFIX = "persona-marco-"
# The Stock agent's name on the audit rows it leaves (``args->>'agent'``).
STOCK_AGENT_NAME = "stock"
# What the Stock agent - definition starter grants: the catalog tools, and no
# tool that reads warehouse_inventory. A turn answered with it is a lab not done
# yet, not a wrong answer.
STARTER_GRANT = ("search_products", "browse_department", "compare_products")
SEND = "uv run scripts/lab_run.py send --lab 2"
SEND_2A = "uv run scripts/lab_run.py send --lab 2 --task 2A"
RESTART = "sudo systemctl restart pellier"
STOCK_AGENT_FILE = BACKEND / "agents" / "stock_agent.py"
WORKSHEET = REPO / "workshop" / "lab-2-check-stock.sql"
WORKSHEET_STARTER = REPO / "workshop" / "starters" / "lab-2-check-stock.sql"
WORKSHEET_RUN = "psql -f workshop/lab-2-check-stock.sql"
FUNCTION_REGION = "Stock check - not carried"
STAMP_PREFIX = "Lab 2B function sha256 "
_DOLLAR = "$check_stock$"

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
EXPECTED_2B = ("not carried -> not_found with no count; several -> ambiguous with the "
               "candidates; sold out -> success with 0 units; in stock -> success with "
               "the warehouse rows; the live pellier.check_stock is the one in your file")
_NEXT_2B = ("what should a piece Pellier does not carry return? Write that test in the "
            f"{FUNCTION_REGION} region of workshop/lab-2-check-stock.sql, then run it: "
            f"{WORKSHEET_RUN}. It commits your function only when its four probes match.")

# The catalog's own answer to "which pieces does this query name?": every word
# of the query in the name, the matching rule check_stock documents.
_MATCH_SQL = """
    SELECT "productId" AS product_id, name
      FROM pellier.product_catalog
     WHERE NULLIF(btrim("imgUrl"), '') IS NOT NULL AND {tokens}
     ORDER BY "productId"::int
"""
_STOCK_SQL = """
    SELECT warehouse_code, quantity, ship_window_min, ship_window_max
      FROM pellier.warehouse_inventory
     WHERE product_id = %s
     ORDER BY warehouse_code
"""
_LATEST_STOCK_TURN = f"""
SELECT args->>'turn_id' AS turn_id
  FROM pellier.tool_audit
 WHERE session_id LIKE %(session)s AND args->>'agent' = %(agent)s
   AND created_at >= {check.SINCE_SQL}
 ORDER BY audit_id DESC
 LIMIT 1
"""
_TURN_ROWS = """
SELECT audit_id, tool, args, result, created_at
  FROM pellier.tool_audit
 WHERE session_id LIKE %(session)s AND args->>'turn_id' = %(turn)s
 ORDER BY audit_id
"""
_LIVE_FUNCTION = """
SELECT encode(sha256(convert_to(prosrc, 'UTF8')), 'hex') AS source_sha,
       coalesce(obj_description(oid, 'pg_proc'), '') AS stamp
  FROM pg_proc
 WHERE oid = to_regprocedure('pellier.check_stock(text)')
"""
_MARCO_STOCK_CALLS = f"""
SELECT audit_id, args, result
  FROM pellier.tool_audit
 WHERE session_id LIKE %(session)s AND tool = 'check_stock' AND result IS NOT NULL
   AND created_at >= {check.SINCE_SQL}
 ORDER BY audit_id DESC
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


def _windows(rows: Sequence[Dict[str, Any]]) -> Dict[str, Tuple[Any, Any]]:
    """Each warehouse's recorded ship window in business days, as (min, max)."""
    return {str(row.get("warehouse_code")): (row.get("ship_window_min"), row.get("ship_window_max"))
            for row in rows}


def _windows_text(windows: Dict[str, Tuple[Any, Any]]) -> str:
    return ", ".join(f"{code} {low}-{high}" for code, (low, high) in sorted(windows.items()))


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
# Task 2A: the grant the answering Stock agent held, and what it was told
# ---------------------------------------------------------------------------

EXPECTED_2A = ("the Stock agent that answered Marco's latest stock question held check_stock "
               "alone and called only check_stock; the counts and ship windows it was given "
               "for every piece Pellier carries equal warehouse_inventory")
_NEXT_2A_GRANT = ("which tool must the Stock agent - definition block in agents/stock_agent.py "
                  "connect for a stock answer to come from a warehouse row, and what else may "
                  "it hold? Restart the backend so the running agent loads it, send Marco's "
                  f"requests again ({SEND}), then rerun this check.")


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def latest_stock_turn(conn: Any) -> List[Dict[str, Any]]:
    """Every audit row of Marco's latest turn the Stock agent answered, in call order."""
    pattern = MARCO_SESSION_PREFIX + "%"
    with conn.cursor() as cur:
        cur.execute(_LATEST_STOCK_TURN, {"session": pattern, "agent": STOCK_AGENT_NAME,
                                         "since": check.reset_point(2)})
        latest = cur.fetchone()
        if not latest or not latest.get("turn_id"):
            return []
        cur.execute(_TURN_ROWS, {"session": pattern, "turn": latest["turn_id"]})
        return [dict(row) for row in cur.fetchall()]


def recorded_grant(rows: Sequence[Dict[str, Any]]) -> Optional[List[str]]:
    """The store tools the answering agent held, as its first audit row recorded them."""
    grant = _as_dict(rows[0].get("args")).get("grant") if rows else None
    return [str(name) for name in grant] if isinstance(grant, list) else None


def _grant_verdict(grant: Optional[List[str]]) -> Tuple[Optional[str], str]:
    """(state, observed) for the recorded grant; ``(None, "")`` when it is check_stock alone."""
    if grant == ["check_stock"]:
        return None, ""
    if grant is None:
        return check.NOT_YET, "the turn's audit rows record no grant"
    text = ", ".join(grant) or "no store tools"
    if sorted(grant) == sorted(STARTER_GRANT):
        return check.NOT_YET, ("the Stock agent that answered still held the tools it ships with: "
                               + text + ", none of which reads warehouse_inventory")
    return check.CONTRADICTED, f"the Stock agent that answered was granted {text}"


def _call_problems(rows: Sequence[Dict[str, Any]]) -> List[str]:
    problems: List[str] = []
    others = sorted({row["tool"] for row in rows if row["tool"] != "check_stock"})
    if others:
        problems.append("the turn called " + ", ".join(others)
                        + ", which read the catalog, not warehouse_inventory")
    if not any(row["tool"] == "check_stock" for row in rows):
        problems.append("the turn never called check_stock")
    return problems


def _judge_stock_row(conn: Any, row: Dict[str, Any]) -> Tuple[Optional[bool], str]:
    """Whether one recorded check_stock answer about a carried piece matches its rows.

    Returns ``(None, line)`` for a query that names no piece or several: what the
    function says about those is Task 2B's to judge, not the grant's.
    """
    args, result = _as_dict(row.get("args")), _as_dict(row.get("result"))
    query = str(args.get("product_query") or "")
    catalog = catalog_answer(conn, query)
    told = _counts(result.get("warehouses") or [])
    said = describe_envelope(result)
    if len(catalog["matches"]) != 1:
        return None, (f"audit {row['audit_id']}: check_stock(\"{query}\") said {said}; the "
                      f"catalog matches {len(catalog['matches'])}, which Task 2B judges")
    product = catalog["matches"][0]
    real = _counts(catalog.get("stock") or [])
    told_windows = _windows(result.get("warehouses") or [])
    real_windows = _windows(catalog.get("stock") or [])
    named = str((result.get("product") or {}).get("productId") or "")
    ok = (result.get("status") == "success" and named == str(product["product_id"])
          and told == real and told_windows == real_windows)
    return ok, (f"audit {row['audit_id']}: check_stock(\"{query}\") gave "
                f"{_counts_text(told) if told else str(result.get('total_units')) + ' units'}; "
                f"warehouse_inventory for {product['product_id']}: {_counts_text(real)}; ship "
                f"windows in business days, given {_windows_text(told_windows) or 'none'}, "
                f"recorded {_windows_text(real_windows) or 'none'}")


def _count_problems(conn: Any, rows: Sequence[Dict[str, Any]], evidence: List[str]) -> List[str]:
    problems: List[str] = []
    for row in rows:
        if row["tool"] != "check_stock":
            continue
        ok, line = _judge_stock_row(conn, row)
        evidence.append(line)
        if ok is False:
            problems.append(f"audit {row['audit_id']} does not match the catalog")
    return problems


def stale_2a(created: Any, when: Optional[check.Timeline]) -> Optional[Tuple[str, str]]:
    """Why Marco's newest recorded Stock-agent turn cannot show the agent now running, and
    the next step; else None. A refused call leaves no row, so without this an older turn
    answered before the edit would stand in for the one just sent."""
    if when is None:
        return None
    edited, started = when.edited_at, when.started_at
    if edited and started and started < edited:
        return (f"pellier last started at {check.clock(started)}, before your last change to "
                f"stock_agent.py at {check.clock(edited)}, so the running agent is not your "
                "edit yet",
                f"restart the backend ({RESTART}), send Marco's Brooklyn count again "
                f"({SEND_2A}), then rerun this check.")
    if not isinstance(created, datetime) or edited is None:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if created < edited:
        return (f"Marco's newest recorded Stock-agent turn ran at {check.clock(created)}, "
                f"before your last change to stock_agent.py at {check.clock(edited)}, so the "
                "agent before your edit answered it",
                f"send Marco's Brooklyn count again ({SEND_2A}), then rerun this check.")
    return None


def judge_2a(conn: Any, when: Optional[check.Timeline] = None) -> check.Finding:
    """Marco's latest Stock-agent turn: its recorded grant, its calls and its counts."""
    title = "the Stock agent holds check_stock alone"
    rows = latest_stock_turn(conn)
    if not rows:
        return check.Finding("2A", title, check.NOT_YET, EXPECTED_2A,
                             "no tool call by Marco's Stock agent recorded yet",
                             ["pellier.tool_audit: no row with agent 'stock' in a persona-marco- "
                              "session"],
                             f"send Marco's requests with {SEND}, then rerun this check. "
                             "Already sent? As shipped, the Stock agent does not hold "
                             "check_stock, so a call to it did not run and left no row: "
                             "apply Task 2A (uv run scripts/lab_run.py solution --lab 2 --task 2A)."
                             + check.since_note(2, SEND))
    grant = recorded_grant(rows)
    evidence = [
        f"pellier.tool_audit turn {check.short(_as_dict(rows[0]['args']).get('turn_id'), 20)}: "
        + ", ".join(f"{row['tool']} (audit {row['audit_id']})" for row in rows),
        f"audit {rows[0]['audit_id']}: the Stock agent that answered held "
        + (", ".join(grant) if grant is not None else "no recorded grant"),
    ]
    late = stale_2a(rows[0].get("created_at"), when)
    if late is not None:
        return check.Finding("2A", title, check.NOT_YET, EXPECTED_2A, late[0], evidence, late[1])
    state, observed = _grant_verdict(grant)
    if state is not None:
        return check.Finding("2A", title, state, EXPECTED_2A, observed, evidence, _NEXT_2A_GRANT)
    problems = _call_problems(rows)
    counts = _count_problems(conn, rows, evidence)
    if problems:
        return check.Finding("2A", title, check.CONTRADICTED, EXPECTED_2A,
                             "; ".join(problems + counts), evidence, _NEXT_2A_GRANT)
    if counts:
        return check.Finding("2A", title, check.CONTRADICTED, EXPECTED_2A, "; ".join(counts),
                             evidence, "check_stock reported a count or ship window "
                             "warehouse_inventory does not hold for a piece Pellier carries: "
                             "rerun this check after "
                             f"sending Marco's requests again ({SEND}).")
    calls = sum(1 for row in rows if row["tool"] == "check_stock")
    observed = (f"held check_stock alone; {calls} check_stock call(s), every count and ship "
                "window for a piece Pellier carries matches")
    return check.Finding("2A", title, check.PROVED, EXPECTED_2A, observed, evidence)


# ---------------------------------------------------------------------------
# Task 2B: pellier.check_stock, as it is live
# ---------------------------------------------------------------------------


def function_body(text: str) -> Optional[str]:
    """The function source between the SQL file's ``$check_stock$`` quotes, or None."""
    parts = text.split(_DOLLAR)
    return parts[1] if len(parts) == 3 else None


def _sha(text: Optional[str]) -> Optional[str]:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None


def judge_function(conn: Any, worksheet: pathlib.Path = WORKSHEET,
                   starter: pathlib.Path = WORKSHEET_STARTER) -> Tuple[Optional[str], str, str]:
    """(state, observed, evidence) for the live function's source; state None when it is yours."""
    with conn.cursor() as cur:
        cur.execute(_LIVE_FUNCTION)
        live = cur.fetchone()
    if not live:
        return (check.CONTRADICTED, "pellier.check_stock is missing from the database",
                "pg_proc: no pellier.check_stock(text)")
    try:
        yours = _sha(function_body(worksheet.read_text(encoding="utf-8")))
        shipped = _sha(function_body(starter.read_text(encoding="utf-8")))
    except OSError:
        yours = shipped = None
    evidence = (f"pg_proc: pellier.check_stock source sha256 {check.short(live['source_sha'])}, "
                f"comment '{live['stamp'] or 'none'}'")
    if yours and live["source_sha"] == yours and live["stamp"] == STAMP_PREFIX + yours:
        return None, "the live function is the one your file committed", evidence
    if shipped and live["source_sha"] == shipped:
        return (check.NOT_YET, "the live function is the one Pellier shipped; your file has "
                               "not committed", evidence)
    return (check.NOT_YET, "the live function is not the one in your file: run it again",
            evidence)


def judge_2b(
    conn: Any, tool: Callable[..., str], inputs: Dict[str, Tuple[str, str]],
    worksheet: pathlib.Path = WORKSHEET,
) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Run ``tool`` once per case, judge each answer, then read the live function's source."""
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
    function_state, function_observed, function_evidence = judge_function(conn, worksheet)
    evidence.append(function_evidence)
    title = "check_stock keeps not carried, several and sold out apart"
    matched = sum(1 for row in rows if row[-1] == "matches")
    observed = f"{matched} of {len(CASES)} cases match" + (
        "; " + "; ".join(differs + bad_inputs) if differs or bad_inputs else "")
    if bad_inputs:
        return check.Finding("2B", title, check.NOT_YET, EXPECTED_2B, observed, evidence,
                             "choose a query that is what its case says: run the check again "
                             "with another --unknown, --ambiguous or --sold-out."), rows
    if differs:
        return check.Finding("2B", title, check.CONTRADICTED, EXPECTED_2B, observed,
                             evidence, _NEXT_2B), rows
    if function_state is not None:
        return check.Finding("2B", title, function_state, EXPECTED_2B,
                             f"{observed}; {function_observed}", evidence,
                             f"run your file so its function is the live one: {WORKSHEET_RUN}"
                             ), rows
    return check.Finding("2B", title, check.PROVED, EXPECTED_2B,
                         f"{observed}; {function_observed}", evidence), rows


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
# Task 2B, as recorded: what Marco's turns were told
# ---------------------------------------------------------------------------

EXPECTED_2B_RECORDED = (
    "Marco's latest check_stock call about a piece the catalog does not carry recorded "
    "not_found with no count, and his latest call of every other case recorded the "
    "catalog's answer")
_NEXT_2B_RECORDED = (
    "what should pellier.check_stock return for a piece Pellier does not carry? Commit your "
    f"file ({WORKSHEET_RUN}), send Marco's requests again ({SEND}), then rerun this.")


def recorded_cases(conn: Any) -> Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Marco's latest recorded check_stock call for each case, with the catalog's answer."""
    with conn.cursor() as cur:
        cur.execute(_MARCO_STOCK_CALLS, {"session": MARCO_SESSION_PREFIX + "%",
                                         "since": check.reset_point(2)})
        rows = [dict(row) for row in cur.fetchall()]
    found: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    for row in rows:
        catalog = catalog_answer(conn, str(_as_dict(row["args"]).get("product_query") or ""))
        case = classify(catalog)
        if case in CASES and case not in found:
            found[case] = (row, catalog)
        if len(found) == len(CASES):
            break
    return found


def judge_recorded_2b(conn: Any) -> check.Finding:
    """Task 2B from the rows Marco's turns left: the not-carried case decides."""
    title = "check_stock keeps not carried, several and sold out apart"
    found = recorded_cases(conn)
    if "unknown" not in found:
        return check.Finding("2B", title, check.NOT_YET, EXPECTED_2B_RECORDED,
                             "no check_stock call of Marco's asked about a piece Pellier does "
                             "not carry", ["pellier.tool_audit: no such row in a persona-marco- "
                                           "session"],
                             f"send Marco's requests with {SEND}, then rerun this."
                             + check.since_note(2, SEND))
    evidence: List[str] = []
    differs: List[str] = []
    for case in CASES:
        if case not in found:
            continue
        row, catalog = found[case]
        envelope = _as_dict(row["result"])
        query = str(_as_dict(row["args"]).get("product_query") or "")
        evidence.append(f"audit {row['audit_id']}: check_stock(\"{query}\") recorded "
                        f"{describe_envelope(envelope)}; the catalog: {describe_catalog(catalog)}")
        if not keeps_contract(case, envelope, catalog):
            differs.append(f"{_CASE_LABEL[case]}: \"{query}\" recorded "
                           f"{describe_envelope(envelope)}")
    unasked = [_CASE_LABEL[case] for case in CASES if case not in found]
    observed = f"{len(found) - len(differs)} of {len(found)} recorded cases match" + (
        f" (not asked yet: {', '.join(unasked)})" if unasked else "")
    if differs:
        return check.Finding("2B", title, check.CONTRADICTED, EXPECTED_2B_RECORDED,
                             observed + "; " + "; ".join(differs), evidence, _NEXT_2B_RECORDED)
    return check.Finding("2B", title, check.PROVED, EXPECTED_2B_RECORDED, observed, evidence)


def with_resend_hint(live: check.Finding, recorded: check.Finding) -> check.Finding:
    """The live 2B finding, with a line when Marco's recorded turns predate the commit.

    The check runs the live function, so it passes the moment the SQL file
    commits. Marco's chat and the evidence export read his recorded turns, so they
    show the change only once his requests are sent again.
    """
    if live.state != check.PROVED or recorded.state == check.PROVED:
        return live
    hint = ("Marco's recorded turns were answered before your function was live. Send his "
            f"requests again ({SEND}) to see the cape answered as not carried; the evidence "
            "export reads those turns.")
    return replace(live, evidence=[*live.evidence, hint])


# ---------------------------------------------------------------------------
# Running against the box's database
# ---------------------------------------------------------------------------


def live_tool(conn: Any, cfg: Dict[str, str]) -> Callable[..., str]:
    """``services.store_tools.check_stock``, the shaping both rails use, on this connection."""
    for key, value in cfg.items():
        os.environ.setdefault(key, value)
    sys.path.insert(0, str(BACKEND))
    from services import store_tools

    def run_sql(sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def tool(product_query: str) -> str:
        return json.dumps(store_tools.check_stock(run_sql, product_query=product_query),
                          default=str)

    return tool


def marco_cape_request(repo: pathlib.Path = REPO) -> str:
    """Marco's required request about the piece Pellier does not carry."""
    scenarios = json.loads((repo / "data" / "scenarios.json").read_text("utf-8"))
    return next(str(row["prompt"]) for row in scenarios
                if row.get("persona") == "marco" and row.get("journey_role") == "required"
                and row.get("journey_stage") == "exercise")


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
            if task == "2A":
                return judge_2a(conn, check.edit_timeline(STOCK_AGENT_FILE)), []
            finding, rows = judge_2b(conn, live_tool(conn, cfg), inputs)
            return with_resend_hint(finding, judge_recorded_2b(conn)), rows
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return check.Finding(task, title, check.UNCHECKED, "a reachable database",
                             "the check could not look",
                             [f"{type(exc).__name__}: {str(exc)[:160]}"],
                             "check that the database in pellier/backend/.env is reachable."), []


def cases_table(rows: Sequence[Sequence[str]]) -> str:
    """The 2B cases, narrow enough for a laptop terminal.

    Each case is one line (case, query, chosen by, verdict); what the catalog expects
    and what check_stock said go on the two lines beneath it.
    """
    head = check.table(("case", "query", "chosen by", "verdict"),
                       [(case, query, chosen_by, verdict)
                        for case, query, chosen_by, _expected, _observed, verdict in rows])
    lines = head.split("\n")
    indent = " " * (4 + max(len("case"), *(len(row[0]) for row in rows)))
    out = [lines[0]]
    for line, row in zip(lines[1:], rows):
        out += [line, f"{indent}expected  {row[3]}", f"{indent}observed  {row[4]}"]
    return "\n".join(out)


def marco_line(rows: Sequence[Sequence[str]], request: str) -> str:
    """Marco's sentence about the cape, and what check_stock answers for its piece."""
    unknown = next((row for row in rows if row[0] == _CASE_LABEL["unknown"]), None)
    if unknown is None:
        return ""
    return (f'Marco asks "{request}"\n'
            f'  check_stock("{unknown[1]}") answers {unknown[4]}; the catalog: {unknown[3]}')


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task", choices=("2A", "2B"), required=True)
    parser.add_argument("--unknown", help="A piece Pellier does not carry (Task 2B)")
    parser.add_argument("--ambiguous", help="A query that names several pieces (Task 2B)")
    parser.add_argument("--sold-out", dest="sold_out",
                        help="A carried piece with no units (Task 2B)")
    args = parser.parse_args(argv)
    finding, rows = run(args.task, _inputs(args))
    if args.task == "2A":
        print("Lab 2A: Marco's latest stock answer comes from check_stock alone")
    else:
        print("Lab 2B: pellier.check_stock answers from the catalog and warehouse_inventory")
        if rows:
            print(marco_line(rows, marco_cape_request()))
            print(cases_table(rows))
    print(check.render(finding))
    passed = finding.state == check.PROVED
    print(f"Lab {args.task} check {'passed' if passed else 'failed'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
