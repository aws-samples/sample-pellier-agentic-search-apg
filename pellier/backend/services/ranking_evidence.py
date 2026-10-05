"""How a search ranked: the Builder view's "how scores stack up per arm".

The payload is taken from the real pipeline run. ``rrf_merge`` keeps each
row's full-text rank, vector rank and RRF score; the rerank stage adds its
score; the final order is what the shopper saw. Nothing is re-run.

The filter counts need one aggregate statement, because the two branch
queries carry ``LIMIT`` clauses and cannot say how many rows a predicate
removed. That statement is compiled from the plan's own predicates, so its
counts describe exactly the SQL the search ran. It runs only for the
in-process evidence sink, never for the model and never on the Lambda.

On the managed rail the detail is read back from the retrieval receipt the
Lambda wrote for the turn, when that receipt is readable. The receipt holds
ranks and scores but not vector similarity or filter counts, and the payload
says so.

The same run also fills the storefront's results grid. ``results_payload``
carries the tool's own result order (at most ``RESULT_IDS_MAX`` product ids),
the limits it applied as the page's tags, and the filter counts, so the page
shows the agent's result and never runs a second search of its own.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from services.catalog_vocabulary import KNOWN_MATERIALS

TOP_ROWS = 8
# The most product ids a results payload carries: the size of the fused pool.
RESULT_IDS_MAX = 30
RRF_K_DEFAULT = 60

# What "Kept" counts: the hard limits alone. The strict first pass also asks
# for the soft preferences the shopper implied, so the pool can be smaller.
KEPT_NOTE = (
    "Kept counts the hard limits only; the first pass also asks for the "
    "preferences the shopper implied, so the fused pool can be smaller"
)

# The brief's order for "how many each limit removed".
_REASON_ORDER = ("budget", "stock", "exclusions", "department")

Run = Callable[[str, Sequence[Any]], List[Dict[str, Any]]]


# One excluded value, so each value's removals are counted on their own.
_EXCLUSION_CLAUSE = "NOT (tags ?| %s OR materials ?| %s)"
EXCLUSION_REASON = "exclusions"

# A count clause: its reason, its SQL, its parameters.
CountClause = Tuple[str, str, List[Any]]


def _reason_for(clause: str) -> str:
    if clause.startswith("price"):
        return "budget"
    if clause.startswith("quantity"):
        return "stock"
    if clause.startswith("NOT (tags"):
        return EXCLUSION_REASON
    if clause.startswith("category"):
        return "department"
    return "other"


def _kind(reason: str) -> str:
    """``exclusions:candle`` is an exclusion; every other reason is its own kind."""
    return reason.split(":", 1)[0]


def _count_clauses(plan: Any, extra: Iterable[CountClause]) -> List[CountClause]:
    """The plan's hard limits as count clauses, one per excluded value, in the brief's order.

    An exclusion clause fails a row that carries any excluded value, so the
    clauses for each value, taken together, keep exactly the rows the plan's
    one clause keeps. Counting them one after another says how many each
    value removed, the way the shopper named them.
    """
    clauses, params = plan.compile_predicates(include_soft=False)
    per_clause: List[CountClause] = []
    cursor = 0
    for clause in clauses:
        width = clause.count("%s")
        clause_params = list(params[cursor:cursor + width])
        cursor += width
        reason = _reason_for(clause)
        if reason != EXCLUSION_REASON:
            per_clause.append((reason, clause, clause_params))
            continue
        for value in clause_params[0]:
            per_clause.append((f"{EXCLUSION_REASON}:{value}", _EXCLUSION_CLAUSE, [[value], [value]]))
    per_clause.extend(extra)
    return sorted(
        per_clause,
        key=lambda item: _REASON_ORDER.index(_kind(item[0])) if _kind(item[0]) in _REASON_ORDER else 99,
    )


def filter_count_sql(
    plan: Any, extra: Iterable[CountClause] = ()
) -> Tuple[str, List[Any], List[str]]:
    """Compile one aggregate statement counting what each hard limit removed.

    Limits are applied in the brief's order (budget, stock, exclusions,
    department), each counted among the rows the earlier limits kept, so the
    removals sum with ``kept`` to the catalog total. Each excluded value is
    its own limit, so "4 candles" and "2 watches" are separate counts.

    Args:
        plan: The search plan whose hard predicates the search ran.
        extra: Clauses the tool applied beside the plan, such as the
            department a browse reads, as ``(reason, clause, params)``.

    Returns:
        ``(sql, params, reasons)`` where ``reasons`` names the removal columns
        in order (``budget``, ``stock``, ``exclusions:candle`` and so on).
    """
    ordered = _count_clauses(plan, extra)

    selects = ["count(*) AS total"]
    bound: List[Any] = []
    kept_clauses: List[str] = []
    reasons: List[str] = []
    for index, (reason, clause, clause_params) in enumerate(ordered):
        prefix = " AND ".join(f"({kept})" for kept in kept_clauses)
        where = f"NOT ({clause})" if not prefix else f"{prefix} AND NOT ({clause})"
        selects.append(f"count(*) FILTER (WHERE {where}) AS removed_{index}")
        for _, _, earlier in ordered[: len(kept_clauses)]:
            bound.extend(earlier)
        bound.extend(clause_params)
        kept_clauses.append(clause)
        reasons.append(reason)
    if kept_clauses:
        selects.append(
            "count(*) FILTER (WHERE " + " AND ".join(f"({kept})" for kept in kept_clauses) + ") AS kept"
        )
        for _, _, clause_params in ordered:
            bound.extend(clause_params)
    else:
        selects.append("count(*) AS kept")
    sql = (
        "SELECT " + ", ".join(selects)
        + ' FROM pellier.product_catalog WHERE "imgUrl" IS NOT NULL'
    )
    return sql, bound, reasons


# A material is a mass noun: "No wool", never "No wools".
_MASS_NOUNS = frozenset(material.lower() for material in KNOWN_MATERIALS)


def plural(word: str) -> str:
    """A shopper's word for more than one: "candles", "watches"; a material stays "wool"."""
    word = str(word or "").strip()
    if not word or word.lower() in _MASS_NOUNS or word.endswith("s"):
        return word
    if re.search(r"(ch|sh|x|z)$", word):
        return word + "es"
    return word + "s"



def filter_counts(
    run: Run, plan: Any, extra: Iterable[CountClause] = ()
) -> Optional[Dict[str, Any]]:
    """Run the count statement and shape it for the panel and the page.

    Returns:
        ``{"kept", "of", "removed", "excluded"}``. ``removed`` is keyed by
        kind (``exclusions`` sums every excluded value); ``excluded`` lists
        each excluded value with its own count and the noun to show with it
        ("4 candles", "1 candle").
    """
    sql, params, reasons = filter_count_sql(plan, extra)
    rows = run(sql, tuple(params))
    if not rows:
        return None
    row = rows[0]
    removed: Dict[str, int] = {}
    excluded: List[Dict[str, Any]] = []
    for index, reason in enumerate(reasons):
        count = int(row.get(f"removed_{index}") or 0)
        kind = _kind(reason)
        removed[kind] = removed.get(kind, 0) + count
        if kind == EXCLUSION_REASON:
            value = reason.split(":", 1)[1]
            excluded.append({"value": value, "count": count, "noun": value if count == 1 else plural(value)})
    return {
        "kept": int(row.get("kept") or 0),
        "of": int(row.get("total") or 0),
        "removed": removed,
        "excluded": excluded,
    }


def _float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ranking_from_execution(
    execution: Any,
    *,
    final_rows: Sequence[Dict[str, Any]],
    counts: Optional[Dict[str, Any]],
    rrf_k: int = RRF_K_DEFAULT,
    top: int = TOP_ROWS,
) -> Dict[str, Any]:
    """The in-process ranking payload, from one real ``SearchExecution``.

    Args:
        execution: The pipeline run; ``candidates`` is the fused pool in RRF
            order with each row's branch ranks and scores.
        final_rows: The eligible rows in the order shown, after rerank and
            merchandising. ``after`` positions come from here.
        counts: The filter counts, or ``None`` when they were not taken.
        rrf_k: The RRF constant, so a reader can redraw ``1 / (k + rank)``.
        top: How many final rows to carry.
    """
    candidates = list(getattr(execution, "candidates", None) or [])
    before = {str(row.get("product_id")): index + 1 for index, row in enumerate(candidates)}
    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(list(final_rows)[:top]):
        pid = str(row.get("product_id"))
        rows.append({
            "product_id": pid,
            "name": row.get("name"),
            "fts_rank": _int(row.get("fts_rank")),
            "vec_rank": _int(row.get("vec_rank")),
            "similarity": _float(row.get("similarity")),
            "rrf_score": _float(row.get("rrf_score")),
            "rerank_score": _float(row.get("rerank_score")),
            "before": before.get(pid),
            "after": index + 1,
        })
    payload: Dict[str, Any] = {
        "available": True,
        "rail": "in-process",
        "method": getattr(execution, "search_method", None),
        "rrf_k": int(rrf_k),
        "rerank_pool": _int(getattr(execution, "rerank_pool_k", None)),
        "arms": {
            "full_text": sum(1 for row in candidates if row.get("fts_rank") is not None),
            "vector": sum(1 for row in candidates if row.get("vec_rank") is not None),
            "fused": len(candidates),
        },
        "filters": counts,
        "rows": rows,
    }
    if counts:
        # The strict first pass also asks for the preferences the shopper
        # implied, so the fused pool can be smaller than what the hard limits kept.
        payload["note"] = KEPT_NOTE
    return payload


def _jsonb(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def ranking_from_receipt(
    receipt: Dict[str, Any],
    *,
    names: Optional[Dict[str, str]] = None,
    rail: str = "gateway-mcp",
    top: int = TOP_ROWS,
) -> Dict[str, Any]:
    """The managed-rail payload, read back from one ``retrieval_receipts`` row.

    Final order is the cited rows first, then the rest of the pool by rerank
    score, then by RRF order. The receipt carries no similarity and no filter
    counts, and the payload says so rather than inventing them.
    """
    names = names or {}
    candidates = [str(pid) for pid in _jsonb(receipt.get("candidate_product_ids"), [])]
    vector_ranks = _jsonb(receipt.get("vector_ranks"), {})
    lexical_ranks = _jsonb(receipt.get("lexical_ranks"), {})
    rrf_scores = _jsonb(receipt.get("rrf_scores"), {})
    rerank_scores = _jsonb(receipt.get("rerank_scores"), {})
    snapshots = _jsonb(receipt.get("citation_snapshots"), [])
    for snapshot in snapshots:
        if isinstance(snapshot, dict) and snapshot.get("entity_id") and snapshot.get("quote"):
            names.setdefault(str(snapshot["entity_id"]), str(snapshot["quote"]).split(":")[0])

    before = {pid: index + 1 for index, pid in enumerate(candidates)}
    final = receipt_final_order(receipt)
    rows: List[Dict[str, Any]] = []
    for index, pid in enumerate(final[:top]):
        rows.append({
            "product_id": pid,
            "name": names.get(pid),
            "fts_rank": _int(lexical_ranks.get(pid)),
            "vec_rank": _int(vector_ranks.get(pid)),
            "similarity": None,
            "rrf_score": _float(rrf_scores.get(pid)),
            "rerank_score": _float(rerank_scores.get(pid)),
            "before": before.get(pid),
            "after": index + 1,
        })
    config = _jsonb(receipt.get("retrieval_config"), {})
    return {
        "available": True,
        "rail": rail,
        "receipt_id": _int(receipt.get("receipt_id")),
        "method": config.get("search_method"),
        "rrf_k": _int(config.get("rrf_k")) or RRF_K_DEFAULT,
        "rerank_pool": _int(config.get("rerank_pool_k")),
        "arms": {
            "full_text": len(lexical_ranks),
            "vector": len(vector_ranks),
            "fused": len(candidates),
        },
        "filters": None,
        "rows": rows,
        "note": "Read from the retrieval receipt: no vector similarity or filter counts on this rail",
    }


def receipt_final_order(receipt: Dict[str, Any]) -> List[str]:
    """A receipt's result order: the cited rows, then the pool by rerank score, then RRF order."""
    candidates = [str(pid) for pid in _jsonb(receipt.get("candidate_product_ids"), [])]
    rerank_scores = _jsonb(receipt.get("rerank_scores"), {})
    cited = [str(pid) for pid in _jsonb(receipt.get("citation_ids"), [])]
    before = {pid: index + 1 for index, pid in enumerate(candidates)}
    rest = [pid for pid in candidates if pid not in cited]
    rest.sort(key=lambda pid: (-(_float(rerank_scores.get(pid)) or -1.0), before[pid]))
    return cited + rest


def ranking_unavailable(rail: str, reason: str) -> Dict[str, Any]:
    """Say plainly that the detail is not available, instead of faking it."""
    return {"available": False, "rail": rail, "reason": reason}


# ---------------------------------------------------------------------------
# The storefront's results grid
# ---------------------------------------------------------------------------

# Where a limit on the page came from. ``carried`` shows as "from earlier".
ORIGIN_STATED = "stated"
ORIGIN_CARRIED = "carried"
ORIGIN_AGENT = "agent"


def _money(dollars: Any) -> str:
    amount = float(dollars)
    return f"${amount:g}" if amount == int(amount) else f"${amount:.2f}"


def result_limits(
    plan: Optional[Dict[str, Any]],
    *,
    carried: Optional[Sequence[str]] = None,
    carried_exclusions: Sequence[str] = (),
    shopper_price: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """The limits a catalog tool applied, as the page's tags.

    One tag per limit and one per excluded value, in the findings' order.
    ``origin`` says where each came from: ``carried`` (kept from earlier in
    the conversation), ``stated`` (said in this message) or ``agent`` (a
    ceiling the agent passed that the shopper did not state). It is ``None``
    when the rail keeps no record of the shopper's limits (``carried`` is
    ``None``), so the page never marks a limit it cannot place.

    Args:
        plan: ``SearchPlan.to_dict()`` of the plan that ran.
        carried: The limit kinds kept from earlier, or ``None`` when unknown.
        carried_exclusions: The excluded values kept from earlier.
        shopper_price: The shopper's own ceiling for this turn, carried or
            stated; a plan ceiling that differs from it came from the agent.
    """
    plan = plan or {}
    hard = plan.get("hard_constraints") or {}
    known = carried is not None
    kinds = set(carried or ())

    def origin(was_carried: bool) -> Optional[str]:
        if not known:
            return None
        return ORIGIN_CARRIED if was_carried else ORIGIN_STATED

    tags: List[Dict[str, Any]] = []
    price = _float(hard.get("price_max_usd"))
    if price is not None:
        shopper = _float(shopper_price)
        if known and (shopper is None or abs(shopper - price) > 1e-9):
            budget_origin: Optional[str] = ORIGIN_AGENT
        else:
            budget_origin = origin("budget" in kinds)
        tags.append({"kind": "budget", "label": f"Under {_money(price)}", "origin": budget_origin})
    if hard.get("in_stock_only"):
        tags.append({"kind": "stock", "label": "In stock", "origin": origin("stock" in kinds)})
    kept_values = {str(value).lower() for value in carried_exclusions}
    for value in plan.get("exclusions") or []:
        if not value:
            continue
        tags.append({
            "kind": "exclusions",
            "value": str(value),
            "label": f"No {plural(str(value))}",
            "origin": origin(str(value).lower() in kept_values),
        })
    for category in hard.get("categories") or []:
        if category:
            tags.append({
                "kind": "department",
                "value": str(category),
                "label": str(category),
                "origin": origin("department" in kinds),
            })
    return tags


def results_payload(
    *,
    product_ids: Sequence[Any],
    limits: List[Dict[str, Any]],
    filters: Optional[Dict[str, Any]],
    rail: str = "in-process",
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """What the page grid shows for one catalog tool call, beside the result the model reads.

    It names no tool: it travels in the shopper's view of the step, and the
    tool is Builder evidence (``builder.tool``).

    Args:
        product_ids: The tool's own result order; at most ``RESULT_IDS_MAX``
            are kept.
        limits: ``result_limits`` for the plan that ran.
        filters: ``filter_counts`` for that plan, or ``None`` when not taken.
        rail: Which rail ran the tool.
        note: What this payload cannot say, in plain words.
    """
    payload: Dict[str, Any] = {
        "available": True,
        "rail": rail,
        "product_ids": [str(pid) for pid in product_ids][:RESULT_IDS_MAX],
        "limits": limits,
        "filters": filters,
    }
    if note:
        payload["note"] = note
    return payload


RECEIPT_RESULTS_NOTE = (
    "Read from the retrieval receipt: no filter counts, and no record of which "
    "limits were kept from earlier"
)


def results_from_receipt(receipt: Dict[str, Any], *, rail: str = "gateway-mcp") -> Dict[str, Any]:
    """The managed rail's grid, read back from one ``retrieval_receipts`` row.

    The receipt holds the result order and the plan, so the order and the
    limits carry over. It holds no filter counts and no record of which
    limits the shopper stated earlier, and the payload says so.
    """
    plan = _jsonb(receipt.get("search_plan"), {})
    return results_payload(
        product_ids=receipt_final_order(receipt),
        limits=result_limits(plan if isinstance(plan, dict) else {}),
        filters=None,
        rail=rail,
        note=RECEIPT_RESULTS_NOTE,
    )


def results_unavailable(rail: str, reason: str) -> Dict[str, Any]:
    """Say plainly that the page cannot show this result, instead of guessing one."""
    return {"available": False, "rail": rail, "reason": reason}
