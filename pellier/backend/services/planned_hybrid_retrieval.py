"""The eval harness's entry point into the shared search pipeline.

The planned hybrid pipeline itself lives in ``services.store_tools``
(:func:`~services.store_tools.run_search_plan`), the one implementation the
shopper tool runs on both rails. This module keeps Anna's canonical query and
its labels, which the retrieval harness (``scripts/eval_retrieval_harness.py``)
reads, and :func:`execute_search_plan`, the async entry point the harness
calls. Because that entry point runs the same function the shopper's
``search_products`` runs, what the harness measures is what a shopper gets.

Pipeline for one pass:

    typed plan -> hard SQL predicates on both branches -> vector + FTS -> RRF
    -> rerank over a bounded pool -> eligibility recheck -> returned rows
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Sequence

from config import settings
from services import store_tools
from services.store_tools import (  # noqa: F401 - re-exported for the harness and its tests
    SearchExecution,
    SearchStage,
)

# The canonical Lab 1 query. The eval harness reads the same entry.
CANONICAL_ANNA_QUERY = "A housewarming gift under $100 that is currently in stock."

# Provided labels for the retrieval harness; participants do not build an
# evaluation framework or label a golden set in this workshop. Labeled by
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
