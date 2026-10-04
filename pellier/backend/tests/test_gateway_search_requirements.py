"""Managed ``search_products`` carries the shopper's requirements as SQL filters.

The Gateway rail runs no structured extractor. The Shopping agent passes the
shopper's budget, stock and exclusion requirements as explicit arguments, and
the plan compiles them into the same predicates an in-process reading produces.
These tests drive ``lambda_handler`` with a Data API stand-in that applies the
predicates it is handed, so a sold-out item, a candle and an item over budget
can only come back if the SQL never asked to exclude them.
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


def _row(product_id: str, name: str, price: str, quantity: int, tags: List[str]) -> Dict[str, Any]:
    return {
        "product_id": product_id,
        "name": name,
        "brand": "Pellier",
        "color": "Sand",
        "description": name,
        "img_url": "https://example.com/p.jpg",
        "category": "Home",
        "price": price,
        "rating": "4.8",
        "reviews": "20",
        "badge": None,
        "tags": json.dumps(tags),
        "materials": json.dumps(["linen"]),
        "quantity": quantity,
        "updated_at": "2026-08-01T00:00:00+00:00",
        "similarity": 0.9,
        "fts_rank_score": 0.5,
    }


CATALOG = [
    _row("P-1", "Linen Table Runner", "48.0", 5, ["home", "gift"]),
    _row("P-2", "Beeswax Pillar Candle", "32.0", 9, ["candle", "gift"]),
    _row("P-3", "Stoneware Serving Bowl", "64.0", 0, ["ceramic", "gift"]),
    _row("P-4", "Cashmere Throw", "240.0", 3, ["home", "gift"]),
]


class _PredicateHonouringDataApi:
    """Applies the price, stock and exclusion predicates the branch SQL declares."""

    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.rows = rows
        self.branches: List[tuple[str, Dict[str, Any]]] = []
        self.audit_calls: List[Dict[str, Any]] = []

    def execute_sql(self, sql: str, parameters: list | None = None) -> List[Dict[str, Any]]:
        bound = {item["name"]: item["value"] for item in parameters or []}
        if "FROM pellier.product_catalog" not in sql:
            return []
        self.branches.append((sql, bound))
        return [dict(row) for row in self.rows if self._passes(sql, bound, row)]

    @staticmethod
    def _passes(sql: str, bound: Dict[str, Any], row: Dict[str, Any]) -> bool:
        for name, value in bound.items():
            if f"price <= :{name}" in sql and float(row["price"]) > float(value["doubleValue"]):
                return False
            if f"tags ?| :{name}" in sql:
                excluded = set(value["arrayValue"]["stringValues"])
                if excluded & set(json.loads(row["tags"])) or excluded & set(json.loads(row["materials"])):
                    return False
        if "quantity > 0" in sql and int(row["quantity"]) <= 0:
            return False
        return True

    def execute_statement(self, **kwargs: Any) -> Dict[str, Any]:
        self.audit_calls.append(kwargs)
        return {"numberOfRecordsUpdated": 1}


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> _PredicateHonouringDataApi:
    fake = _PredicateHonouringDataApi(CATALOG)
    monkeypatch.setattr(dataapi, "execute_sql", fake.execute_sql)
    monkeypatch.setattr(dataapi, "rds_client", fake)
    monkeypatch.setattr(lambda_tools, "query_embedding", lambda _query: [0.1, 0.2])
    monkeypatch.setattr(
        lambda_tools,
        "rerank_documents",
        lambda *, query, documents, top_n: [
            {"index": index, "relevance_score": 1.0 - index / 10}
            for index in range(min(top_n, len(documents)))
        ],
    )
    return fake


def test_stock_exclusion_and_budget_requirements_are_hard_filters(
    transport: _PredicateHonouringDataApi,
) -> None:
    result = lambda_tools.TOOLS["search_products"](
        {
            "query": "a housewarming gift",
            "in_stock_only": True,
            "exclusions": ["candle"],
            "max_price": 100,
            "limit": 5,
        },
        None,
    )

    assert [product["productId"] for product in result["products"]] == ["P-1"]
    plan = result["search_plan"]
    assert plan["hard_constraints"]["in_stock_only"] is True
    assert plan["hard_constraints"]["price_max_usd"] == 100.0
    assert plan["exclusions"] == ["candle"]
    assert plan["extraction_status"] == "parsed"
    assert set(result["hard_constraints_enforced"]) == {"price <= $100", "in stock"}
    assert "constraint_notice" not in result

    assert transport.branches, "no catalogue branch ran"
    for sql, bound in transport.branches:
        assert "quantity > 0" in sql
        assert "price <= :p" in sql
        assert "NOT (tags ?| :p" in sql
        arrays = [v["arrayValue"]["stringValues"] for v in bound.values() if "arrayValue" in v]
        assert arrays and all(values == ["candle"] for values in arrays)


def test_without_the_arguments_the_plan_carries_only_the_price_ceiling(
    transport: _PredicateHonouringDataApi,
) -> None:
    result = lambda_tools.TOOLS["search_products"](
        {"query": "a housewarming gift", "max_price": 100, "limit": 5}, None
    )

    assert {product["productId"] for product in result["products"]} == {"P-1", "P-2", "P-3"}
    plan = result["search_plan"]
    assert plan["hard_constraints"]["in_stock_only"] is False
    assert plan["exclusions"] == []
    assert plan["extraction_status"] == "not_run"
    for sql, _bound in transport.branches:
        assert "quantity > 0" not in sql
        assert "tags ?|" not in sql


def test_the_published_schema_declares_the_two_requirement_arguments() -> None:
    from gateway_tool_schemas import schema_for

    search = next(tool for tool in schema_for("store", workshop=True) if tool["name"] == "search_products")
    properties = search["inputSchema"]["properties"]
    assert properties["in_stock_only"]["type"] == "boolean"
    assert properties["exclusions"] == {
        "type": "array",
        "items": {"type": "string"},
        "description": properties["exclusions"]["description"],
    }
    assert "hard filter" in properties["exclusions"]["description"]


def test_the_managed_shopping_prompt_asks_for_the_requirements_as_arguments() -> None:
    from services.agentcore_gateway import _managed_specialist_prompt

    shopping = _managed_specialist_prompt("shopping")
    for argument in ("max_price", "in_stock_only=true", "exclusions"):
        assert argument in shopping
    assert "in_stock_only" not in _managed_specialist_prompt("support")
