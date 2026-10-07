"""The Gateway Lambda's catalog tools, run by PostgreSQL under the RDS Data API's rules.

ExecuteStatement refuses an ``arrayValue`` parameter with "Array parameters are not
supported". A stand-in that accepts any field shape never notices: a managed
``search_products`` or ``browse_department`` carrying an exclusion, a category or a
preferred tag failed live while the mocked tests passed. Here the stand-in refuses what
the service refuses and a fresh Pellier database executes the rest, so a list parameter
has to travel the way the Data API accepts it and the SQL has to work on real rows.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

_DEPLOY = Path(__file__).resolve().parents[3] / "scripts" / "deploy"
if str(_DEPLOY) not in sys.path:
    sys.path.insert(0, str(_DEPLOY))

import pellier_store_tools as lambda_tools
from common import dataapi

_NAMED = re.compile(r"(?<!:):(p\d+)\b")
_SCALARS = ("stringValue", "longValue", "doubleValue", "booleanValue")


def _conninfo(cluster: Any) -> dict[str, Any]:
    return {"host": str(cluster.socket), "port": 5432, "user": "postgres", "dbname": "postgres",
            "autocommit": True, "row_factory": dict_row}


def _value(field: dict[str, Any]) -> Any:
    if "arrayValue" in field:
        raise AssertionError(
            "ValidationException: Array parameters are not supported (the RDS Data API "
            "refuses arrayValue in ExecuteStatement parameters)"
        )
    if field.get("isNull"):
        return None
    for kind in _SCALARS:
        if kind in field:
            return field[kind]
    raise AssertionError(f"unhandled Data API parameter {field}")


def _execute_on(cluster: Any):
    def execute_sql(sql: str, parameters: list | None = None) -> list[dict[str, Any]]:
        values = {item["name"]: _value(item["value"]) for item in parameters or []}
        with psycopg.connect(**_conninfo(cluster)) as conn, conn.cursor() as cur:
            cur.execute(_NAMED.sub(r"%(\1)s", sql), values)
            return [dict(row) for row in cur.fetchall()] if cur.description else []
    return execute_sql


@pytest.fixture
def data_api(fresh_db, monkeypatch: pytest.MonkeyPatch):  # noqa: F811
    monkeypatch.setattr(dataapi, "execute_sql", _execute_on(fresh_db))
    monkeypatch.setattr(lambda_tools, "query_embedding",
                        lambda _query: [0.01] * dataapi.EMBED_DIMENSION)
    monkeypatch.setattr(
        lambda_tools,
        "rerank_documents",
        lambda *, query, documents, top_n: [
            {"index": index, "relevance_score": 1.0 - index / 100}
            for index in range(min(top_n, len(documents)))
        ],
    )
    return fresh_db


def _catalog(cluster: Any, product_ids: list[str]) -> list[dict[str, Any]]:
    with psycopg.connect(**_conninfo(cluster)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT product_id, price, quantity, tags, materials FROM pellier.product_catalog "
            "WHERE product_id = ANY(%s)",
            (product_ids,),
        )
        return [dict(row) for row in cur.fetchall()]


def test_a_list_parameter_never_travels_as_array_value() -> None:
    sql, parameters = dataapi._named("SELECT 1 WHERE category = ANY(%s) AND price <= %s",
                                     (["Home", "Kitchen"], 100.0))

    assert sql == "SELECT 1 WHERE category = ANY(CAST(:p0 AS text[])) AND price <= :p1"
    assert parameters[0] == {"name": "p0", "value": {"stringValue": '{"Home","Kitchen"}'}}
    assert all("arrayValue" not in item["value"] for item in parameters)


def test_list_elements_round_trip_through_postgres_unchanged(data_api) -> None:
    awkward = ["a,b", 'say "hi"', "back\\slash", "{brace}", "NULL", " spaced ", ""]

    rows = dataapi.run_store_sql("SELECT unnest(%s) AS item", (awkward,))

    assert [row["item"] for row in rows] == awkward
    assert dataapi.run_store_sql("SELECT cardinality(%s) AS n", ([],)) == [{"n": 0}]


def test_managed_search_keeps_annas_limits_on_real_rows(data_api) -> None:
    result = lambda_tools.TOOLS["search_products"](
        {
            "query": "A housewarming gift for a friend who loves slow mornings",
            "in_stock_only": True,
            "exclusions": ["candle"],
            "max_price": 100,
            "limit": 5,
        },
        None,
    )

    products = result["products"]
    assert products, result
    for row in _catalog(data_api, [product["productId"] for product in products]):
        assert float(row["price"]) <= 100
        assert row["quantity"] > 0
        assert "candle" not in row["tags"] and "candle" not in row["materials"]


def test_managed_department_browse_returns_real_rows(data_api) -> None:
    with psycopg.connect(**_conninfo(data_api)) as conn, conn.cursor() as cur:
        cur.execute("SELECT category FROM pellier.product_catalog GROUP BY category "
                    "ORDER BY count(*) DESC, category LIMIT 1")
        department = cur.fetchone()["category"]

    result = lambda_tools.TOOLS["browse_department"](
        {"department": department, "exclusions": ["candle"], "limit": 5}, None
    )

    assert result["products"], result
