"""Lab 2's contract: the starters fail the way the guide's Spot step shows, the solutions do not.

Task 2A. The starter ``check_stock`` folds not_found into zero: Marco asks about
the Velvet Opera Cape, which Pellier does not carry, and the Builder view says
"Sold out in all three warehouses". The solution keeps it not_found.

Task 2B. The starter Stock agent is granted the shopping tools beside
``check_stock``, so it can answer a stock question from a product listing
instead of the warehouse rows. The solution grants ``check_stock`` alone.
``scripts/lab2_contract_check.py --task 2B`` judges a turn by both.

The tool bodies run on the real schema and seed; the Stock agent is built by
its real factory.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict

import psycopg
import pytest
from psycopg.rows import dict_row

from services import agent_tools
from services.turn_steps import finding_for, parse_result
from tests import lab_variants
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
lab2 = importlib.import_module("lab2_contract_check")

NOT_CARRIED = "Velvet Opera Cape"
CATALOG_TOOLS = {"search_products", "browse_department", "compare_products"}


@pytest.fixture(scope="module")
def conn(fresh_db: Any) -> Any:  # noqa: F811 - the imported fixture
    connection = psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                                 dbname="postgres", autocommit=True, row_factory=dict_row)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture()
def tool_db(conn: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """``agent_tools`` reading the real schema on this connection."""
    monkeypatch.setattr(agent_tools, "_db_service", lab2._RowsOn(conn))
    monkeypatch.setattr(agent_tools, "_main_loop", None)
    return conn


def _ask(variant: str, query: str) -> Dict[str, Any]:
    return json.loads(lab_variants.check_stock_body(variant)(product_query=query))


# ---------------------------------------------------------------------------
# Task 2A: check_stock
# ---------------------------------------------------------------------------


def test_the_starter_calls_a_piece_pellier_does_not_carry_sold_out(tool_db) -> None:
    envelope = _ask(lab_variants.STARTER, NOT_CARRIED)
    assert envelope["status"] == "success"
    assert envelope["total_units"] == 0
    assert finding_for("check_stock", parse_result(json.dumps(envelope))) == (
        "Sold out in all three warehouses")


def test_the_solution_says_pellier_does_not_carry_it(tool_db) -> None:
    envelope = _ask(lab_variants.SOLUTION, NOT_CARRIED)
    assert envelope["status"] == "not_found"
    assert "total_units" not in envelope
    assert finding_for("check_stock", parse_result(json.dumps(envelope))) == (
        "Not a piece Pellier carries")


@pytest.mark.parametrize("variant", [lab_variants.STARTER, lab_variants.SOLUTION])
def test_both_report_a_carried_piece_from_the_warehouse_rows(tool_db, variant) -> None:
    envelope = _ask(variant, "Hadley Linen Shirt")
    counts = {row["warehouse_code"]: row["quantity"] for row in envelope["warehouses"]}
    assert counts == {"BK-01": 0, "ATX-02": 6, "PDX-01": 14}
    assert envelope["total_units"] == 20


def test_the_2a_check_fails_the_starter_and_passes_the_solution(tool_db) -> None:
    inputs = {case: (lab2.DEFAULT_INPUTS[case], "default") for case in lab2.CASES}
    starter, rows = lab2.judge_2a(tool_db, lab_variants.check_stock_body(lab_variants.STARTER),
                                  inputs)
    assert starter.state == "CONTRADICTED"
    assert f'not carried: "{NOT_CARRIED}" came back success, 0 units' in starter.observed
    assert [row[-1] for row in rows] == ["differs", "matches", "matches", "matches"]
    assert any("warehouse_inventory for 2 Hadley Linen Shirt" in line for line in starter.evidence)

    solution, rows = lab2.judge_2a(tool_db, lab_variants.check_stock_body(lab_variants.SOLUTION),
                                   inputs)
    assert solution.state == "PROVED", solution
    assert [row[-1] for row in rows] == ["matches"] * 4


def test_a_test_input_that_is_not_its_case_cannot_pass(tool_db) -> None:
    inputs = {case: (lab2.DEFAULT_INPUTS[case], "default") for case in lab2.CASES}
    inputs["unknown"] = ("Hadley Linen Shirt", "you")
    finding, _rows = lab2.judge_2a(
        tool_db, lab_variants.check_stock_body(lab_variants.SOLUTION), inputs)
    assert finding.state == "NOT YET"
    assert "is in stock" in finding.observed


# ---------------------------------------------------------------------------
# Task 2B: the Stock agent's grant
# ---------------------------------------------------------------------------


def _names(tools: Any) -> list:
    return [tool.tool_name for tool in tools]


def test_the_starter_grants_catalog_tools_and_the_solution_only_check_stock() -> None:
    starter = _names(lab_variants.stock_grant(lab_variants.STARTER))
    solution = _names(lab_variants.stock_grant(lab_variants.SOLUTION))
    assert set(starter) == CATALOG_TOOLS | {"check_stock"}
    assert solution == ["check_stock"]


@pytest.mark.parametrize("variant", [lab_variants.STARTER, lab_variants.SOLUTION])
def test_the_factory_builds_the_agent_with_exactly_that_grant(monkeypatch, variant) -> None:
    from agents import stock_agent

    grant = lab_variants.stock_grant(variant)
    monkeypatch.setattr(stock_agent, "_STOCK_TOOLS", grant)
    agent = stock_agent.build_stock_agent()
    assert set(agent.tool_names) == set(_names(grant))


def _audit(conn: Any, turn: str, tool: str, args: Dict[str, Any], result: Dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms) "
            "VALUES (%s, %s, 'agent', %s::jsonb, %s::jsonb, 10)",
            (f"persona-marco-{turn}", tool, json.dumps({**args, "turn_id": turn}),
             json.dumps(result)))


def test_the_2b_check_fails_a_turn_that_read_the_catalog(conn) -> None:
    _audit(conn, "turn-guess", "search_products", {"query": "Hadley Linen Shirt Brooklyn"},
           {"status": "success", "count": 1, "products": [{"productId": "2"}]})
    starter_grant = _names(lab_variants.stock_grant(lab_variants.STARTER))
    finding = lab2.judge_2b(conn, starter_grant)
    assert finding.state == "CONTRADICTED"
    assert "the turn called search_products" in finding.observed
    assert "the turn never called check_stock" in finding.observed
    assert "granted search_products" in finding.observed


def test_the_2b_check_passes_one_grounded_turn(conn, tool_db) -> None:
    envelope = _ask(lab_variants.SOLUTION, "Hadley Linen Shirt")
    _audit(conn, "turn-grounded", "check_stock", {"product_query": "Hadley Linen Shirt"}, envelope)
    finding = lab2.judge_2b(conn, ["check_stock"])
    assert finding.state == "PROVED", finding
    assert any("warehouse_inventory for 2: ATX-02 6, BK-01 0, PDX-01 14" in line
               for line in finding.evidence)


def test_the_2b_check_fails_a_count_the_warehouse_rows_do_not_hold(conn) -> None:
    guessed = {"status": "success", "product": {"productId": "2", "name": "Hadley Linen Shirt"},
               "total_units": 21, "warehouses": [{"warehouse_code": "BK-01", "quantity": 8},
                                                 {"warehouse_code": "ATX-02", "quantity": 6},
                                                 {"warehouse_code": "PDX-01", "quantity": 7}]}
    _audit(conn, "turn-wrong", "check_stock", {"product_query": "Hadley Linen Shirt"}, guessed)
    finding = lab2.judge_2b(conn, ["check_stock"])
    assert finding.state == "CONTRADICTED"
    assert "does not match the catalog" in finding.observed


def test_the_2b_check_fails_the_starters_folded_answer(conn, tool_db) -> None:
    envelope = _ask(lab_variants.STARTER, NOT_CARRIED)
    _audit(conn, "turn-folded", "check_stock", {"product_query": NOT_CARRIED}, envelope)
    finding = lab2.judge_2b(conn, ["check_stock"])
    assert finding.state == "CONTRADICTED"
    assert any("no catalog product carries that name" in line for line in finding.evidence)
