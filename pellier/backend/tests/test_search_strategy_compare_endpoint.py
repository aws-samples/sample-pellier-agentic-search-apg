"""Contract tests for the live four-strategy retrieval comparison."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from config import settings

import app as app_module
import services.embeddings as embeddings_module
import services.hybrid_search as hybrid_module
import services.planned_hybrid_retrieval as retrieval_module
import services.rerank as rerank_module
import services.retrieval_receipt as receipt_module
import services.structured_extract as extract_module
import services.vector_search as vector_module
import services.agent_tools as agent_tools_module

REPO = Path(__file__).resolve().parents[3]
LAB_2_SQL = REPO / "workshop" / "lab-2-rrf.sql"
LAB_2_STARTER_SQL = REPO / "workshop" / "starters" / "lab-2-rrf.sql"
LAB_2_SOLUTION_SQL = (
    REPO / "solutions" / "the-quiet-search" / "sql" / "lab-2-rrf-solution.sql"
)
LAB_2_MARKERS = (
    "-- === WORKSHOP · PostgreSQL RRF · fusion expression: START ===",
    "-- === WORKSHOP · PostgreSQL RRF · fusion expression: END ===",
)


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
                "category": "Home Decor",
            }
            for index in range(1, 7)
        ]

    async def vector_search_planned(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        # Record the compiled predicates so a test can assert the agentic
        # strategy really ran a plan rather than ad-hoc kwargs.
        self.last_predicates = list(kwargs.get("predicates") or [])
        self.last_predicate_params = list(kwargs.get("predicate_params") or [])
        return [
            {
                "name": f"Planned {index}",
                "product_id": index,
                "description": "A planned result",
                "category": "Home Decor",
            }
            for index in range(1, 7)
        ]


class _HybridSearch:
    def __init__(self, db: Any) -> None:
        self.db = db
        self.search_calls: list[dict[str, Any]] = []

    async def search(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_calls.append(kwargs)
        return self._rows()

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
                "category": "Home Decor",
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
            "categories": ["Home Decor"],
            "tags": ["gift"],
            "price_max_usd": 100,
            "in_stock_only": True,
            "exclusions": ["candle"],
            "soft_signal": "considered housewarming gift",
        }


class _EmptyPoolHybridSearch(_HybridSearch):
    """Every planned attempt comes back empty, forcing the full ladder."""

    def __init__(self, db: Any) -> None:
        super().__init__(db)

    async def search(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        self.search_calls.append(kwargs)
        return []


@pytest.fixture(autouse=True)
def _stub_services(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import planned_hybrid_retrieval

    # Mechanism contracts use a completed budget. The starter comparison below
    # separately verifies the narrow lab default and its observable repair.
    monkeypatch.setattr(planned_hybrid_retrieval, "DEFAULT_RERANK_POOL_K", 30)
    monkeypatch.setattr(app_module, "db_service", object())
    monkeypatch.setattr(embeddings_module, "EmbeddingService", _Embedding)
    monkeypatch.setattr(vector_module, "VectorSearch", _VectorSearch)
    monkeypatch.setattr(hybrid_module, "HybridSearch", _HybridSearch)
    monkeypatch.setattr(rerank_module, "get_rerank_service", lambda: _Reranker())
    monkeypatch.setattr(
        extract_module, "get_structured_extractor", lambda: _Extractor()
    )


@pytest.fixture
def receipt_writes(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Record every retrieval receipt the comparison persists."""
    written: list[Any] = []

    async def _persist(db: Any, receipt: Any) -> bool:
        written.append(receipt)
        return True

    monkeypatch.setattr(receipt_module, "persist_receipt", _persist)
    return written


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

    assert len(body["strategies"]) == 4
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
    for strategy in (body["strategies"][2], body["strategies"][3]):
        assert strategy["rerank"]["status"] == "applied"
        assert strategy["rerank"]["model"] == "cohere.rerank-v3-5:0"
        assert strategy["rerank"]["candidates"] >= strategy["rerank"]["returned"] > 0
        assert strategy["rerank"]["poolK"] >= 3
    assert agentic["strategy"] == "agentic (Sonnet → filter → hybrid → rerank)"
    assert agentic["shares_storefront_executor"] is True
    assert "shares_storefront_executor" not in body["strategies"][2]


def test_hybrid_rerank_strategy_runs_an_unconstrained_plan_without_widening() -> None:
    body = asyncio.run(
        app_module.compare_search_strategies(
            query="A milestone gift for a new homeowner"
        )
    )

    hybrid_rerank = body["strategies"][2]
    assert hybrid_rerank["strategy"] == "hybrid + rerank"
    assert hybrid_rerank["rerank"]["candidates"] == 6
    assert "extractedFilters" not in hybrid_rerank
    assert "relaxations" not in hybrid_rerank


def test_agentic_strategy_persists_one_receipt_citing_its_returned_rows(
    receipt_writes: list[Any],
) -> None:
    """Lab 2's SQL reads this receipt; it must describe the rows the row shows."""
    body = asyncio.run(
        app_module.compare_search_strategies(
            query="A housewarming gift under $100 that is currently in stock."
        )
    )

    assert len(receipt_writes) == 1
    row = receipt_writes[0].to_row()
    agentic = body["strategies"][3]
    shown = [str(product["productId"]) for product in agentic["products"]]
    assert row["citation_ids"] == shown
    assert [s["entity_id"] for s in row["citation_snapshots"]] == shown
    assert row["query_preview"] == (
        "A housewarming gift under $100 that is currently in stock."
    )
    assert row["hard_constraints"]["price_max_usd"] == 100.0
    assert set(row["candidate_product_ids"]) >= set(shown)
    assert row["rerank_scores"]
    assert row["rail"] == "in-process"
    assert row["retrieval_config"]["source"] == "observatory-compare"
    assert row["latency_breakdown"]
    assert body["receipt"]["persisted"] is True
    assert body["receipt"]["comparisonId"] == row["turn_id"]
    assert row["turn_id"].startswith("compare-")


def test_comparison_identifies_each_request_even_when_the_query_is_unchanged(
    receipt_writes: list[Any],
) -> None:
    first = asyncio.run(app_module.compare_search_strategies(query="A gift under $100"))
    second = asyncio.run(app_module.compare_search_strategies(query="A gift under $100"))
    assert first["receipt"]["comparisonId"] != second["receipt"]["comparisonId"]
    assert [r.turn_id for r in receipt_writes] == [
        first["receipt"]["comparisonId"], second["receipt"]["comparisonId"]
    ]


def test_comparison_discloses_missing_durable_evidence_without_failing_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(db: Any, receipt: Any) -> bool:
        return False

    monkeypatch.setattr(receipt_module, "persist_receipt", unavailable)
    body = asyncio.run(app_module.compare_search_strategies(query="A gift under $100"))
    assert body["strategies"][-1]["products"]
    assert body["receipt"]["persisted"] is False
    assert body["receipt"]["comparisonId"].startswith("compare-")


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

    hybrid_rerank = body["strategies"][2]["rerank"]
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
    agentic_rerank = body["strategies"][3]["rerank"]
    assert agentic_rerank["status"] == "fallback"
    assert agentic_rerank["fallbackOrder"] == "planned-hybrid-rrf"


def test_candidate_budget_comparison_exposes_exact_candidate_loss(monkeypatch, completed_search_plan) -> None:
    from services import planned_hybrid_retrieval

    monkeypatch.setattr(planned_hybrid_retrieval, "DEFAULT_RERANK_POOL_K", 3)
    before = asyncio.run(app_module.compare_search_strategies(query="A gift under $100"))
    monkeypatch.setattr(planned_hybrid_retrieval, "DEFAULT_RERANK_POOL_K", 20)
    after = asyncio.run(app_module.compare_search_strategies(query="A gift under $100"))
    narrow = before["strategies"][3]
    wide = after["strategies"][3]
    assert len(narrow["rerank"]["candidateIds"]) == 3
    assert len(wide["rerank"]["candidateIds"]) > 3
    assert narrow["extractedFilters"]["priceMaxUsd"] == wide["extractedFilters"]["priceMaxUsd"]
    assert narrow["extractedFilters"]["filterUsed"] == "drop_tags"
    assert wide["extractedFilters"]["filterUsed"] == "strict"


def test_exhausted_ladder_never_drops_a_hard_constraint(
    monkeypatch: pytest.MonkeyPatch,
    completed_search_plan,
) -> None:
    """Even when every attempt returns nothing, price/stock/exclusions hold.

    Regression guard for the audit's A2 finding: the previous ladder's
    final ``drop_all`` rung removed price and in-stock entirely, so this
    query could answer with an out-of-stock $250 candle.
    """
    empty = _EmptyPoolHybridSearch(object())
    monkeypatch.setattr(hybrid_module, "HybridSearch", lambda db: empty)

    body = asyncio.run(
        app_module.compare_search_strategies(
            query="in-stock housewarming gift under $100, no candles"
        )
    )

    attempts = [
        list(call.get("hard_clauses") or [])
        for call in empty.search_calls
        if call.get("hard_clauses")
    ]
    assert attempts, "the agentic strategy should have attempted retrieval"
    for predicates in attempts:
        assert "price <= %s" in predicates
        assert "quantity > 0" in predicates
        assert "NOT (tags ?| %s)" in predicates

    agentic = body["strategies"][-1]
    assert agentic["searchPlan"]["hard_constraints"]["price_max_usd"] == 100.0
    assert agentic["searchPlan"]["hard_constraints"]["in_stock_only"] is True
    assert agentic["hardConstraintsEnforced"] == [
        "price <= $100",
        "in stock",
        "category in Home Decor",
    ]
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
    assert [product["name"] for product in body["strategies"][3]["products"]]


def test_the_search_explain_surface_deliberately_does_not_run_the_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It exposes the artifacts the executor collapses, so it drives the branches.

    Pinned behaviorally so the divergence stays a decision. The docstrings in
    ``services/planned_hybrid_retrieval.py`` and on ``explain_search`` record
    the reasoning; if this fails, one of them is stale.
    """

    async def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            "explain_search ran the shared executor; update the docstrings or "
            "route it deliberately"
        )

    monkeypatch.setattr(retrieval_module, "execute_search_plan", _forbidden)

    body = asyncio.run(app_module.explain_search(query="linen for a resort"))

    assert [stage["stage"] for stage in body["stages"]][:2] == ["embed", "vector"]


def _lab_2_receipt_cte() -> str:
    """The ``receipt`` CTE from the Lab 2 build artifact, as shipped."""
    text = LAB_2_SQL.read_text(encoding="utf-8")
    start = text.index("WITH receipt AS (")
    end = text.index(")", text.index("LIMIT 1", start)) + 1
    return text[start:end]


def test_lab_2_selects_the_comparison_surface_and_names_the_turn_it_read() -> None:
    """Bind the worksheet to the captured request without depending on query copy."""
    text = LAB_2_SQL.read_text(encoding="utf-8")
    cte = _lab_2_receipt_cte()

    predicates = [
        line.strip()
        for line in cte.splitlines()
        if line.strip().startswith(("WHERE ", "AND "))
    ]
    assert predicates == [
        "WHERE receipt_id > :'receipt_high_water'::bigint",
        "AND turn_id = :'comparison_id'",
        "AND retrieval_config->>'source' = "
        f"'{app_module.OBSERVATORY_COMPARE_RECEIPT_SOURCE}'",
    ]
    assert "query_preview =" not in text
    assert "ORDER BY receipt_id DESC" in cte
    assert "LIMIT 1" in cte
    # The participant can see which turn the fusion table came from.
    assert "r.query_preview," in text
    assert "\\echo 'Lab 2 fusion source query:' :lab_2_query" in text
    for marker in LAB_2_MARKERS:
        assert text.count(marker) == 1


def test_every_shipped_copy_of_lab_2_carries_the_same_receipt_selection() -> None:
    """Starter and solution differ by the fusion expression, never by the source."""
    predicate = (
        "AND retrieval_config->>'source' = "
        f"'{app_module.OBSERVATORY_COMPARE_RECEIPT_SOURCE}'"
    )
    for path in (LAB_2_SQL, LAB_2_STARTER_SQL, LAB_2_SOLUTION_SQL):
        assert predicate in path.read_text(encoding="utf-8"), path
        assert "AND turn_id = :'comparison_id'" in path.read_text(encoding="utf-8"), path
        assert "AND recomputed_rrf IS NOT NULL" in path.read_text(encoding="utf-8"), path


def test_the_storefront_writer_leaves_the_comparison_source_unset() -> None:
    """The discriminator only discriminates while only one surface sets it."""
    assert "source" not in agent_tools_module._hybrid_retrieval_config()


def test_lab_2_would_select_exactly_the_receipt_the_comparison_just_wrote(
    receipt_writes: list[Any],
) -> None:
    """The one coupling that matters: endpoint writes it, Lab 2 reads it.

    The simulated table starts with three older receipts, including one
    carrying the retired literal the SQL used to pin, so a selection that
    still matched on query text would pick the wrong row. A storefront
    retrieval receipt then lands *after* the comparison's, which is what any
    ordinary shopper turn does while the participant reads the page: a
    selection that took the newest row above the mark would read that turn.
    A later comparison must not replace the requested comparison either.
    """
    retired = "Keep the gift under $100 and show me the strongest two options."
    storefront_config = agent_tools_module._hybrid_retrieval_config()
    table: list[dict[str, Any]] = [
        {"receipt_id": 1, "query_preview": retired, "retrieval_config": {}},
        {
            "receipt_id": 2,
            "query_preview": "Marco's Brooklyn warehouse turn",
            "retrieval_config": storefront_config,
        },
        {"receipt_id": 3, "query_preview": retired, "retrieval_config": {}},
    ]
    high_water = max(row["receipt_id"] for row in table)
    query = "Something quietly celebratory for a first flat"

    asyncio.run(app_module.compare_search_strategies(query=query))

    assert len(receipt_writes) == 1
    written = receipt_writes[0].to_row()
    table.append(
        {
            "receipt_id": high_water + 1,
            "turn_id": written["turn_id"],
            "query_preview": written["query_preview"],
            "retrieval_config": written["retrieval_config"],
        }
    )
    table.append(
        {
            "receipt_id": high_water + 2,
            "query_preview": "linen for a resort",
            "retrieval_config": storefront_config,
        }
    )

    table.append({
        "receipt_id": high_water + 3,
        "turn_id": "another-comparison",
        "query_preview": "a later unrelated comparison",
        "retrieval_config": written["retrieval_config"],
    })

    # The shipped predicate selects the exact comparison ID above the high-water
    # mark and verifies its source. Neither query text nor recency proves identity.
    candidates = [
        row
        for row in table
        if row["receipt_id"] > high_water
        and row.get("turn_id") == written["turn_id"]
        and row["retrieval_config"].get("source")
        == app_module.OBSERVATORY_COMPARE_RECEIPT_SOURCE
    ]
    selected = sorted(candidates, key=lambda row: row["receipt_id"], reverse=True)[0]

    assert selected["receipt_id"] == high_water + 1
    assert selected["query_preview"] == query
    assert selected["query_preview"] != retired


def teardown_function() -> None:
    app_module.db_service = None


def test_controlled_fallback_executes_authored_plan_and_records_both_passes(
    monkeypatch, receipt_writes, completed_search_plan,
):
    class SparsePreference(_HybridSearch):
        async def search(self, *args, **kwargs):
            # The live seed has no eligible watch below $100. Both branches
            # return no rows for that preference; widened branches return rows.
            if ['watch'] in (kwargs.get('hard_params') or []):
                return []
            return await super().search(*args, **kwargs)

    monkeypatch.setattr(hybrid_module, 'HybridSearch', SparsePreference)
    monkeypatch.setattr(extract_module, 'get_structured_extractor',
                        lambda: pytest.fail('controlled case must not claim model extraction'))
    body = asyncio.run(app_module.compare_search_strategies(
        app_module.ANNA_FALLBACK_QUERY, scenario='anna-fallback'))
    assert body['planSource'] == 'workshop-controlled'
    assert 'Sonnet' not in body['strategies'][-1]['strategy']
    row = receipt_writes[0].to_row()
    config = row['retrieval_config']
    assert config['original_preference_tags'] == ['watch']
    assert config['relaxation_steps'] == ['drop_tags']
    assert row['exclusions'] == ['candle']
    assert row['hard_constraints'] == config['original_contract']['hard_constraints']
    counts = [stage['count'] for stage in config['attempt_stages'] if stage['name'] == 'eligibility']
    assert len(counts) == 2 and counts[0] == 0 and counts[1] > 0


@pytest.mark.parametrize('query, scenario', [
    ('another query', 'anna-fallback'), ('gift', 'unbounded-test-mode'),
])
def test_controlled_fallback_rejects_unknown_or_mislabelled_scenarios(query, scenario):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(app_module.compare_search_strategies(query, scenario=scenario))
    assert exc.value.status_code == 400


def test_controlled_fallback_records_the_participants_chosen_preference(
    monkeypatch, receipt_writes, completed_search_plan,
):
    class SparseLeather(_HybridSearch):
        async def search(self, *args, **kwargs):
            if ['leather'] in (kwargs.get('hard_params') or []):
                return []
            return await super().search(*args, **kwargs)

    monkeypatch.setattr(hybrid_module, 'HybridSearch', SparseLeather)
    monkeypatch.setattr(extract_module, 'get_structured_extractor',
                        lambda: pytest.fail('controlled case must not claim model extraction'))
    query = app_module.anna_fallback_query('leather')
    assert 'Prefer leather' in query
    # The controlled case derives its own text when none is supplied.
    body = asyncio.run(app_module.compare_search_strategies(
        scenario='anna-fallback', prefer='Leather'))
    assert body['query'] == query
    assert body['scenarioPreference'] == 'leather'
    row = receipt_writes[0].to_row()
    config = row['retrieval_config']
    assert config['scenario_input'] == {'scenario': 'anna-fallback', 'preference': 'leather'}
    assert config['original_preference_tags'] == ['leather']
    # Only the preference varies; the requirements are the scenario's own.
    assert row['exclusions'] == ['candle']
    assert row['hard_constraints'] == config['original_contract']['hard_constraints']
    assert row['hard_constraints']['price_max_usd'] == 100
    assert row['hard_constraints']['in_stock_only'] is True
    assert row['query_preview'] == query


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
