"""Lab 2's check grades the participant's test inputs, then the tool, against the catalog.

The judging is pure over a catalog answer and a tool envelope, so the edge cases
run offline here. ``tests/test_lab2_starter_failure.py`` runs the whole check on
the real schema against the starter and the solution.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
check = importlib.import_module("lab2_contract_check")

VEST = {"product_id": "43", "name": "Quilted Silk Vest"}
SHIRTS = [{"product_id": "2", "name": "Hadley Linen Shirt"},
          {"product_id": "11", "name": "Italian Linen Camp Shirt"}]
ZERO_STOCK = [{"warehouse_code": "BK-01", "quantity": 0},
              {"warehouse_code": "ATX-02", "quantity": 0}]
SHIRT = {"product_id": "2", "name": "Hadley Linen Shirt"}
SHIRT_STOCK = [{"warehouse_code": "BK-01", "quantity": 0},
               {"warehouse_code": "ATX-02", "quantity": 6},
               {"warehouse_code": "PDX-01", "quantity": 14}]

CATALOG = {
    "unknown": {"matches": [], "stock": []},
    "several": {"matches": SHIRTS, "stock": []},
    "sold_out": {"matches": [VEST], "stock": ZERO_STOCK},
    "in_stock": {"matches": [SHIRT], "stock": SHIRT_STOCK},
}
ENVELOPES = {
    "unknown": {"status": "not_found", "query": "Velvet Opera Cape"},
    "several": {"status": "ambiguous", "candidates": [{"productId": "2"}, {"productId": "11"}]},
    "sold_out": {"status": "success", "product": {"productId": "43"}, "total_units": 0,
                 "warehouses": ZERO_STOCK},
    "in_stock": {"status": "success", "product": {"productId": "2"}, "total_units": 20,
                 "warehouses": SHIRT_STOCK},
}


@pytest.mark.parametrize("case", check.CASES)
def test_the_catalogs_own_answer_keeps_the_contract(case) -> None:
    assert check.classify(CATALOG[case]) == case
    assert check.keeps_contract(case, ENVELOPES[case], CATALOG[case]) is True


@pytest.mark.parametrize("case, envelope", [
    # The starter's fold: a piece Pellier does not carry reported as sold out.
    ("unknown", {"status": "success", "total_units": 0, "warehouses": []}),
    ("unknown", {"status": "not_found", "total_units": 0}),
    ("several", {"status": "success", "product": {"productId": "2"}, "total_units": 8,
                 "warehouses": [{"warehouse_code": "BK-01", "quantity": 8}]}),
    ("several", {"status": "ambiguous", "candidates": [{"productId": "99"}, {"productId": "2"}]}),
    ("sold_out", {"status": "not_found"}),
    ("sold_out", {"status": "success", "product": {"productId": "2"}, "total_units": 0,
                  "warehouses": ZERO_STOCK}),
    ("in_stock", {"status": "success", "product": {"productId": "2"}, "total_units": 21,
                  "warehouses": [{"warehouse_code": "BK-01", "quantity": 8}]}),
])
def test_a_tool_that_changes_the_business_answer_fails(case, envelope) -> None:
    assert check.keeps_contract(case, envelope, CATALOG[case]) is False


@pytest.mark.parametrize("warehouses", [
    [], [{}], [{"warehouse_code": "BK-01", "quantity": 1}], [{"quantity": None}],
])
def test_zero_total_does_not_pass_without_the_warehouse_rows(warehouses) -> None:
    envelope = {"status": "success", "product": {"productId": "43"}, "total_units": 0,
                "warehouses": warehouses}
    assert check.keeps_contract("sold_out", envelope, CATALOG["sold_out"]) is False


@pytest.mark.parametrize("catalog, expected", [
    ({"matches": [VEST], "stock": [{"warehouse_code": "BK-01", "quantity": 3}]}, "in_stock"),
    ({"matches": [VEST], "stock": []}, "no_warehouse_rows"),
])
def test_a_query_is_classified_from_the_catalog_alone(catalog, expected) -> None:
    assert check.classify(catalog) == expected


def test_blank_choices_use_the_defaults_and_say_so() -> None:
    inputs = check._inputs(argparse.Namespace(unknown="Opera cloak", ambiguous=None, sold_out="  "))
    assert inputs["unknown"] == ("Opera cloak", "you")
    assert inputs["several"] == (check.DEFAULT_INPUTS["several"], "default")
    assert inputs["sold_out"] == (check.DEFAULT_INPUTS["sold_out"], "default")
    assert inputs["in_stock"] == ("Hadley Linen Shirt", "fixed")


def test_the_grant_is_read_from_the_definition(tmp_path: Path) -> None:
    source = tmp_path / "stock_agent.py"
    source.write_text("_STOCK_TOOLS = [agent_tools.search_products, agent_tools.check_stock]\n")
    assert check.granted_tools(source) == ["search_products", "check_stock"]
    source.write_text("_STOCK_TOOLS = [check_stock]\n")
    assert check.granted_tools(source) == ["check_stock"]
    source.write_text("nothing here\n")
    assert check.granted_tools(source) is None


def test_the_check_runs_the_participants_tool_body_not_the_logic_directly() -> None:
    source = (SCRIPTS / "lab2_contract_check.py").read_text()
    assert "return agent_tools.check_stock" in source
    assert "store_tools" not in source
