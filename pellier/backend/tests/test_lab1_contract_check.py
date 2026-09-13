"""The supplied Lab 1 two-case check grades envelopes, not prose."""
from __future__ import annotations

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


def test_the_contract_passes_when_unknown_and_zero_are_kept_apart() -> None:
    check = _load()
    report = check.judge({
        "unknown": {"status": "not_found", "query": "Hadley cashmere scarf"},
        "sold_out": {"status": "success", "total_units": 0, "warehouses": [{"quantity": 0}]},
    })
    assert report["passed"] is True
    assert [c["passed"] for c in report["cases"]] == [True, True]
    assert "does not carry" in report["cases"][0]["conclusion"]
    assert "sold out" in report["cases"][1]["conclusion"]


def test_a_count_for_an_unknown_piece_fails() -> None:
    check = _load()
    report = check.judge({
        "unknown": {"status": "success", "total_units": 0, "warehouses": []},
        "sold_out": {"status": "success", "total_units": 0, "warehouses": []},
    })
    assert report["passed"] is False
    assert report["cases"][0]["passed"] is False


def test_not_found_for_a_sold_out_piece_fails() -> None:
    check = _load()
    report = check.judge({
        "unknown": {"status": "not_found"},
        "sold_out": {"status": "not_found"},
    })
    assert report["passed"] is False
    assert report["cases"][1]["passed"] is False


@pytest.mark.parametrize("warehouses", [
    [], [{}], [{"quantity": 1}], [{"quantity": False}], [{"quantity": None}], [None],
])
def test_zero_total_does_not_pass_without_zero_stock_at_each_warehouse(warehouses) -> None:
    report = _load().judge({
        "unknown": {"status": "not_found"},
        "sold_out": {"status": "success", "total_units": 0, "warehouses": warehouses},
    })
    assert report["passed"] is False
    assert report["cases"][1]["passed"] is False


def test_the_check_runs_the_participants_tool_body_not_the_logic_directly() -> None:
    source = SCRIPT.read_text()
    assert "agent_tools.check_inventory" in source
    assert "BusinessLogic" not in source
