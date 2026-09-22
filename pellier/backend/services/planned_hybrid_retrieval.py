"""The shared search executor behind Pellier's shopper retrieval surfaces.

Five callers run :func:`execute_search_plan`: the storefront tool
(``services.agent_tools.search_products_hybrid``), the Observatory strategy
comparison's strategies 3 and 4 (``app.compare_search_strategies``), the Lab 2
receipt written from strategy 4, the micro-eval
(``app.micro_eval_search_strategies``), and the eval harness
(``scripts/eval_retrieval_harness.py``). For those five, one pipeline means one
truth: what a participant measures in the Observatory is what a shopper gets,
and a receipt written from an execution describes the rows the caller showed.

Two retrieval paths in this repository deliberately do not run this executor,
and neither gets the post-rerank eligibility recheck below:

* ``services.replacement_search.find_replacements`` — the Operator Concierge's
  replacement finder. It adds two hard predicates this executor has no place
  for (never the SKU being replaced, and availability reconciled against the
  ledger via ``inventory_evidence.RECONCILED_AVAILABLE_SQL`` rather than the
  aggregate cache), it walks its ladder on candidate count before reranking
  rather than on returned count after it, and it shows the reranker every
  candidate while returning only the best twelve. Routing it through this
  executor would change which ladder rung serves, how many Bedrock rerank calls
  a request makes, and which candidates the reranker ever sees. It composes the
  same parts — ``search_plan``, ``HybridSearch``, ``rerank`` — one level up.
* ``app.explain_search`` — the Observatory "Search" mechanism surface. It exists
  to expose the intermediate artifacts (branch SQL, per-branch ranks, the
  fusion-to-rerank position delta) that this executor collapses into stage
  counts, so it drives ``HybridSearch.search_explained`` directly. It is a
  teaching read model and never produces shopper-visible rows or a receipt.

Pipeline for one pass:

    typed plan -> hard SQL predicates on both branches -> vector + FTS -> RRF
    -> rerank over a bounded pool -> eligibility recheck -> returned rows

Hard constraints are enforced twice on purpose. They enter candidate
generation as SQL so invalid rows never consume reranker capacity, and they
are rechecked after the reranker so a row that slipped past the SQL (a stale
plan, a fake in a test, a future branch that forgets the predicates) is still
refused before it becomes evidence.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from config import settings
from services.search_plan import STRATEGY_HYBRID, STRATEGY_VECTOR

# The canonical Lab 2 query. The eval harness pins the same entry;
# ``tests/test_search_micro_eval.py`` keeps the two aligned.
CANONICAL_ANNA_QUERY = "A housewarming gift under $100 that is currently in stock."

# Provided labels support the optional diagnostic comparison; participants do not
# build an evaluation framework or label a golden set in this workshop.
CANONICAL_ANNA_GOLDEN_IDS: tuple[str, ...] = ("21", "22", "23", "25", "27", "29")

# Provided bounded candidate pool. Tune only in the optional retrieval extension;
# Task 2B authors the search-plan contract, not a prescribed pool-size constant.
DEFAULT_RERANK_POOL_K = 15

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
#    WHERE category = 'Beauty'
#      AND quantity > 0
#      AND tags @> '["gift"]'::jsonb
#      AND NOT (tags ? 'archive')
#    ORDER BY "productId";
CANONICAL_HELD_OUT_QUERY = "A beauty gift for someone who loves a slow morning ritual."
CANONICAL_HELD_OUT_GOLDEN_IDS: tuple[str, ...] = ("26", "47", "55", "56")

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
        "rule": "in-stock Beauty pieces tagged gift",
    },
    {
        # An exclusion the shopper states. The candle in the housewarming set must
        # not come back, and the rest of that set must.
        "id": "exclusion",
        "kind": HELD_OUT_KIND_LABELS,
        "query": "A housewarming gift under $100, but no candles.",
        "golden_ids": ("22", "23", "25", "27", "29"),
        "rule": "in-stock Home Decor pieces tagged gift and home at or under $100, not tagged candle",
    },
    {
        # A ceiling low enough that most gifts fall out; the two that remain must lead.
        "id": "tight_budget",
        "kind": HELD_OUT_KIND_LABELS,
        "query": "A small gift under $40.",
        "golden_ids": ("23", "30"),
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

# Below three documents the reranker has nothing to reorder.
RERANK_POOL_MIN = 3

# The micro-eval repeats each pool-size variant to measure the warm path, and
# the endpoint reports cold and warm apart rather than blending them. Every
# repetition sends an identical rerank request, and `services/rerank.py` caches
# on (query, documents, top_n, model_id), so with the cache enabled the first
# pass pays Bedrock and passes 2..N are cache hits. A single p50 over both
# describes neither, and moves with the repetition count rather than with
# anything about the system. Repetitions buy nothing else: over a fixed pool
# the quality metrics are deterministic, so they are scored once from the first
# pass. Every extra repetition is still two SQL round trips -- and one more
# Bedrock Rerank call when the cache is off -- which is why the ceiling is low
# and the default is lower.
MICRO_EVAL_REPETITIONS_DEFAULT = 3
MICRO_EVAL_REPETITIONS_MAX = 5

# The same amplification argument bounds the other axis. Distinct pool sizes
# multiply with repetitions, so an uncapped list of sizes would let one URL
# buy an unbounded number of Bedrock Rerank calls. Four is generous for a
# teaching surface whose default compares two.
MICRO_EVAL_POOL_SIZES_MAX = 4

STAGE_EMBED = "embed"
STAGE_VECTOR = "vector"
STAGE_HYBRID = "hybrid"
STAGE_RERANK = "rerank"
STAGE_ELIGIBILITY = "eligibility"

SEARCH_METHOD_VECTOR = "vector"
SEARCH_METHOD_HYBRID = "hybrid"
SEARCH_METHOD_HYBRID_RERANK = "hybrid+rerank"
SEARCH_METHOD_RERANK_FALLBACK = "hybrid (rerank fallback to RRF order)"

EmbedFn = Callable[[str], Sequence[float]]
RerankFn = Callable[..., List[Dict[str, Any]]]


@dataclass
class SearchStage:
    """One pipeline stage: how many rows left it and how long it took."""

    name: str
    count: int
    latency_ms: int


@dataclass
class SearchExecution:
    """Everything one search run produced, ready to show and to prove.

    Attributes:
        plan: The plan rung that produced ``returned``. When the relaxation
            ladder widened preferences this is the widened rung, and its
            ``relaxations`` list says exactly what changed.
        query: The raw query text that was embedded and lexically matched.
        candidates: The fused RRF pool, in RRF order, with ``vec_rank``,
            ``fts_rank``, and ``rrf_score`` on every row.
        ordered: The eligible rows in final rank order, with ``rerank_score``
            (``None`` when the reranker did not run or fell back).
        returned: ``ordered[:limit]``; the rows the caller will show.
        stages: Per-stage counts and latencies in execution order. A relaxed
            run records every pass, so the strict attempt stays visible.
        rerank_pool_k: The bound on documents sent to the reranker.
        relaxation_steps: Names of the ladder steps applied, in order.
        search_method: The label the storefront payload reports.
    """

    plan: Any
    query: str
    candidates: List[Dict[str, Any]]
    ordered: List[Dict[str, Any]]
    returned: List[Dict[str, Any]]
    stages: List[SearchStage]
    rerank_pool_k: int
    relaxation_steps: List[str] = field(default_factory=list)
    search_method: str = SEARCH_METHOD_HYBRID_RERANK

    @property
    def rerank_pool(self) -> List[Dict[str, Any]]:
        """The candidates the reranker was allowed to see."""
        return self.candidates[: self.rerank_pool_k]

    def stage(self, name: str) -> Optional[SearchStage]:
        """Return the last recorded stage with this name, if it ran."""
        for recorded in reversed(self.stages):
            if recorded.name == name:
                return recorded
        return None

    def latency_breakdown(self) -> Dict[str, int]:
        """Sum stage latencies by name for the retrieval receipt."""
        breakdown: Dict[str, int] = {}
        for recorded in self.stages:
            breakdown[recorded.name] = breakdown.get(recorded.name, 0) + recorded.latency_ms
        return breakdown


def catalog_document(row: Dict[str, Any]) -> str:
    """Return the bounded catalog representation supplied to the reranker."""
    name = " ".join(str(row.get("name") or "").split())
    description = " ".join(str(row.get("description") or "").split())
    category = " ".join(str(row.get("category") or "").split())
    if len(description) > 240:
        description = description[:237] + "…"
    return f"{name} — {description} ({category})"


def resolve_rerank_pool_k(config: Dict[str, Any]) -> int:
    """Bound the rerank pool between the floor and the reranker's own cap."""
    requested = config.get("rerank_pool_k") or DEFAULT_RERANK_POOL_K
    ceiling = max(RERANK_POOL_MIN, int(settings.RERANK_MAX_DOCUMENTS))
    return max(RERANK_POOL_MIN, min(int(requested), ceiling))


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _project_rerank(
    pool: List[Dict[str, Any]], results: Sequence[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Project reranker indices back onto the pool, ignoring invalid ones.

    An out-of-range index is skipped rather than projected onto an unknown
    row. If nothing valid comes back the caller falls back to RRF order.
    """
    ordered: List[Dict[str, Any]] = []
    for result in results:
        try:
            index = int(result["index"])
        except (KeyError, TypeError, ValueError):
            continue
        if index < 0 or index >= len(pool):
            continue
        try:
            score = float(result.get("relevance_score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        ordered.append({**pool[index], "rerank_score": score})
    return ordered


def _as_number(value: Any) -> Optional[float]:
    """Coerce a row value to a float, or return ``None`` when it will not.

    Catalog rows reach the eligibility recheck from SQL, from a Gateway
    payload, and from test fakes, so a price or quantity can arrive as a
    ``Decimal``, a numeric string, ``None``, or something that is not a number
    at all. A value that will not coerce is *absent*, not zero: an absent
    field cannot be judged against a hard constraint, and guessing a number
    for it would either invent a violation or hide one. A bare ``bool`` is
    treated as absent too, because ``float(True)`` is a coincidence of the
    type system rather than a price.

    Args:
        value: The raw row value.

    Returns:
        The value as a float, or ``None`` when it cannot be coerced.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _violates_hard_constraints(row: Dict[str, Any], plan: Any) -> bool:
    """Return True when a row breaks a hard predicate the plan declared.

    A field the row does not carry, or carries as something uncoercible,
    cannot be judged and is not treated as a violation; the SQL predicate
    remains the enforcement point for it.
    """
    hard = plan.hard
    price = _as_number(row.get("price"))
    ceiling = _as_number(hard.price_max_usd)
    if ceiling is not None and price is not None and price > ceiling + 1e-9:
        return True
    category = row.get("category")
    if hard.categories and category is not None:
        allowed = {value.lower() for value in hard.categories}
        if str(category).lower() not in allowed:
            return True
    quantity = _as_number(row.get("quantity"))
    if hard.in_stock_only and quantity is not None and quantity <= 0:
        return True
    tags = row.get("tags")
    if plan.exclusions and tags is not None:
        excluded = {value.lower() for value in plan.exclusions}
        if {str(tag).lower() for tag in tags} & excluded:
            return True
    return False


async def _retrieve_candidates(
    db: Any,
    *,
    plan: Any,
    query: str,
    embedding: Sequence[float],
    config: Dict[str, Any],
    stages: List[SearchStage],
) -> List[Dict[str, Any]]:
    """Run candidate generation for the plan's declared strategy."""
    from services.hybrid_search import HybridSearch

    hard_clauses, hard_params = plan.compile_predicates()
    hybrid = HybridSearch(db)
    started = time.perf_counter()
    if plan.retrieval_strategy == STRATEGY_VECTOR:
        candidates = await hybrid.vector_only(
            query_embedding=list(embedding),
            k=int(config.get("k_vector") or settings.HYBRID_VECTOR_K),
            hard_clauses=hard_clauses,
            hard_params=hard_params,
        )
        stages.append(SearchStage(STAGE_VECTOR, len(candidates), _elapsed_ms(started)))
        return candidates
    candidates = await hybrid.search(
        query=query,
        query_embedding=list(embedding),
        k_vector=int(config.get("k_vector") or settings.HYBRID_VECTOR_K),
        k_fts=int(config.get("k_fts") or settings.HYBRID_FTS_K),
        rrf_k=int(config.get("rrf_k") or settings.HYBRID_RRF_K),
        top_n=int(config.get("top_n") or settings.HYBRID_TOP_N),
        hard_clauses=hard_clauses,
        hard_params=hard_params,
    )
    stages.append(SearchStage(STAGE_HYBRID, len(candidates), _elapsed_ms(started)))
    return candidates


async def _rank_candidates(
    candidates: List[Dict[str, Any]],
    *,
    plan: Any,
    query: str,
    rerank: RerankFn,
    pool_k: int,
    stages: List[SearchStage],
) -> tuple[List[Dict[str, Any]], str]:
    """Order the pool: rerank for ``hybrid+rerank``, RRF order otherwise."""
    if plan.retrieval_strategy == STRATEGY_VECTOR:
        return [dict(row) for row in candidates], SEARCH_METHOD_VECTOR
    if plan.retrieval_strategy == STRATEGY_HYBRID:
        return [{**row, "rerank_score": None} for row in candidates], SEARCH_METHOD_HYBRID

    pool = [dict(row) for row in candidates[:pool_k]]
    rerank_query = (getattr(plan.soft, "soft_signal", "") or "").strip() or query
    started = time.perf_counter()
    results: List[Dict[str, Any]] = []
    if pool:
        results = await asyncio.to_thread(
            rerank,
            query=rerank_query,
            documents=[catalog_document(row) for row in pool],
            top_n=len(pool),
        )
    ordered = _project_rerank(pool, results or [])
    stages.append(SearchStage(STAGE_RERANK, len(ordered), _elapsed_ms(started)))
    if not ordered:
        return [{**row, "rerank_score": None} for row in pool], SEARCH_METHOD_RERANK_FALLBACK
    return ordered, SEARCH_METHOD_HYBRID_RERANK


async def _run_pass(
    db: Any,
    *,
    plan: Any,
    query: str,
    embedding: Sequence[float],
    limit: int,
    rerank: RerankFn,
    config: Dict[str, Any],
    pool_k: int,
    stages: List[SearchStage],
) -> SearchExecution:
    """Execute one plan rung end to end and record its stages."""
    candidates = await _retrieve_candidates(
        db, plan=plan, query=query, embedding=embedding, config=config, stages=stages
    )
    ranked, search_method = await _rank_candidates(
        candidates, plan=plan, query=query, rerank=rerank, pool_k=pool_k, stages=stages
    )
    started = time.perf_counter()
    ordered = [row for row in ranked if not _violates_hard_constraints(row, plan)]
    stages.append(SearchStage(STAGE_ELIGIBILITY, len(ordered), _elapsed_ms(started)))
    return SearchExecution(
        plan=plan,
        query=query,
        candidates=candidates,
        ordered=ordered,
        returned=ordered[:limit],
        stages=stages,
        rerank_pool_k=pool_k,
        relaxation_steps=[relaxation.step for relaxation in plan.relaxations],
        search_method=search_method,
    )


def _product_ids(rows: Sequence[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    for row in rows:
        value = row.get("product_id", row.get("productId"))
        if value is not None and str(value).strip():
            ids.append(str(value))
    return ids


def _breaks_price_or_stock(row: Dict[str, Any], plan: Any) -> bool:
    price = _as_number(row.get("price"))
    ceiling = _as_number(plan.hard.price_max_usd)
    if ceiling is not None and price is not None and price > ceiling + 1e-9:
        return True
    quantity = _as_number(row.get("quantity"))
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
    """Run a typed plan through the shared retrieval pipeline.

    Args:
        db: A database service exposing ``get_connection()``.
        plan: A :class:`~services.search_plan.SearchPlan`. Its hard
            constraints and exclusions compile into both branch queries; its
            ``retrieval_strategy`` selects vector-only, hybrid, or
            hybrid+rerank; its ``soft_signal`` is what the reranker scores.
        query: The raw query text, embedded once and lexically matched.
        limit: How many rows the caller will show. Clamped to at least one.
        embed: Callable returning the query embedding. Called once per run,
            on a worker thread, so a Bedrock call never blocks the loop.
        rerank: Callable with the ``RerankService.rerank`` signature
            (``query``, ``documents``, ``top_n`` keywords). Also run on a
            worker thread.
        config: Optional knobs: ``k_vector``, ``k_fts``, ``rrf_k``, ``top_n``
            (fused pool cap), and ``rerank_pool_k`` (documents the reranker
            may see; defaults to ``settings.RERANK_MAX_DOCUMENTS``, floor 3).
        relax: When True and the strict pass returns fewer than ``limit``
            rows, walk the plan's relaxation ladder. Each applied step is
            recorded in ``relaxation_steps``. Hard constraints never widen.

    Returns:
        A :class:`SearchExecution` describing the pass that produced the
        returned rows, with every pass's stages recorded in order.
    """
    limit = max(1, int(limit))
    pool_k = resolve_rerank_pool_k(config or {})
    stages: List[SearchStage] = []

    started = time.perf_counter()
    embedding = await asyncio.to_thread(embed, query)
    stages.append(SearchStage(STAGE_EMBED, len(embedding), _elapsed_ms(started)))

    async def run_rung(rung: Any) -> SearchExecution:
        return await _run_pass(
            db,
            plan=rung,
            query=query,
            embedding=embedding,
            limit=limit,
            rerank=rerank,
            config=config or {},
            pool_k=pool_k,
            stages=stages,
        )

    # A complete strict result needs no fallback. Keep the unfinished Lab 2
    # fallback isolated from earlier requests that already satisfy the plan.
    execution = await run_rung(plan)
    if relax and len(execution.returned) < limit:
        for rung in plan.relaxation_ladder()[1:]:
            if len(execution.returned) >= limit:
                break
            execution = await run_rung(rung)
    return execution
