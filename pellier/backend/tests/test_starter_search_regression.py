"""Planner-on search with the Task 1B starter; real plan and executor, stubbed external services.

The starter's fallback is the one ``workshop/starters`` ships, whatever the live
file holds. A full first search never reaches it. A sparse one does, and its
retry drops the shopper's hard limits: that is the Lab 1 failure the guide's
Spot step shows, and the solution's retry keeps them.
"""
import json
from unittest.mock import MagicMock

import pytest

from services import agent_tools, embeddings, rerank, search_plan, structured_extract
from services.retrieval_receipt import INSERT_SQL as RECEIPT_INSERT_SQL
from services.retrieval_receipt import _COLUMN_ORDER
from tests import lab_variants

QUERY = "A housewarming gift under $100, in stock, no candles or wool; prefer slow mornings."
EXTRACTED = {
    "price_max_usd": 100,
    "in_stock_only": True,
    "exclusions": ["candle", "wool"],
    "tags": ["gift", "slow", "home"],
    "soft_signal": "a housewarming gift for slow mornings",
}
HARD_PREDICATES = ("price <= %s", "quantity > 0", "NOT (tags ?| %s OR materials ?| %s)")


def row(i, **changes):
    return {
        "product_id": str(i), "name": f"Cotton gift {i}", "brand": "Pellier",
        "description": "A cotton gift", "price": 48, "quantity": 10,
        "category": "Home", "tags": ["gift", "slow", "home"],
        "materials": ["cotton"], "rating": 4.5, "reviews": "2",
        "rrf_score": 0.1, "img_url": "", "color": "Ivory", **changes,
    }


class FakeDB:
    """The pool behind ``agent_tools._run_sql``: branch rows out, statements recorded.

    ``strict_rows`` answer a statement carrying the tag preference; ``wide_rows``
    answer one without it, which is what a fallback attempt sends.
    """

    def __init__(self):
        self.strict_rows = []
        self.wide_rows = []
        self.vector_calls = []
        self.receipts = []

    async def fetch_all(self, sql, *params):
        if sql == RECEIPT_INSERT_SQL:
            self.receipts.append(dict(zip(_COLUMN_ORDER, params)))
            return [{"receipt_id": 1}]
        if "to_tsquery" in sql:
            return []
        if sql.startswith("SELECT count(*)"):
            return [{"total": 100, "kept": len(self.strict_rows)}]
        self.vector_calls.append((sql, params))
        return list(self.strict_rows if "tags ?& %s" in sql else self.wide_rows)


@pytest.fixture
def search(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(agent_tools, "_db_service", db)
    monkeypatch.setattr(agent_tools, "_main_loop", None)
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

    def run(variant=lab_variants.STARTER):
        monkeypatch.setattr(search_plan.SearchPlan, "_with_relaxations",
                            lab_variants.plan_fallback(variant))
        return json.loads(agent_tools.search_products(query=QUERY, limit=5))

    run.db = db
    run.extractor = extractor
    return run


def receipt_config(db):
    assert len(db.receipts) == 1
    return json.loads(db.receipts[0]["retrieval_config"])


def test_a_full_first_search_never_reaches_the_fallback(search) -> None:
    search.db.strict_rows.extend(row(i) for i in range(5))
    result = search()
    assert "error" not in result, result
    assert result["count"] == 5
    assert result["search_plan"]["relaxations"] == []
    assert len(search.db.vector_calls) == 1
    for predicate in HARD_PREDICATES:
        assert predicate in search.db.vector_calls[0][0]
    assert len(receipt_config(search.db)["attempts"]) == 1
    search.extractor.extract.assert_called_once_with(QUERY)


def test_the_starter_retry_sends_a_search_without_the_shoppers_limits(search) -> None:
    search.db.strict_rows.append(row(1))
    search.db.wide_rows.extend([row(2, price=149), row(3, quantity=0), row(4, tags=["candle"]),
                                row(5)])
    result = search()
    first, retry = search.db.vector_calls
    for predicate in HARD_PREDICATES:
        assert predicate in first[0]
        assert predicate not in retry[0]
    returned = {product["productId"] for product in result["products"]}
    assert {"2", "3", "4"} <= returned, "the retry let a $149 piece, a sold-out and a candle in"
    assert result["search_plan"]["relaxations"][0]["step"] == "drop_tags"
    assert result["search_plan"]["hard_constraints"]["price_max_usd"] is None
    assert receipt_config(search.db)["relaxation_steps"] == ["drop_tags"]


def test_the_solution_retry_keeps_the_shoppers_limits(search) -> None:
    search.db.strict_rows.append(row(1))
    search.db.wide_rows.extend([row(2, price=149), row(3, quantity=0), row(4, tags=["candle"]),
                                row(5)])
    result = search(lab_variants.SOLUTION)
    for sql, _params in search.db.vector_calls:
        for predicate in HARD_PREDICATES:
            assert predicate in sql
    assert {product["productId"] for product in result["products"]} == {"5"}
    assert result["search_plan"]["hard_constraints"]["price_max_usd"] == 100


def test_unexpected_plan_errors_are_not_hidden(search, monkeypatch) -> None:
    def broken(_self):
        raise ValueError("unexpected plan failure")

    result = search()
    assert "error" not in result
    monkeypatch.setattr(search_plan.SearchPlan, "relaxation_ladder", broken)
    result = json.loads(agent_tools.search_products(query=QUERY))
    assert result == {"error": "unexpected plan failure"}


def test_ineligible_rows_stay_out_of_the_first_search(search) -> None:
    search.db.strict_rows.extend([
        row(1), row(2, price=149), row(3, quantity=0), row(4, tags=["candle"]),
    ])
    search.db.wide_rows.append(row(1))
    result = search(lab_variants.SOLUTION)
    assert [product["productId"] for product in result["products"]] == ["1"]


def test_an_extraction_notice_survives_the_solution_retry(search) -> None:
    search.extractor.extract.return_value = {**EXTRACTED, "exclusions": ["candle", "glitter"]}
    search.db.wide_rows.append(row(1))
    result = search(lab_variants.SOLUTION)
    assert "error" not in result, result
    assert result["search_plan"]["relaxations"][0]["step"] == "drop_tags"
    assert "glitter" in result["constraint_notice"]


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
def test_annas_opening_questions_answer_before_task_1b(search, query, envelope) -> None:
    search.extractor.extract.return_value = {**envelope, "soft_signal": query}
    search.db.wide_rows.append(row(1))
    search.db.strict_rows.clear()
    result = search()
    assert "error" not in result, result
    assert result["count"] == 1
    assert len(search.db.vector_calls) == 2
