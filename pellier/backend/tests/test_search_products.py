"""Tests for the ``search_products`` tool: the planned hybrid pipeline.

``services.agent_tools.search_products`` is a thin ``@tool`` wrapper over
``services.store_tools.search_products``. These tests drive the wrapper over a
fake database service (a real coroutine ``fetch_all``) with a fake embedder and
reranker, so the pipeline runs offline. The order matters: embed, hybrid
(vector + full text + RRF), rerank, eligibility recheck, return.

Runnable from the repo root:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_search_products.py -v
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Sequence
from unittest.mock import MagicMock

import pytest

import services.agent_tools as agent_tools
import services.embeddings as embeddings_module
import services.rerank as rerank_module
from services import store_tools
from services.retrieval_receipt import INSERT_SQL as RECEIPT_INSERT_SQL

_PREDICATE_EXCLUSION = "NOT (tags ?| %s OR materials ?| %s)"


class _FakeDB:
    """The pool behind ``agent_tools._run_sql``.

    Serves candidate rows from the vector branch (and, optionally, the
    full-text branch), and records every statement in order with its kind.
    """

    def __init__(self, events: List[str], rows: List[Dict[str, Any]]) -> None:
        self.events = events
        self.rows = rows
        self.fts_rows: List[Dict[str, Any]] = []
        self.statements: List[tuple[str, str, Sequence[Any]]] = []

    async def fetch_all(self, sql: str, *params: Any) -> List[Dict[str, Any]]:
        if sql == RECEIPT_INSERT_SQL:
            kind, rows = "receipt", [{"receipt_id": 1}]
        elif "to_tsquery" in sql:
            kind, rows = "fts", self.fts_rows
        elif sql.startswith("SELECT count(*)"):
            # The Builder view's filter counts: one aggregate after the
            # search, never a second retrieval pass.
            kind, rows = "counts", [{"total": 100, "kept": len(self.rows)}]
        else:
            kind, rows = "vector", self.rows
        self.events.append(kind)
        self.statements.append((kind, sql, params))
        return [dict(row) for row in rows]

    def branches(self, kind: str) -> List[tuple[str, Sequence[Any]]]:
        return [(sql, params) for k, sql, params in self.statements if k == kind]


@pytest.fixture
def candidates() -> List[Dict[str, Any]]:
    """Five fake candidates from the vector branch."""
    return [
        {
            "product_id": i,
            "name": f"Product {i}",
            "brand": "Pellier",
            "color": "Sand",
            "description": f"Description for product {i}",
            "img_url": f"https://example.com/{i}.jpg",
            "category": "Clothing",
            "price": 50.0 + i * 10,  # 60, 70, 80, 90, 100
            "rating": 4.7,
            "reviews": "50",
            "badge": None,
            "tags": [],
            "updated_at": "2026-09-04T00:00:00+00:00",
        }
        for i in range(1, 6)
    ]


@pytest.fixture
def events() -> List[str]:
    return []


@pytest.fixture
def db(
    monkeypatch: pytest.MonkeyPatch, events: List[str], candidates: List[Dict[str, Any]]
) -> _FakeDB:
    """Install the fake pool and make ``_run_async`` run its coroutines."""
    fake = _FakeDB(events, candidates)
    monkeypatch.setattr(agent_tools, "_db_service", fake)
    monkeypatch.setattr(agent_tools, "_run_async", asyncio.run)
    return fake


@pytest.fixture
def patch_embedding(monkeypatch: pytest.MonkeyPatch, events: List[str]) -> MagicMock:
    """Stub EmbeddingService.embed_query to a fixed 1024-dim vector."""
    embed_service = MagicMock()

    def _embed(_query: str) -> List[float]:
        events.append("embed")
        return [0.01] * 1024

    embed_service.embed_query.side_effect = _embed
    monkeypatch.setattr(
        embeddings_module, "EmbeddingService", lambda *_, **__: embed_service
    )
    return embed_service


@pytest.fixture
def patch_rerank(monkeypatch: pytest.MonkeyPatch, events: List[str]) -> MagicMock:
    """Stub get_rerank_service to a reranker that reverses input order.

    Reversing lets a test tell hybrid order from reranked order.
    """
    svc = MagicMock()
    ranking = [
        {"index": 4, "relevance_score": 0.95},
        {"index": 3, "relevance_score": 0.88},
        {"index": 2, "relevance_score": 0.71},
        {"index": 1, "relevance_score": 0.55},
        {"index": 0, "relevance_score": 0.40},
    ]

    def _rerank(**_kwargs: Any) -> List[Dict[str, Any]]:
        events.append("rerank")
        return list(ranking)

    svc.rerank.side_effect = _rerank
    monkeypatch.setattr(rerank_module, "get_rerank_service", lambda: svc)
    return svc


@pytest.fixture
def pipeline(db: _FakeDB, patch_embedding: MagicMock, patch_rerank: MagicMock) -> _FakeDB:
    """Everything the tool needs, offline."""
    return db


def _search(**kwargs: Any) -> Dict[str, Any]:
    return json.loads(agent_tools.search_products(**kwargs))


# ---------------------------------------------------------------------------
# Pipeline order
# ---------------------------------------------------------------------------


class TestPipelineOrder:

    def test_embed_then_hybrid_then_rerank_then_return(
        self, pipeline: _FakeDB, patch_embedding: MagicMock, patch_rerank: MagicMock,
        events: List[str],
    ) -> None:
        from services import tool_evidence

        # A chat turn collects evidence; the Builder view's filter counts run
        # only then, after the search, as one aggregate statement.
        channel = tool_evidence.open_channel()
        try:
            result = _search(query="something beautiful", limit=3)
        finally:
            tool_evidence.close_channel(channel)

        assert result["status"] == "success"
        # Embed once, both hybrid branches, then rerank, then the receipt,
        # then the Builder view's filter counts. The search itself runs once.
        assert events == ["embed", "vector", "fts", "rerank", "receipt", "counts"]
        assert patch_embedding.embed_query.call_count == 1
        assert patch_rerank.rerank.call_count == 1
        rerank_kwargs = patch_rerank.rerank.call_args.kwargs
        assert rerank_kwargs["query"] == "something beautiful"
        # Five candidates -> five documents passed to rerank.
        assert len(rerank_kwargs["documents"]) == 5

    def test_the_count_statement_runs_only_when_a_turn_collects_evidence(
        self, pipeline: _FakeDB, events: List[str],
    ) -> None:
        """Outside a chat turn nothing reads the counts, so they are not taken."""
        result = _search(query="something beautiful", limit=3)
        assert result["status"] == "success"
        assert events == ["embed", "vector", "fts", "rerank", "receipt"]

    def test_search_method_says_hybrid_plus_rerank_when_rerank_succeeds(
        self, pipeline: _FakeDB
    ) -> None:
        assert _search(query="q", limit=5)["search_method"] == "hybrid+rerank"

    def test_pool_size_reflects_hybrid_output(self, pipeline: _FakeDB) -> None:
        assert _search(query="q", limit=2)["pool_size"] == 5

    def test_rerank_pool_is_bounded_and_reported(
        self, pipeline: _FakeDB, patch_rerank: MagicMock
    ) -> None:
        pipeline.rows[:] = [
            {**pipeline.rows[0], "product_id": index, "name": f"Product {index}"}
            for index in range(1, 31)
        ]
        patch_rerank.rerank.side_effect = lambda **kw: [
            {"index": i, "relevance_score": 1 - i / 100} for i in range(len(kw["documents"]))
        ]

        result = _search(query="q", limit=5)

        assert result["pool_size"] == 30
        assert result["rerank_pool_k"] == store_tools.DEFAULT_RERANK_POOL_K == 15
        assert len(patch_rerank.rerank.call_args.kwargs["documents"]) == 15


# ---------------------------------------------------------------------------
# Rerank actually reorders results
# ---------------------------------------------------------------------------


class TestReranking:

    def test_rerank_order_overrides_hybrid_order(self, pipeline: _FakeDB) -> None:
        # The reranker reverses the pool, so the first result is product 5
        # (last by RRF), not product 1 (first by RRF).
        names = [p["name"] for p in _search(query="q", limit=5)["products"]]
        assert names[0] == "Product 5"
        assert names[-1] == "Product 1"

    def test_milestone_home_query_promotes_the_housewarming_hero(
        self, pipeline: _FakeDB, candidates: List[Dict[str, Any]]
    ) -> None:
        candidates[1]["name"] = "Tall Stoneware Vase"
        result = _search(query="A milestone gift for a new homeowner", limit=5)
        assert [p["name"] for p in result["products"]][0] == "Tall Stoneware Vase"

    def test_promotion_is_disclosed_as_a_versioned_merchandising_rule(
        self, pipeline: _FakeDB, candidates: List[Dict[str, Any]]
    ) -> None:
        """The boost must be visible in the payload, not a silent reorder.

        Regression guard for the audit's A5 finding: an undisclosed
        promotion contaminates every relevance comparison that reads this
        tool's output.
        """
        candidates[1]["name"] = "Tall Stoneware Vase"
        result = _search(query="A milestone gift for a new homeowner", limit=5)
        applied = result["merchandising_rules_applied"]
        assert len(applied) == 1
        assert applied[0]["ruleId"] == store_tools.MERCHANDISING_RULE_ID
        assert applied[0]["product"] == "Tall Stoneware Vase"
        assert applied[0]["toRank"] == 1
        assert applied[0]["fromRank"] > 1

    def test_no_merchandising_key_when_no_rule_fires(
        self, pipeline: _FakeDB, candidates: List[Dict[str, Any]]
    ) -> None:
        candidates[1]["name"] = "Tall Stoneware Vase"
        assert "merchandising_rules_applied" not in _search(query="something beautiful", limit=5)

    def test_no_boost_reported_when_relevance_already_won(
        self, pipeline: _FakeDB, candidates: List[Dict[str, Any]]
    ) -> None:
        """If the hero already ranks first, nothing was promoted."""
        # The stub reranker reverses order, so index 4 lands at rank 1.
        candidates[4]["name"] = "Tall Stoneware Vase"
        result = _search(query="A milestone gift for a new homeowner", limit=5)
        assert result["products"][0]["name"] == "Tall Stoneware Vase"
        assert "merchandising_rules_applied" not in result

    def test_non_home_milestone_queries_keep_rerank_order(
        self, pipeline: _FakeDB, candidates: List[Dict[str, Any]]
    ) -> None:
        candidates[1]["name"] = "Tall Stoneware Vase"
        names = [p["name"] for p in _search(query="something beautiful", limit=5)["products"]]
        assert names[0] == "Product 5"
        assert names[3] == "Tall Stoneware Vase"

    def test_each_product_has_rerank_score(self, pipeline: _FakeDB) -> None:
        for product in _search(query="q", limit=3)["products"]:
            assert isinstance(product["rerank_score"], float)


# ---------------------------------------------------------------------------
# Failure mode: rerank returns []
# ---------------------------------------------------------------------------


class TestRerankFailureFallback:

    def test_empty_rerank_falls_back_to_rrf_order(
        self, pipeline: _FakeDB, patch_rerank: MagicMock
    ) -> None:
        patch_rerank.rerank.side_effect = lambda **_kw: []  # rerank failed
        result = _search(query="q", limit=5)
        assert "rerank fallback" in result["search_method"]
        # All candidates kept in original RRF order.
        assert [p["name"] for p in result["products"]] == [f"Product {i}" for i in range(1, 6)]

    def test_a_raising_reranker_is_an_error_envelope_not_a_crash(
        self, pipeline: _FakeDB, patch_rerank: MagicMock
    ) -> None:
        patch_rerank.rerank.side_effect = RuntimeError("bedrock down")
        assert _search(query="q") == {"error": "bedrock down"}


# ---------------------------------------------------------------------------
# Limits and eligibility after the reranker
# ---------------------------------------------------------------------------


class TestFilters:

    def test_max_price_is_rechecked_after_rerank(self, pipeline: _FakeDB) -> None:
        # Candidate prices: 60, 70, 80, 90, 100. The fake database ignores the
        # SQL predicate and the reranker puts the $100 row first, so only the
        # post-rerank recheck can drop 5 and 4.
        result = _search(query="q", max_price=80, limit=5)
        prices = [p["price"] for p in result["products"]]
        assert prices == [80.0, 70.0, 60.0]

    def test_min_rating_filter_passes_through(self, pipeline: _FakeDB) -> None:
        # All fixture candidates have rating 4.7; min_rating=4.8 drops all.
        assert _search(query="q", min_rating=4.8, limit=5)["count"] == 0

    def test_an_agent_category_never_empties_the_results(self, pipeline: _FakeDB) -> None:
        """All five candidates are Clothing; the agent's "Shoes" guess removes none."""
        assert _search(query="q", category="Shoes", limit=5)["count"] == 5

    def test_stock_and_exclusions_are_rechecked_after_rerank(
        self, pipeline: _FakeDB, candidates: List[Dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        candidates[4].update(quantity=0)  # reranked first, sold out
        candidates[3].update(tags=["candle"])  # reranked second, excluded
        for row in candidates[:3]:
            row["quantity"] = 5
        _planned(monkeypatch, {
            "in_stock_only": True, "exclusions": ["candle"],
            "soft_signal": "gift", "extraction_status": "parsed",
        })

        result = _search(query="a gift in stock, no candles", limit=5)

        assert [p["name"] for p in result["products"]] == ["Product 3", "Product 2", "Product 1"]


class TestLimitClamping:

    @pytest.fixture
    def many(self, pipeline: _FakeDB) -> _FakeDB:
        pipeline.rows[:] = [
            {**pipeline.rows[0], "product_id": index, "name": f"Product {index}"}
            for index in range(1, 31)
        ]
        return pipeline

    def run(self, many: _FakeDB, **kwargs: Any) -> Dict[str, Any]:
        reranker = MagicMock()
        reranker.rerank.side_effect = lambda **kw: [
            {"index": i, "relevance_score": 1 - i / 100} for i in range(len(kw["documents"]))
        ]
        return json.loads(
            json.dumps(
                store_tools.search_products(
                    lambda sql, params: asyncio.run(many.fetch_all(sql, *params)),
                    query="linen",
                    embed=lambda _q: [0.1],
                    rerank=reranker.rerank,
                    config={"rerank_pool_k": 30},
                    **kwargs,
                ),
                default=str,
            )
        )

    def test_a_huge_limit_is_clamped_to_the_row_ceiling(self, many: _FakeDB) -> None:
        assert self.run(many, limit=500)["count"] == store_tools.MAX_ROWS

    @pytest.mark.parametrize("limit", [0, -3])
    def test_a_limit_below_one_returns_one_row(self, many: _FakeDB, limit: int) -> None:
        assert self.run(many, limit=limit)["count"] == 1

    def test_a_non_numeric_limit_falls_back_to_the_default(self, many: _FakeDB) -> None:
        assert self.run(many, limit="lots")["count"] == 5


# ---------------------------------------------------------------------------
# Hard constraints reach retrieval BEFORE rerank (audit finding A3)
# ---------------------------------------------------------------------------


class TestHardConstraintsRunBeforeRerank:
    """Price and explicit category must gate candidate *generation*.

    Filtering only after the reranker means invalid candidates consume
    reranker capacity, the final list can come back unexpectedly short,
    and the candidate pool stops representing the valid candidate set,
    which also makes retrieval evaluation measure the wrong thing.
    """

    def test_price_ceiling_is_pushed_into_both_branches(self, pipeline: _FakeDB) -> None:
        _search(query="linen shirt", max_price=100, limit=5)

        for kind in ("vector", "fts"):
            (sql, params), = pipeline.branches(kind)
            assert "price <= %s" in sql
            assert 100.0 in params

    def test_an_agent_category_is_recorded_not_enforced(self, pipeline: _FakeDB) -> None:
        """The agent's guess is not the shopper's restriction."""
        result = _search(query="linen shirt", category="Shoes", limit=5)

        for kind in ("vector", "fts"):
            (sql, params), = pipeline.branches(kind)
            assert "category = ANY" not in sql
            assert ["Shoes"] not in params
        assert result["search_plan"]["inferred_categories"] == ["Shoes"]
        assert result["search_plan"]["category_source"] is None

    def test_no_constraints_means_no_predicates(self, pipeline: _FakeDB) -> None:
        _search(query="linen shirt", limit=5)

        for kind in ("vector", "fts"):
            (sql, params), = pipeline.branches(kind)
            for predicate in ("price <=", "quantity > 0", "tags ?", "category = ANY"):
                assert predicate not in sql
            # Only the query text (or embedding) and the branch size are bound.
            assert len(params) == 2

    def test_min_rating_stays_a_post_rerank_preference(self, pipeline: _FakeDB) -> None:
        """Rating is a preference over the reranked list, not a SQL gate."""
        _search(query="linen shirt", min_rating=4.8, limit=5)

        for kind in ("vector", "fts"):
            (sql, _params), = pipeline.branches(kind)
            assert "rating >=" not in sql

    def test_payload_reports_enforced_constraints(self, pipeline: _FakeDB) -> None:
        result = _search(query="q", max_price=100, limit=5)

        assert result["constraints_applied_before_rerank"] is True
        assert result["hard_constraints_enforced"] == ["price <= $100"]


# ---------------------------------------------------------------------------
# What the shopper must be told when a requirement goes unchecked
# ---------------------------------------------------------------------------


def _planned(monkeypatch: pytest.MonkeyPatch, envelope: Dict[str, Any] | None) -> None:
    monkeypatch.setattr(agent_tools, "_extract_query_structure", lambda _q: envelope)


class TestConstraintNotice:

    def test_material_exclusion_reaches_sql_and_unsupported_one_is_admitted(
        self, monkeypatch: pytest.MonkeyPatch, pipeline: _FakeDB
    ) -> None:
        _planned(monkeypatch, {
            "exclusions": ["wool"], "unsupported_exclusions": ["nothing scented"],
            "soft_signal": "a throw", "extraction_status": "parsed",
        })
        result = _search(query="a throw, no wool")

        for kind in ("vector", "fts"):
            (sql, params), = pipeline.branches(kind)
            assert _PREDICATE_EXCLUSION in sql
            assert ["wool"] in params
        assert result["search_plan"]["unenforced_exclusions"] == ["nothing scented"]
        assert result["constraint_notice"].endswith("may not meet them: nothing scented.")

    def test_failed_extraction_is_reported_not_hidden(
        self, monkeypatch: pytest.MonkeyPatch, pipeline: _FakeDB
    ) -> None:
        from services.structured_extract import StructuredExtractor

        _planned(monkeypatch, StructuredExtractor._empty("q", status="extraction_failed"))
        assert "could not be read" in _search(query="q")["constraint_notice"]

    def test_nothing_unchecked_means_no_notice(self, pipeline: _FakeDB) -> None:
        assert "constraint_notice" not in _search(query="q")

    def test_exclusions_and_stock_reach_sql_with_the_plan_on_the_payload(
        self, monkeypatch: pytest.MonkeyPatch, pipeline: _FakeDB
    ) -> None:
        _planned(monkeypatch, {
            "exclusions": ["candle"], "in_stock_only": True,
            "soft_signal": "a gift", "extraction_status": "parsed",
        })
        result = _search(query="a gift in stock, no candles")

        for kind in ("vector", "fts"):
            (sql, params), = pipeline.branches(kind)
            assert _PREDICATE_EXCLUSION in sql
            assert "quantity > 0" in sql
        assert result["search_plan"]["exclusions"] == ["candle"]
        assert "constraint_notice" not in result

    def test_unsupported_exclusion_is_admitted(
        self, monkeypatch: pytest.MonkeyPatch, pipeline: _FakeDB
    ) -> None:
        _planned(monkeypatch, {"unsupported_exclusions": ["no plastic"], "soft_signal": "q"})
        result = _search(query="q, no plastic")
        assert result["constraint_notice"].endswith("may not meet them: no plastic.")

    def test_explicit_price_is_a_sql_predicate_and_the_plan_says_no_extraction_ran(
        self, monkeypatch: pytest.MonkeyPatch, pipeline: _FakeDB
    ) -> None:
        _planned(monkeypatch, None)
        result = _search(query="q", max_price=100)
        (sql, _params), = pipeline.branches("vector")
        assert "price <= %s" in sql
        assert result["search_plan"]["extraction_status"] == "not_run"


class TestExtractionFailureIsExplicit:
    """The wrapper's own exception path, not a ready-made failure envelope."""

    def test_an_extractor_that_raises_is_reported_not_treated_as_no_requirements(
        self, monkeypatch: pytest.MonkeyPatch, pipeline: _FakeDB
    ) -> None:
        import services.structured_extract as structured_extract

        def unavailable():
            raise RuntimeError("extractor unavailable")

        monkeypatch.setattr(structured_extract, "get_structured_extractor", unavailable)
        result = _search(query="a gift, no candles")

        assert result["search_plan"]["extraction_status"] == "extraction_failed"
        assert "could not be read" in result["constraint_notice"]

    def test_a_reading_with_no_requirements_is_not_a_failure(
        self, pipeline: _FakeDB
    ) -> None:
        """The conftest extractor reads nothing; the plan says it was read, not skipped."""
        result = _search(query="q")
        assert result["search_plan"]["extraction_status"] == "parsed"
        assert "constraint_notice" not in result


class TestTheShoppersWordsDriveRequirements:
    """The agent picks search words; the planner reads what the shopper typed."""

    def test_a_shortened_agent_query_cannot_drop_no_candles(
        self, monkeypatch: pytest.MonkeyPatch, pipeline: _FakeDB
    ) -> None:
        import services.structured_extract as structured_extract
        from services.turn_identity import shopper_words_var

        read: List[str] = []

        class _Extractor:
            def extract(self, text: str) -> Dict[str, Any]:
                read.append(text)
                return {"exclusions": ["candle"], "price_max_usd": 100,
                        "soft_signal": "gift", "extraction_status": "parsed"}

        monkeypatch.setattr(structured_extract, "get_structured_extractor", _Extractor)
        token = shopper_words_var.set("A gift under $100, no candles")
        try:
            agent_tools.search_products(query="housewarming gifts")
        finally:
            shopper_words_var.reset(token)

        assert read == ["A gift under $100, no candles"]
        for kind in ("vector", "fts"):
            (sql, _params), = pipeline.branches(kind)
            assert _PREDICATE_EXCLUSION in sql
            assert "price <= %s" in sql


# ---------------------------------------------------------------------------
# The @tool wrapper: what it decides, and what it hands the shared pipeline
# ---------------------------------------------------------------------------


class TestWrapper:

    def test_an_uninitialised_database_is_a_readable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(agent_tools, "_db_service", None)
        assert _search(query="q") == {"error": "Database service not initialized"}

    def test_it_hands_store_tools_the_pool_runner_extraction_config_and_receipt_context(
        self, monkeypatch: pytest.MonkeyPatch, patch_embedding: MagicMock, patch_rerank: MagicMock
    ) -> None:
        monkeypatch.setattr(agent_tools, "_db_service", object())
        monkeypatch.setattr(agent_tools, "_extract_query_structure", lambda _q: {"soft_signal": "x"})
        seen: Dict[str, Any] = {}

        def spy(run: Any, **kwargs: Any) -> Dict[str, Any]:
            seen["run"], seen["kwargs"] = run, kwargs
            return {"status": "success"}

        monkeypatch.setattr(store_tools, "search_products", spy)

        _search(query="linen", max_price=90.0, min_rating=4.0, category="Home", limit=3)

        kwargs = seen["kwargs"]
        assert seen["run"] is agent_tools._run_sql
        assert kwargs["embed"] == patch_embedding.embed_query
        assert kwargs["rerank"] == patch_rerank.rerank
        assert kwargs["extracted"] == {"soft_signal": "x"}
        assert (kwargs["max_price"], kwargs["min_rating"]) == (90.0, 4.0)
        assert (kwargs["category"], kwargs["limit"]) == ("Home", 3)
        assert kwargs["config"] == agent_tools._retrieval_config()
        assert set(kwargs["receipt"]) == {
            "turn_id", "session_id", "principal_sub", "rail", "embedding_model", "rerank_model",
        }

    def test_run_sql_binds_positional_params_and_returns_plain_dicts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: List[tuple[str, Sequence[Any]]] = []

        class _Pool:
            async def fetch_all(self, sql: str, *params: Any) -> List[Dict[str, Any]]:
                seen.append((sql, params))
                return [{"a": 1}]

        monkeypatch.setattr(agent_tools, "_db_service", _Pool())
        monkeypatch.setattr(agent_tools, "_run_async", asyncio.run)

        assert agent_tools._run_sql("SELECT %s, %s", ("x", 2)) == [{"a": 1}]
        assert seen == [("SELECT %s, %s", ("x", 2))]
