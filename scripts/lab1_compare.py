#!/usr/bin/env python3
"""Lab 1B's check: Anna's latest search kept every limit she asked for.

When the first search is sparse, the fallback retries with fewer preferences;
it must never retry with fewer limits. This finds the newest retrieval receipt
written in Anna's session (``persona-anna-...``, the session choosing Anna on
the home page starts) and compares two things it records: the limits the
shopper asked for (``retrieval_config.requested``, the plan built from her
words before any fallback) and the limits the search that answered kept. It
then reads every product that search returned from the catalog and checks each
requested limit against it.

The search must have needed the fallback: a receipt with no recorded
relaxation never ran Task 1B's code, so it proves nothing either way. A
request that stated no limit proves nothing either, so the check asks for the
guide's request.

    python3 scripts/lab1_compare.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workshop_check as check  # noqa: E402  (sibling module)

ANNA_SESSION_PREFIX = "persona-anna-"
# The guide's request, the one Anna's first suggestion sends: three limits the
# first search cannot fill, so the fallback has to run.
ANNA_REQUEST = ("A housewarming gift for a friend who loves slow mornings. "
                "In stock, under $100, and no candles.")
TITLE = "Anna's limits survive the fallback"
EXPECTED = (
    "the fallback ran and the search that answered kept every limit the shopper asked "
    "for; every product it returned meets them"
)
NEXT_STEP = (
    "open _with_relaxations in pellier/backend/services/search_plan.py: does the "
    "next attempt keep the budget, the stock rule and the exclusions? Restart, "
    "send Anna's request again, then rerun this check."
)
NEXT_REQUEST = (f"choose Anna on the home page and send the guide's request (\"{ANNA_REQUEST}\"), "
                "then rerun this check.")

_LATEST_RECEIPT = """
SELECT receipt_id, session_id, created_at, query_preview, citation_ids, relaxations,
       hard_constraints, exclusions, retrieval_config
  FROM pellier.retrieval_receipts
 WHERE session_id LIKE %s
 ORDER BY receipt_id DESC
 LIMIT 1
"""

_PRODUCTS = """
SELECT "productId" AS product_id, name, price, quantity, category, tags, materials
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


def _plural(word: str) -> str:
    if word.endswith("s"):
        return word
    return word + ("es" if re.search(r"(ch|sh|x|z)$", word) else "s")


def limits_of(hard_constraints: Any, exclusions: Any) -> Dict[str, Any]:
    """One plan's hard limits: budget, stock, exclusions and departments."""
    hard = _as_dict(hard_constraints)
    price = hard.get("price_max_usd")
    return {
        "price": float(price) if price is not None else None,
        "in_stock": bool(hard.get("in_stock_only")),
        "exclusions": sorted({str(value).lower() for value in _as_list(exclusions) if value}),
        "categories": sorted({str(value).lower() for value in
                              _as_list(hard.get("categories")) if value}),
    }


def requested_limits(receipt: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """What the shopper asked for, or None on a receipt that predates recording it."""
    requested = _as_dict(receipt.get("retrieval_config")).get("requested")
    if not isinstance(requested, dict):
        return None
    return limits_of(requested.get("hard_constraints"), requested.get("exclusions"))


def kept_limits(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """What the search that answered applied, after any fallback."""
    return limits_of(receipt.get("hard_constraints"), receipt.get("exclusions"))


def phrases(limits: Dict[str, Any]) -> List[str]:
    """The limits in the shopper's words: "under $100", "in stock", "no candles"."""
    said = []
    if limits["price"] is not None:
        said.append(f"under ${limits['price']:g}")
    if limits["in_stock"]:
        said.append("in stock")
    said.extend(f"no {_plural(value)}" for value in limits["exclusions"])
    if limits["categories"]:
        said.append(" or ".join(limits["categories"]) + " only")
    return said


def dropped(requested: Dict[str, Any], kept: Dict[str, Any]) -> List[str]:
    """Each requested limit the search that answered no longer applied."""
    lost = []
    if requested["price"] is not None and (kept["price"] is None
                                           or kept["price"] > requested["price"]):
        lost.append(f"under ${requested['price']:g}")
    if requested["in_stock"] and not kept["in_stock"]:
        lost.append("in stock")
    lost.extend(f"no {_plural(value)}" for value in requested["exclusions"]
                if value not in kept["exclusions"])
    narrowed = set(kept["categories"]) <= set(requested["categories"])
    if requested["categories"] and not (kept["categories"] and narrowed):
        lost.append(" or ".join(requested["categories"]) + " only")
    return lost


def product_breaks(product: Dict[str, Any], limits: Dict[str, Any]) -> List[str]:
    """The requested limits one catalog row breaks, in the shopper's words."""
    broken = []
    if limits["price"] is not None and float(product["price"]) > limits["price"]:
        broken.append(f"${float(product['price']):.2f}")
    if limits["in_stock"] and int(product["quantity"] or 0) <= 0:
        broken.append("sold out")
    labels = {str(value).lower() for value in
              _as_list(product.get("tags")) + _as_list(product.get("materials"))}
    broken.extend(f"excluded {value}" for value in limits["exclusions"] if value in labels)
    category = str(product.get("category") or "").lower()
    if limits["categories"] and category not in limits["categories"]:
        broken.append(f"in {product.get('category') or 'no department'}")
    return broken


def _relaxations(receipt: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [step for step in _as_list(receipt.get("relaxations")) if isinstance(step, dict)]


def _evidence(receipt: Dict[str, Any], requested: Optional[Dict[str, Any]]) -> List[str]:
    steps = _relaxations(receipt)
    retried = "; ".join(
        f"{step.get('step')} (dropped {', '.join(step.get('dropped') or []) or 'nothing'})"
        for step in steps
    ) or "no relaxation recorded"
    created = receipt.get("created_at")
    when = created.strftime("%H:%M:%S UTC") if hasattr(created, "strftime") else str(created)
    asked = (", ".join(phrases(requested)) or "no limit") if requested else "not recorded"
    return [
        f"pellier.retrieval_receipts receipt {receipt['receipt_id']}, session "
        f"{check.short(receipt.get('session_id'), 22)}, {when}",
        f"query: \"{receipt.get('query_preview') or ''}\"",
        f"the shopper asked: {asked}",
        f"the search that answered recorded: {retried}; limits it kept: "
        f"{', '.join(phrases(kept_limits(receipt))) or 'none'}",
    ]


def evaluate(conn: Any) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Judge Anna's newest search receipt. Returns the finding and one row per product."""
    with conn.cursor() as cur:
        cur.execute(_LATEST_RECEIPT, (ANNA_SESSION_PREFIX + "%",))
        receipt = cur.fetchone()
        if not receipt:
            return check.Finding(
                "1B", TITLE, check.NOT_YET, EXPECTED,
                "no search receipt in a session of Anna's yet",
                ["pellier.retrieval_receipts has no row whose session starts persona-anna-"],
                NEXT_REQUEST,
            ), []
        ids = [str(value) for value in _as_list(receipt.get("citation_ids"))]
        cur.execute(_PRODUCTS, (ids,))
        catalog = {str(row["product_id"]): row for row in cur.fetchall()}
    requested = requested_limits(receipt)
    rows, broken_lines = _rows(ids, catalog, requested or limits_of({}, []))
    return _judge(receipt, requested, ids, broken_lines), rows


def _rows(
    ids: Sequence[str], catalog: Dict[str, Dict[str, Any]], limits: Dict[str, Any],
) -> Tuple[List[Sequence[Any]], List[str]]:
    rows: List[Sequence[Any]] = []
    broken_lines: List[str] = []
    for product_id in ids:
        product = catalog.get(product_id)
        if product is None:
            rows.append((product_id, "(not in the catalog)", "", "", "missing"))
            broken_lines.append(f"{product_id} is not in the catalog")
            continue
        broken = product_breaks(product, limits)
        verdict = ("breaks: " + ", ".join(broken)) if broken else "ok"
        rows.append((
            product_id, str(product["name"])[:30], f"${float(product['price']):.2f}",
            int(product["quantity"] or 0), verdict,
        ))
        if broken:
            broken_lines.append(f"{product_id} {product['name']} is " + " and ".join(broken))
    return rows, broken_lines


def _judge(
    receipt: Dict[str, Any], requested: Optional[Dict[str, Any]], ids: Sequence[str],
    broken_lines: Sequence[str],
) -> check.Finding:
    evidence = _evidence(receipt, requested)
    if not ids:
        return check.Finding("1B", TITLE, check.NOT_YET, EXPECTED,
                             "Anna's latest search returned no products", evidence, NEXT_REQUEST)
    if requested is None or not phrases(requested):
        observed = ("the receipt does not record what the shopper asked" if requested is None
                    else "the request stated no limit, so there was nothing to keep")
        return check.Finding("1B", TITLE, check.NOT_YET, EXPECTED, observed, evidence,
                             NEXT_REQUEST)
    if not _relaxations(receipt):
        observed = (f"the first search answered, so the fallback never ran; {len(ids)} "
                    f"returned, {len(broken_lines)} break a limit")
        return check.Finding("1B", TITLE, check.NOT_YET, EXPECTED, observed, evidence,
                             NEXT_REQUEST)
    lost = dropped(requested, kept_limits(receipt))
    if broken_lines or lost:
        observed = f"{len(ids) - len(broken_lines)} of {len(ids)} keep every limit asked for"
        if broken_lines:
            observed += "; " + "; ".join(broken_lines)
        if lost:
            observed += "; the search that answered dropped " + ", ".join(lost)
        return check.Finding("1B", TITLE, check.CONTRADICTED, EXPECTED, observed, evidence,
                             NEXT_STEP)
    return check.Finding("1B", TITLE, check.PROVED, EXPECTED,
                         f"all {len(ids)} keep {', '.join(phrases(requested))} after the "
                         "fallback", evidence)


def run(env_path: pathlib.Path = check.DEFAULT_ENV) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Connect with the backend's settings and evaluate; never raises."""
    cfg = check.db_config(env_path)
    if cfg is None:
        return check.Finding("1B", TITLE, check.UNCHECKED, EXPECTED, "the check could not look",
                             [check.missing_settings_reason(env_path)]), []
    try:
        with check.connect(cfg) as conn:
            return evaluate(conn)
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return check.Finding("1B", TITLE, check.UNCHECKED, EXPECTED, "the check could not look",
                             [f"{type(exc).__name__}: {str(exc)[:160]}"],
                             "check that the database in pellier/backend/.env is reachable."), []


def main(argv: Optional[Sequence[str]] = None) -> int:
    del argv
    finding, rows = run()
    print("Lab 1B: every product in Anna's latest search keeps the limits she asked for")
    if rows:
        print(check.table(("product", "name", "price", "in stock", "verdict"), rows))
    print(check.render(finding))
    passed = finding.state == check.PROVED
    print("Lab 1B check passed" if passed else "Lab 1B check failed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
