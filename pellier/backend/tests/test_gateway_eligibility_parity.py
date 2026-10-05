"""The Gateway Lambda runs the same ``store_tools`` pipeline as the in-process tool.

Parity is by construction now: there is one search implementation,
``services/store_tools.py``, and the Lambda ``scripts/deploy/pellier_store_tools.py``
only hands it the Data API runner. These tests pin that wiring (the Lambda
dispatches every tool to ``store_tools`` with ``run_store_sql``) and the
transport (``run_store_sql`` binds ``%s`` placeholders as Data API
parameters), then drive a search through both to prove the eligibility recheck
and the LIKE escaping survive the Data API's string-typed rows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_DEPLOY = Path(__file__).resolve().parents[3] / "scripts" / "deploy"
if str(_DEPLOY) not in sys.path:
    sys.path.insert(0, str(_DEPLOY))

import common.dataapi as dataapi  # noqa: E402
import pellier_store_tools as lambda_tools  # noqa: E402
from gateway_tool_schemas import TOOL_SCHEMAS  # noqa: E402
from services import store_tools  # noqa: E402


class _DataApiFake:
    """Replaces ``dataapi.execute_sql``: records bound statements, serves branch rows."""

    def __init__(self, vector_rows: List[Dict[str, Any]] = (), fts_rows: List[Dict[str, Any]] = ()):
        self.vector_rows = list(vector_rows)
        self.fts_rows = list(fts_rows)
        self.statements: List[tuple[str, Dict[str, Any]]] = []

    def __call__(self, sql: str, parameters: list | None = None) -> List[Dict[str, Any]]:
        bound = {item["name"]: item["value"] for item in parameters or []}
        self.statements.append((sql, bound))
        if "to_tsquery" in sql:
            return [dict(row) for row in self.fts_rows]
        if "query_embedding" in sql:
            return [dict(row) for row in self.vector_rows]
        return []


def _data_api_row(product_id: str, name: str, price: str, quantity: int = 3) -> Dict[str, Any]:
    """A catalog row as the Data API returns it: numbers and JSON arrive as text."""
    return {
        "product_id": product_id,
        "name": name,
        "brand": "Pellier",
        "color": "Sand",
        "description": "linen",
        "img_url": "https://example.com/p.jpg",
        "category": "Clothing",
        "price": price,
        "rating": "4.5",
        "reviews": "12",
        "badge": None,
        "tags": '["linen"]',
        "materials": '["linen"]',
        "quantity": quantity,
        "updated_at": "2026-08-01 00:00:00",
    }


def _rank_in_order(*, query: str, documents: List[str], top_n: int) -> List[Dict[str, Any]]:
    return [{"index": i, "relevance_score": 1.0 - i / 10} for i in range(len(documents))]


# ---------------------------------------------------------------------------
# Lexical query: one builder, both rails
# ---------------------------------------------------------------------------


def test_grey_and_gray_search_the_same_catalog_word() -> None:
    assert store_tools.or_tsquery("a grey crewneck") == "gray | crewneck"
    assert store_tools.or_tsquery("a gray crewneck") == "gray | crewneck"


def test_the_lambda_lexical_branch_is_the_or_joined_query(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _DataApiFake([_data_api_row("1", "Linen Shirt", "120")])
    monkeypatch.setattr(dataapi, "execute_sql", fake)
    monkeypatch.setattr(lambda_tools, "query_embedding", lambda _q: [0.1, 0.2])
    monkeypatch.setattr(lambda_tools, "rerank_documents", _rank_in_order)

    lambda_tools.TOOLS["search_products"](
        {"query": "a thoughtful gift for someone who loves morning rituals"}, None
    )

    fts = [(sql, bound) for sql, bound in fake.statements if "to_tsquery" in sql]
    assert len(fts) == 1
    sql, bound = fts[0]
    assert "plainto_tsquery" not in sql
    assert bound["p0"] == {"stringValue": "thoughtful | gift | morning | rituals"}


# ---------------------------------------------------------------------------
# Dispatch: every Lambda tool is a store_tools function on the Data API runner
# ---------------------------------------------------------------------------


def test_the_lambda_publishes_exactly_the_nine_store_tools() -> None:
    catalogue = {tool["name"] for tool in TOOL_SCHEMAS["store"]["tools"]}
    assert set(lambda_tools.TOOLS) == catalogue == set(store_tools.TOOL_NAMES)
    assert len(store_tools.TOOL_NAMES) == 9
    assert TOOL_SCHEMAS["store"]["target_name"] == "pellier-store-tools"


@pytest.mark.parametrize("tool_name", store_tools.TOOL_NAMES)
def test_each_lambda_tool_dispatches_to_store_tools_with_the_data_api_runner(
    monkeypatch: pytest.MonkeyPatch, tool_name: str
) -> None:
    seen: Dict[str, Any] = {}

    def spy(run: Any, **kwargs: Any) -> Dict[str, Any]:
        seen["run"], seen["kwargs"] = run, kwargs
        return {"status": "success", "tool": tool_name}

    monkeypatch.setattr(store_tools, tool_name, spy)
    scoped_run = object()
    bound: list[str] = []

    def as_customer(customer_id: str, work: Any) -> Any:
        bound.append(customer_id)
        return work(scoped_run)

    monkeypatch.setattr(lambda_tools, "run_as_customer", as_customer)

    result = lambda_tools.TOOLS[tool_name]({"customer_id": "CUST-THEO"}, None)

    assert result == {"status": "success", "tool": tool_name}
    if tool_name in ("get_orders", "get_tickets"):
        # A customer's own read runs as pellier_agent with that customer named.
        assert seen["run"] is scoped_run and bound == ["CUST-THEO"]
    else:
        assert seen["run"] is dataapi.run_store_sql and bound == []


def test_search_products_hands_store_tools_the_gateway_pipeline_pieces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: Dict[str, Any] = {}

    def spy(run: Any, **kwargs: Any) -> Dict[str, Any]:
        seen["run"], seen["kwargs"] = run, kwargs
        return {"status": "success"}

    monkeypatch.setattr(store_tools, "search_products", spy)

    lambda_tools.TOOLS["search_products"](
        {"query": "linen", "max_price": "150", "min_rating": "4.2", "limit": "3", "category": "Home"},
        "turn-abcdef123456",
    )

    kwargs = seen["kwargs"]
    assert seen["run"] is dataapi.run_store_sql
    assert kwargs["embed"] is dataapi.query_embedding
    assert kwargs["rerank"] is dataapi.rerank_documents
    assert kwargs["extracted"] is None
    assert kwargs["max_price"] == 150.0
    assert kwargs["min_rating"] == 4.2
    assert kwargs["limit"] == 3
    assert kwargs["category"] == "Home"
    assert "config" not in kwargs, "the Lambda runs on DEFAULT_RETRIEVAL_CONFIG"
    assert kwargs["receipt"] == {
        "turn_id": "turn-abcdef123456",
        "rail": "gateway-mcp",
        "embedding_model": dataapi.EMBED_MODEL_ID,
        "rerank_model": dataapi.RERANK_MODEL_ID,
    }


def test_search_products_writes_no_receipt_without_a_turn_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: Dict[str, Any] = {}
    monkeypatch.setattr(
        store_tools, "search_products", lambda run, **kwargs: seen.update(kwargs) or {}
    )

    lambda_tools.TOOLS["search_products"]({"query": "linen"}, None)

    assert seen["receipt"] is None


# ---------------------------------------------------------------------------
# Eligibility recheck after the reranker, through the Data API transport
# ---------------------------------------------------------------------------


def test_the_lambda_rechecks_eligibility_after_the_reranker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row past the SQL predicates is dropped after reranking, as in process."""
    rows = [
        _data_api_row("1", "Linen Shirt", "120"),
        _data_api_row("2", "Cashmere Coat", "900"),
        _data_api_row("3", "Linen Tunic", "80"),
    ]
    fake = _DataApiFake(vector_rows=rows)
    monkeypatch.setattr(dataapi, "execute_sql", fake)
    monkeypatch.setattr(lambda_tools, "query_embedding", lambda _q: [0.1, 0.2])
    monkeypatch.setattr(lambda_tools, "rerank_documents", _rank_in_order)

    result = lambda_tools.TOOLS["search_products"](
        {"query": "linen", "max_price": 150, "limit": 5}, None
    )

    # The fake ignores the SQL predicate, so a post-rerank check must drop the coat
    # (the eligibility recheck, then select_shown_products' price defence).
    assert [product["productId"] for product in result["products"]] == ["1", "3"]
    assert result["hard_constraints_enforced"]
    assert result["constraints_applied_before_rerank"] is True


def test_the_price_ceiling_reaches_both_branches_as_a_bound_data_api_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _DataApiFake(
        vector_rows=[_data_api_row("1", "Linen Shirt", "120")],
        fts_rows=[_data_api_row("1", "Linen Shirt", "120")],
    )
    monkeypatch.setattr(dataapi, "execute_sql", fake)
    monkeypatch.setattr(lambda_tools, "query_embedding", lambda _q: [0.1, 0.2])
    monkeypatch.setattr(lambda_tools, "rerank_documents", _rank_in_order)

    lambda_tools.TOOLS["search_products"]({"query": "linen shirt", "max_price": 150}, None)

    branches = [(sql, bound) for sql, bound in fake.statements if "FROM pellier.product_catalog" in sql]
    assert len(branches) == 2
    for sql, bound in branches:
        assert "%s" not in sql
        assert "price <= :p1" in sql
        assert bound["p1"] == {"doubleValue": 150.0}


def test_a_category_argument_is_recorded_and_never_a_sql_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _DataApiFake(vector_rows=[_data_api_row("1", "Linen Shirt", "120")])
    monkeypatch.setattr(dataapi, "execute_sql", fake)
    monkeypatch.setattr(lambda_tools, "query_embedding", lambda _q: [0.1, 0.2])
    monkeypatch.setattr(lambda_tools, "rerank_documents", _rank_in_order)

    result = lambda_tools.TOOLS["search_products"](
        {"query": "bowls", "category": "Kitchen and table"}, None
    )

    assert "Kitchen and table" in result["search_plan"]["inferred_categories"]
    for sql, bound in fake.statements:
        assert "category = ANY" not in sql
        assert {"stringValue": "Kitchen and table"} not in bound.values()


# ---------------------------------------------------------------------------
# LIKE metacharacters stay literal on the Data API rail
# ---------------------------------------------------------------------------


def test_browse_department_escapes_like_metacharacters_on_the_lambda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _DataApiFake()
    monkeypatch.setattr(dataapi, "execute_sql", fake)

    lambda_tools.TOOLS["browse_department"]({"department": r"Home_100% \ Decor"}, None)

    sql, bound = fake.statements[-1]
    assert "ESCAPE" in sql
    assert bound["p0"] == {"stringValue": r"%home\_100\% \\ decor%"}
    assert bound["p0"] == {"stringValue": store_tools.prepare_like_pattern(r"Home_100% \ Decor")}


def test_check_stock_escapes_like_metacharacters_on_the_lambda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _DataApiFake()
    monkeypatch.setattr(dataapi, "execute_sql", fake)

    lambda_tools.TOOLS["check_stock"]({"product_query": r"100%_deal"}, None)

    sql, bound = fake.statements[-1]
    assert "ESCAPE" in sql
    assert bound["p0"] == {"stringValue": r"%100\%\_deal%"}


# ---------------------------------------------------------------------------
# run_store_sql: positional %s -> named Data API parameters
# ---------------------------------------------------------------------------


def test_run_store_sql_rewrites_placeholders_in_order_and_types_the_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _DataApiFake()
    monkeypatch.setattr(dataapi, "execute_sql", fake)

    dataapi.run_store_sql(
        "SELECT 1 WHERE a = %s AND b <= %s AND c > %s AND d IS %s AND e = ANY(%s) AND f = %s",
        ("text", 4.5, 7, None, ["x", "y"], True),
    )

    sql, bound = fake.statements[-1]
    assert sql == (
        "SELECT 1 WHERE a = :p0 AND b <= :p1 AND c > :p2 AND d IS :p3 "
        "AND e = ANY(:p4) AND f = :p5"
    )
    assert bound == {
        "p0": {"stringValue": "text"},
        "p1": {"doubleValue": 4.5},
        "p2": {"longValue": 7},
        "p3": {"isNull": True},
        "p4": {"arrayValue": {"stringValues": ["x", "y"]}},
        "p5": {"booleanValue": True},
    }


def test_run_store_sql_refuses_more_parameters_than_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _DataApiFake()
    monkeypatch.setattr(dataapi, "execute_sql", fake)

    with pytest.raises(ValueError, match="placeholders"):
        dataapi.run_store_sql("SELECT %s", ("a", "b"))

    assert fake.statements == []


def test_run_store_sql_refuses_more_placeholders_than_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _DataApiFake()
    monkeypatch.setattr(dataapi, "execute_sql", fake)

    with pytest.raises(ValueError, match="placeholders"):
        dataapi.run_store_sql("SELECT %s, %s", ("a",))

    assert fake.statements == []


def test_the_lambda_envelope_carries_the_search_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _DataApiFake(vector_rows=[_data_api_row("1", "Linen Shirt", "120")])
    monkeypatch.setattr(dataapi, "execute_sql", fake)
    monkeypatch.setattr(lambda_tools, "query_embedding", lambda _q: [0.1, 0.2])
    monkeypatch.setattr(lambda_tools, "rerank_documents", _rank_in_order)

    response = lambda_tools.lambda_handler(
        {"name": "search_products", "arguments": {"query": "linen"}}, None
    )

    payload = json.loads(response["content"][0]["text"])
    assert payload["status"] == "success"
    assert [product["productId"] for product in payload["products"]] == ["1"]


def test_stock_and_exclusion_requirements_reach_the_plan_as_a_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The managed rail has no extractor; the explicit arguments are the reading."""
    seen: Dict[str, Any] = {}
    monkeypatch.setattr(
        store_tools, "search_products", lambda run, **kwargs: seen.update(kwargs) or {}
    )

    lambda_tools.TOOLS["search_products"](
        {"query": "a gift", "in_stock_only": "true", "exclusions": ["candle", "wool"]}, None
    )
    assert seen["extracted"] == {
        "in_stock_only": True,
        "exclusions": ["candle", "wool"],
        "soft_signal": "a gift",
    }

    lambda_tools.TOOLS["search_products"]({"query": "a gift", "exclusions": "candle"}, None)
    assert seen["extracted"] == {"in_stock_only": False, "exclusions": ["candle"], "soft_signal": "a gift"}
