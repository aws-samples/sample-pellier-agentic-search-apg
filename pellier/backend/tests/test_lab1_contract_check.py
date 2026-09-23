"""Lab 1's contract check grades the participant's test inputs, then the tool."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "lab1_contract_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("lab1_contract_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


VEST = {"product_id": "43", "name": "Quilted Silk Vest"}
SHIRTS = [{"product_id": "2", "name": "Hadley Linen Shirt"},
          {"product_id": "7", "name": "Italian Linen Camp Shirt"}]
ZERO_STOCK = [{"warehouse_id": "BK-01", "quantity": 0}, {"warehouse_id": "ATX-02", "quantity": 0}]

CATALOG = {
    "unknown": {"matches": [], "stock": []},
    "ambiguous": {"matches": SHIRTS, "stock": []},
    "sold_out": {"matches": [VEST], "stock": ZERO_STOCK},
}
ENVELOPES = {
    "unknown": {"status": "not_found", "query": "Hadley cashmere scarf"},
    "ambiguous": {"status": "ambiguous",
                  "candidates": [{"productId": "2"}, {"productId": "7"}]},
    "sold_out": {"status": "success", "product": {"productId": "43"}, "total_units": 0,
                 "warehouses": [{"quantity": 0}, {"quantity": 0}]},
}


def _verdicts(check, catalog=None, envelopes=None):
    catalog = {**CATALOG, **(catalog or {})}
    envelopes = {**ENVELOPES, **(envelopes or {})}
    return [check.judge_case(case, f"query for {case}", "participant",
                             catalog[case], envelopes[case]) for case in check.CASES]


def test_the_contract_passes_when_all_three_answers_stay_distinct() -> None:
    check = _load()
    report = check.judge(_verdicts(check))
    assert report["passed"] is True
    assert [c["catalogClass"] for c in report["cases"]] == ["unknown", "ambiguous", "sold_out"]
    assert "ask which one" in report["cases"][1]["conclusion"]


@pytest.mark.parametrize("case, catalog", [
    # The participant offered a carried piece as "unknown".
    ("unknown", {"matches": [VEST], "stock": ZERO_STOCK}),
    # One match is not ambiguity.
    ("ambiguous", {"matches": [VEST], "stock": ZERO_STOCK}),
    # A piece with stock is not a sold-out test.
    ("sold_out", {"matches": [VEST], "stock": [{"warehouse_id": "BK-01", "quantity": 3}]}),
])
def test_a_test_input_that_is_not_what_it_claims_fails(case, catalog) -> None:
    check = _load()
    report = check.judge(_verdicts(check, catalog={case: catalog}))
    failed = next(c for c in report["cases"] if c["case"] == case)
    assert report["passed"] is False
    assert failed["inputPassed"] is False
    assert "cannot test" in failed["conclusion"]


def test_a_catalog_read_failure_is_unchecked_never_not_found() -> None:
    check = _load()
    verdicts = _verdicts(check, catalog={"unknown": {"error": "OperationalError: timeout"}})
    report = check.judge(verdicts)
    assert report["passed"] is False
    assert report["cases"][0]["catalogClass"] == "UNCHECKED"
    assert report["cases"][0]["passed"] is False


@pytest.mark.parametrize("case, envelope", [
    ("unknown", {"status": "success", "total_units": 0, "warehouses": []}),
    ("ambiguous", {"status": "success", "product": {"productId": "2"}, "total_units": 8,
                   "warehouses": [{"quantity": 8}]}),
    ("ambiguous", {"status": "ambiguous", "candidates": [{"productId": "99"},
                                                         {"productId": "2"}]}),
    ("sold_out", {"status": "not_found"}),
    ("sold_out", {"status": "success", "product": {"productId": "2"}, "total_units": 0,
                  "warehouses": [{"quantity": 0}]}),
])
def test_a_tool_that_changes_the_business_answer_fails(case, envelope) -> None:
    check = _load()
    report = check.judge(_verdicts(check, envelopes={case: envelope}))
    failed = next(c for c in report["cases"] if c["case"] == case)
    assert report["passed"] is False
    assert failed["inputPassed"] is True and failed["toolPassed"] is False


@pytest.mark.parametrize("warehouses", [
    [], [{}], [{"quantity": 1}], [{"quantity": False}], [{"quantity": None}], [None],
])
def test_zero_total_does_not_pass_without_zero_stock_at_each_warehouse(warehouses) -> None:
    check = _load()
    envelope = {"status": "success", "product": {"productId": "43"}, "total_units": 0,
                "warehouses": warehouses}
    report = check.judge(_verdicts(check, envelopes={"sold_out": envelope}))
    assert report["passed"] is False


def test_omitted_inputs_use_recorded_recovery_defaults() -> None:
    check = _load()
    inputs = check._inputs(argparse.Namespace(unknown="Velvet opera cape", ambiguous=None,
                                              sold_out="  "))
    assert inputs["unknown"] == ("Velvet opera cape", "participant")
    assert inputs["ambiguous"] == (check.DEFAULT_INPUTS["ambiguous"], "recovery-default")
    assert inputs["sold_out"] == (check.DEFAULT_INPUTS["sold_out"], "recovery-default")


def test_the_check_runs_the_participants_tool_body_not_the_logic_directly() -> None:
    source = SCRIPT.read_text()
    assert "agent_tools.check_inventory" in source
    assert "BusinessLogic" not in source
