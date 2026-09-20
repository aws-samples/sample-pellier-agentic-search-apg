"""Exercise the legacy reference directly without replacing participant modules."""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(scope="module")
def business_logic_class():
    source = (
        Path(__file__).resolve().parents[3]
        / "solutions/the-quiet-search/services/business_logic.py"
    )
    spec = importlib.util.spec_from_file_location("_quiet_search_reference", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BusinessLogic


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("category", "limit", "expected_params"),
    [
        (None, 7, (7,)),
        ("", 2, (2,)),
        ("Home Decor", 3, ("%Home Decor%", 3)),
        ("Home' OR TRUE; --", 4, ("%Home' OR TRUE; --%", 4)),
    ],
    ids=["no-category", "empty-category", "category", "quoted-category"],
)
async def test_trending_binds_category_before_limit(
    business_logic_class, category, limit, expected_params
):
    db = SimpleNamespace(
        fetch_all=AsyncMock(
            return_value=[
                {
                    "productId": "test-product",
                    "price": Decimal("19.25"),
                    "trending_score": Decimal("480.0"),
                }
            ]
        )
    )

    result = await business_logic_class(db).get_trending_products(
        limit=limit, category=category
    )

    db.fetch_all.assert_awaited_once()
    query, *params = db.fetch_all.call_args.args
    assert db.fetch_all.call_args.kwargs == {}
    assert tuple(params) == expected_params
    assert query.count("%s") == len(expected_params)
    assert "LIMIT %s" in query
    if category:
        assert query.index("category_name ILIKE %s") < query.index("LIMIT %s")
        assert category not in query
    else:
        assert "category_name ILIKE" not in query
    assert result["status"] == "success"
    assert result["count"] == 1
    assert result["products"] == [
        {"productId": "test-product", "price": 19.25, "trending_score": 480.0}
    ]
    assert result["metadata"]["limit"] == limit


@pytest.mark.asyncio
async def test_trending_defaults_allow_an_empty_result(business_logic_class):
    db = SimpleNamespace(fetch_all=AsyncMock(return_value=[]))

    result = await business_logic_class(db).get_trending_products()

    db.fetch_all.assert_awaited_once()
    query, *params = db.fetch_all.call_args.args
    assert params == [5]
    assert query.count("%s") == 1
    assert "category_name ILIKE" not in query
    assert result["status"] == "success"
    assert result["count"] == 0
    assert result["products"] == []
    assert result["metadata"]["limit"] == 5
