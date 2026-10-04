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
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

TOP_ROWS = 8
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


def _reason_for(clause: str) -> str:
    if clause.startswith("price"):
        return "budget"
    if clause.startswith("quantity"):
        return "stock"
    if clause.startswith("NOT (tags"):
        return "exclusions"
    if clause.startswith("category"):
        return "department"
    return "other"


def filter_count_sql(plan: Any) -> Tuple[str, List[Any], List[str]]:
    """Compile one aggregate statement counting what each hard limit removed.

    Limits are applied in the brief's order (budget, stock, exclusions,
    department), each counted among the rows the earlier limits kept, so the
    removals sum with ``kept`` to the catalog total.

    Returns:
        ``(sql, params, reasons)`` where ``reasons`` names the removal columns
        in order (``removed_budget`` and so on).
    """
    clauses, params = plan.compile_predicates(include_soft=False)
    per_clause: List[Tuple[str, str, List[Any]]] = []
    cursor = 0
    for clause in clauses:
        width = clause.count("%s")
        per_clause.append((_reason_for(clause), clause, list(params[cursor:cursor + width])))
        cursor += width
    ordered = sorted(per_clause, key=lambda item: _REASON_ORDER.index(item[0]) if item[0] in _REASON_ORDER else 99)

    selects = ["count(*) AS total"]
    bound: List[Any] = []
    kept_clauses: List[str] = []
    reasons: List[str] = []
    for reason, clause, clause_params in ordered:
        prefix = " AND ".join(f"({kept})" for kept in kept_clauses)
        where = f"NOT ({clause})" if not prefix else f"{prefix} AND NOT ({clause})"
        selects.append(f"count(*) FILTER (WHERE {where}) AS removed_{reason}")
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


def filter_counts(run: Run, plan: Any) -> Optional[Dict[str, Any]]:
    """Run the count statement and shape it as ``{"kept", "of", "removed": {...}}``."""
    sql, params, reasons = filter_count_sql(plan)
    rows = run(sql, tuple(params))
    if not rows:
        return None
    row = rows[0]
    removed = {reason: int(row.get(f"removed_{reason}") or 0) for reason in reasons}
    return {
        "kept": int(row.get("kept") or 0),
        "of": int(row.get("total") or 0),
        "removed": removed,
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
    cited = [str(pid) for pid in _jsonb(receipt.get("citation_ids"), [])]
    snapshots = _jsonb(receipt.get("citation_snapshots"), [])
    for snapshot in snapshots:
        if isinstance(snapshot, dict) and snapshot.get("entity_id") and snapshot.get("quote"):
            names.setdefault(str(snapshot["entity_id"]), str(snapshot["quote"]).split(":")[0])

    before = {pid: index + 1 for index, pid in enumerate(candidates)}
    rest = [pid for pid in candidates if pid not in cited]
    rest.sort(key=lambda pid: (-(_float(rerank_scores.get(pid)) or -1.0), before[pid]))
    final = cited + rest
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


def ranking_unavailable(rail: str, reason: str) -> Dict[str, Any]:
    """Say plainly that the detail is not available, instead of faking it."""
    return {"available": False, "rail": rail, "reason": reason}
