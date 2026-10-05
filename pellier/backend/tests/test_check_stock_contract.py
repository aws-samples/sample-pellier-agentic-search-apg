"""Lab 2's contract: unknown is not zero, and zero is not unknown.

``store_tools.check_stock`` is what the participant's tool body wires in.
These pin the envelopes the Stock agent reports from, so a build that turns a
not-found piece into "0 in stock", or a sold-out piece into "we don't carry
that", fails here before it misleads a shopper.
"""
from __future__ import annotations

from typing import Any

from services import store_tools


class _Run:
    def __init__(self, catalog: list[dict[str, Any]], warehouses: list[dict[str, Any]]) -> None:
        self.catalog, self.warehouses = catalog, warehouses

    def __call__(self, sql: str, params: Any = ()) -> list[dict[str, Any]]:
        if "FROM pellier.product_catalog" in sql:
            return [dict(r) for r in self.catalog]
        if "FROM pellier.warehouse_inventory" in sql:
            return [dict(r) for r in self.warehouses]
        raise AssertionError(f"unexpected query: {sql[:60]}")


VEST = {"productId": "43", "name": "Quilted Silk Vest", "brand": "Pellier", "color": "Ivory", "price": 193.13}
_WAREHOUSES = ("BK-01", "ATX-02", "PDX-01")


def _rows(quantity: int) -> list[dict[str, Any]]:
    return [
        {"warehouse_code": w, "warehouse_name": w, "city": "c", "ship_window_min": 1,
         "ship_window_max": 3, "quantity": quantity}
        for w in _WAREHOUSES
    ]


def test_a_piece_the_catalog_does_not_carry_is_not_found() -> None:
    result = store_tools.check_stock(_Run([], []), product_query="Hadley cashmere scarf")
    assert result["status"] == "not_found"
    assert "total_units" not in result and "warehouses" not in result


def test_a_sold_out_piece_is_a_success_with_zero_units() -> None:
    result = store_tools.check_stock(_Run([VEST], _rows(0)), product_query="Quilted Silk Vest")
    assert result["status"] == "success"
    assert result["total_units"] == 0
    assert [w["warehouse_code"] for w in result["warehouses"]] == list(_WAREHOUSES)
    assert result["product"]["name"] == "Quilted Silk Vest"


def test_several_matches_are_ambiguous_with_candidates_and_no_count() -> None:
    shirt = {"productId": "1", "name": "Hadley Linen Shirt", "brand": "Hadley", "color": "White", "price": 88}
    other = {"productId": "2", "name": "Pellier Linen Shirt", "brand": "Pellier", "color": "Ivory", "price": 78}
    result = store_tools.check_stock(_Run([shirt, other], _rows(4)), product_query="Linen shirt")
    assert result["status"] == "ambiguous"
    assert [c["productId"] for c in result["candidates"]] == ["1", "2"]
    assert "total_units" not in result and "warehouses" not in result


def test_an_empty_query_is_not_found_rather_than_zero() -> None:
    result = store_tools.check_stock(_Run([VEST], []), product_query="   ")
    assert result["status"] == "not_found"


def test_data_api_string_quantities_still_sum_to_integers() -> None:
    rows = [{**row, "quantity": "3", "ship_window_min": "1", "ship_window_max": "2"} for row in _rows(0)]
    result = store_tools.check_stock(_Run([VEST], rows), product_query="Quilted Silk Vest")
    assert result["total_units"] == 9
    assert result["warehouses"][0]["ship_window_max"] == 2
