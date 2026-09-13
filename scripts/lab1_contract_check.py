#!/usr/bin/env python3
"""Lab 1's supplied two-case check: unknown is not zero, and zero is not unknown.

Runs the participant's own ``check_inventory`` tool body twice, through the same
``@tool`` wrapper the Inventory Agent calls, and prints the two result envelopes
side by side:

    a piece the catalog does not carry   -> status "not_found", no count
    a piece it carries with no units     -> status "success", total_units 0

Exit 0 when both hold, 3 when the body turns one answer into the other. Nothing
here is inferred from the model's prose; the tool's own JSON is the evidence.

Run from the repository root on a workshop box (the backend .env supplies DB_*):

    python3 scripts/lab1_contract_check.py --json /tmp/pellier-evidence/lab-1-contract.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
from typing import Any, Dict, List, Tuple
from urllib.parse import quote_plus

REPO = pathlib.Path(__file__).resolve().parents[1]
BACKEND = REPO / "pellier" / "backend"

UNKNOWN_PIECE = "Hadley cashmere scarf"
SOLD_OUT_PIECE = "Quilted Silk Vest"
QUESTION = "What can the agent legitimately conclude in each case?"

CASES: Tuple[Tuple[str, str, str], ...] = (
    ("unknown", UNKNOWN_PIECE, "not_found"),
    ("sold_out", SOLD_OUT_PIECE, "success"),
)


def judge(envelopes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Grade the two envelopes against the contract, and say what each allows.

    ``envelopes`` maps the case name to the tool's parsed JSON. Returns the
    per-case verdicts and an overall ``passed``.
    """
    verdicts: List[Dict[str, Any]] = []
    unknown = envelopes.get("unknown") or {}
    sold_out = envelopes.get("sold_out") or {}

    unknown_ok = unknown.get("status") == "not_found" and "total_units" not in unknown
    verdicts.append({
        "case": "unknown",
        "query": UNKNOWN_PIECE,
        "status": unknown.get("status"),
        "total_units": unknown.get("total_units"),
        "passed": unknown_ok,
        "conclusion": (
            "the catalog does not carry this piece; the agent may say so and nothing "
            "about stock" if unknown_ok
            else "the tool reported a count for a piece the catalog does not carry"
        ),
    })
    total = sold_out.get("total_units")
    warehouses = sold_out.get("warehouses")
    sold_out_ok = (
        sold_out.get("status") == "success"
        and isinstance(total, (int, float)) and not isinstance(total, bool) and total == 0
        and isinstance(warehouses, list) and bool(warehouses)
        and all(
            isinstance(row, dict)
            and isinstance(row.get("quantity"), (int, float))
            and not isinstance(row["quantity"], bool)
            and row["quantity"] == 0
            for row in warehouses
        )
    )
    verdicts.append({
        "case": "sold_out",
        "query": SOLD_OUT_PIECE,
        "status": sold_out.get("status"),
        "total_units": total,
        "passed": sold_out_ok,
        "conclusion": (
            "the catalog carries this piece and every warehouse holds zero; the agent "
            "may say it is sold out" if sold_out_ok
            else "the tool did not report a known piece with zero units"
        ),
    })
    return {"question": QUESTION, "cases": verdicts, "passed": all(v["passed"] for v in verdicts)}


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


async def _run_cases() -> Dict[str, Dict[str, Any]]:
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
        envelopes: Dict[str, Dict[str, Any]] = {}
        for case, query, _expected in CASES:
            raw = await asyncio.to_thread(agent_tools.check_inventory, product_query=query)
            try:
                envelopes[case] = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                envelopes[case] = {"status": "unparseable", "raw": str(raw)[:200]}
        return envelopes
    finally:
        await service.disconnect()


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", help="Also write the report to this path")
    args = parser.parse_args(argv)
    envelopes = asyncio.run(_run_cases())
    report = judge(envelopes)
    report["envelopes"] = envelopes
    print(f"{'case':<10} {'query':<24} {'status':<12} {'total_units':<12} verdict")
    for row in report["cases"]:
        print(
            f"{row['case']:<10} {row['query']:<24} {str(row['status']):<12} "
            f"{str(row['total_units']):<12} {'PASS' if row['passed'] else 'FAIL'}"
        )
        print(f"           {row['conclusion']}")
    print()
    print(QUESTION)
    print("PASSED" if report["passed"] else "FAILED: the tool body turns one answer into the other")
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(report, indent=2, default=str))
    return 0 if report["passed"] else 3


if __name__ == "__main__":
    sys.exit(main())
