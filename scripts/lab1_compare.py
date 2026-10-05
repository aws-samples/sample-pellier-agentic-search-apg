#!/usr/bin/env python3
"""Lab 1B's check: every product Anna's latest search returned keeps her limits.

Anna asks for a gift under $100, in stock, with no candles. When the first
search is sparse, the fallback retries with fewer preferences; it must never
retry with fewer limits. This finds the newest retrieval receipt written in
Anna's session (``persona-anna-...``, the session choosing Anna on the home
page starts), reads every product it returned from the catalog, and checks the
three limits against each one.

The search must have needed the fallback: a receipt with no recorded
relaxation never ran Task 1B's code, so it proves nothing either way.

    python3 scripts/lab1_compare.py
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workshop_check as check  # noqa: E402  (sibling module)

ANNA_SESSION_PREFIX = "persona-anna-"
PRICE_LIMIT = 100
EXCLUDED = "candle"
EXPECTED = (
    f"the fallback ran and kept under ${PRICE_LIMIT}, in stock and no {EXCLUDED}s; every "
    "product it returned meets all three"
)
NEXT_STEP = (
    "open _with_relaxations in pellier/backend/services/search_plan.py: does the "
    "next attempt keep the budget, the stock rule and the exclusions? Restart, "
    "send Anna's request again, then rerun this check."
)

_LATEST_RECEIPT = """
SELECT receipt_id, session_id, created_at, query_preview, citation_ids, relaxations,
       hard_constraints, exclusions
  FROM pellier.retrieval_receipts
 WHERE session_id LIKE %s
 ORDER BY receipt_id DESC
 LIMIT 1
"""

_PRODUCTS = """
SELECT "productId" AS product_id, name, price, quantity, tags, materials
  FROM pellier.product_catalog
 WHERE "productId" = ANY(%s)
"""


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, str):
        value = json.loads(value or "[]")
    return list(value or [])


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value or "{}")
    return dict(value or {})


def product_breaks(product: Dict[str, Any]) -> List[str]:
    """The limits one catalog row breaks, in the shopper's words."""
    broken = []
    if float(product["price"]) > PRICE_LIMIT:
        broken.append(f"${float(product['price']):.2f}")
    if int(product["quantity"] or 0) <= 0:
        broken.append("sold out")
    listed = _as_list(product.get("tags")) + _as_list(product.get("materials"))
    labels = {str(value).lower() for value in listed}
    if EXCLUDED in labels:
        broken.append("a candle")
    return broken


def _kept_limits(receipt: Dict[str, Any]) -> str:
    hard = _as_dict(receipt.get("hard_constraints"))
    kept = []
    if hard.get("price_max_usd") is not None:
        kept.append(f"under ${float(hard['price_max_usd']):g}")
    if hard.get("in_stock_only"):
        kept.append("in stock")
    exclusions = _as_list(receipt.get("exclusions"))
    if exclusions:
        kept.append("no " + ", ".join(str(value) for value in exclusions))
    return ", ".join(kept) or "none"


def _dropped_limits(receipt: Dict[str, Any]) -> List[str]:
    """Anna's limits the search that answered no longer applied."""
    hard = _as_dict(receipt.get("hard_constraints"))
    price = hard.get("price_max_usd")
    dropped = []
    if price is None or float(price) > PRICE_LIMIT:
        dropped.append(f"under ${PRICE_LIMIT}")
    if not hard.get("in_stock_only"):
        dropped.append("in stock")
    if EXCLUDED not in {str(value).lower() for value in _as_list(receipt.get("exclusions"))}:
        dropped.append(f"no {EXCLUDED}s")
    return dropped


def _relaxations(receipt: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [step for step in _as_list(receipt.get("relaxations")) if isinstance(step, dict)]


def _evidence(receipt: Dict[str, Any]) -> List[str]:
    steps = _relaxations(receipt)
    retried = "; ".join(
        f"{step.get('step')} (dropped {', '.join(step.get('dropped') or []) or 'nothing'})"
        for step in steps
    ) or "no relaxation recorded"
    created = receipt.get("created_at")
    when = created.strftime("%H:%M:%S UTC") if hasattr(created, "strftime") else str(created)
    return [
        f"pellier.retrieval_receipts receipt {receipt['receipt_id']}, session "
        f"{check.short(receipt.get('session_id'), 22)}, {when}",
        f"query: \"{receipt.get('query_preview') or ''}\"",
        f"the search that answered recorded: {retried}; limits it kept: {_kept_limits(receipt)}",
    ]


def evaluate(conn: Any) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Judge Anna's newest search receipt. Returns the finding and one row per product."""
    title = "Anna's limits survive the fallback"
    with conn.cursor() as cur:
        cur.execute(_LATEST_RECEIPT, (ANNA_SESSION_PREFIX + "%",))
        receipt = cur.fetchone()
        if not receipt:
            return check.Finding(
                "1B", title, check.NOT_YET, EXPECTED,
                "no search receipt in a session of Anna's yet",
                ["pellier.retrieval_receipts has no row whose session starts persona-anna-"],
                "choose Anna on the home page, send her gift request in Ask Pellier, "
                "then rerun this check.",
            ), []
        ids = [str(value) for value in _as_list(receipt.get("citation_ids"))]
        cur.execute(_PRODUCTS, (ids,))
        catalog = {str(row["product_id"]): row for row in cur.fetchall()}
    rows, broken_lines = _rows(ids, catalog)
    return _judge(title, receipt, ids, rows, broken_lines), rows


def _rows(
    ids: Sequence[str], catalog: Dict[str, Dict[str, Any]]
) -> Tuple[List[Sequence[Any]], List[str]]:
    rows: List[Sequence[Any]] = []
    broken_lines: List[str] = []
    for product_id in ids:
        product = catalog.get(product_id)
        if product is None:
            rows.append((product_id, "(not in the catalog)", "", "", "", "missing"))
            broken_lines.append(f"{product_id} is not in the catalog")
            continue
        broken = product_breaks(product)
        candle = "yes" if "a candle" in broken else "no"
        verdict = ("breaks: " + ", ".join(broken)) if broken else "ok"
        rows.append((
            product_id, str(product["name"])[:30], f"${float(product['price']):.2f}",
            int(product["quantity"] or 0), candle, verdict,
        ))
        if broken:
            broken_lines.append(f"{product_id} {product['name']} is " + " and ".join(broken))
    return rows, broken_lines


def _judge(
    title: str, receipt: Dict[str, Any], ids: Sequence[str],
    rows: Sequence[Sequence[Any]], broken_lines: Sequence[str],
) -> check.Finding:
    evidence = _evidence(receipt)
    if not ids:
        return check.Finding("1B", title, check.NOT_YET, EXPECTED,
                             "Anna's latest search returned no products", evidence,
                             "send Anna's gift request again, then rerun this check.")
    dropped = _dropped_limits(receipt)
    if broken_lines or dropped:
        observed = f"{len(ids) - len(broken_lines)} of {len(ids)} keep all three limits"
        if broken_lines:
            observed += "; " + "; ".join(broken_lines)
        if dropped:
            observed += "; the search that answered dropped " + ", ".join(dropped)
        return check.Finding("1B", title, check.CONTRADICTED, EXPECTED, observed, evidence,
                             NEXT_STEP)
    if not _relaxations(receipt):
        return check.Finding(
            "1B", title, check.NOT_YET, EXPECTED,
            f"all {len(ids)} keep the limits, but the first search was enough, so the "
            "fallback never ran",
            evidence, "send the request from the guide, which the first search cannot fill, "
                      "then rerun this check.",
        )
    return check.Finding("1B", title, check.PROVED, EXPECTED,
                         f"all {len(ids)} keep all three limits after the fallback", evidence)


def run(env_path: pathlib.Path = check.DEFAULT_ENV) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Connect with the backend's settings and evaluate; never raises."""
    title = "Anna's limits survive the fallback"
    cfg = check.db_config(env_path)
    if cfg is None:
        return check.Finding("1B", title, check.UNCHECKED, EXPECTED, "the check could not look",
                             [check.missing_settings_reason(env_path)]), []
    try:
        with check.connect(cfg) as conn:
            return evaluate(conn)
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return check.Finding("1B", title, check.UNCHECKED, EXPECTED, "the check could not look",
                             [f"{type(exc).__name__}: {str(exc)[:160]}"],
                             "check that the database in pellier/backend/.env is reachable."), []


def main(argv: Optional[Sequence[str]] = None) -> int:
    del argv
    finding, rows = run()
    print("Lab 1B: every product in Anna's latest search keeps her limits")
    if rows:
        print(check.table(("product", "name", "price", "in stock", "candle", "verdict"), rows))
    print(check.render(finding))
    passed = finding.state == check.PROVED
    print("Lab 1B check passed" if passed else "Lab 1B check failed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
