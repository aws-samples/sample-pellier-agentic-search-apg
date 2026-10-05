"""The storefront grid shows the agent's own search result, never a second search.

A catalog tool publishes its result order, the limits it applied and the
filter counts on the evidence channel, beside the result the model reads.
These tests pin that the ids follow the tool's actual order (the rows the
model read first, in the same order, then the rest of the fused pool in RRF
order), that the model-facing result does not change, that each limit says
where it came from, and that the managed rail carries what its receipt allows
and says plainly what it cannot.
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
from services import active_requirements, store_tools, tool_evidence
from services.ranking_evidence import (
    RECEIPT_RESULTS_NOTE,
    RESULT_IDS_MAX,
    result_limits,
    results_from_receipt,
)
from services.retrieval_receipt import INSERT_SQL as RECEIPT_INSERT_SQL
from services.search_plan import build_plan
from services.turn_steps import TurnSteps


def _row(pid: int, *, price: float = 40.0, rating: float = 4.5) -> Dict[str, Any]:
    return {
        "product_id": pid, "name": f"Product {pid}", "brand": "Pellier", "color": "Sand",
        "description": f"Product {pid}", "img_url": f"/p/{pid}.webp", "category": "Home",
        "price": price, "rating": rating, "reviews": "10", "badge": None, "tags": ["home"],
        "materials": ["ceramic"], "quantity": 5, "updated_at": None,
    }


class _FakeDB:
    """Twenty vector rows and ten full-text rows; the counts row for the evidence."""

    def __init__(self) -> None:
        self.vector = [_row(pid) for pid in range(1, 21)]
        self.fts = [_row(pid) for pid in range(15, 25)]
        self.kinds: List[str] = []

    async def fetch_all(self, sql: str, *params: Any) -> List[Dict[str, Any]]:
        if sql == RECEIPT_INSERT_SQL:
            self.kinds.append("receipt")
            return [{"receipt_id": 9}]
        if sql.startswith("SELECT count(*)"):
            self.kinds.append("counts")
            return [{"total": 100, "removed_0": 31, "removed_1": 1, "removed_2": 4, "kept": 64}]
        if "to_tsquery" in sql:
            self.kinds.append("fts")
            return [dict(row) for row in self.fts]
        self.kinds.append("vector")
        return [dict(row) for row in self.vector]


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> _FakeDB:
    fake = _FakeDB()
    monkeypatch.setattr(agent_tools, "_db_service", fake)
    monkeypatch.setattr(agent_tools, "_run_async", asyncio.run)
    embed = MagicMock()
    embed.embed_query.side_effect = lambda _q: [0.01] * 8
    monkeypatch.setattr(embeddings_module, "EmbeddingService", lambda *_, **__: embed)
    reranker = MagicMock()
    # Reverse the rerank pool, so the reranked order differs from RRF order.
    reranker.rerank.side_effect = lambda **kw: [
        {"index": index, "relevance_score": 0.9 - 0.01 * position}
        for position, index in enumerate(reversed(range(len(kw["documents"]))))
    ]
    monkeypatch.setattr(rerank_module, "get_rerank_service", lambda: reranker)
    monkeypatch.setattr(
        agent_tools, "_extract_query_structure",
        lambda _q: {"price_max_usd": 100.0, "in_stock_only": True, "exclusions": ["candle"]},
    )
    return fake


def _search_in_turn(**kwargs: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
    channel = tool_evidence.open_channel()
    try:
        parsed = json.loads(agent_tools.search_products.__wrapped__(**kwargs))
        evidence = tool_evidence.take("search_products")
    finally:
        tool_evidence.close_channel(channel)
    return parsed, evidence


# ---------------------------------------------------------------------------
# The ids follow the tool's actual order
# ---------------------------------------------------------------------------


def test_the_ids_are_the_models_products_first_then_the_pool_in_rrf_order(db: _FakeDB) -> None:
    parsed, evidence = _search_in_turn(query="a vase", limit=5)
    results = evidence["results"]
    ids = results["product_ids"]

    shown = [product["productId"] for product in parsed["products"]]
    assert ids[: len(shown)] == shown, "the grid starts with exactly what the model read"

    # The whole fused pool fits in one result: the reranked pool, then the rest in RRF order.
    pool_k = store_tools.DEFAULT_RERANK_POOL_K
    vector = [str(row["product_id"]) for row in db.vector]
    fts = [str(row["product_id"]) for row in db.fts]
    rrf = [str(row["product_id"]) for row in store_tools.rrf_merge(
        [{"product_id": pid} for pid in vector], [{"product_id": pid} for pid in fts], 60,
    )]
    assert ids[:pool_k] == list(reversed(rrf[:pool_k]))
    assert ids[pool_k:] == rrf[pool_k:]
    assert len(ids) == len(set(ids)) == len(rrf) <= RESULT_IDS_MAX
    # The page's count describes the grid: the size of this result, from the backend.
    assert results["count"] == len(ids)


def test_the_results_carry_limits_and_the_filter_counts(db: _FakeDB) -> None:
    _, evidence = _search_in_turn(query="a vase", limit=5)
    results = evidence["results"]
    assert results["available"] is True and results["rail"] == "in-process"
    assert results["filters"] == evidence["ranking"]["filters"]
    assert results["filters"]["kept"] == 64 and results["filters"]["of"] == 100
    assert results["filters"]["excluded"] == [{"value": "candle", "count": 4, "noun": "candles"}]
    assert [(tag["label"], tag["origin"]) for tag in results["limits"]] == [
        ("Under $100", "stated"), ("In stock", "stated"), ("No candles", "stated"),
    ]
    assert "tool" not in results, "the shopper's view of a step names no tool"


def test_the_model_facing_result_is_unchanged_by_the_evidence(db: _FakeDB) -> None:
    outside = agent_tools.search_products.__wrapped__(query="a vase", limit=5)
    inside = json.dumps(_search_in_turn(query="a vase", limit=5)[0], indent=2)
    assert inside == outside
    assert "product_ids" not in outside and "limits" not in outside


def test_ids_respect_the_same_checks_as_the_products_shown() -> None:
    plan = build_plan("a vase", {"price_max_usd": 100.0}, top_k=3)
    ordered = [_row(1, rating=4.9), _row(2, rating=3.0), _row(3, rating=4.8)]
    candidates = [*ordered, _row(4, price=120.0), _row(5, rating=4.6)] + [_row(pid) for pid in range(6, 60)]
    ids = store_tools.result_product_ids(
        ordered, candidates, plan=plan, max_price=None, min_rating=4.5,
    )
    # Rating below the floor and a row over the plan's ceiling never reach the grid.
    assert ids[:3] == ["1", "3", "5"]
    assert "2" not in ids and "4" not in ids
    assert len(ids) == RESULT_IDS_MAX


# ---------------------------------------------------------------------------
# A browse: its rows in order, the model still reads its limit
# ---------------------------------------------------------------------------


class _BrowseRun:
    def __init__(self) -> None:
        self.calls: List[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        self.calls.append((sql, tuple(params)))
        if sql.startswith("SELECT count(*)"):
            return [{"total": 100, "removed_0": 86, "kept": 14}]
        limit = params[-1]
        return [
            {"productId": str(pid), "name": f"Piece {pid}", "brand": "Pellier", "price": 30,
             "rating": 4.5, "reviews": 3, "category": "Home", "imgUrl": "/p.webp", "tags": []}
            for pid in range(40, 40 + min(limit, 14))
        ]


def test_a_browse_in_a_turn_fills_the_grid_and_the_model_reads_five(monkeypatch) -> None:
    run = _BrowseRun()
    monkeypatch.setattr(agent_tools, "_db_service", object())
    monkeypatch.setattr(agent_tools, "_run_sql", run)
    channel = tool_evidence.open_channel()
    try:
        parsed = json.loads(agent_tools.browse_department.__wrapped__(department="Home"))
        evidence = tool_evidence.take("browse_department")
    finally:
        tool_evidence.close_channel(channel)

    assert run.calls[0][1][-1] == RESULT_IDS_MAX
    assert [p["productId"] for p in parsed["products"]] == ["40", "41", "42", "43", "44"]
    results = evidence["results"]
    assert results["product_ids"] == [str(pid) for pid in range(40, 54)]
    assert results["count"] == 14
    assert results["filters"]["kept"] == 14 and results["filters"]["removed"] == {"department": 86}
    assert "LIKE %s" in run.calls[1][0], "the counts reuse the browse's own department predicate"


def test_a_browse_outside_a_turn_reads_only_its_limit(monkeypatch) -> None:
    run = _BrowseRun()
    monkeypatch.setattr(agent_tools, "_db_service", object())
    monkeypatch.setattr(agent_tools, "_run_sql", run)
    parsed = json.loads(agent_tools.browse_department.__wrapped__(department="Home", limit=3))
    assert len(run.calls) == 1 and run.calls[0][1][-1] == 3
    assert parsed["count"] == 3


# ---------------------------------------------------------------------------
# Where each limit came from
# ---------------------------------------------------------------------------

PLAN = {
    "hard_constraints": {"price_max_usd": 100.0, "in_stock_only": True, "categories": ["Home"]},
    "exclusions": ["candle", "watch"],
}


def test_carried_limits_say_so_one_excluded_value_at_a_time() -> None:
    tags = result_limits(
        PLAN, carried=["budget", "stock", "exclusions"], carried_exclusions=["candle"], shopper_price=100.0,
    )
    assert [(tag["label"], tag["origin"]) for tag in tags] == [
        ("Under $100", "carried"),
        ("In stock", "carried"),
        ("No candles", "carried"),
        ("No watches", "stated"),
        ("Home", "stated"),
    ]


def test_a_ceiling_the_shopper_never_stated_is_the_agents() -> None:
    tags = result_limits(
        {"hard_constraints": {"price_max_usd": 50.0}}, carried=[], shopper_price=None,
    )
    assert tags == [{"kind": "budget", "label": "Under $50", "origin": "agent"}]
    tags = result_limits(
        {"hard_constraints": {"price_max_usd": 50.0}}, carried=["budget"], shopper_price=100.0,
    )
    assert tags[0]["origin"] == "agent"


def test_a_rail_with_no_record_places_no_limit() -> None:
    assert {tag["origin"] for tag in result_limits(PLAN)} == {None}


def test_carried_exclusions_name_only_the_values_kept_from_earlier(monkeypatch) -> None:
    active_requirements.remember("sess-c3", {"exclusions": ["candle"], "price_max_usd": 100.0})
    token = active_requirements.bind_turn(
        session_id="sess-c3", message="no watches either",
        conversation_history=[{"role": "user", "content": "no candles, under $100"}],
    )
    try:
        reading, carried = active_requirements.turn_requirements(
            lambda: {"exclusions": ["watch"], "price_max_usd": None}
        )
        assert reading["exclusions"] == ["watch", "candle"]
        assert carried == ["budget", "exclusions"]
        assert active_requirements.carried_exclusions() == ["candle"]
    finally:
        active_requirements.reset_turn(token)
        active_requirements.forget_session("sess-c3")
    assert active_requirements.carried_exclusions() == []


# ---------------------------------------------------------------------------
# The step event and the managed rail
# ---------------------------------------------------------------------------

RESULTS = {"available": True, "rail": "in-process", "product_ids": ["31", "36"], "limits": [], "filters": None}


def test_the_done_step_carries_the_results_beside_builder() -> None:
    steps = TurnSteps()
    steps.running("search_products", {"query": "gift"})
    done = steps.finished(
        "search_products",
        json.dumps({"status": "success", "count": 2, "products": [], "search_plan": {}}),
        evidence={"results": RESULTS},
    )
    assert done["results"] == RESULTS
    assert "results" not in done["builder"]

    failed = steps.finished("search_products", json.dumps({"error": "boom"}), evidence={"results": RESULTS})
    assert failed["status"] == "failed" and "results" not in failed


def test_a_step_without_results_has_no_results_key() -> None:
    steps = TurnSteps()
    done = steps.finished("check_stock", json.dumps({"status": "not_found"}))
    assert "results" not in done


def test_the_managed_step_carries_the_receipts_results() -> None:
    steps = TurnSteps()
    done = steps.managed({"tool": "search_products", "status": "success", "results": RESULTS})
    assert done["results"] == RESULTS


def test_results_from_a_receipt_keep_its_order_and_say_what_it_lacks() -> None:
    receipt = {
        "candidate_product_ids": json.dumps(["1", "3", "2", "4"]),
        "rerank_scores": json.dumps({"1": 0.4, "2": 0.9, "3": 0.8}),
        "citation_ids": json.dumps(["2", "3"]),
        "search_plan": json.dumps(
            {"hard_constraints": {"price_max_usd": 100.0, "in_stock_only": True}, "exclusions": ["candle"]}
        ),
    }
    results = results_from_receipt(receipt)
    assert results["product_ids"] == ["2", "3", "1", "4"] and results["count"] == 4
    assert [tag["label"] for tag in results["limits"]] == ["Under $100", "In stock", "No candles"]
    assert {tag["origin"] for tag in results["limits"]} == {None}
    assert results["filters"] is None and results["note"] == RECEIPT_RESULTS_NOTE
    assert results["rail"] == "gateway-mcp"
