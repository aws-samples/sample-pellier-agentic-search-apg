"""Lab 2's contract: unknown is not zero, and zero is not unknown.

``pellier.check_stock`` decides (Task 2B's worksheet, real-PostgreSQL proof in
``tests/test_lab2_check_stock_postgres.py``); ``store_tools.check_stock`` shapes its
rows into the envelopes the Stock agent reports from. These pin that shaping: no row
is not_found, several rows are the candidates, one row is passed on as the function
returned it, and a Data API row (strings, JSON as text) reads the same as a psycopg
one.
"""
from __future__ import annotations

import json
from typing import Any, List

from services import store_tools


class _Run:
    """Answers the one statement check_stock runs with the function's rows."""

    def __init__(self, rows: List[dict[str, Any]]) -> None:
        self.rows, self.calls = rows, []

    def __call__(self, sql: str, params: Any = ()) -> list[dict[str, Any]]:
        if "pellier.check_stock(%s)" not in sql:
            raise AssertionError(f"unexpected query: {sql[:60]}")
        self.calls.append(tuple(params))
        return [dict(r) for r in self.rows]


_WAREHOUSES = ("BK-01", "ATX-02", "PDX-01")


def _warehouses(quantity: Any) -> list[dict[str, Any]]:
    return [
        {"warehouse_code": w, "warehouse_name": w, "city": "c", "ship_window_min": 1,
         "ship_window_max": 3, "quantity": quantity}
        for w in _WAREHOUSES
    ]


def _row(product_id: Any, name: Any, total: Any, warehouses: Any) -> dict[str, Any]:
    return {"product_id": product_id, "name": name, "brand": "Pellier", "color": "Ivory",
            "price": 193.13, "total_units": total, "warehouses": warehouses}


def test_no_row_is_not_found_with_no_count() -> None:
    result = store_tools.check_stock(_Run([]), product_query="Hadley cashmere scarf")
    assert result["status"] == "not_found"
    assert "total_units" not in result and "warehouses" not in result


def test_the_query_is_bound_as_written_for_the_function_to_match() -> None:
    run = _Run([])
    store_tools.check_stock(run, product_query="100% wool_scarf")
    assert run.calls == [("100% wool_scarf",)]


def test_a_sold_out_piece_is_a_success_with_zero_units() -> None:
    run = _Run([_row("43", "Quilted Silk Vest", 0, _warehouses(0))])
    result = store_tools.check_stock(run, product_query="Quilted Silk Vest")
    assert result["status"] == "success"
    assert result["total_units"] == 0
    assert [w["warehouse_code"] for w in result["warehouses"]] == list(_WAREHOUSES)
    assert result["product"] == {"productId": "43", "name": "Quilted Silk Vest",
                                 "brand": "Pellier", "color": "Ivory", "price": 193.13}


def test_several_rows_are_ambiguous_with_candidates_and_no_count() -> None:
    rows = [_row("1", "Hadley Linen Shirt", None, None),
            _row("2", "Pellier Linen Shirt", None, None)]
    result = store_tools.check_stock(_Run(rows), product_query="Linen shirt")
    assert result["status"] == "ambiguous"
    assert [c["productId"] for c in result["candidates"]] == ["1", "2"]
    assert "total_units" not in result and "warehouses" not in result


def test_one_row_is_passed_on_as_the_function_returned_it() -> None:
    """The as-shipped function's row for a piece nobody carries reads as 0 in stock.

    Python does not repair it: the function is where Task 2B fixes it.
    """
    result = store_tools.check_stock(_Run([_row(None, None, 0, [])]),
                                     product_query="Velvet Opera Cape")
    assert result["status"] == "success"
    assert result["product"]["productId"] is None
    assert result["total_units"] == 0 and result["warehouses"] == []


def test_an_empty_query_is_not_found_without_a_database_call() -> None:
    run = _Run([_row("43", "Quilted Silk Vest", 0, [])])
    result = store_tools.check_stock(run, product_query="   ")
    assert result["status"] == "not_found"
    assert run.calls == []


def test_a_data_api_row_with_strings_and_json_text_reads_the_same() -> None:
    row = _row("43", "Quilted Silk Vest", "9",
               json.dumps([{**w, "quantity": "3", "ship_window_max": "2"} for w in _warehouses(0)]))
    row["price"] = "193.13"
    result = store_tools.check_stock(_Run([row]), product_query="Quilted Silk Vest")
    assert result["total_units"] == 9
    assert [w["quantity"] for w in result["warehouses"]] == [3, 3, 3]
    assert result["warehouses"][0]["ship_window_max"] == 2
    assert result["product"]["price"] == 193.13
