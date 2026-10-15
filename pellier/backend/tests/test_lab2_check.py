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
check = importlib.import_module("lab2_check")

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


@pytest.mark.parametrize("grant, state", [
    (["check_stock"], None),
    (["search_products", "browse_department", "compare_products"], "NOT YET"),
    (["compare_products", "browse_department", "search_products"], "NOT YET"),
    (None, "NOT YET"),
    # check_stock connected but the catalog tools left in: a wrong grant, not an unfinished one.
    (["search_products", "browse_department", "compare_products", "check_stock"], "CONTRADICTED"),
    (["search_products", "check_stock"], "CONTRADICTED"),
    ([], "CONTRADICTED"),
])
def test_the_recorded_grant_decides_before_the_calls(grant, state) -> None:
    """The starter's grant is a lab not done yet (or not reloaded); any other is wrong."""
    verdict, observed = check._grant_verdict(grant)
    assert verdict == state
    assert bool(observed) is (state is not None)


def test_the_recorded_grant_is_read_from_the_turns_first_row() -> None:
    rows = [{"args": {"grant": ["check_stock"], "turn_id": "t"}}, {"args": {"grant": ["x"]}}]
    assert check.recorded_grant(rows) == ["check_stock"]
    assert check.recorded_grant([{"args": '{"turn_id": "t"}'}]) is None
    assert check.recorded_grant([]) is None


def test_the_check_reads_no_source() -> None:
    """2B is judged from the turn record, so an edit without a restart cannot pass."""
    source = (SCRIPTS / "lab2_check.py").read_text()
    assert "import ast" not in source and "stock_agent.py\")" not in source
    assert "args->>'agent' = %s" in source


def test_the_check_runs_the_participants_tool_body_not_the_logic_directly() -> None:
    source = (SCRIPTS / "lab2_check.py").read_text()
    assert "return agent_tools.check_stock" in source
    assert "store_tools" not in source


def _finding(state: str) -> object:
    return check.check.Finding("2A", "title", state, "expected", "observed", ["row"])


@pytest.mark.parametrize("recorded", ["NOT YET", "CONTRADICTED"])
def test_a_pass_the_recorded_turns_do_not_show_asks_for_marcos_requests_again(recorded) -> None:
    """The guide's check runs the checkout; the storefront and the export read Marco's turns.

    The backend reloads when the file is saved, so the hint asks for his requests again and
    never for a restart.
    """
    finding = check.with_restart_hint(_finding("PROVED"), _finding(recorded))
    assert finding.state == "PROVED"
    assert finding.evidence[0] == "row"
    assert "python3 scripts/lab_run.py send --lab 2" in finding.evidence[-1]
    assert "restart" not in finding.evidence[-1].lower()


def test_the_2a_table_fits_a_laptop_terminal_and_keeps_its_columns() -> None:
    """The event's rows ran to about 150 columns and wrapped at 133; each now fits in 100."""
    rows = [
        ("not carried", "Velvet Opera Cape", "default", "not_found: no product matches",
         "success, 0 units (no rows)", "differs"),
        ("sold out", "Quilted Silk Vest", "default", "success, 0 units (ATX-02 0, BK-01 0, PDX-01 0)",
         "success, 0 units (ATX-02 0, BK-01 0, PDX-01 0)", "matches"),
        ("in stock", "Hadley Linen Shirt", "fixed", "success, 20 units (ATX-02 6, BK-01 0, PDX-01 14)",
         "success, 20 units (ATX-02 6, BK-01 0, PDX-01 14)", "matches"),
    ]
    lines = check.cases_table(rows).splitlines()
    assert max(len(line) for line in lines) <= 100
    assert lines[0].split() == ["case", "query", "chosen", "by", "verdict"]
    assert lines[1].split()[:2] == ["not", "carried"] and lines[1].rstrip().endswith("differs")
    assert lines[2].split()[:1] == ["expected"] and lines[3].split()[:1] == ["observed"]


@pytest.mark.parametrize("guide, recorded", [("PROVED", "PROVED"), ("CONTRADICTED", "NOT YET")])
def test_no_restart_line_when_the_turns_agree_or_the_check_fails(guide, recorded) -> None:
    finding = check.with_restart_hint(_finding(guide), _finding(recorded))
    assert finding.evidence == ["row"]
