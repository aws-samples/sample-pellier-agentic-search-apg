"""Tests for ``HybridSearch.search`` and the RRF merge math.

Anna's anchor capability — pgvector + Postgres FTS with RRF merge.
We mock psycopg so the tests run offline; the real Aurora migration
is exercised live in the verification phase.

Runnable from the repo root:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_hybrid_search.py -v
"""
from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Sequence

import pytest

from services.hybrid_search import HybridSearch
from services.sql_query_logger import SQLQueryLogger
import services.sql_query_logger as sql_query_logger_module


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _build_or_tsquery — the OR-joining query compiler that fixes the
# AND-of-all-stems over-filtering both plainto and websearch default to
# ---------------------------------------------------------------------------


class TestBuildOrTsquery:
    """The compiler that turns conversational queries into OR-joined to_tsquery input."""

    def test_drops_stop_words_and_keeps_content_tokens(self) -> None:
        out = HybridSearch._build_or_tsquery(
            "a thoughtful gift for someone who loves morning rituals"
        )
        # 'a', 'for', 'who' are stop-words; 'someone', 'loves' are in our
        # extra stop-word list (conversational filler / generic verbs).
        assert "thoughtful" in out
        assert "gift" in out
        assert "morning" in out
        assert "rituals" in out
        # Stop-words removed:
        for w in ["someone", "loves", "for", "who", "the"]:
            assert w not in out

    def test_or_joins_remaining_tokens(self) -> None:
        out = HybridSearch._build_or_tsquery("beeswax candle for the dining table")
        # 'for' and 'the' drop; 'beeswax', 'candle', 'dining', 'table' keep.
        # Order preserved so the OR-tree matches user intent for ts_rank_cd.
        parts = out.split(" | ")
        assert "beeswax" in parts
        assert "candle" in parts
        assert "dining" in parts
        assert "table" in parts
        assert "for" not in parts
        assert "the" not in parts

    def test_dedupes_repeated_tokens(self) -> None:
        out = HybridSearch._build_or_tsquery("candle candle CANDLE")
        # All three normalize to 'candle' after lowercase; only one survives.
        assert out == "candle"

    def test_strips_punctuation(self) -> None:
        out = HybridSearch._build_or_tsquery("wrap-ready, gift-table, hand-thrown!")
        # Punctuation removed; tokens preserved (with internal hyphens stripped
        # by the per-token .strip("-") call).
        for word in ["wrap", "ready", "gift", "table", "hand", "thrown"]:
            assert word in out

    def test_drops_short_tokens(self) -> None:
        out = HybridSearch._build_or_tsquery("a is or by candle")
        # All ≤2 chars except 'candle'.
        assert out == "candle"

    def test_pure_stop_word_query_returns_empty(self) -> None:
        out = HybridSearch._build_or_tsquery("the and for what who")
        assert out == ""

    def test_empty_input_returns_empty(self) -> None:
        assert HybridSearch._build_or_tsquery("") == ""
        assert HybridSearch._build_or_tsquery("   ") == ""


# ---------------------------------------------------------------------------
# Fake psycopg machinery — same pattern as test_vector_search.py but the
# fake cursor returns different result sets on consecutive `execute` calls
# (vector branch first, BM25 branch second). asyncio.gather schedules both
# coroutines concurrently but they end up sharing this cursor, which is the
# canonical test pattern for concurrent reads through a single mock.
# ---------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, result_sets: List[List[Dict[str, Any]]]):
        self._result_sets = list(result_sets)
        self._next_idx = 0
        self._last_rows: List[Dict[str, Any]] = []
        self.calls: List[tuple[str, Optional[Sequence[Any]]]] = []

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def execute(
        self, sql: str, params: Optional[Sequence[Any]] = None
    ) -> None:
        self.calls.append((sql, params))
        # Pick the next result set based on which branch's SQL is running.
        # The vector branch SQL uses '<=>' (cosine distance); BM25 uses
        # 'plainto_tsquery'. This is the cleanest way to give each branch
        # the right rows without coupling to call order.
        # Matches both plainto_tsquery and websearch_to_tsquery so the test
        # is robust to which Postgres FTS query function the implementation
        # uses (plainto = AND-of-stems, websearch = OR-default — the live
        # path uses websearch because plainto over-filters conversational
        # queries).
        if "to_tsquery" in sql:
            self._last_rows = self._bm25_rows
        elif "<=>" in sql:
            self._last_rows = self._vector_rows
        else:
            self._last_rows = []

    async def fetchall(self) -> List[Dict[str, Any]]:
        return list(self._last_rows)

    @property
    def _vector_rows(self) -> List[Dict[str, Any]]:
        return self._result_sets[0] if len(self._result_sets) > 0 else []

    @property
    def _bm25_rows(self) -> List[Dict[str, Any]]:
        return self._result_sets[1] if len(self._result_sets) > 1 else []


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakeDB:
    def __init__(self, vector_rows: List[Dict[str, Any]],
                 bm25_rows: List[Dict[str, Any]]):
        self.cursor = FakeCursor([vector_rows, bm25_rows])
        self.conn = FakeConnection(self.cursor)

    @asynccontextmanager
    async def get_connection(self):
        yield self.conn


def _make_row(product_id: int, **extra: Any) -> Dict[str, Any]:
    base = {
        "product_id": product_id,
        "name": f"Product {product_id}",
        "brand": "Pellier Editions",
        "color": "Sand",
        "description": f"Description for product {product_id}",
        "img_url": f"https://example.com/{product_id}.jpg",
        "category": "Apparel",
        "price": 100.0,
        "rating": 4.7,
        "reviews": "50",
        "badge": None,
        "tags": [],
    }
    base.update(extra)
    return base


@pytest.fixture
def embedding() -> List[float]:
    return [0.01] * 1024


@pytest.fixture(autouse=True)
def isolated_query_logger(monkeypatch: pytest.MonkeyPatch) -> SQLQueryLogger:
    logger = SQLQueryLogger(max_logs=100)
    monkeypatch.setattr(sql_query_logger_module, "_query_logger", logger)
    return logger


# ---------------------------------------------------------------------------
# RRF math — the central correctness claim
# ---------------------------------------------------------------------------


class TestRRFMerge:
    """The fusion formula: score(d) = sum over each list L : 1 / (rrf_k + rank_L(d))."""

    def test_doc_in_both_lists_at_rank_1_scores_higher_than_only_one(self) -> None:
        v_rows = [_make_row(1), _make_row(2)]
        b_rows = [_make_row(1), _make_row(3)]  # product 1 in both, 3 only in BM25
        merged = HybridSearch._rrf_merge(v_rows, b_rows, rrf_k=60)
        # product 1 is rank-1 in both → 1/61 + 1/61 = 2/61 ≈ 0.0328
        # product 2 is rank-2 in vector only → 1/62 ≈ 0.0161
        # product 3 is rank-2 in BM25 only → 1/62 ≈ 0.0161
        assert [r["product_id"] for r in merged] == [1, 2, 3] \
            or [r["product_id"] for r in merged] == [1, 3, 2]
        assert merged[0]["product_id"] == 1
        assert math.isclose(merged[0]["rrf_score"], 2.0 / 61, abs_tol=1e-9)

    def test_doc_in_only_one_list_scores_lower_than_both(self) -> None:
        v_rows = [_make_row(10)]
        b_rows = [_make_row(20)]
        merged = HybridSearch._rrf_merge(v_rows, b_rows, rrf_k=60)
        assert len(merged) == 2
        scores = {r["product_id"]: r["rrf_score"] for r in merged}
        assert math.isclose(scores[10], 1.0 / 61, abs_tol=1e-9)
        assert math.isclose(scores[20], 1.0 / 61, abs_tol=1e-9)

    def test_rank_decay_damps_tail_contributions(self) -> None:
        # A doc at rank 1 should outscore a doc at rank 30 by a wide margin.
        v_rows = [_make_row(i) for i in range(1, 31)]
        b_rows = []
        merged = HybridSearch._rrf_merge(v_rows, b_rows, rrf_k=60)
        head = merged[0]["rrf_score"]
        tail = merged[-1]["rrf_score"]
        # rank 1: 1/61 ≈ 0.0164; rank 30: 1/90 ≈ 0.0111
        assert head > tail
        assert head / tail > 1.4  # head is meaningfully higher

    def test_rrf_score_is_monotonic_in_rank_within_a_list(self) -> None:
        v_rows = [_make_row(i) for i in range(1, 6)]
        merged = HybridSearch._rrf_merge(v_rows, [], rrf_k=60)
        scores = [r["rrf_score"] for r in merged]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# search() end-to-end — both branches run, results merged
# ---------------------------------------------------------------------------


class TestHybridSearchEndToEnd:

    def test_runs_both_branches_and_merges(self, embedding: List[float]) -> None:
        v_rows = [_make_row(1, similarity=0.92), _make_row(2, similarity=0.88)]
        b_rows = [_make_row(1, bm25_score=0.7), _make_row(3, bm25_score=0.5)]
        db = FakeDB(v_rows, b_rows)
        svc = HybridSearch(db)  # type: ignore[arg-type]
        results = _run(svc.search(
            query="something beautiful",
            query_embedding=embedding,
            k_vector=20, k_bm25=20, top_n=30,
        ))
        # 3 unique product ids across both lists.
        ids = sorted([r["product_id"] for r in results])
        assert ids == [1, 2, 3]
        # All rows have rrf_score; the duplicate (id=1) keeps the
        # vector-branch projection (so similarity field survives).
        head = next(r for r in results if r["product_id"] == 1)
        assert "rrf_score" in head
        assert head.get("similarity") == 0.92  # vector row preserved

    def test_top_n_caps_results(self, embedding: List[float]) -> None:
        v_rows = [_make_row(i) for i in range(1, 21)]
        b_rows = [_make_row(i) for i in range(100, 120)]
        db = FakeDB(v_rows, b_rows)
        svc = HybridSearch(db)  # type: ignore[arg-type]
        results = _run(svc.search(
            query="anything",
            query_embedding=embedding,
            top_n=5,
        ))
        assert len(results) == 5

    def test_empty_bm25_branch_falls_back_to_vector(
        self, embedding: List[float]
    ) -> None:
        v_rows = [_make_row(i) for i in range(1, 4)]
        db = FakeDB(v_rows, [])
        svc = HybridSearch(db)  # type: ignore[arg-type]
        results = _run(svc.search(
            query="zero-bm25-match",
            query_embedding=embedding,
            top_n=30,
        ))
        # All 3 vector rows survive; rrf_scores reflect rank-only.
        ids = sorted([r["product_id"] for r in results])
        assert ids == [1, 2, 3]
        # rank 1 score should be exactly 1/61 (only one branch contributing)
        head = max(results, key=lambda r: r["rrf_score"])
        assert math.isclose(head["rrf_score"], 1.0 / 61, abs_tol=1e-9)

    def test_query_logger_records_all_three_logs(
        self, embedding: List[float],
        isolated_query_logger: SQLQueryLogger,
    ) -> None:
        v_rows = [_make_row(1)]
        b_rows = [_make_row(2)]
        db = FakeDB(v_rows, b_rows)
        svc = HybridSearch(db)  # type: ignore[arg-type]
        # Use a query with real content tokens so _build_or_tsquery
        # produces a non-empty OR-query and the BM25 branch actually
        # executes its SQL (bare "q" would short-circuit to []).
        _run(svc.search("linen shirt", embedding, top_n=30))
        types = [q.query_type for q in isolated_query_logger.queries]
        # vector branch + bm25 branch + outer hybrid_search summary
        assert "hybrid_vector_branch" in types
        assert "hybrid_bm25_branch" in types
        assert "hybrid_search" in types

    def test_pure_stop_word_query_skips_bm25_branch(
        self, embedding: List[float],
        isolated_query_logger: SQLQueryLogger,
    ) -> None:
        """When the user query is all stop-words, _bm25_search short-
        circuits to [] without executing SQL. Vector branch still runs.
        """
        v_rows = [_make_row(1)]
        b_rows: List[Dict[str, Any]] = []
        db = FakeDB(v_rows, b_rows)
        svc = HybridSearch(db)  # type: ignore[arg-type]
        results = _run(svc.search("the and for what who", embedding, top_n=30))
        # Vector branch produced results; BM25 contributed nothing.
        assert len(results) == 1
        types = [q.query_type for q in isolated_query_logger.queries]
        assert "hybrid_vector_branch" in types
        # No bm25 SQL executed.
        assert "hybrid_bm25_branch" not in types
