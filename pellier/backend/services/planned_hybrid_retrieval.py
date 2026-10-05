"""Lab 1's measurement surface over the shared search pipeline.

The planned hybrid pipeline itself lives in ``services.store_tools``
(:func:`~services.store_tools.run_search_plan`), the one implementation the
shopper tool runs on both rails. This module keeps what Lab 1 measures it
with: the canonical query and its labels, the held-out cases, the micro-eval
scoring, and :func:`execute_search_plan`, the async entry point the strategy
comparison (``app.compare_search_strategies``), the micro-eval and the eval
harness (``scripts/eval_retrieval_harness.py``) call. Because that entry point
runs the same function the shopper's ``search_products`` runs, what a
participant measures is what a shopper gets.

Pipeline for one pass:

    typed plan -> hard SQL predicates on both branches -> vector + FTS -> RRF
    -> rerank over a bounded pool -> eligibility recheck -> returned rows
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Sequence

from config import settings
from services import store_tools
from services.store_tools import (  # noqa: F401 - the measurement surface re-exports the pipeline's names
    DEFAULT_RERANK_POOL_K,
    RERANK_POOL_MIN,
    SEARCH_METHOD_HYBRID,
    SEARCH_METHOD_HYBRID_RERANK,
    SEARCH_METHOD_RERANK_FALLBACK,
    SEARCH_METHOD_VECTOR,
    STAGE_ELIGIBILITY,
    STAGE_EMBED,
    STAGE_HYBRID,
    STAGE_RERANK,
    STAGE_VECTOR,
    SearchExecution,
    SearchStage,
    run_search_plan,
)

# The canonical Lab 1 query. The eval harness reads the same entry.
CANONICAL_ANNA_QUERY = "A housewarming gift under $100 that is currently in stock."

# Provided labels support the optional diagnostic comparison; participants do not
# build an evaluation framework or label a golden set in this workshop. Labeled by
# definition, the in-stock Home pieces tagged both gift and home at or under $100:
#
#   SELECT "productId"
#     FROM pellier.product_catalog
#    WHERE category = 'Home'
#      AND price <= 100
#      AND quantity > 0
#      AND tags @> '["gift","home"]'::jsonb
#    ORDER BY "productId"::int;
CANONICAL_ANNA_GOLDEN_IDS: tuple[str, ...] = ("21", "23", "25", "27", "29", "80", "83")

# Optional provided diagnostics for the rerank pool size;
# these check the choice on requests the labels never described. They are
# provided rather than authored. A pool size chosen on Anna's labels has to
# hold here, or it is a hypothesis rather than a decision.
#
# One held-out product slice with its own labels, from a different part of the
# catalog. Definition, pinned the same way the golden set is:
#
#   SELECT "productId"
#     FROM pellier.product_catalog
#    WHERE category = 'Bath and body'
#      AND quantity > 0
#      AND tags @> '["gift"]'::jsonb
#    ORDER BY "productId";
CANONICAL_HELD_OUT_QUERY = "A beauty gift for someone who loves a slow morning ritual."
CANONICAL_HELD_OUT_GOLDEN_IDS: tuple[str, ...] = ("26",)

# Four query cases, each exercising a different way retrieval can be wrong while
# the ranking looks fine. ``labels`` cases are scored like the tuning set; the
# other kinds are pass/fail on what came back.
HELD_OUT_KIND_LABELS = "labels"
HELD_OUT_KIND_MUST_NOT_RETURN = "must_not_return"
HELD_OUT_KIND_NO_RESULT = "no_result"
HELD_OUT_CASES: tuple[dict, ...] = (
    {
        "id": "slice",
        "kind": HELD_OUT_KIND_LABELS,
        "query": CANONICAL_HELD_OUT_QUERY,
        "golden_ids": CANONICAL_HELD_OUT_GOLDEN_IDS,
        "rule": "in-stock Bath and body pieces tagged gift",
    },
    {
        # An exclusion the shopper states. The candle in the housewarming set must
        # not come back, and the rest of that set must.
        "id": "exclusion",
        "kind": HELD_OUT_KIND_LABELS,
        "query": "A housewarming gift under $100, but no candles.",
        "golden_ids": ("23", "25", "27", "29", "83"),
        "rule": "in-stock Home pieces tagged gift and home at or under $100, not tagged candle",
    },
    {
        # A ceiling that drops about half the gifts; the ones at or under it must lead.
        "id": "tight_budget",
        "kind": HELD_OUT_KIND_LABELS,
        "query": "A small gift under $40.",
        "golden_ids": ("21", "23", "25", "26", "27", "29", "30", "73", "76", "77", "80"),
        "rule": "in-stock pieces tagged gift at or under $40",
    },
    {
        # A piece the catalog carries with no units. Relevance would rank it first;
        # eligibility must keep it out of the answer.
        "id": "unavailable",
        "kind": HELD_OUT_KIND_MUST_NOT_RETURN,
        "query": "Is the Quilted Silk Vest available?",
        "must_not_return": ("43",),
        "rule": "a sold-out piece is never returned",
    },
    {
        # Nothing in the catalog satisfies this; the honest answer is no rows.
        "id": "no_result",
        "kind": HELD_OUT_KIND_NO_RESULT,
        "query": "A cashmere gift under $30.",
        "rule": "no in-stock cashmere piece costs $30 or less",
    },
)


def score_held_out_case(case: dict, execution: SearchExecution, *, limit: int) -> Dict[str, Any]:
    """One held-out case, one pool size: the metrics for a labelled case, a
    pass/fail for the other kinds. Never a score invented from a case that has
    no labels."""
    returned_ids = _product_ids(execution.returned)
    if case["kind"] == HELD_OUT_KIND_LABELS:
        variant = micro_eval_variant(
            execution, latencies_ms=[0.0], golden_ids=case["golden_ids"], limit=limit
        )
        variant["passed"] = variant["context_precision"] > 0.0
        return variant
    if case["kind"] == HELD_OUT_KIND_MUST_NOT_RETURN:
        leaked = sorted(set(returned_ids) & set(case["must_not_return"]))
        return {
            "pool_k": execution.rerank_pool_k,
            "returned": len(returned_ids),
            "leaked": leaked,
            "passed": not leaked,
        }
    return {
        "pool_k": execution.rerank_pool_k,
        "returned": len(returned_ids),
        "passed": len(returned_ids) == 0,
    }

EmbedFn = Callable[[str], Sequence[float]]
RerankFn = Callable[..., List[Dict[str, Any]]]


def resolve_rerank_pool_k(config: Dict[str, Any]) -> int:
    """Bound the rerank pool between the floor and the configured reranker cap."""
    return store_tools.resolve_rerank_pool_k(
        {**config, "rerank_max_documents": settings.RERANK_MAX_DOCUMENTS}
    )


def _executor_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """The caller's knobs over the configured defaults."""
    return {
        "k_vector": settings.HYBRID_VECTOR_K,
        "k_fts": settings.HYBRID_FTS_K,
        "rrf_k": settings.HYBRID_RRF_K,
        "top_n": settings.HYBRID_TOP_N,
        **{key: value for key, value in (config or {}).items() if value},
        "rerank_max_documents": settings.RERANK_MAX_DOCUMENTS,
    }


def _product_ids(rows: Sequence[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    for row in rows:
        value = row.get("product_id", row.get("productId"))
        if value is not None and str(value).strip():
            ids.append(str(value))
    return ids


def _breaks_price_or_stock(row: Dict[str, Any], plan: Any) -> bool:
    price = store_tools.as_number(row.get("price"))
    ceiling = store_tools.as_number(plan.hard.price_max_usd)
    if ceiling is not None and price is not None and price > ceiling + 1e-9:
        return True
    quantity = store_tools.as_number(row.get("quantity"))
    return bool(plan.hard.in_stock_only and quantity is not None and quantity <= 0)


def _percentile(values: Sequence[float], fraction: float) -> float:
    """Linear-interpolated percentile; small samples, so no nearest-rank jumps."""
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def micro_eval_variant(
    execution: SearchExecution,
    *,
    latencies_ms: Sequence[float],
    golden_ids: Sequence[str],
    limit: int,
) -> Dict[str, Any]:
    """Score one pool-size variant against the golden ids.

    The quality metrics come from a single execution on purpose. Every input
    they read — the rerank pool, the returned rows, the plan's hard
    constraints — is fixed for a given pool size, so repeating the pass
    reproduces the same numbers while spending two more SQL round trips and
    another Bedrock Rerank call. Only latency varies between repetitions, so
    only latency is sampled: pass every repetition's wall clock in
    ``latencies_ms`` and score the first pass's execution.

    Args:
        execution: The first (and scoring) pass for this pool size.
        latencies_ms: Wall-clock milliseconds, one per repetition.
        golden_ids: The labeled relevant product ids for the query.
        limit: The row count the caller asked for.

    Returns:
        The variant record. Definitions:
            candidate_coverage: golden ids inside the rerank pool / golden ids.
            context_precision: returned ids that are golden / returned ids.
            mrr: 1 / rank of the first golden id in the returned rows, else 0.
            hard_constraint_violations: returned rows breaking price or stock.
            short_result_rate: 1.0 when the pass returned fewer than ``limit``
                rows, else 0.0. A rate over one deterministic observation.
            citation_coverage: returned rows carrying a citable id / returned.
                This is *citable-result* coverage: whether a row could be
                cited, not whether the answer's claims were supported by
                citations. Answer-level citation support is a separate
                measurement over generated text and is not scored here.
            latency_ms_p50 / p95: percentiles over whatever ``latencies_ms``
                holds. The caller decides what that is, and the micro-eval
                endpoint passes the cold pass alone, so read these as
                percentiles over the samples given -- not as evidence that
                more than one sample was taken.
    """
    golden = {str(value) for value in golden_ids}
    pool_ids = set(_product_ids(execution.rerank_pool))
    returned = execution.returned
    returned_ids = _product_ids(returned)
    relevant = [pid for pid in returned_ids if pid in golden]
    first_hit = next(
        (1.0 / rank for rank, pid in enumerate(returned_ids, 1) if pid in golden), 0.0
    )
    return {
        "pool_k": execution.rerank_pool_k,
        "candidate_coverage": _mean([len(golden & pool_ids) / len(golden)] if golden else []),
        "context_precision": _mean(
            [len(relevant) / len(returned_ids)] if returned_ids else []
        ),
        "mrr": _mean([first_hit]),
        "hard_constraint_violations": sum(
            1 for row in returned if _breaks_price_or_stock(row, execution.plan)
        ),
        "short_result_rate": float(len(returned) < limit),
        "citation_coverage": _mean(
            [len(returned_ids) / len(returned)] if returned else []
        ),
        "latency_ms_p50": _percentile(latencies_ms, 0.5),
        "latency_ms_p95": _percentile(latencies_ms, 0.95),
    }


async def execute_search_plan(
    db: Any,
    *,
    plan: Any,
    query: str,
    limit: int,
    embed: EmbedFn,
    rerank: RerankFn,
    config: Dict[str, Any],
    relax: bool = True,
) -> SearchExecution:
    """Run a typed plan through the shared pipeline from async code.

    The pipeline is synchronous and takes a statement runner, so the same
    function serves the shopper tool on both rails. Here it runs on a worker
    thread, and each statement is sent back to this event loop through
    ``db.fetch_all``.

    Args:
        db: A database service exposing ``fetch_all(sql, *params)``.
        plan: A :class:`~services.search_plan.SearchPlan`.
        query: The raw query text, embedded once and lexically matched.
        limit: How many rows the caller will show. Clamped to at least one.
        embed: Callable returning the query embedding.
        rerank: Callable with the ``RerankService.rerank`` signature.
        config: Optional knobs: ``k_vector``, ``k_fts``, ``rrf_k``, ``top_n``
            and ``rerank_pool_k``. Missing knobs use the configured defaults.
        relax: Walk the plan's relaxation ladder when the strict pass is short.

    Returns:
        The :class:`~services.store_tools.SearchExecution` of the pass that
        produced the returned rows.
    """
    loop = asyncio.get_running_loop()

    def run(sql: str, params: Sequence[Any]) -> List[Dict[str, Any]]:
        rows = asyncio.run_coroutine_threadsafe(db.fetch_all(sql, *params), loop).result()
        return [dict(row) for row in rows or []]

    return await asyncio.to_thread(
        store_tools.run_search_plan,
        run,
        plan=plan,
        query=query,
        limit=limit,
        embed=embed,
        rerank=rerank,
        config=_executor_config(config),
        relax=relax,
    )
