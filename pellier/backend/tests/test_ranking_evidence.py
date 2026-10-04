"""The ranking payload comes from the real pipeline, with ranks that match its arms."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

from services import store_tools
from services.ranking_evidence import (
    filter_count_sql,
    filter_counts,
    ranking_from_execution,
    ranking_from_receipt,
    ranking_unavailable,
)
from services.search_plan import build_plan


def _row(pid: int, name: str, price: float, similarity: float | None = None) -> Dict[str, Any]:
    row = {
        "product_id": pid, "name": name, "brand": "Pellier", "color": "Ivory",
        "description": f"{name} description", "img_url": f"/p/{pid}.webp",
        "category": "Home", "price": price, "rating": 4.5, "reviews": 10,
        "badge": None, "tags": ["home"], "materials": ["ceramic"], "quantity": 5,
        "updated_at": None,
    }
    if similarity is not None:
        row["similarity"] = similarity
    return row


VECTOR_ROWS = [_row(1, "Tall Stoneware Vase", 42, 0.81), _row(2, "Ceramic Bud Vase", 22, 0.77), _row(3, "Brass Photo Frame", 38, 0.70)]
FTS_ROWS = [dict(_row(3, "Brass Photo Frame", 38), fts_rank_score=0.9), dict(_row(4, "Linen Napkins, Set of 4", 44), fts_rank_score=0.4)]


def _run(sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    if "query_embedding" in sql:
        return [dict(row) for row in VECTOR_ROWS]
    if "to_tsquery" in sql:
        return [dict(row) for row in FTS_ROWS]
    return []


def _rerank(*, query: str, documents: List[str], top_n: int) -> List[Dict[str, Any]]:
    # Reverse the pool so the before and after positions differ.
    return [{"index": index, "relevance_score": 0.9 - 0.1 * position}
            for position, index in enumerate(reversed(range(len(documents))))]


def _fixture_execution():
    plan = build_plan("a vase for the hall", {"price_max_usd": 100}, top_k=4)
    return store_tools.run_search_plan(
        _run, plan=plan, query="a vase for the hall", limit=4,
        embed=lambda text: [0.1, 0.2, 0.3], rerank=_rerank,
        config=dict(store_tools.DEFAULT_RETRIEVAL_CONFIG), relax=False,
    )


def test_ranks_match_the_arms_of_the_fixture_pipeline_run() -> None:
    execution = _fixture_execution()
    ranking = ranking_from_execution(execution, final_rows=execution.ordered, counts=None)

    rows = {row["product_id"]: row for row in ranking["rows"]}
    assert rows["1"]["vec_rank"] == 1 and rows["1"]["fts_rank"] is None
    assert rows["3"]["vec_rank"] == 3 and rows["3"]["fts_rank"] == 1
    assert rows["4"]["vec_rank"] is None and rows["4"]["fts_rank"] == 2
    assert rows["1"]["similarity"] == 0.81 and rows["4"]["similarity"] is None
    assert rows["3"]["rrf_score"] == 1 / 63 + 1 / 61
    assert ranking["arms"] == {"full_text": 2, "vector": 3, "fused": 4}
    assert ranking["rrf_k"] == 60 and ranking["available"] is True
    assert ranking["method"] == "hybrid+rerank"


def test_before_and_after_positions_are_rrf_order_then_final_order() -> None:
    execution = _fixture_execution()
    ranking = ranking_from_execution(execution, final_rows=execution.ordered, counts=None)

    rrf_order = [str(row["product_id"]) for row in execution.candidates]
    final_order = [str(row["product_id"]) for row in execution.ordered]
    for row in ranking["rows"]:
        assert row["before"] == rrf_order.index(row["product_id"]) + 1
        assert row["after"] == final_order.index(row["product_id"]) + 1
    # The fake reranker reverses the pool, so at least one row moved.
    assert any(row["before"] != row["after"] for row in ranking["rows"])
    assert all(row["rerank_score"] is not None for row in ranking["rows"])


def test_filter_count_sql_follows_the_plans_own_predicates() -> None:
    plan = build_plan(
        "a gift", {"price_max_usd": 100, "in_stock_only": True, "exclusions": ["candle"]}, top_k=5,
    )
    sql, params, reasons = filter_count_sql(plan)

    assert reasons == ["budget", "stock", "exclusions"]
    assert "count(*) FILTER (WHERE NOT (price <= %s)) AS removed_budget" in sql
    assert "count(*) FILTER (WHERE (price <= %s) AND NOT (quantity > 0)) AS removed_stock" in sql
    assert "AS removed_exclusions" in sql and "AS kept" in sql
    # Budget: price. Stock: price prefix. Exclusions: price prefix, then the two arrays.
    # Kept: price, then the two arrays.
    assert params == [100.0, 100.0, 100.0, ["candle"], ["candle"], 100.0, ["candle"], ["candle"]]
    assert sql.count("%s") == len(params)


def test_filter_counts_shape_from_one_aggregate_row() -> None:
    plan = build_plan("a gift", {"price_max_usd": 100, "in_stock_only": True}, top_k=5)
    seen: List[str] = []

    def run(sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        seen.append(sql)
        return [{"total": 100, "removed_budget": 61, "removed_stock": 9, "kept": 30}]

    counts = filter_counts(run, plan)
    assert counts == {"kept": 30, "of": 100, "removed": {"budget": 61, "stock": 9}}
    assert len(seen) == 1, "one aggregate statement, never a second search"


def test_no_limits_means_everything_is_kept() -> None:
    sql, params, reasons = filter_count_sql(build_plan("anything", {}, top_k=5))
    assert reasons == [] and params == [] and "count(*) AS kept" in sql


def test_ranking_from_receipt_reads_ranks_and_says_what_it_lacks() -> None:
    receipt = {
        "receipt_id": 77,
        "retrieval_config": json.dumps({"search_method": "hybrid+rerank", "rrf_k": 60, "rerank_pool_k": 15}),
        "candidate_product_ids": json.dumps(["1", "3", "2", "4"]),
        "vector_ranks": json.dumps({"1": 1, "2": 2, "3": 3}),
        "lexical_ranks": json.dumps({"3": 1, "4": 2}),
        "rrf_scores": json.dumps({"1": 0.0164, "2": 0.0161, "3": 0.0323, "4": 0.0161}),
        "rerank_scores": json.dumps({"1": 0.4, "2": 0.9, "3": 0.8}),
        "citation_ids": json.dumps(["2", "3"]),
        "citation_snapshots": json.dumps([{"entity_id": "2", "quote": "Ceramic Bud Vase: small"}]),
    }
    ranking = ranking_from_receipt(receipt, names={"3": "Brass Photo Frame"})

    assert ranking["available"] is True and ranking["rail"] == "gateway-mcp"
    assert [row["product_id"] for row in ranking["rows"]] == ["2", "3", "1", "4"]
    assert ranking["rows"][0]["name"] == "Ceramic Bud Vase"
    assert ranking["rows"][1]["name"] == "Brass Photo Frame"
    assert ranking["rows"][0]["before"] == 3 and ranking["rows"][0]["after"] == 1
    assert ranking["rows"][1]["fts_rank"] == 1 and ranking["rows"][1]["vec_rank"] == 3
    assert all(row["similarity"] is None for row in ranking["rows"])
    assert ranking["filters"] is None and "no vector similarity" in ranking["note"]
    assert ranking["receipt_id"] == 77


def test_unavailable_payload_says_so_plainly() -> None:
    assert ranking_unavailable("gateway-mcp", "No retrieval receipt was written for this turn") == {
        "available": False,
        "rail": "gateway-mcp",
        "reason": "No retrieval receipt was written for this turn",
    }
