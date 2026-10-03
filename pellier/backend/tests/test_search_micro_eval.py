"""Contract tests for the Observatory micro-eval and the canonical golden set.

The micro-eval runs the canonical Anna query through the shared executor at
different rerank pool sizes and reports what a smaller pool costs. The
numbers must come from the executor's own evidence: the pool the reranker
saw, the rows returned, the rows cited.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

import os

import pytest

import app as app_module
import services.embeddings as embeddings_module
import services.hybrid_search as hybrid_module
import services.planned_hybrid_retrieval as retrieval_module
import services.rerank as rerank_module
import services.structured_extract as extract_module

REPO = Path(__file__).resolve().parents[3]
HARNESS = REPO / "scripts" / "eval_retrieval_harness.py"

CANONICAL_QUERY = "A housewarming gift under $100 that is currently in stock."


class _Embedding:
    def embed_query(self, query: str) -> list[float]:
        return [0.1] * 1024


def _rows(count: int) -> list[dict[str, Any]]:
    return [
        {
            "product_id": str(index),
            "name": f"Gift {index}",
            "description": "A considered housewarming object",
            "category": "Home Decor",
            "price": 40.0 + index,
            "tags": ["gift", "home"],
            "quantity": 6,
            "updated_at": "2026-09-04T00:00:00+00:00",
            "vec_rank": index,
            "fts_rank": None,
            "rrf_score": 1.0 / (60 + index),
        }
        for index in range(1, count + 1)
    ]


class _HybridSearch:
    rows: list[dict[str, Any]] = _rows(6)

    def __init__(self, db: Any) -> None:
        self.db = db

    async def search(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [dict(row) for row in self.rows]


class _Reranker:
    """Keeps RRF order so the golden ranks stay predictable, and counts calls."""

    def __init__(self) -> None:
        self.calls = 0

    def rerank(self, *, query: str, documents: list[str], top_n: int) -> list[dict]:
        self.calls += 1
        return [
            {"index": index, "relevance_score": 1.0 - index * 0.05}
            for index in range(min(top_n, len(documents)))
        ]


class _Extractor:
    def extract(self, query: str) -> dict[str, Any]:
        return {
            "categories": ["Home Decor"],
            "tags": [],
            "price_max_usd": 100,
            "in_stock_only": True,
            "exclusions": [],
            "soft_signal": "housewarming gift",
        }


@pytest.fixture
def stub_services(monkeypatch: pytest.MonkeyPatch) -> _Reranker:
    """Offline services plus a fixture golden set of ids 1 to 5.

    Returns the shared reranker so a test can count how many Bedrock calls
    the route would have made.
    """
    reranker = _Reranker()
    monkeypatch.setattr(app_module, "db_service", object())
    monkeypatch.setattr(embeddings_module, "EmbeddingService", _Embedding)
    monkeypatch.setattr(hybrid_module, "HybridSearch", _HybridSearch)
    monkeypatch.setattr(rerank_module, "get_rerank_service", lambda: reranker)
    monkeypatch.setattr(extract_module, "get_structured_extractor", lambda: _Extractor())
    monkeypatch.setattr(
        retrieval_module, "CANONICAL_ANNA_GOLDEN_IDS", ("1", "2", "3", "4", "5")
    )
    monkeypatch.setattr(retrieval_module, "CANONICAL_HELD_OUT_GOLDEN_IDS", ("2", "3"))
    monkeypatch.setattr(_HybridSearch, "rows", _rows(6))
    return reranker


def _variant(body: dict[str, Any], pool_k: int) -> dict[str, Any]:
    for variant in body["variants"]:
        if variant["pool_k"] == pool_k:
            return variant
    raise AssertionError(f"no variant for pool_k={pool_k}: {body['variants']}")


def test_micro_eval_envelope_matches_the_frontend_contract(stub_services: _Reranker) -> None:
    body = asyncio.run(app_module.micro_eval_search_strategies(pool_k=[20, 3]))

    assert set(body) == {
        "query",
        "limit",
        "repetitions",
        # Lab 1b's labelled set. Every quality ratio below divides by it, so
        # the surface needs the count to tell "unlabelled" from "scored zero".
        "golden_set_size",
        "variants",
        # The same knob scored on provided labels for a second query, and the
        # verdict on whether the tuning winner holds there.
        "held_out",
        "held_out_cases",
        "generalizes",
    }
    assert body["golden_set_size"] == len(retrieval_module.CANONICAL_ANNA_GOLDEN_IDS)
    assert body["query"] == CANONICAL_QUERY
    assert body["limit"] == 5
    assert body["repetitions"] == retrieval_module.MICRO_EVAL_REPETITIONS_DEFAULT == 3
    assert [variant["pool_k"] for variant in body["variants"]] == [20, 3]
    expected_keys = {
        "pool_k",
        "candidate_coverage",
        "context_precision",
        "mrr",
        "hard_constraint_violations",
        "short_result_rate",
        "citation_coverage",
        "latency_ms_p50",
        "latency_ms_p95",
        # Cold and warm reported apart: repetitions send an identical rerank
        # request, so every sample after the first is a cache hit rather than a
        # second Bedrock call. One blended percentile described neither.
        "latency_cold_ms",
        "latency_warm_ms_p50",
        "latency_samples",
        "rerank_cache",
    }
    for variant in body["variants"]:
        assert set(variant) == expected_keys
        assert variant["latency_ms_p95"] >= variant["latency_ms_p50"] >= 0
        assert variant["latency_cold_ms"] >= 0
        assert variant["latency_samples"]["cold"] == 1
        assert variant["latency_samples"]["warm"] == (
            retrieval_module.MICRO_EVAL_REPETITIONS_DEFAULT - 1
        )
        assert "ttl_seconds" in variant["rerank_cache"]


def test_a_pool_of_three_covers_fewer_golden_ids_than_a_pool_of_twenty(
    stub_services: _Reranker,
) -> None:
    body = asyncio.run(app_module.micro_eval_search_strategies(pool_k=[20, 3]))

    wide = _variant(body, 20)
    narrow = _variant(body, 3)
    assert wide["candidate_coverage"] == pytest.approx(1.0)
    assert narrow["candidate_coverage"] == pytest.approx(0.6)
    assert narrow["candidate_coverage"] < wide["candidate_coverage"]
    # Three candidates can never fill five slots.
    assert wide["short_result_rate"] == pytest.approx(0.0)
    assert narrow["short_result_rate"] == pytest.approx(1.0)
    # What was returned was still all relevant and all cited.
    for variant in (wide, narrow):
        assert variant["context_precision"] == pytest.approx(1.0)
        assert variant["mrr"] == pytest.approx(1.0)
        assert variant["citation_coverage"] == pytest.approx(1.0)
        assert variant["hard_constraint_violations"] == 0


def test_micro_eval_defaults_to_pool_sizes_twenty_and_three(stub_services: _Reranker) -> None:
    body = asyncio.run(app_module.micro_eval_search_strategies())

    assert [variant["pool_k"] for variant in body["variants"]] == [20, 3]


def test_rows_breaking_the_ceiling_never_reach_the_returned_evidence(
    stub_services: _Reranker, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = _rows(6)
    rows[0]["price"] = 150.0
    rows[1]["quantity"] = 0
    monkeypatch.setattr(_HybridSearch, "rows", rows)

    body = asyncio.run(app_module.micro_eval_search_strategies(pool_k=[20]))

    variant = _variant(body, 20)
    assert variant["hard_constraint_violations"] == 0
    # Golden ids 1 and 2 were refused, so only three of five remain reachable.
    assert variant["context_precision"] == pytest.approx(0.75)


def test_micro_eval_rejects_a_pool_size_below_one(stub_services: _Reranker) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(app_module.micro_eval_search_strategies(pool_k=[0]))
    assert exc_info.value.status_code == 400


def test_repetitions_default_to_three_bedrock_rerank_calls_per_variant(
    stub_services: _Reranker,
) -> None:
    """Each pass is a rerank call, so the default bounds the amplification."""
    body = asyncio.run(app_module.micro_eval_search_strategies(pool_k=[20]))

    assert body["repetitions"] == 3
    assert stub_services.calls == 3 + 5  # one held-out pass per pool size per case (5 cases)
    assert len(body["variants"]) == 1


def test_repetitions_is_a_caller_parameter_reported_as_the_count_actually_run(
    stub_services: _Reranker,
) -> None:
    body = asyncio.run(
        app_module.micro_eval_search_strategies(pool_k=[20], repetitions=1)
    )

    assert body["repetitions"] == 1
    assert stub_services.calls == 1 + 5  # one held-out pass per pool size per case (5 cases)
    # One observation still yields both percentiles, and they agree.
    variant = _variant(body, 20)
    assert variant["latency_ms_p95"] == variant["latency_ms_p50"]


def test_repetitions_above_the_ceiling_are_clamped_to_five(
    stub_services: _Reranker,
) -> None:
    body = asyncio.run(
        app_module.micro_eval_search_strategies(pool_k=[20], repetitions=50)
    )

    assert body["repetitions"] == retrieval_module.MICRO_EVAL_REPETITIONS_MAX == 5
    assert stub_services.calls == 5 + 5  # one held-out pass per pool size per case (5 cases)


def test_deterministic_metrics_are_scored_once_and_do_not_drift_with_repetitions(
    stub_services: _Reranker,
) -> None:
    """Coverage, precision, MRR and violations cannot vary over a fixed pool."""
    one = asyncio.run(
        app_module.micro_eval_search_strategies(pool_k=[20, 3], repetitions=1)
    )
    five = asyncio.run(
        app_module.micro_eval_search_strategies(pool_k=[20, 3], repetitions=5)
    )

    deterministic = (
        "pool_k",
        "candidate_coverage",
        "context_precision",
        "mrr",
        "hard_constraint_violations",
        "short_result_rate",
        "citation_coverage",
    )
    for first, second in zip(one["variants"], five["variants"]):
        assert {key: first[key] for key in deterministic} == {
            key: second[key] for key in deterministic
        }


def test_two_pool_sizes_that_clamp_to_the_same_pool_run_as_one_variant(
    stub_services: _Reranker,
) -> None:
    """Below the floor of three, 1 and 2 are the same pool and the same work."""
    body = asyncio.run(
        app_module.micro_eval_search_strategies(pool_k=[1, 2], repetitions=1)
    )

    assert [variant["pool_k"] for variant in body["variants"]] == [3]
    assert stub_services.calls == 1 + 5  # one held-out pass per pool size per case (5 cases)


def test_a_pool_size_over_the_reranker_cap_is_reported_at_the_resolved_size(
    stub_services: _Reranker,
) -> None:
    from config import settings

    body = asyncio.run(
        app_module.micro_eval_search_strategies(pool_k=[500], repetitions=1)
    )

    assert [variant["pool_k"] for variant in body["variants"]] == [
        settings.RERANK_MAX_DOCUMENTS
    ]


def test_micro_eval_declares_the_observatory_authentication_dependency() -> None:
    """An unauthenticated route here is a Bedrock amplifier with a URL."""
    import inspect

    from fastapi.params import Depends as DependsParam
    from services.auth import get_current_user

    parameter = inspect.signature(
        app_module.micro_eval_search_strategies
    ).parameters["user"]

    assert isinstance(parameter.default, DependsParam)
    assert parameter.default.dependency is get_current_user


def test_harness_golden_set_pins_the_canonical_anna_query() -> None:
    """The harness and the micro-eval must label the same query the same way."""
    spec = importlib.util.spec_from_file_location("pellier_eval_harness", HARNESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # ``@dataclass`` resolves annotations through ``sys.modules[cls.__module__]``,
    # so the module has to be registered before its body executes.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)

    entries = [g for g in module.GOLDEN_QUERIES if g.query == retrieval_module.CANONICAL_ANNA_QUERY]
    assert len(entries) == 1
    assert entries[0].query == CANONICAL_QUERY
    assert entries[0].expected == retrieval_module.CANONICAL_ANNA_GOLDEN_IDS
    assert entries[0].filters.price_max == 100
    for name in ("_where_for_filters", "_vector_search", "_fts_search", "_rrf_merge", "_rerank"):
        assert not hasattr(module, name), f"harness still owns private retrieval: {name}"


def test_four_distinct_pool_sizes_are_the_most_one_request_may_compare(
    stub_services: _Reranker,
) -> None:
    """At the ceiling the route still runs, and the Bedrock cost is bounded.

    Four variants at the repetition ceiling is 20 rerank calls. That product
    is the whole reason the ceiling exists, so it is asserted rather than
    described.
    """
    body = asyncio.run(
        app_module.micro_eval_search_strategies(
            pool_k=[3, 4, 5, 6],
            repetitions=retrieval_module.MICRO_EVAL_REPETITIONS_MAX,
        )
    )

    assert retrieval_module.MICRO_EVAL_POOL_SIZES_MAX == 4
    assert [variant["pool_k"] for variant in body["variants"]] == [3, 4, 5, 6]
    assert stub_services.calls == 20 + 20  # one held-out pass per pool size per case (4 pools x 5 cases)


def test_more_distinct_pool_sizes_than_the_ceiling_are_refused_by_name(
    stub_services: _Reranker,
) -> None:
    """Silently truncating would bill for work the caller did not see refused."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            app_module.micro_eval_search_strategies(pool_k=[3, 4, 5, 6, 7])
        )

    assert exc_info.value.status_code == 400
    assert "4" in str(exc_info.value.detail)
    assert "pool_k" in str(exc_info.value.detail)
    assert stub_services.calls == 0


def test_requests_that_clamp_onto_each_other_count_once_against_the_ceiling(
    stub_services: _Reranker,
) -> None:
    """The ceiling counts variants actually run, not values typed."""
    body = asyncio.run(
        app_module.micro_eval_search_strategies(
            pool_k=[1, 2, 3, 4, 5, 6], repetitions=1
        )
    )

    assert [variant["pool_k"] for variant in body["variants"]] == [3, 4, 5, 6]
    assert stub_services.calls == 4 + 20  # one held-out pass per pool size per case (4 pools x 5 cases)


def test_micro_eval_scores_the_same_knob_on_the_held_out_labels(
    stub_services: _Reranker,
) -> None:
    """One knob, two label sets: the tuning labels choose, the held-out labels check."""
    body = asyncio.run(app_module.micro_eval_search_strategies(pool_k=[20, 3]))
    held_out = body["held_out"]
    assert held_out["query"] == retrieval_module.CANONICAL_HELD_OUT_QUERY
    assert held_out["golden_set_size"] == 2
    assert [v["pool_k"] for v in held_out["variants"]] == [v["pool_k"] for v in body["variants"]]
    for variant in held_out["variants"]:
        assert 0.0 <= variant["context_precision"] <= 1.0
        assert 0.0 <= variant["candidate_coverage"] <= 1.0
    verdict = body["generalizes"]
    assert set(verdict) == {"tuning_best_pool_k", "held_out_best_pool_k", "held_out_means", "agree"}
    assert verdict["agree"] == (verdict["tuning_best_pool_k"] == verdict["held_out_best_pool_k"])
    cases = body["held_out_cases"]
    assert [c["id"] for c in cases] == ["slice", "exclusion", "tight_budget", "unavailable", "no_result"]
    for case in cases:
        assert [v["pool_k"] for v in case["variants"]] == [v["pool_k"] for v in body["variants"]]
        assert all("passed" in v for v in case["variants"])
    labelled = [c for c in cases if c["kind"] == "labels"]
    assert all(c["golden_set_size"] > 0 for c in labelled)
    unavailable = next(c for c in cases if c["id"] == "unavailable")
    assert all("leaked" in v for v in unavailable["variants"])


def _reference_tuning_ids() -> set[str]:
    """The labels Lab 1b arrives at, read from the reference solution.

    The starter ships the tuning set empty, so a disjointness check against the
    live constant is vacuous; the solution's ids are what the held-out slice
    must not repeat.
    """
    import re

    source = (
        Path(__file__).resolve().parents[3]
        / "solutions" / "the-quiet-search" / "eval" / "planned_hybrid_retrieval_solution.py"
    ).read_text()
    match = re.search(r"CANONICAL_ANNA_GOLDEN_IDS[^=]*=\s*\(([^)]*)\)", source)
    assert match, "the reference solution pins no golden ids"
    return set(re.findall(r'"(\d+)"', match.group(1)))


def test_the_held_out_slice_is_provided_and_disjoint_from_the_reference_labels() -> None:
    """The product slice must not be the tuning set with a different name."""
    held_out = retrieval_module.CANONICAL_HELD_OUT_GOLDEN_IDS
    assert held_out, "the held-out slice ships labelled; it is not a participant build"
    assert all(pid.isdigit() for pid in held_out)
    reference = _reference_tuning_ids()
    assert reference, "the reference solution's tuning set is empty"
    assert not set(held_out) & reference
    assert retrieval_module.CANONICAL_HELD_OUT_QUERY != retrieval_module.CANONICAL_ANNA_QUERY


def test_the_held_out_query_cases_cover_the_four_agreed_failure_modes() -> None:
    cases = {c["id"]: c for c in retrieval_module.HELD_OUT_CASES}
    assert set(cases) == {"slice", "exclusion", "tight_budget", "unavailable", "no_result"}
    reference = _reference_tuning_ids()
    exclusion = set(cases["exclusion"]["golden_ids"])
    assert exclusion < reference, "the exclusion case is the tuning set minus the excluded piece"
    assert "21" not in exclusion, "the candle must be excluded"
    assert set(cases["tight_budget"]["golden_ids"]) == {"23", "30"}
    assert cases["unavailable"]["must_not_return"] == ("43",), "the sold-out vest"
    assert cases["no_result"]["kind"] == "no_result"
    for case in cases.values():
        assert case["query"] != retrieval_module.CANONICAL_ANNA_QUERY


_HELD_OUT_DEFINITIONS = {
    "slice": """SELECT "productId" FROM pellier.product_catalog
                 WHERE category = 'Beauty' AND quantity > 0
                   AND tags @> '["gift"]'::jsonb
                 ORDER BY "productId"::int""",
    "exclusion": """SELECT "productId" FROM pellier.product_catalog
                     WHERE category = 'Home Decor' AND price <= 100 AND quantity > 0
                       AND tags @> '["gift","home"]'::jsonb AND NOT (tags ? 'candle')
                     ORDER BY "productId"::int""",
    "tight_budget": """SELECT "productId" FROM pellier.product_catalog
                        WHERE price <= 40 AND quantity > 0
                          AND tags @> '["gift"]'::jsonb
                        ORDER BY "productId"::int""",
    "no_result": """SELECT "productId" FROM pellier.product_catalog
                     WHERE price <= 30 AND quantity > 0
                       AND tags @> '["cashmere"]'::jsonb
                     ORDER BY "productId"::int""",
}


def test_the_held_out_definitions_match_the_pinned_ids_on_a_live_catalog() -> None:
    """The pinned ids are the rows each documented rule selects, on the real catalog."""
    dsn = os.environ.get("PELLIER_LIVE_POSTGRES_URL") or os.environ.get("PELLIER_TEST_DSN")
    if not dsn:
        pytest.skip("set PELLIER_LIVE_POSTGRES_URL to check the held-out definitions live")
    psycopg = pytest.importorskip("psycopg")
    cases = {c["id"]: c for c in retrieval_module.HELD_OUT_CASES}
    with psycopg.connect(dsn) as conn:
        for case_id, sql in _HELD_OUT_DEFINITIONS.items():
            rows = tuple(str(r[0]) for r in conn.execute(sql).fetchall())
            expected = tuple(cases[case_id].get("golden_ids") or ())
            assert rows == expected, f"{case_id}: catalog selects {rows}, pinned {expected}"
        sold_out = conn.execute(
            "SELECT quantity FROM pellier.product_catalog WHERE \"productId\" = '43'"
        ).fetchone()
        assert sold_out and int(sold_out[0]) == 0, "the unavailable case needs the vest sold out"
