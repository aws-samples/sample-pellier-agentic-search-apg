"""Lab 2b's contract: unknown is not zero, and zero is not unknown.

``BusinessLogic.check_inventory`` is what the participant's tool body wires in.
These pin the two envelopes the Inventory Agent reports from, so a build that
turns a not-found piece into "0 in stock", or a sold-out piece into "we don't
carry that", fails here before it misleads a shopper.
"""
from __future__ import annotations

from typing import Any

import pytest

from services.business_logic import BusinessLogic


class _Db:
    def __init__(self, catalog: list[dict[str, Any]], warehouses: list[dict[str, Any]]) -> None:
        self.catalog, self.warehouses = catalog, warehouses

    async def fetch_all(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        if "FROM pellier.product_catalog" in sql:
            return [dict(r) for r in self.catalog]
        if "FROM pellier.warehouse_inventory" in sql:
            return [dict(r) for r in self.warehouses]
        raise AssertionError(f"unexpected query: {sql[:60]}")


VEST = {"productId": "43", "name": "Quilted Silk Vest", "brand": "Pellier Atelier", "color": "Ivory", "price": 193.13}
_WAREHOUSES = ("BK-01", "ATX-02", "PDX-01")


@pytest.mark.asyncio
async def test_a_piece_the_catalog_does_not_carry_is_not_found() -> None:
    result = await BusinessLogic(_Db([], [])).check_inventory("Hadley cashmere scarf")
    assert result["status"] == "not_found"
    assert "total_units" not in result and "warehouses" not in result


@pytest.mark.asyncio
async def test_a_sold_out_piece_is_a_success_with_zero_units() -> None:
    warehouses = [
        {"warehouse_id": w, "warehouse_name": w, "city": "c", "ship_window_min": 1,
         "ship_window_max": 3, "quantity": 0}
        for w in _WAREHOUSES
    ]
    result = await BusinessLogic(_Db([VEST], warehouses)).check_inventory("Quilted Silk Vest")
    assert result["status"] == "success"
    assert result["total_units"] == 0
    assert [w["warehouse_id"] for w in result["warehouses"]] == list(_WAREHOUSES)
    assert result["product"]["name"] == "Quilted Silk Vest"


@pytest.mark.asyncio
async def test_an_empty_query_is_not_found_rather_than_zero() -> None:
    result = await BusinessLogic(_Db([VEST], [])).check_inventory("   ")
    assert result["status"] == "not_found"
