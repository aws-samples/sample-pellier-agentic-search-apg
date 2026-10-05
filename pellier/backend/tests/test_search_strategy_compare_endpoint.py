"""Contract tests for the live five-strategy retrieval comparison."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import HTTPException

from config import settings

import app as app_module
import services.embeddings as embeddings_module
import services.hybrid_search as hybrid_module
import services.planned_hybrid_retrieval as retrieval_module
import services.rerank as rerank_module
import services.structured_extract as extract_module
import services.store_tools as store_tools_module
import services.vector_search as vector_module



class _Embedding:
    def embed_query(self, query: str) -> list[float]:
        return [0.1] * 1024


class _VectorSearch:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def vector_search(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            {"name": "Vector first", "product_id": 1},
            {"name": "Vector second", "product_id": 2},
        ]

    async def vector_search_filtered(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": f"Filtered {index}",
                "product_id": index,
                "description": "A filtered result",
                "category": "Home",
            }
            for index in range(1, 7)
        ]


class _HybridSearch:
    def __init__(self, db: Any) -> None:
        self.db = db
        self.search_calls: list[dict[str, Any]] = []
        self.keyword_calls: list[dict[str, Any]] = []

    async def search(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_calls.append(kwargs)
        return self._rows()

    async def keyword_only(self, query: str, k: int = 0) -> list[dict[str, Any]]:
        self.keyword_calls.append({"query": query, "k": k})
        return [
            {"name": f"Keyword {index}", "product_id": 100 + index}
            for index in range(1, 4)
        ]

    async def search_explained(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        rows = self._rows()
        return {
            "vector_rows": rows,
            "fts_rows": rows,
            "merged": rows,
            "params": {"k_vector": 20, "k_fts": 20, "rrf_k": 60, "top_n": 5},
            "vector_sql": "SELECT 1",
            "fts_sql": "SELECT 2",
        }

    @staticmethod
    def _rows() -> list[dict[str, Any]]:
        return [
            {
                "name": f"Hybrid {index}",
                "product_id": index,
                "description": "A hybrid result",
                "category": "Home",
            }
            for index in range(1, 7)
        ]


class _Reranker:
    def rerank(
        self, *, query: str, documents: list[str], top_n: int
    ) -> list[dict[str, int]]:
        return [{"index": index} for index in reversed(range(min(top_n, len(documents))))]


class _UnavailableReranker:
    def rerank(
        self, *, query: str, documents: list[str], top_n: int
    ) -> list[dict[str, int]]:
        return []


class _Extractor:
    """Stands in for Sonnet. Facets must be real catalog values — the
    planner drops anything outside ``KNOWN_CATEGORIES`` / ``KNOWN_TAGS``,
    so a fixture using invented facets would silently test nothing."""

    def extract(self, query: str) -> dict[str, Any]:
        return {
            "categories": ["Home"],
            "tags": ["gift"],
            "price_max_usd": 100,
            "in_stock_only": True,
            "exclusions": ["candle"],
            "soft_signal": "considered housewarming gift",
        }


class _PlannedDB:
    """The database service behind the planned strategies (4 and 5).

    ``execute_search_plan`` sends every branch statement through
    ``fetch_all``. Each statement is recorded with the phase (the number of
    ``execute_search_plan`` calls started so far, when a test counts them) so
    a test can tell strategy 4's statements from strategy 5's. Rows come back
    from both branches unless ``empty_when(sql, params)`` says otherwise.
    """

    def __init__(self, empty_when: Any = None) -> None:
        self.empty_when = empty_when
        self.phase = 0
        self.statements: list[tuple[int, str, tuple[Any, ...]]] = []

    async def fetch_all(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        self.statements.append((self.phase, sql, params))
        if self.empty_when is not None and self.empty_when(sql, params):
            return []
        return _HybridSearch._rows()

    def phase_statements(self, phase: int) -> list[tuple[str, tuple[Any, ...]]]:
        return [(sql, params) for ph, sql, params in self.statements if ph == phase]


@pytest.fixture
def planned_db(monkeypatch: pytest.MonkeyPatch) -> _PlannedDB:
    fake = _PlannedDB()
    monkeypatch.setattr(app_module, "db_service", fake)
    return fake


@pytest.fixture(autouse=True)
def _stub_services(monkeypatch: pytest.MonkeyPatch, planned_db: _PlannedDB) -> None:
    # Mechanism contracts use a completed budget. The starter comparison below
    # separately verifies the narrow lab default and its observable repair.
    monkeypatch.setattr(store_tools_module, "DEFAULT_RERANK_POOL_K", 30)
    monkeypatch.setattr(embeddings_module, "EmbeddingService", _Embedding)
    monkeypatch.setattr(vector_module, "VectorSearch", _VectorSearch)
    monkeypatch.setattr(hybrid_module, "HybridSearch", _HybridSearch)
    monkeypatch.setattr(rerank_module, "get_rerank_service", lambda: _Reranker())
    monkeypatch.setattr(
        extract_module, "get_structured_extractor", lambda: _Extractor()
    )


def test_comparison_labels_single_run_latency_and_modeled_cost_honestly() -> None:
    body = asyncio.run(
        app_module.compare_search_strategies(
            query="A milestone gift for a new homeowner"
        )
    )

    assert body["query"] == "A milestone gift for a new homeowner"
    assert body["sharedQueryEmbeddingObservedMs"] >= 0
    assert "not a percentile" in body["measurementAssumptions"]["latency"]
    assert "not a billing measurement" in body["measurementAssumptions"]["cost"]
    assert "not calculated" in body["measurementAssumptions"]["quality"]

    assert len(body["strategies"]) == 5
    for strategy in body["strategies"]:
        assert strategy["observedMs"] >= 0
        assert strategy["modeledCostPerThousandUsd"] >= 0
        assert "p50Ms" not in strategy
        assert "costPerThousandUsd" not in strategy
        assert strategy["products"]

    agentic = body["strategies"][-1]
    assert agentic["extractedFilters"]["priceMaxUsd"] == 100
    assert agentic["extractedFilters"]["filterUsed"] == "strict"
    # The typed plan that ran is reported alongside the raw extraction.
    plan = agentic["searchPlan"]
    assert plan["hard_constraints"]["price_max_usd"] == 100.0
    assert plan["hard_constraints"]["in_stock_only"] is True
    assert plan["exclusions"] == ["candle"]
    assert agentic["relaxations"] == []
    for strategy in (body["strategies"][3], body["strategies"][4]):
        assert strategy["rerank"]["status"] == "applied"
        assert strategy["rerank"]["model"] == "cohere.rerank-v3-5:0"
        assert strategy["rerank"]["candidates"] >= strategy["rerank"]["returned"] > 0
        assert strategy["rerank"]["poolK"] >= 3
    assert agentic["strategy"] == "agentic (Sonnet → filter → hybrid → rerank)"
    assert agentic["shares_storefront_executor"] is True
    assert "shares_storefront_executor" not in body["strategies"][3]


def test_comparison_lists_keyword_vector_and_hybrid_side_by_side_in_order() -> None:
    body = asyncio.run(
        app_module.compare_search_strategies(query="linen shirt for a trip")
    )

    assert [s["strategy"] for s in body["strategies"][:3]] == [
        "keyword only", "vector only", "hybrid (RRF)",
    ]
    keyword, vector, hybrid = body["strategies"][:3]
    assert [p["productId"] for p in keyword["products"]] == [101, 102, 103]
    assert [p["productId"] for p in vector["products"]] == [1, 2]
    assert [p["productId"] for p in hybrid["products"]] == [1, 2, 3, 4, 5]
    assert keyword["observedMs"] >= 0
    assert keyword["modeledCostPerThousandUsd"] == 0.0
    assert "rerank" not in keyword and "extractedFilters" not in keyword


def test_keyword_strategy_reads_the_raw_query_through_the_full_text_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instances: list[_HybridSearch] = []

    class _Recording(_HybridSearch):
        def __init__(self, db: Any) -> None:
            super().__init__(db)
            instances.append(self)

    monkeypatch.setattr(hybrid_module, "HybridSearch", _Recording)
    asyncio.run(app_module.compare_search_strategies(query="  linen shirt  "))

    keyword_calls = [call for inst in instances for call in inst.keyword_calls]
    assert keyword_calls == [{"query": "linen shirt", "k": 5}]


def test_keyword_strategy_with_no_lexical_match_reports_an_empty_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NoLexicalMatch(_HybridSearch):
        async def keyword_only(self, query: str, k: int = 0) -> list[dict[str, Any]]:
            return []

    monkeypatch.setattr(hybrid_module, "HybridSearch", _NoLexicalMatch)
    body = asyncio.run(app_module.compare_search_strategies(query="something quiet"))

    keyword = body["strategies"][0]
    assert keyword["strategy"] == "keyword only"
    assert keyword["products"] == []
    assert len(body["strategies"]) == 5


def test_hybrid_rerank_strategy_runs_an_unconstrained_plan_without_widening() -> None:
    body = asyncio.run(
        app_module.compare_search_strategies(
            query="A milestone gift for a new homeowner"
        )
    )

    hybrid_rerank = body["strategies"][3]
    assert hybrid_rerank["strategy"] == "hybrid + rerank"
    assert hybrid_rerank["rerank"]["candidates"] == 6
    assert "extractedFilters" not in hybrid_rerank
    assert "relaxations" not in hybrid_rerank


def test_comparison_discloses_rerank_fallback_instead_of_reusing_the_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rerank_module,
        "get_rerank_service",
        lambda: _UnavailableReranker(),
    )

    body = asyncio.run(
        app_module.compare_search_strategies(
            query="A milestone gift for a new homeowner"
        )
    )

    hybrid_rerank = body["strategies"][3]["rerank"]
    # An unconfigured pool resolves to the reranker's own document cap, which
    # is the value the fallback disclosure must report: the pool the reranker
    # was offered, not the zero documents it came back with.
    assert {
        key: value for key, value in hybrid_rerank.items()
        if key not in {"candidateIds", "fusedCandidates"}
    } == {
        "status": "fallback",
        "model": "cohere.rerank-v3-5:0",
        "candidates": 6,
        "returned": 0,
        "poolK": 30,
        "fallbackOrder": "rrf",
    }
    assert len(hybrid_rerank["candidateIds"]) == hybrid_rerank["candidates"]
    assert hybrid_rerank["candidateIds"] == [
        row["productId"] for row in hybrid_rerank["fusedCandidates"]
    ]
    assert settings.RERANK_MAX_DOCUMENTS == 30
    agentic_rerank = body["strategies"][4]["rerank"]
    assert agentic_rerank["status"] == "fallback"
    assert agentic_rerank["fallbackOrder"] == "planned-hybrid-rrf"


def test_candidate_budget_comparison_exposes_exact_candidate_loss(monkeypatch, completed_search_plan) -> None:
    monkeypatch.setattr(store_tools_module, "DEFAULT_RERANK_POOL_K", 3)
    before = asyncio.run(app_module.compare_search_strategies(query="A gift under $100"))
    monkeypatch.setattr(store_tools_module, "DEFAULT_RERANK_POOL_K", 20)
    after = asyncio.run(app_module.compare_search_strategies(query="A gift under $100"))
    narrow = before["strategies"][4]
    wide = after["strategies"][4]
    assert len(narrow["rerank"]["candidateIds"]) == 3
    assert len(wide["rerank"]["candidateIds"]) > 3
    assert narrow["extractedFilters"]["priceMaxUsd"] == wide["extractedFilters"]["priceMaxUsd"]
    assert narrow["extractedFilters"]["filterUsed"] == "drop_tags"
    assert wide["extractedFilters"]["filterUsed"] == "strict"


def test_exhausted_ladder_never_drops_a_hard_constraint(
    monkeypatch: pytest.MonkeyPatch,
    planned_db: _PlannedDB,
    completed_search_plan,
) -> None:
    """Even when every attempt returns nothing, price/stock/exclusions hold.

    Regression guard for the audit's A2 finding: the previous ladder's
    final ``drop_all`` rung removed price and in-stock entirely, so this
    query could answer with an out-of-stock $250 candle.
    """
    planned_db.empty_when = lambda _sql, _params: True
    real = retrieval_module.execute_search_plan

    async def _phased(db: Any, **kwargs: Any) -> Any:
        planned_db.phase += 1
        return await real(db, **kwargs)

    monkeypatch.setattr(retrieval_module, "execute_search_plan", _phased)

    body = asyncio.run(
        app_module.compare_search_strategies(
            query="in-stock housewarming gift under $100, no candles"
        )
    )

    # Phase 2 is the agentic strategy: the strict pass, then the widened pass.
    attempts = planned_db.phase_statements(2)
    assert attempts, "the agentic strategy should have attempted retrieval"
    for sql, params in attempts:
        assert "price <= %s" in sql
        assert "quantity > 0" in sql
        assert "NOT (tags ?| %s OR materials ?| %s)" in sql
        assert "category = ANY" not in sql
    assert any("tags ?& %s" in sql for sql, _params in attempts)
    assert not all("tags ?& %s" in sql for sql, _params in attempts)

    agentic = body["strategies"][-1]
    assert agentic["searchPlan"]["hard_constraints"]["price_max_usd"] == 100.0
    assert agentic["searchPlan"]["hard_constraints"]["in_stock_only"] is True
    assert agentic["hardConstraintsEnforced"] == [
        "price <= $100",
        "in stock",
    ]
    # The model guessed Home from "housewarming"; a guess is recorded, never enforced.
    assert agentic["searchPlan"]["inferred_categories"] == ["Home"]
    # Widening happened, and it is disclosed rather than silent.
    assert [r["step"] for r in agentic["relaxations"]] == ["drop_tags"]
    assert agentic["relaxations"][0]["dropped"] == ["gift"]


def test_comparison_rejects_blank_query() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(app_module.compare_search_strategies(query="  "))
    assert exc_info.value.status_code == 400


def test_the_comparison_runs_both_planned_strategies_through_the_shared_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Behavioral, not textual: the real executor is called, twice, as configured.

    Strategy 3 runs an unconstrained plan with widening off; strategy 4 runs the
    extracted plan with the storefront's ladder. Counting call sites in the
    source proved neither, and would have broken on a reformat.
    """
    real = retrieval_module.execute_search_plan
    calls: list[dict[str, Any]] = []

    async def _recording(db: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return await real(db, **kwargs)

    monkeypatch.setattr(retrieval_module, "execute_search_plan", _recording)

    body = asyncio.run(
        app_module.compare_search_strategies(
            query="A milestone gift for a new homeowner"
        )
    )

    assert len(calls) == 2
    unconstrained, agentic = calls
    assert unconstrained["relax"] is False
    assert unconstrained["plan"].hard.price_max_usd is None
    assert agentic.get("relax", True) is True
    assert agentic["plan"].hard.price_max_usd == 100.0
    # Both strategies embed once for the whole request, not once each.
    assert unconstrained["embed"] is agentic["embed"]
    # And the rows the executor returned are the rows the surface reports.
    assert [product["name"] for product in body["strategies"][4]["products"]]


def test_controlled_fallback_executes_authored_plan_and_reports_both_passes(
    monkeypatch, planned_db, completed_search_plan,
):
    # The live seed has no eligible watch below $100. Both branches return no
    # rows for that preference; widened branches return rows.
    planned_db.empty_when = lambda _sql, params: ['watch'] in params
    monkeypatch.setattr(extract_module, 'get_structured_extractor',
                        lambda: pytest.fail('controlled case must not claim model extraction'))
    body = asyncio.run(app_module.compare_search_strategies(
        app_module.ANNA_FALLBACK_QUERY, scenario='anna-fallback'))
    assert body['planSource'] == 'workshop-controlled'
    agentic = body['strategies'][-1]
    assert 'Sonnet' not in agentic['strategy']
    assert [r['step'] for r in agentic['relaxations']] == ['drop_tags']
    assert agentic['relaxations'][0]['dropped'] == ['watch']
    assert agentic['searchPlan']['exclusions'] == ['candle']
    assert agentic['searchPlan']['hard_constraints']['price_max_usd'] == 100
    assert agentic['products']


@pytest.mark.parametrize('query, scenario', [
    ('another query', 'anna-fallback'), ('gift', 'unbounded-test-mode'),
])
def test_controlled_fallback_rejects_unknown_or_mislabelled_scenarios(query, scenario):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(app_module.compare_search_strategies(query, scenario=scenario))
    assert exc.value.status_code == 400


def test_controlled_fallback_reports_the_participants_chosen_preference(
    monkeypatch, planned_db, completed_search_plan,
):
    planned_db.empty_when = lambda _sql, params: ['leather'] in params
    monkeypatch.setattr(extract_module, 'get_structured_extractor',
                        lambda: pytest.fail('controlled case must not claim model extraction'))
    query = app_module.anna_fallback_query('leather')
    assert 'Prefer leather' in query
    # The controlled case derives its own text when none is supplied.
    body = asyncio.run(app_module.compare_search_strategies(
        scenario='anna-fallback', prefer='Leather'))
    assert body['query'] == query
    assert body['scenarioPreference'] == 'leather'
    plan = body['strategies'][-1]['searchPlan']
    assert body['strategies'][-1]['relaxations'][0]['dropped'] == ['leather']
    # Only the preference varies; the requirements are the scenario's own.
    assert plan['exclusions'] == ['candle']
    assert plan['hard_constraints']['price_max_usd'] == 100
    assert plan['hard_constraints']['in_stock_only'] is True


def test_the_canonical_watch_case_is_unchanged():
    assert app_module.anna_fallback_query('watch') == app_module.ANNA_FALLBACK_QUERY


@pytest.mark.parametrize('query, scenario, prefer', [
    # The text must name the preference under test.
    (app_module.ANNA_FALLBACK_QUERY, 'anna-fallback', 'leather'),
    # The excluded tag cannot also be preferred.
    ('A gift under $100, in stock, and no candles. Prefer candle, but other gifts are fine.',
     'anna-fallback', 'candle'),
    # Only planner tags are accepted.
    ('A gift under $100, in stock, and no candles. Prefer rockets, but other gifts are fine.',
     'anna-fallback', 'rockets'),
    # A preference outside the controlled case is refused.
    ('gift', None, 'leather'),
])
def test_controlled_preference_is_validated(query, scenario, prefer):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(app_module.compare_search_strategies(query, scenario=scenario, prefer=prefer))
    assert exc.value.status_code == 400


def test_a_normal_comparison_still_requires_a_query():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(app_module.compare_search_strategies())
    assert exc.value.status_code == 400
