#!/usr/bin/env python3
"""Golden-query retrieval harness for the governed Pellier workshop.

Runs the same Aurora catalog through four retrieval strategies:

* vector
* hybrid
* hybrid+rerank
* agentic, planned by the *real* ``services.search_plan`` planner

Every strategy runs through the backend's shared executor,
``services.planned_hybrid_retrieval.execute_search_plan``. The harness owns
no SQL, no fusion, and no rerank call of its own: an evaluation that scores a
private copy of the pipeline cannot detect a regression in the shipped one.

The agentic row deliberately does **not** use the pinned filters in each
golden query's definition. Pinned filters make that row an oracle-filter
experiment: it measures how good retrieval could be if a perfect planner
existed, which is exactly the number that hides planner bugs. Instead the
harness runs the shipped extractor plus the shipped planner, then scores
the plan itself against the pinned filters as ground truth. A planning
mistake now shows up as a planner-precision miss rather than disappearing
into a healthy-looking recall figure.

Three evaluation layers, per the governed-workshop audit:

1. **Planner correctness**: did the plan recover the expected hard
   constraints, and did it invent any that were not asked for?
2. **Retriever/ranker quality**: Recall@5, Hit@1, MRR@5, candidate
   coverage, short-result rate, and hard-constraint compliance.
3. **Exit status**: the harness fails with a non-zero exit code when a
   threshold regresses, so CI can gate on relevance instead of merely
   printing it.

The harness does not need the FastAPI server running, but it uses the same
Bedrock models, the same database service, and the same PostgreSQL tables as
the app. ``--pool-k`` is the candidate count per branch before RRF and the
rerank pool bound, so a small value shows what the reranker cannot recover.

Run ``--json`` for machine-readable output, ``--no-gate`` to report without
enforcing thresholds (useful when exploring), and ``--strict-planner`` to
also gate on planner precision.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import boto3


EMBED_MODEL_DEFAULT = "us.cohere.embed-v4:0"
RERANK_MODEL_DEFAULT = "cohere.rerank-v3-5:0"

STRATEGIES = ("vector", "hybrid", "rerank", "agentic")


# CI thresholds. A regression below any of these fails the run with a
# non-zero exit status. They are floors observed on the seeded catalog,
# set just below current measured performance so ordinary noise does not
# flap the gate but a real relevance regression trips it.
#
# The three ``*_max`` violation budgets are zero on purpose: a hard
# constraint that is violated even once is a correctness bug, not a
# quality metric to average away.
THRESHOLDS: dict[str, float] = {
    "rerank_recall_at_5_min": 0.70,
    "rerank_mrr_at_5_min": 0.55,
    "agentic_recall_at_5_min": 0.60,
    "hybrid_candidate_coverage_min": 0.75,
    "hard_constraint_violation_rate_max": 0.0,
    "exclusion_violation_rate_max": 0.0,
    # Same budget, different question: these two score the returned rows
    # against what the shopper asked for rather than against the plan the
    # planner produced, so a silently dropped requirement fails the gate.
    "requested_constraint_violation_rate_max": 0.0,
    "requested_exclusion_violation_rate_max": 0.0,
    "planner_hallucinated_constraint_rate_max": 0.0,
}

# Planner precision is gated only under --strict-planner: the extractor is
# a live model call, so this number moves with model behaviour rather than
# with the code under test.
PLANNER_RECALL_MIN = 0.60


@dataclass(frozen=True)
class Filters:
    """What the shopper actually asked for, independent of any produced plan.

    ``in_stock`` defaults to True because every golden id below was labeled
    against the sellable catalog -- the same population ``_baseline_plan``
    pins. Leaving stock out of the requested truth is what let a planner drop
    it and still score a perfect run.
    """

    categories: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    price_max: float | None = None
    in_stock: bool = True
    exclusions: tuple[str, ...] = ()


@dataclass(frozen=True)
class GoldenQuery:
    label: str
    query: str
    expected: tuple[str, ...]
    filters: Filters = field(default_factory=Filters)
    # A case that asserts "return nothing eligible" has no relevant ids to
    # recall, and averaging its 0.0 into the corpus would move the relevance
    # thresholds for a reason that has nothing to do with relevance.
    scored_for_recall: bool = True


def _canonical_anna_labels() -> tuple[str, tuple[str, ...]]:
    """Read the optional Anna evaluation labels from the backend source, not a copy.

    These are supplied judgments for the workshop's fixed query, outside the
    participant's plan-contract edit. They must not change between runs to
    make a result look better. They are a small evaluation set, not universal
    ground truth about gifts.

    Parsed rather than imported: importing that module constructs ``Settings``,
    so a harness that imported it could not even be read without database
    credentials in the environment.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "pellier"
        / "backend"
        / "services"
        / "planned_hybrid_retrieval.py"
    ).read_text(encoding="utf-8")

    wanted = {"CANONICAL_ANNA_QUERY": "", "CANONICAL_ANNA_GOLDEN_IDS": ()}
    for node in ast.walk(ast.parse(source)):
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target in wanted and node.value is not None:
            wanted[target] = ast.literal_eval(node.value)

    return str(wanted["CANONICAL_ANNA_QUERY"]), tuple(wanted["CANONICAL_ANNA_GOLDEN_IDS"])


_ANNA_QUERY, _ANNA_EXPECTED = _canonical_anna_labels()

GOLDEN_QUERIES: tuple[GoldenQuery, ...] = (
    GoldenQuery(
        "anna_housewarming",
        _ANNA_QUERY,
        _ANNA_EXPECTED,
        Filters(categories=("Home Decor", "Gifts"), tags=("gift", "home"), price_max=100),
    ),
    GoldenQuery(
        "goa_linen",
        "linen shirts and layers for ten days in Goa",
        ("11", "14", "16", "18"),
        Filters(categories=("Apparel",), tags=("linen", "travel", "resort")),
    ),
    GoldenQuery(
        "drawstring_trousers",
        "drawstring linen trousers for resort packing",
        ("14",),
        Filters(categories=("Apparel",), tags=("linen", "resort")),
    ),
    GoldenQuery(
        "panama_hat",
        "packable panama hat for coastal sun",
        ("19",),
        Filters(categories=("Accessories",), tags=("travel", "resort")),
    ),
    GoldenQuery(
        "dopp_kit",
        "canvas dopp kit for carry-on toiletries",
        ("12",),
        Filters(categories=("Accessories",), tags=("canvas", "travel")),
    ),
    GoldenQuery(
        "weekend_bag",
        "leather weekend bag for a 48 hour trip",
        ("3", "17"),
        Filters(categories=("Accessories",), tags=("leather", "travel")),
    ),
    GoldenQuery(
        "beeswax_under_50",
        "beeswax candle under fifty dollars",
        ("21", "38"),
        Filters(categories=("Home Decor",), tags=("candle", "artisanal"), price_max=50),
    ),
    GoldenQuery(
        "ring_dish",
        "small ceramic ring dish gift",
        ("23",),
        Filters(categories=("Home Decor",), tags=("ceramic", "gift"), price_max=50),
    ),
    GoldenQuery(
        "soap_gift",
        "handmade soap gift set",
        ("26",),
        Filters(categories=("Beauty",), tags=("beauty", "gift", "artisanal")),
    ),
    GoldenQuery(
        "pour_over",
        "stoneware pour over coffee ritual",
        ("31",),
        Filters(categories=("Home Decor",), tags=("ceramic", "slow")),
    ),
    GoldenQuery(
        "ceramic_tumblers",
        "charcoal ceramic tumblers set",
        ("36",),
        Filters(categories=("Home Decor",), tags=("ceramic",)),
    ),
    GoldenQuery(
        "table_runner",
        "linen table runner for dinner",
        ("39",),
        Filters(categories=("Home Decor",), tags=("linen", "home")),
    ),
    GoldenQuery(
        "linen_throw",
        "raw linen throw for sofa",
        ("32",),
        Filters(categories=("Home Decor",), tags=("linen", "slow")),
    ),
    GoldenQuery(
        "card_wallet",
        "minimal leather card wallet",
        ("13",),
        Filters(categories=("Accessories",), tags=("leather", "minimal")),
    ),
    GoldenQuery(
        "terracotta_planter",
        "terracotta planter for a patio",
        ("34",),
        Filters(categories=("Home Decor",), tags=("ceramic", "earth")),
    ),
    GoldenQuery(
        "merino_socks",
        "merino travel socks temperature regulating",
        ("20",),
        Filters(categories=("Apparel",), tags=("merino", "travel")),
    ),
    # A stated negative. Before exclusions survived extraction this query
    # scored a clean run while returning exactly what the shopper refused.
    GoldenQuery(
        "housewarming_no_candles",
        "a housewarming gift under $100, in stock, no candles",
        ("23", "36"),
        Filters(
            categories=("Home Decor", "Gifts"),
            tags=("gift", "home"),
            price_max=100,
            exclusions=("candle",),
        ),
    ),
    # An impossible ceiling. The only correct answer is an empty eligible set,
    # so this is scored for constraint compliance and excluded from recall.
    GoldenQuery(
        "impossible_budget",
        "a leather weekend bag under three dollars",
        (),
        Filters(categories=("Accessories",), tags=("leather",), price_max=3),
        scored_for_recall=False,
    ),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_env() -> None:
    for env_path in (_repo_root() / ".env", _repo_root() / "pellier" / "backend" / ".env"):
        if not env_path.is_file():
            continue
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip("'\"")


def _import_backend() -> dict[str, Any]:
    """Import the shipped planner, executor, and services from the backend.

    The harness is standalone, so the backend package is not on the path
    by default. Importing it here (rather than reimplementing retrieval)
    is the whole point: an evaluation that scores its own private copy of
    the pipeline cannot detect a regression in the shipped one.
    """
    backend = _repo_root() / "pellier" / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from services import search_plan  # noqa: PLC0415
    from services.database import DatabaseService  # noqa: PLC0415
    from services.planned_hybrid_retrieval import execute_search_plan  # noqa: PLC0415
    from services.rerank import get_rerank_service  # noqa: PLC0415
    from services.structured_extract import get_structured_extractor  # noqa: PLC0415

    return {
        "build_plan": search_plan.build_plan,
        "strategies": {
            "vector": search_plan.STRATEGY_VECTOR,
            "hybrid": search_plan.STRATEGY_HYBRID,
            "rerank": search_plan.STRATEGY_HYBRID_RERANK,
        },
        "strict_policy": search_plan.RELAXATION_POLICY_STRICT,
        "database_service": DatabaseService,
        "execute_search_plan": execute_search_plan,
        "rerank": get_rerank_service().rerank,
        "extractor": get_structured_extractor(),
    }


def _embed_queries(queries: list[str], *, region: str, model_id: str) -> list[list[float]]:
    body = {
        "texts": queries,
        "input_type": "search_query",
        "embedding_types": ["float"],
        "output_dimension": 1024,
    }
    client = boto3.client("bedrock-runtime", region_name=region)
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(response["body"].read())
    embeddings = payload.get("embeddings", {})
    vectors = embeddings.get("float", []) if isinstance(embeddings, dict) else embeddings
    if len(vectors) != len(queries):
        raise RuntimeError(f"Expected {len(queries)} embeddings, got {len(vectors)}")
    for vector in vectors:
        if len(vector) != 1024:
            raise RuntimeError(f"Expected 1024-dim embedding, got {len(vector)}")
    return [[float(v) for v in vector] for vector in vectors]


def _plan_for(build_plan: Any, golden: "GoldenQuery", extractor: Any, top_k: int) -> Any:
    """Run the shipped extractor + planner for one golden query.

    Falls back to an empty extraction when the model call fails, which
    scores as a planner miss rather than silently substituting the pinned
    oracle filters.
    """
    try:
        extracted = extractor.extract(golden.query)
    except Exception as exc:  # pragma: no cover - live Bedrock failure path
        print(f"  ! extractor failed for {golden.label}: {exc}")
        extracted = {}
    return build_plan(golden.query, extracted, top_k=top_k)


def _baseline_plan(backend: dict[str, Any], query: str, strategy: str, top_k: int) -> Any:
    """A plan with no model input for the three non-agentic rows.

    ``in_stock_only`` is pinned so the baselines measure the sellable
    catalog, the same population the golden ids were labeled against.
    """
    return backend["build_plan"](
        query,
        {"in_stock_only": True},
        top_k=top_k,
        retrieval_strategy=backend["strategies"][strategy],
        relaxation_policy=backend["strict_policy"],
    )


def _executor_config(args: argparse.Namespace) -> dict[str, Any]:
    pool_k = max(1, int(args.pool_k))
    return {
        "k_vector": pool_k,
        "k_fts": pool_k,
        "rrf_k": int(args.rrf_k),
        "top_n": max(pool_k, int(args.top_k)),
        "rerank_pool_k": pool_k,
    }


def _score_plan(plan: Any, expected: Filters) -> dict[str, Any]:
    """Compare a produced plan against the golden query's pinned filters.

    Returns per-query planner metrics: how much of the expected
    constraint set the planner recovered, and whether it invented a
    constraint nobody asked for (the more dangerous error, since an
    invented hard constraint silently removes valid results).
    """
    expected_categories = {c.lower() for c in expected.categories}
    got_categories = {c.lower() for c in plan.hard.categories}
    expected_price = expected.price_max
    got_price = plan.hard.price_max_usd

    recovered = 0
    total = 0
    hallucinated = 0

    if expected_categories:
        total += 1
        if expected_categories & got_categories:
            recovered += 1
    if got_categories - expected_categories and expected_categories:
        hallucinated += 1
    elif got_categories and not expected_categories:
        hallucinated += 1

    if expected_price is not None:
        total += 1
        # A tighter ceiling than asked for is still a miss: it removes
        # valid candidates.
        if got_price is not None and abs(got_price - expected_price) < 0.01:
            recovered += 1
    elif got_price is not None:
        hallucinated += 1

    # Stock. A dropped in-stock requirement is the quietest planner failure
    # there is: nothing looks wrong until a shopper is offered something the
    # warehouse cannot ship.
    if expected.in_stock:
        total += 1
        if plan.hard.in_stock_only:
            recovered += 1
    elif plan.hard.in_stock_only:
        hallucinated += 1

    # Exclusions, scored per requested term rather than as a set, so dropping
    # one of two stated negatives is a partial miss and not a pass.
    expected_exclusions = {e.lower() for e in expected.exclusions}
    got_exclusions = {e.lower() for e in plan.exclusions}
    for term in expected_exclusions:
        total += 1
        if term in got_exclusions:
            recovered += 1
    hallucinated += len(got_exclusions - expected_exclusions)

    return {
        "expected_categories": sorted(expected_categories),
        "planned_categories": sorted(got_categories),
        "expected_price_max": expected_price,
        "planned_price_max": got_price,
        "expected_in_stock": expected.in_stock,
        "expected_exclusions": sorted(expected_exclusions),
        "planned_in_stock_only": plan.hard.in_stock_only,
        "planned_exclusions": list(plan.exclusions),
        "planned_soft_tags": list(plan.soft.tags),
        "constraints_recovered": recovered,
        "constraints_expected": total,
        "hallucinated_constraints": hallucinated,
        "relaxations": [r.step for r in plan.relaxations],
    }


def _score_compliance(rows: list[dict[str, Any]], plan: Any) -> dict[str, int]:
    """Count returned rows that violate the plan's own hard constraints.

    This is the metric the audit's A3 finding is really about: if filters
    are applied after reranking (or not at all), invalid rows reach the
    result list. Scoring compliance on the *returned* rows catches that
    regardless of where filtering was supposed to happen.
    """
    return _count_violations(
        rows,
        price_max=plan.hard.price_max_usd,
        categories={c.lower() for c in plan.hard.categories},
        exclusions={t.lower() for t in plan.exclusions},
        in_stock=bool(plan.hard.in_stock_only),
    )


def _score_requested_compliance(
    rows: list[dict[str, Any]], expected: Filters
) -> dict[str, int]:
    """Count returned rows that violate what the SHOPPER asked for.

    ``_score_compliance`` scores the plan the planner produced, which makes the
    plan both the thing under test and the test oracle: a requirement the
    planner silently dropped disappears from the plan and therefore from the
    measurement, and the run scores clean. This scores the same rows against
    the pinned golden filters instead, so a dropped constraint shows up as a
    violation rather than as an absence. The two numbers answer different
    questions and are reported separately on purpose:

        requested  -- did the shopper get what they asked for?
        planned    -- did the executor honour the plan it was given?
    """
    return _count_violations(
        rows,
        price_max=expected.price_max,
        categories={c.lower() for c in expected.categories},
        exclusions={e.lower() for e in expected.exclusions},
        in_stock=bool(expected.in_stock),
    )


def _count_violations(
    rows: list[dict[str, Any]],
    *,
    price_max: float | None,
    categories: set[str],
    exclusions: set[str],
    in_stock: bool,
) -> dict[str, int]:
    """One violation counter, used against a plan and against the truth."""
    hard_violations = 0
    exclusion_violations = 0
    for row in rows:
        price = row.get("price")
        if price_max is not None and price is not None and float(price) > price_max + 0.001:
            hard_violations += 1
        category = str(row.get("category") or "").lower()
        if categories and category and category not in categories:
            hard_violations += 1
        # Stock was never counted here. An out-of-stock row under a plan that
        # required in-stock results scored zero violations, which is precisely
        # the failure this whole function exists to catch.
        quantity = row.get("quantity")
        if in_stock and quantity is not None:
            try:
                if float(quantity) <= 0:
                    hard_violations += 1
            except (TypeError, ValueError):
                pass
        row_tags = {str(t).lower() for t in (row.get("tags") or [])}
        if exclusions and (row_tags & exclusions):
            exclusion_violations += 1
    return {
        "rows": len(rows),
        "hard_violations": hard_violations,
        "exclusion_violations": exclusion_violations,
    }


def _recall_at_5(product_ids: list[str], expected: tuple[str, ...]) -> tuple[int, int, float]:
    hits = len(set(product_ids[:5]) & set(expected))
    total = len(expected)
    return hits, total, hits / total if total else 0.0


def _recall(product_ids: list[str], expected: tuple[str, ...]) -> tuple[int, int, float]:
    hits = len(set(product_ids) & set(expected))
    total = len(expected)
    return hits, total, hits / total if total else 0.0


def _mrr_at_5(product_ids: list[str], expected: tuple[str, ...]) -> float:
    expected_set = set(expected)
    for idx, product_id in enumerate(product_ids[:5], start=1):
        if product_id in expected_set:
            return 1.0 / idx
    return 0.0


def _hit_at_1(product_ids: list[str], expected: tuple[str, ...]) -> int:
    return int(bool(product_ids) and product_ids[0] in set(expected))


def _print_summary(results: dict[str, list[tuple[int, int, float, int, int]]]) -> None:
    print("strategy | hits | expected | recall@5 | hit@1 | mrr@5 | short@5")
    print("---------|------|----------|----------|-------|-------|--------")
    for strategy, pairs in results.items():
        hits = sum(pair[0] for pair in pairs)
        expected = sum(pair[1] for pair in pairs)
        recall = hits / expected if expected else 0.0
        mrr = sum(pair[2] for pair in pairs) / len(pairs) if pairs else 0.0
        hit_at_1 = sum(pair[3] for pair in pairs) / len(pairs) if pairs else 0.0
        short_rate = sum(pair[4] for pair in pairs) / len(pairs) if pairs else 0.0
        print(
            f"{strategy:<8} | {hits:>4} | {expected:>8} | {recall:.3f}    | "
            f"{hit_at_1:.3f} | {mrr:.3f} | {short_rate:.3f}"
        )


def _metric_totals(
    results: dict[str, list[tuple[int, int, float, int, int]]],
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for strategy, pairs in results.items():
        hits = sum(pair[0] for pair in pairs)
        expected = sum(pair[1] for pair in pairs)
        count = len(pairs) or 1
        out[strategy] = {
            "hits": hits,
            "expected": expected,
            "recall_at_5": round(hits / expected if expected else 0.0, 3),
            "hit_at_1": round(sum(pair[3] for pair in pairs) / count, 3),
            "mrr_at_5": round(sum(pair[2] for pair in pairs) / count, 3),
            "short_result_rate_at_5": round(sum(pair[4] for pair in pairs) / count, 3),
        }
    return out


def _timing_totals(timings: dict[str, list[float]]) -> dict[str, float]:
    return {
        strategy: round((sum(values) / len(values)) * 1000, 1) if values else 0.0
        for strategy, values in timings.items()
    }


def _planner_totals(scores: list[dict[str, Any]]) -> dict[str, float]:
    """Aggregate per-query planner scores into rates."""
    expected = sum(int(s["constraints_expected"]) for s in scores)
    recovered = sum(int(s["constraints_recovered"]) for s in scores)
    hallucinated = sum(int(s["hallucinated_constraints"]) for s in scores)
    queries = len(scores) or 1
    return {
        "constraints_expected": expected,
        "constraints_recovered": recovered,
        "constraint_recall": round(recovered / expected, 3) if expected else 1.0,
        "hallucinated_constraints": hallucinated,
        "hallucinated_constraint_rate": round(hallucinated / queries, 3),
    }


def _compliance_totals(scores: list[dict[str, int]]) -> dict[str, float]:
    """Aggregate hard-constraint compliance over all returned rows."""
    rows = sum(int(s["rows"]) for s in scores)
    hard = sum(int(s["hard_violations"]) for s in scores)
    exclusion = sum(int(s["exclusion_violations"]) for s in scores)
    denominator = rows or 1
    return {
        "rows_scored": rows,
        "hard_violations": hard,
        "hard_constraint_violation_rate": round(hard / denominator, 3),
        "exclusion_violations": exclusion,
        "exclusion_violation_rate": round(exclusion / denominator, 3),
    }


def _evaluate_gate(
    *,
    totals: dict[str, dict[str, float]],
    coverage: float,
    planner: dict[str, float],
    compliance: dict[str, float],
    requested: dict[str, float],
    strict_planner: bool,
) -> dict[str, Any]:
    """Check every threshold and return the pass/fail verdict.

    Returns a dict with ``passed`` and a ``failures`` list of
    human-readable strings, so both the JSON and the text output can
    report exactly which threshold moved.
    """
    checks: list[tuple[str, float, float, bool]] = [
        (
            "rerank recall@5",
            totals["rerank"]["recall_at_5"],
            THRESHOLDS["rerank_recall_at_5_min"],
            True,
        ),
        (
            "rerank mrr@5",
            totals["rerank"]["mrr_at_5"],
            THRESHOLDS["rerank_mrr_at_5_min"],
            True,
        ),
        (
            "agentic recall@5",
            totals["agentic"]["recall_at_5"],
            THRESHOLDS["agentic_recall_at_5_min"],
            True,
        ),
        (
            "hybrid candidate coverage",
            coverage,
            THRESHOLDS["hybrid_candidate_coverage_min"],
            True,
        ),
        (
            "hard-constraint violation rate",
            compliance["hard_constraint_violation_rate"],
            THRESHOLDS["hard_constraint_violation_rate_max"],
            False,
        ),
        (
            "requested-constraint violation rate",
            requested["hard_constraint_violation_rate"],
            THRESHOLDS["requested_constraint_violation_rate_max"],
            False,
        ),
        (
            "requested-exclusion violation rate",
            requested["exclusion_violation_rate"],
            THRESHOLDS["requested_exclusion_violation_rate_max"],
            False,
        ),
        (
            "exclusion violation rate",
            compliance["exclusion_violation_rate"],
            THRESHOLDS["exclusion_violation_rate_max"],
            False,
        ),
        (
            "planner hallucinated-constraint rate",
            planner["hallucinated_constraint_rate"],
            THRESHOLDS["planner_hallucinated_constraint_rate_max"],
            False,
        ),
    ]
    if strict_planner:
        checks.append(
            ("planner constraint recall", planner["constraint_recall"], PLANNER_RECALL_MIN, True)
        )

    failures: list[str] = []
    for label, observed, threshold, is_floor in checks:
        if is_floor and observed < threshold:
            failures.append(f"{label} {observed:.3f} below floor {threshold:.3f}")
        elif not is_floor and observed > threshold:
            failures.append(f"{label} {observed:.3f} above ceiling {threshold:.3f}")

    return {
        "passed": not failures,
        "failures": failures,
        "thresholds": dict(THRESHOLDS),
        "strictPlanner": strict_planner,
    }


async def _run_strategies(
    db: Any,
    golden: GoldenQuery,
    vector: list[float],
    *,
    backend: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, dict[str, Any]]:
    """Run the four strategies for one golden query through the executor.

    The embedding was batched up front, so ``embed`` hands it back unchanged
    and the per-strategy timing covers retrieval, fusion, rerank, and the
    eligibility recheck only. The agentic row is the only one allowed to
    widen: it runs the shipped relaxation ladder exactly as the storefront
    tool does. Baseline rows use a strict single-rung plan.
    """
    config = _executor_config(args)
    top_k = int(args.top_k)

    def embed(_query: str) -> list[float]:
        return vector

    plans = {
        "vector": (_baseline_plan(backend, golden.query, "vector", top_k), False),
        "hybrid": (_baseline_plan(backend, golden.query, "hybrid", top_k), False),
        "rerank": (_baseline_plan(backend, golden.query, "rerank", top_k), False),
        "agentic": (
            _plan_for(backend["build_plan"], golden, backend["extractor"], top_k),
            True,
        ),
    }
    outcomes: dict[str, dict[str, Any]] = {}
    for strategy in STRATEGIES:
        plan, relax = plans[strategy]
        started = time.perf_counter()
        execution = await backend["execute_search_plan"](
            db,
            plan=plan,
            query=golden.query,
            limit=top_k,
            embed=embed,
            rerank=backend["rerank"],
            config=config,
            relax=relax,
        )
        outcomes[strategy] = {
            "execution": execution,
            "elapsed_s": time.perf_counter() - started,
        }
    return outcomes


def _detail_for(
    golden: GoldenQuery,
    outcomes: dict[str, dict[str, Any]],
    *,
    top_k: int,
) -> dict[str, Any]:
    """Score one golden query's outcomes into the per-query report row.

    Coverage is labeled with the pool the executor actually used, read back
    off the execution. ``--pool-k`` is a request, not a setting: the executor
    clamps it to the reranker's document cap and ``HybridSearch`` raises each
    branch to at least five, so reporting the requested number would label a
    pool of 30 as "@50".
    """
    agentic = outcomes["agentic"]["execution"]
    detail: dict[str, Any] = {
        "label": golden.label,
        "query": golden.query,
        "expected": list(golden.expected),
        "latency_ms": {
            strategy: round(outcomes[strategy]["elapsed_s"] * 1000, 1)
            for strategy in STRATEGIES
        },
        "stage_latency_ms": {
            strategy: outcomes[strategy]["execution"].latency_breakdown()
            for strategy in STRATEGIES
        },
    }
    hybrid_execution = outcomes["hybrid"]["execution"]
    pool_ids = [str(row["product_id"]) for row in hybrid_execution.rerank_pool]
    coverage_hits, coverage_total, coverage = _recall(pool_ids, golden.expected)
    detail["hybrid_candidate_coverage"] = {
        "pool_k": hybrid_execution.rerank_pool_k,
        "hits": coverage_hits,
        "expected": coverage_total,
        "coverage": round(coverage, 3),
    }
    detail["planner"] = _score_plan(agentic.plan, golden.filters)
    detail["agentic_hard_constraint_compliance"] = _score_compliance(
        agentic.returned, agentic.plan
    )
    detail["agentic_requested_compliance"] = _score_requested_compliance(
        agentic.returned, golden.filters
    )
    detail["scored_for_recall"] = golden.scored_for_recall
    detail["search_plan"] = agentic.plan.to_dict()
    for strategy in STRATEGIES:
        product_ids = [
            str(row["product_id"]) for row in outcomes[strategy]["execution"].returned
        ]
        hits, total, recall = _recall_at_5(product_ids, golden.expected)
        detail[strategy] = {
            "top5": product_ids[:5],
            "hits": hits,
            "expected": total,
            "recall_at_5": round(recall, 3),
            "hit_at_1": _hit_at_1(product_ids, golden.expected),
            "mrr_at_5": round(_mrr_at_5(product_ids, golden.expected), 3),
            "short_result_at_5": len(product_ids) < top_k,
        }
    return detail


async def _evaluate(args: argparse.Namespace, backend: dict[str, Any]) -> dict[str, Any]:
    """Run every golden query and aggregate the report."""
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    embed_model = (
        os.environ.get("BEDROCK_EMBEDDING_MODEL")
        or os.environ.get("BEDROCK_EMBED_MODEL_ID")
        or EMBED_MODEL_DEFAULT
    )
    rerank_model = os.environ.get("BEDROCK_RERANK_MODEL") or RERANK_MODEL_DEFAULT
    pool_k = max(1, int(args.pool_k))

    started = time.perf_counter()
    embed_started = time.perf_counter()
    vectors = _embed_queries([q.query for q in GOLDEN_QUERIES], region=region, model_id=embed_model)
    embed_elapsed_s = time.perf_counter() - embed_started

    detailed: list[dict[str, Any]] = []
    db = backend["database_service"]()
    await db.connect()
    try:
        for golden, vector in zip(GOLDEN_QUERIES, vectors):
            outcomes = await _run_strategies(db, golden, vector, backend=backend, args=args)
            detailed.append(_detail_for(golden, outcomes, top_k=int(args.top_k)))
    finally:
        await db.disconnect()

    # What the executor resolved, not what the flag asked for.
    resolved_pool_k = (
        detailed[0]["hybrid_candidate_coverage"]["pool_k"] if detailed else pool_k
    )

    # Relevance is averaged over queries that HAVE relevant results. A
    # no-result case contributes a truthful 0.0 recall that means "correctly
    # returned nothing", and averaging that into the corpus would lower the
    # relevance thresholds to accommodate a constraint test.
    recall_scored = [item for item in detailed if item.get("scored_for_recall", True)]
    summary = {
        strategy: [
            (
                item[strategy]["hits"],
                item[strategy]["expected"],
                item[strategy]["mrr_at_5"],
                item[strategy]["hit_at_1"],
                int(item[strategy]["short_result_at_5"]),
            )
            for item in recall_scored
        ]
        for strategy in STRATEGIES
    }
    timings = {
        strategy: [item["latency_ms"][strategy] / 1000 for item in detailed]
        for strategy in STRATEGIES
    }
    totals = _metric_totals(summary)
    coverage_hits = sum(item["hybrid_candidate_coverage"]["hits"] for item in recall_scored)
    coverage_expected = sum(
        item["hybrid_candidate_coverage"]["expected"] for item in recall_scored
    )
    coverage_total = round(coverage_hits / coverage_expected if coverage_expected else 0.0, 3)
    planner_totals = _planner_totals([item["planner"] for item in detailed])
    compliance_totals = _compliance_totals(
        [item["agentic_hard_constraint_compliance"] for item in detailed]
    )
    # Every query is scored for constraint compliance, including the ones
    # excluded from recall: "return nothing eligible" is a constraint claim.
    requested_totals = _compliance_totals(
        [item["agentic_requested_compliance"] for item in detailed]
    )
    return {
        "query_count": len(GOLDEN_QUERIES),
        "recall_scored_query_count": len(recall_scored),
        "rrf_k": args.rrf_k,
        "pool_k": resolved_pool_k,
        "requested_pool_k": int(args.pool_k),
        "top_k": args.top_k,
        "embed_model": embed_model,
        "rerank_model": rerank_model,
        "executor": "services.planned_hybrid_retrieval.execute_search_plan",
        "elapsed_s": round(time.perf_counter() - started, 2),
        "embedding_batch_ms": round(embed_elapsed_s * 1000, 1),
        "avg_strategy_latency_ms": _timing_totals(timings),
        "summary": totals,
        "hybrid_candidate_coverage_at_pool": coverage_total,
        "rerank_lift_mrr_vs_hybrid": round(
            totals["rerank"]["mrr_at_5"] - totals["hybrid"]["mrr_at_5"], 3
        ),
        "agentic_lift_mrr_vs_hybrid": round(
            totals["agentic"]["mrr_at_5"] - totals["hybrid"]["mrr_at_5"], 3
        ),
        "planner": planner_totals,
        "hard_constraint_compliance": compliance_totals,
        "requested_constraint_compliance": requested_totals,
        "gate": _evaluate_gate(
            totals=totals,
            coverage=coverage_total,
            planner=planner_totals,
            compliance=compliance_totals,
            requested=requested_totals,
            strict_planner=args.strict_planner,
        ),
        "queries": detailed,
        "_summary_pairs": summary,
    }


def _print_report(report: dict[str, Any], *, no_gate: bool) -> None:
    """Render the human-readable report."""
    pool_k = report["pool_k"]
    requested = report.get("requested_pool_k", pool_k)
    pool_label = f"{pool_k}" if requested == pool_k else f"{pool_k} (requested {requested})"
    print(
        f"Pellier retrieval eval | queries={report['query_count']} | "
        f"rrf_k={report['rrf_k']} | pool_k={pool_label} | top_k={report['top_k']}"
    )
    print(f"Models: {report['embed_model']} + {report['rerank_model']}")
    print(f"Executor: {report['executor']}")
    print()
    _print_summary(report["_summary_pairs"])
    print()
    print(f"embedding batch latency: {report['embedding_batch_ms']:.1f} ms")
    print("avg strategy latency (ms): " + " | ".join(
        f"{strategy} {latency:.1f}"
        for strategy, latency in report["avg_strategy_latency_ms"].items()
    ))
    print(f"hybrid candidate coverage@pool_k: {report['hybrid_candidate_coverage_at_pool']:.3f}")
    print(
        f"mrr@5 lift vs hybrid: rerank {report['rerank_lift_mrr_vs_hybrid']:+.3f} | "
        f"agentic {report['agentic_lift_mrr_vs_hybrid']:+.3f}"
    )
    print()
    print("query | expected | vector@5 | hybrid@5 | rerank@5 | agentic@5")
    print("------|----------|----------|----------|----------|----------")
    for item in report["queries"]:
        print(
            f"{item['label']} | {','.join(item['expected'])} | "
            f"{','.join(item['vector']['top5']) or '-'} | "
            f"{','.join(item['hybrid']['top5']) or '-'} | "
            f"{','.join(item['rerank']['top5']) or '-'} | "
            f"{','.join(item['agentic']['top5']) or '-'}"
        )
    print()
    planner = report["planner"]
    compliance = report["hard_constraint_compliance"]
    print(
        "planner: constraint recall "
        f"{planner['constraint_recall']:.3f} "
        f"({planner['constraints_recovered']}/{planner['constraints_expected']}) | "
        f"hallucinated-constraint rate {planner['hallucinated_constraint_rate']:.3f}"
    )
    print(
        "hard-constraint compliance: "
        f"violations {compliance['hard_violations']}/{compliance['rows_scored']} rows "
        f"(rate {compliance['hard_constraint_violation_rate']:.3f}) | "
        f"exclusion violations {compliance['exclusion_violations']} "
        f"(rate {compliance['exclusion_violation_rate']:.3f})"
    )
    print()
    gate = report["gate"]
    if gate["passed"]:
        print("GATE: PASS. Every threshold met.")
    else:
        print("GATE: FAIL")
        for failure in gate["failures"]:
            print(f"  - {failure}")
        if no_gate:
            print("  (--no-gate set: reporting only, exit status forced to 0)")
    print()
    print(f"Elapsed: {report['elapsed_s']:.1f}s")


def compare_saved_runs(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Score Lab 2's existing captures; never run retrieval or infer SQL proof.

    Use the same relevance functions and labels as the live harness. Refuse
    incomparable captures rather than manufacture a before/after improvement.
    Database eligibility and receipt correlation remain separate lab checks.
    """
    rows = []
    for capture in (before, after):
        if not isinstance(capture, dict) or capture.get("query") != _ANNA_QUERY:
            raise ValueError("Both captures must contain the fixed Anna query.")
        receipt = capture.get("receipt", {})
        if (not isinstance(receipt, dict) or receipt.get("persisted") is not True
                or not isinstance(receipt.get("comparisonId"), str)
                or not receipt["comparisonId"].strip()):
            raise ValueError("Each capture needs a persisted comparison ID; keep the SQL proof separately.")
        strategies = capture.get("strategies", [])
        if not isinstance(strategies, list):
            raise ValueError("Capture strategies must be a list.")
        matches = [row for row in strategies if isinstance(row, dict)
                   and row.get("shares_storefront_executor") is True]
        if len(matches) != 1:
            raise ValueError("Each capture needs exactly one Storefront executor result.")
        row = matches[0]
        rerank = row.get("rerank", {})
        if not isinstance(rerank, dict) or rerank.get("status") != "applied":
            raise ValueError("Rerank must have applied in both runs; a fallback is not comparable.")
        if not isinstance(rerank.get("model"), str) or not rerank["model"].strip():
            raise ValueError("The executed rerank model is missing.")
        products = row.get("products")
        candidates = rerank.get("candidateIds")
        if not isinstance(products, list) or not products or not isinstance(candidates, list) or not candidates:
            raise ValueError("Both captures need returned products and rerank candidate IDs.")
        ids = [product.get("productId") if isinstance(product, dict) else None for product in products]
        if any(not isinstance(pid, str) or not pid.strip() for pid in ids + candidates):
            raise ValueError("Product and candidate IDs must be non-empty strings.")
        if len(set(ids)) != len(ids) or len(set(candidates)) != len(candidates):
            raise ValueError("Duplicate IDs cannot count as additional evidence.")
        if not set(ids).issubset(candidates):
            raise ValueError("Returned products must belong to the recorded rerank pool.")
        if not isinstance(row.get("searchPlan"), dict) or not row["searchPlan"]:
            raise ValueError("The executed search plan is missing.")
        rows.append(row)
    if before["receipt"]["comparisonId"] == after["receipt"]["comparisonId"]:
        raise ValueError("Before and after must be different comparisons.")
    plans = [row["searchPlan"] for row in rows]
    for plan in plans:
        hard = plan.get("hard_constraints")
        if (not isinstance(hard, dict) or hard.get("price_max_usd") != 100
                or hard.get("in_stock_only") is not True):
            raise ValueError("Both plans must retain Anna's $100 ceiling and in-stock constraint; verify the actual rows in SQL.")
    if (plans[0]["hard_constraints"] != plans[1]["hard_constraints"]
            or plans[0].get("exclusions") != plans[1].get("exclusions")):
        raise ValueError("Hard constraints or exclusions changed; this is not a pool-only comparison.")
    if rows[0]["rerank"]["model"] != rows[1]["rerank"]["model"]:
        raise ValueError("The rerank model changed; this is not a pool-only comparison.")
    if not _ANNA_EXPECTED:
        raise ValueError("Anna's supplied relevance judgments are missing.")

    def score(capture: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
        ids = [product["productId"] for product in row["products"]]
        return {
            "comparison_id": capture["receipt"]["comparisonId"],
            "returned_ids": ids,
            "pool_k": row["rerank"].get("poolK"),
            "rerank_model": row["rerank"]["model"],
            "candidate_coverage": _recall(row["rerank"]["candidateIds"], _ANNA_EXPECTED)[2],
            "recall_at_5": _recall_at_5(ids, _ANNA_EXPECTED)[2],
            "mrr_at_5": _mrr_at_5(ids, _ANNA_EXPECTED),
            "hit_at_1": _hit_at_1(ids, _ANNA_EXPECTED),
            "observed_ms": row.get("observedMs"),
            "modeled_cost_per_thousand_usd": row.get("modeledCostPerThousandUsd"),
        }

    first, second = score(before, rows[0]), score(after, rows[1])
    delta = {metric: round(second[metric] - first[metric], 6) for metric in
             ("candidate_coverage", "recall_at_5", "mrr_at_5", "hit_at_1")}
    quality = [delta[metric] for metric in ("recall_at_5", "mrr_at_5", "hit_at_1")]
    improved, declined = any(value > 0 for value in quality), any(value < 0 for value in quality)
    return {
        "status": "measured",
        "query": _ANNA_QUERY,
        "label_source": "services/planned_hybrid_retrieval.py:CANONICAL_ANNA_GOLDEN_IDS",
        "relevant_ids": list(_ANNA_EXPECTED),
        "before": first,
        "after": second,
        "delta": delta,
        "quality_change": "mixed" if improved and declined else "improved" if improved else "declined" if declined else "unchanged",
        "comparison_context": {
            "same_executed_plan": plans[0] == plans[1],
            "before_plan": plans[0],
            "after_plan": plans[1],
            "interpretation": (
                "Same recorded plan. These scores describe the two saved results, not a causal guarantee."
                if plans[0] == plans[1] else
                "The executed plan also changed. Compare soft preferences and relaxations; do not attribute the score difference to pool size alone."
            ),
        },
        "limits": [
            "One query with supplied relevance judgments; not a production quality gate.",
            "Candidate coverage is not returned-result quality. Preserve unchanged and worse results.",
            "Saved captures are not independently authenticated; verify exact receipts and eligibility in SQL.",
            "Observed latency is one sample; modeled cost is not a bill. This command makes no service calls.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Pellier golden-query retrieval evaluation."
    )
    parser.add_argument(
        "--rrf-k", type=int, default=60, help="RRF damping constant for hybrid strategies."
    )
    parser.add_argument(
        "--pool-k",
        type=int,
        default=20,
        help="Candidate count per vector/FTS branch before RRF, and the rerank pool bound.",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--compare-saved", nargs=2, type=Path, metavar=("BEFORE", "AFTER"),
        help="Score Lab 2's saved comparison JSON with the existing Anna labels; no AWS calls. Always emits JSON.",
    )
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="Report metrics without failing the run on a threshold regression.",
    )
    parser.add_argument(
        "--strict-planner",
        action="store_true",
        help="Also gate on planner constraint recall (moves with model behaviour).",
    )
    args = parser.parse_args()

    if args.compare_saved:
        try:
            captures = [json.loads(path.read_text()) for path in args.compare_saved]
            report = compare_saved_runs(*captures)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(report, indent=2))
        return 0  # Measurements exist, not a claim that quality improved.

    _load_env()
    backend = _import_backend()
    report = asyncio.run(_evaluate(args, backend))
    passed = report["gate"]["passed"]
    if args.json:
        report.pop("_summary_pairs", None)
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_report(report, no_gate=args.no_gate)
    return 0 if (passed or args.no_gate) else 1


if __name__ == "__main__":
    raise SystemExit(main())
