"""Planner-on starter regression; real plan and executor, stubbed external services.

Starter regressions use the real unfinished Task 1B. Only the explicit
after-completion test uses completed_search_plan.
"""
import asyncio
import json
from unittest.mock import MagicMock

import pytest

from services import agent_tools, embeddings, rerank, search_plan, structured_extract
from services.planned_hybrid_retrieval import execute_search_plan
from services.retrieval_receipt import INSERT_SQL as RECEIPT_INSERT_SQL
from services.retrieval_receipt import _COLUMN_ORDER

QUERY = "A housewarming gift under $100, in stock, no candles or wool; prefer slow mornings."
EXTRACTED = {
    "price_max_usd": 100,
    "in_stock_only": True,
    "exclusions": ["candle", "wool"],
    "tags": ["gift", "slow", "home"],
    "soft_signal": "a housewarming gift for slow mornings",
}


def row(i):
    return {
        "product_id": str(i), "name": f"Cotton gift {i}", "brand": "Pellier",
        "description": "A cotton gift", "price": 48, "quantity": 10,
        "category": "Home", "tags": ["gift", "slow", "home"],
        "materials": ["cotton"], "rating": 4.5, "reviews": "2",
        "rrf_score": 0.1, "img_url": "", "color": "Ivory",
    }


class FakeDB:
    """The pool behind ``agent_tools._run_sql``: branch rows out, statements recorded."""

    def __init__(self):
        self.rows = []
        self.vector_calls = []
        self.fts_calls = []
        self.receipts = []
        # The Builder view's filter counts: one aggregate after the search,
        # never a second retrieval pass.
        self.count_calls = []

    async def fetch_all(self, sql, *params):
        if sql == RECEIPT_INSERT_SQL:
            self.receipts.append(dict(zip(_COLUMN_ORDER, params)))
            return [{"receipt_id": 1}]
        if "to_tsquery" in sql:
            self.fts_calls.append((sql, params))
            return []
        if sql.startswith("SELECT count(*)"):
            self.count_calls.append((sql, params))
            return [{"total": len(self.rows), "kept": len(self.rows)}]
        self.vector_calls.append((sql, params))
        return list(self.rows)


@pytest.fixture
def search_dependencies(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(agent_tools, "_db_service", db)
    monkeypatch.setattr(agent_tools, "_run_async", asyncio.run)
    extractor = MagicMock()
    extractor.extract.return_value = dict(EXTRACTED)
    monkeypatch.setattr(structured_extract, "get_structured_extractor", lambda: extractor)
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.01] * 1024
    monkeypatch.setattr(embeddings, "EmbeddingService", lambda: embedder)
    ranker = MagicMock()
    ranker.rerank.side_effect = lambda **kw: [
        {"index": i, "relevance_score": 1 - i / 10}
        for i in range(len(kw["documents"]))
    ]
    monkeypatch.setattr(rerank, "get_rerank_service", lambda: ranker)
    return db, extractor


def receipt_config(db):
    assert len(db.receipts) == 1
    return json.loads(db.receipts[0]["retrieval_config"])


def assert_hard_predicates_reach_sql(db):
    """Every vector and full-text statement carries the shopper's hard requirements."""
    assert db.vector_calls
    for sql, params in db.vector_calls + db.fts_calls:
        assert "price <= %s" in sql
        assert "quantity > 0" in sql
        assert "NOT (tags ?| %s OR materials ?| %s)" in sql
        assert ["candle", "wool"] in params


@pytest.mark.parametrize("count", [0, 1, 4, 5])
def test_starter_keeps_first_search_with_planner_on(search_dependencies, count):
    db, extractor = search_dependencies
    db.rows.extend(row(i) for i in range(count))
    result = json.loads(agent_tools.search_products(query=QUERY, limit=5))
    assert "error" not in result, result
    assert result["count"] == count
    assert result.get("relaxation_unavailable", False) is (count < 5)
    assert bool(result.get("search_notice")) is (count < 5)
    assert result["search_plan"]["relaxations"] == []
    assert len(db.vector_calls) == 1
    assert_hard_predicates_reach_sql(db)
    config = receipt_config(db)
    assert config.get("relaxation_unavailable", False) is (count < 5)
    assert config["relaxation_steps"] == []
    assert len(config["attempts"]) == 1
    extractor.extract.assert_called_once_with(QUERY)


def test_starter_still_refuses_the_participant_contract():
    plan = search_plan.build_plan(QUERY, EXTRACTED)
    with pytest.raises(ValueError, match="Complete Task 1B"):
        plan.relaxation_ladder()


def test_comparison_and_evaluation_still_require_the_exercise(search_dependencies):
    plan = search_plan.build_plan(QUERY, EXTRACTED)
    with pytest.raises(ValueError, match="Complete Task 1B"):
        asyncio.run(execute_search_plan(
            search_dependencies[0], plan=plan, query=QUERY, limit=5,
            embed=lambda _: [0.01] * 1024, rerank=lambda **_: [], config={},
        ))


def test_unexpected_plan_errors_are_not_hidden(search_dependencies, monkeypatch):
    def broken(_self):
        raise ValueError("unexpected plan failure")
    monkeypatch.setattr(search_plan.SearchPlan, "relaxation_ladder", broken)
    result = json.loads(agent_tools.search_products(query=QUERY))
    assert result == {"error": "unexpected plan failure"}


def test_ineligible_rows_stay_out(search_dependencies):
    db, extractor = search_dependencies
    db.rows.extend([
        row(1), {**row(2), "price": 149}, {**row(3), "quantity": 0},
        {**row(4), "tags": ["candle"]},
    ])
    result = json.loads(agent_tools.search_products(query=QUERY))
    assert "error" not in result, result
    assert result["count"] == 1
    assert str(result["products"][0]["productId"]) == "1"
    assert result["relaxation_unavailable"] is True
    assert len(db.vector_calls) == 1
    assert_hard_predicates_reach_sql(db)


def test_extraction_notice_is_retained_with_incomplete_relaxation(search_dependencies):
    db, extractor = search_dependencies
    extractor.extract.return_value = {**EXTRACTED, "exclusions": ["candle", "glitter"]}
    result = json.loads(agent_tools.search_products(query=QUERY))
    assert "error" not in result, result
    assert "glitter" in result["constraint_notice"]
    assert result["search_notice"]


@pytest.mark.parametrize("query,envelope", [
    (
        "A housewarming gift for someone who loves slow Sunday mornings.",
        {"tags": ["gift", "slow", "home"], "categories": ["Home", "Stationery and gifts"]},
    ),
    (
        "A gift up to $100, in stock, with no candles. "
        "I'd prefer a watch, but other gifts are fine.",
        {"tags": ["gift", "watch"], "price_max_usd": 100, "in_stock_only": True,
         "exclusions": ["candle"]},
    ),
])
def test_annas_opening_questions_do_not_error_before_task_1b(search_dependencies, query, envelope):
    db, extractor = search_dependencies
    extractor.extract.return_value = {**envelope, "soft_signal": query}
    result = json.loads(agent_tools.search_products(query=query))
    assert "error" not in result, result
    assert result["count"] == 0
    assert result["relaxation_unavailable"] is True
    assert "have not been checked" in result["search_notice"]
    assert len(db.vector_calls) == 1


def test_completed_task_1b_runs_normally_in_storefront(
    search_dependencies, completed_search_plan, monkeypatch
):
    # The fixture is used only for this after-completion test, never for the
    # starter regressions above. It proves the wrapper does not bypass the lab.
    db, extractor = search_dependencies

    async def fetch_all(sql, *params):
        if sql == RECEIPT_INSERT_SQL:
            db.receipts.append(dict(zip(_COLUMN_ORDER, params)))
            return [{"receipt_id": 1}]
        if "to_tsquery" in sql:
            return []
        if sql.startswith("SELECT count(*)"):
            db.count_calls.append((sql, params))
            return [{"total": 100, "kept": 1}]
        db.vector_calls.append((sql, params))
        return [] if "tags ?& %s" in sql else [row(1)]

    monkeypatch.setattr(db, "fetch_all", fetch_all)
    result = json.loads(agent_tools.search_products(query=QUERY))
    assert "error" not in result, result
    assert result["count"] == 1
    assert result["relaxation_unavailable"] is False
    assert "search_notice" not in result
    config = receipt_config(db)
    assert config["relaxation_steps"] == ["drop_tags"]
    assert len(config["attempts"]) == 2
    assert len(db.vector_calls) == 2
    assert_hard_predicates_reach_sql(db)
