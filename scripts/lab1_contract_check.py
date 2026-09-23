#!/usr/bin/env python3
"""Lab 1's contract check: the participant chooses the test inputs, the catalog judges them.

Three kinds of answer must stay distinct, because the agent reports whatever the
tool returns:

    a piece the catalog does not carry   -> status "not_found", no count
    a query that matches several pieces  -> status "ambiguous", candidates, no count
    a piece it carries with no units     -> status "success", total_units 0

The participant supplies one query for each case. Before the tool runs, this script
classifies every query from its own catalog and warehouse read. A query that does not
belong to the case it was offered for fails as a test input, so a weak test cannot
pass. Then the participant's own ``check_inventory`` body runs through the same
``@tool`` wrapper the Inventory Agent calls, and its envelope is judged against that
classification. A catalog read failure is UNCHECKED and fails the run; it is never
read as "not found".

Omitted inputs fall back to recovery defaults, and the report records which cases
used them.

    python3 scripts/lab1_contract_check.py \
      --unknown "..." --ambiguous "..." --sold-out "..." \
      --json /tmp/pellier-evidence/lab-1-contract.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

REPO = pathlib.Path(__file__).resolve().parents[1]
BACKEND = REPO / "pellier" / "backend"

CASES = ("unknown", "ambiguous", "sold_out")
DEFAULT_INPUTS = {
    "unknown": "Hadley cashmere scarf",
    "ambiguous": "Linen shirt",
    "sold_out": "Quilted Silk Vest",
}
QUESTION = "What can the agent legitimately conclude in each case?"

# The catalog's own answer to "which pieces does this query name?", read without
# the participant's tool. Every whitespace token must appear in the name, which is
# the matching contract the business service documents.
_MATCH_SQL = """
    SELECT "productId" AS product_id, name
      FROM pellier.product_catalog
     WHERE NOT (tags ? 'archive') AND {tokens}
     ORDER BY "productId"
"""
_STOCK_SQL = """
    SELECT warehouse_id, quantity
      FROM pellier.warehouse_inventory
     WHERE product_id = %s
     ORDER BY warehouse_id
"""


def classify(matches: List[Dict[str, Any]], stock: List[Dict[str, Any]]) -> str:
    """Which case a query belongs to, from catalog rows alone."""
    if not matches:
        return "unknown"
    if len(matches) > 1:
        return "ambiguous"
    if stock and all(int(row.get("quantity") or 0) == 0 for row in stock):
        return "sold_out"
    return "in_stock" if stock else "no_warehouse_rows"


def _is_count(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _tool_keeps_contract(case: str, envelope: Dict[str, Any], catalog: Dict[str, Any]) -> bool:
    ids = {str(row["product_id"]) for row in catalog.get("matches") or []}
    if case == "unknown":
        return (envelope.get("status") == "not_found"
                and "total_units" not in envelope and "warehouses" not in envelope)
    if case == "ambiguous":
        candidates = envelope.get("candidates")
        return (envelope.get("status") == "ambiguous"
                and "total_units" not in envelope and "warehouses" not in envelope
                and isinstance(candidates, list) and len(candidates) >= 2
                and all(isinstance(c, dict) and str(c.get("productId")) in ids
                        for c in candidates))
    warehouses = envelope.get("warehouses")
    return (envelope.get("status") == "success"
            and str((envelope.get("product") or {}).get("productId")) in ids
            and _is_count(envelope.get("total_units")) and envelope["total_units"] == 0
            and isinstance(warehouses, list) and bool(warehouses)
            and all(isinstance(row, dict) and _is_count(row.get("quantity"))
                    and row["quantity"] == 0 for row in warehouses))


_CONCLUSIONS = {
    "unknown": ("the catalog does not carry this piece; the agent may say so and "
                "nothing about stock"),
    "ambiguous": ("several pieces match; the agent must ask which one before "
                  "reporting any stock"),
    "sold_out": ("the catalog carries this piece and every warehouse holds zero; "
                 "the agent may say it is sold out"),
}


def judge_case(case: str, query: str, chosen_by: str,
               catalog: Dict[str, Any], envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Grade the test input against the catalog, then the tool against the input."""
    if catalog.get("error"):
        return {"case": case, "query": query, "chosenBy": chosen_by,
                "catalogClass": "UNCHECKED", "status": envelope.get("status"),
                "inputPassed": False, "toolPassed": False, "passed": False,
                "conclusion": f"catalog read failed ({catalog['error']}); nothing was established"}
    catalog_class = classify(catalog.get("matches") or [], catalog.get("stock") or [])
    input_ok = catalog_class == case
    tool_ok = input_ok and _tool_keeps_contract(case, envelope, catalog)
    if not input_ok:
        conclusion = (f"this query is {catalog_class.replace('_', ' ')} in the catalog, "
                      f"so it cannot test the {case.replace('_', ' ')} case")
    elif not tool_ok:
        conclusion = "the tool changed the business answer for this case"
    else:
        conclusion = _CONCLUSIONS[case]
    return {"case": case, "query": query, "chosenBy": chosen_by,
            "catalogClass": catalog_class,
            "catalogMatches": [row["name"] for row in catalog.get("matches") or []][:5],
            "status": envelope.get("status"), "total_units": envelope.get("total_units"),
            "inputPassed": input_ok, "toolPassed": tool_ok, "passed": input_ok and tool_ok,
            "conclusion": conclusion}


def judge(verdicts: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"question": QUESTION, "cases": verdicts,
            "passed": len(verdicts) == len(CASES) and all(v["passed"] for v in verdicts)}


def _load_env() -> Dict[str, str]:
    values: Dict[str, str] = {}
    for path in (REPO / ".env", BACKEND / ".env"):
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip("'\""))
    return values


async def _catalog(service: Any, query: str) -> Dict[str, Any]:
    tokens = [token.lower() for token in query.split() if token]
    if not tokens:
        return {"matches": [], "stock": []}
    try:
        clause = " AND ".join(["strpos(lower(name), %s) > 0"] * len(tokens))
        matches = await service.fetch_all(_MATCH_SQL.format(tokens=clause), *tokens)
        stock = (await service.fetch_all(_STOCK_SQL, str(matches[0]["product_id"]))
                 if len(matches) == 1 else [])
    except Exception as exc:  # noqa: BLE001 - reported as UNCHECKED, never as absence
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"matches": [dict(row) for row in matches], "stock": [dict(row) for row in stock]}


async def _run(inputs: Dict[str, tuple[str, str]]) -> List[Dict[str, Any]]:
    sys.path.insert(0, str(BACKEND))
    for key, value in _load_env().items():
        os.environ.setdefault(key, value)
    from config import settings
    from services import agent_tools
    from services.database import DatabaseService

    cfg = {**_load_env(), **{k: v for k, v in os.environ.items() if k.startswith("DB_")}}
    missing = [k for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not cfg.get(k)]
    if missing:
        raise SystemExit(f"missing database settings: {', '.join(missing)}")
    settings.DATABASE_URL = (
        f"postgresql://{cfg['DB_USER']}:{quote_plus(cfg['DB_PASSWORD'])}"
        f"@{cfg['DB_HOST']}:{cfg.get('DB_PORT', '5432')}/{cfg['DB_NAME']}"
    )
    service = DatabaseService()
    await service.connect()
    try:
        # The tool body dispatches its coroutine onto the main loop from a worker
        # thread, exactly as it does under the Strands agent.
        agent_tools.set_db_service(service)
        agent_tools.set_main_loop(asyncio.get_running_loop())
        verdicts = []
        for case in CASES:
            query, chosen_by = inputs[case]
            catalog = await _catalog(service, query)
            raw = await asyncio.to_thread(agent_tools.check_inventory, product_query=query)
            try:
                envelope = json.loads(raw)
            except (TypeError, ValueError):
                envelope = {"status": "unparseable", "raw": str(raw)[:200]}
            verdict = judge_case(case, query, chosen_by, catalog, envelope)
            verdict["envelope"] = envelope
            verdicts.append(verdict)
        return verdicts
    finally:
        await service.disconnect()


def _inputs(args: argparse.Namespace) -> Dict[str, tuple[str, str]]:
    chosen = {"unknown": args.unknown, "ambiguous": args.ambiguous, "sold_out": args.sold_out}
    return {case: ((value.strip(), "participant") if value and value.strip()
                   else (DEFAULT_INPUTS[case], "recovery-default"))
            for case, value in chosen.items()}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--unknown", help="A piece the catalog does not carry")
    parser.add_argument("--ambiguous", help="A query that names several pieces")
    parser.add_argument("--sold-out", dest="sold_out", help="A carried piece with no units")
    parser.add_argument("--json", help="Also write the report to this path")
    args = parser.parse_args(argv)
    report = judge(asyncio.run(_run(_inputs(args))))
    print(f"{'case':<10} {'query':<24} {'chosen by':<17} {'catalog':<11} "
          f"{'tool status':<12} verdict")
    for row in report["cases"]:
        print(f"{row['case']:<10} {row['query'][:24]:<24} {row['chosenBy']:<17} "
              f"{row['catalogClass']:<11} {str(row['status']):<12} "
              f"{'PASS' if row['passed'] else 'FAIL'}")
        print(f"           {row['conclusion']}")
    print()
    print(QUESTION)
    print("PASSED" if report["passed"] else "FAILED: a test input or the tool broke the contract")
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(report, indent=2, default=str))
    return 0 if report["passed"] else 3


if __name__ == "__main__":
    sys.exit(main())
