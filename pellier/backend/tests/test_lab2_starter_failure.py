"""Lab 2's contract: the starters fail the way the guide's Spot step shows, the solutions do not.

Task 2A. The starter ``check_stock`` folds not_found into zero: Marco asks about
the Velvet Opera Cape, which Pellier does not carry, and the Builder view says
"Sold out in all three warehouses". The solution keeps it not_found.

Task 2B. The starter Stock agent is connected to the catalog tools only, so
it holds no tool that reads ``warehouse_inventory``: it can answer a stock
question from a product listing, or not at all, even though its prompt names
``check_stock``. The solution connects ``check_stock`` alone. The built
agent's own registry is what the audit row records and the Builder view shows;
``scripts/lab2_contract_check.py --task 2B`` judges Marco's latest Stock-agent
turn by that recorded grant, its calls and its counts.

The tool bodies run on the real schema and seed; the Stock agent is built by
its real factory.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Sequence

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


def test_the_starter_connects_only_catalog_tools_and_the_solution_only_check_stock() -> None:
    starter = _names(lab_variants.stock_grant(lab_variants.STARTER))
    solution = _names(lab_variants.stock_grant(lab_variants.SOLUTION))
    assert set(starter) == CATALOG_TOOLS
    assert "check_stock" not in starter
    assert solution == ["check_stock"]


def test_the_starter_prompt_names_a_tool_its_grant_does_not_hold() -> None:
    """The Spot step's evidence line: the prompt asks for check_stock; only the grant decides."""
    from agents import stock_agent
    from services.turn_steps import grant_receipt

    starter = _names(lab_variants.stock_grant(lab_variants.STARTER))
    receipt = grant_receipt(starter, stock_agent.STOCK_PROMPT_RULE)
    assert "check_stock" in receipt["rule"]
    assert "check_stock" not in receipt["tools"]


@pytest.mark.parametrize("variant", [lab_variants.STARTER, lab_variants.SOLUTION])
def test_the_factory_builds_the_agent_with_exactly_that_grant(monkeypatch, variant) -> None:
    from agents import stock_agent

    grant = lab_variants.stock_grant(variant)
    monkeypatch.setattr(stock_agent, "_STOCK_TOOLS", grant)
    agent = stock_agent.build_stock_agent()
    assert set(agent.tool_names) == set(_names(grant))
    # The rule the Builder view prints beside the grant is the prompt's own words.
    assert stock_agent.STOCK_PROMPT_RULE in agent.system_prompt


@pytest.mark.parametrize("variant", [lab_variants.STARTER, lab_variants.SOLUTION])
def test_the_audit_row_records_the_agent_and_the_grant_it_was_built_with(
    monkeypatch, variant,
) -> None:
    """The hook reads the running agent's registry, never the definition's source."""
    from agents import stock_agent
    from services import chat as chat_module
    from services import tool_audit_writer

    grant = lab_variants.stock_grant(variant)
    monkeypatch.setattr(stock_agent, "_STOCK_TOOLS", grant)
    agent = stock_agent.build_stock_agent()
    rows: list = []
    monkeypatch.setattr(tool_audit_writer, "record_allow", lambda **kw: rows.append(kw))
    before, _after = chat_module.make_tool_audit_hooks(session_id="persona-marco-x",
                                                       turn_id="turn-x")
    before(SimpleNamespace(agent=agent, tool_use={
        "name": "check_stock", "toolUseId": "tu-1", "input": {"product_query": "Hadley"}}))
    assert rows[0]["args"]["agent"] == "stock"
    assert rows[0]["args"]["grant"] == _names(grant)


def _audit(conn: Any, turn: str, tool: str, args: Dict[str, Any], result: Dict[str, Any], *,
           agent: Optional[str] = "stock", grant: Optional[Sequence[str]] = ("check_stock",),
           session: str = "persona-marco-") -> None:
    recorded = {**args, "turn_id": turn}
    if agent is not None:
        recorded["agent"] = agent
    if grant is not None:
        recorded["grant"] = list(grant)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms) "
            "VALUES (%s, %s, 'agent', %s::jsonb, %s::jsonb, 10)",
            (f"{session}{turn}", tool, json.dumps(recorded), json.dumps(result)))


STARTER_GRANT = ("search_products", "browse_department", "compare_products")


def test_a_turn_the_starter_grant_answered_is_not_yet(conn) -> None:
    """Also what a definition edited without a restart leaves: the running agent's grant."""
    _audit(conn, "turn-guess", "search_products", {"query": "Hadley Linen Shirt Brooklyn"},
           {"status": "success", "count": 1, "products": [{"productId": "2"}]},
           grant=STARTER_GRANT)
    finding = lab2.judge_2b(conn)
    assert finding.state == "NOT YET", finding
    assert "still held the starter's grant: search_products" in finding.observed
    assert "none of which reads warehouse_inventory" in finding.observed
    assert "restart the backend" in finding.next_step
    assert lab2.STARTER_GRANT == tuple(_names(lab_variants.stock_grant(lab_variants.STARTER)))


def test_a_wider_grant_than_check_stock_is_contradicted(conn) -> None:
    _audit(conn, "turn-wide", "check_stock", {"product_query": "Hadley Linen Shirt"},
           {"status": "success"}, grant=("search_products", "check_stock"))
    finding = lab2.judge_2b(conn)
    assert finding.state == "CONTRADICTED"
    assert "was granted search_products, check_stock" in finding.observed


def test_the_2b_check_passes_one_grounded_turn(conn, tool_db) -> None:
    envelope = _ask(lab_variants.SOLUTION, "Hadley Linen Shirt")
    _audit(conn, "turn-grounded", "check_stock", {"product_query": "Hadley Linen Shirt"}, envelope)
    finding = lab2.judge_2b(conn)
    assert finding.state == "PROVED", finding
    assert any("the Stock agent that answered held check_stock" in line
               for line in finding.evidence)
    assert any("warehouse_inventory for 2: ATX-02 6, BK-01 0, PDX-01 14" in line
               for line in finding.evidence)


def test_a_shopping_turn_by_marco_does_not_change_the_verdict(conn, tool_db) -> None:
    """Marco's own Goa question goes to the Shopping agent; 2B judges his stock turns only."""
    envelope = _ask(lab_variants.SOLUTION, "Hadley Linen Shirt")
    _audit(conn, "turn-stock", "check_stock", {"product_query": "Hadley Linen Shirt"}, envelope)
    _audit(conn, "turn-goa", "search_products", {"query": "linen for Goa"},
           {"status": "success", "count": 1, "products": [{"productId": "11"}]},
           agent="shopping", grant=("search_products", "browse_department", "compare_products"))
    finding = lab2.judge_2b(conn)
    assert finding.state == "PROVED", finding
    assert "turn-stock" in finding.evidence[0]


def test_the_2b_check_fails_a_count_the_warehouse_rows_do_not_hold(conn) -> None:
    guessed = {"status": "success", "product": {"productId": "2", "name": "Hadley Linen Shirt"},
               "total_units": 21, "warehouses": [{"warehouse_code": "BK-01", "quantity": 8},
                                                 {"warehouse_code": "ATX-02", "quantity": 6},
                                                 {"warehouse_code": "PDX-01", "quantity": 7}]}
    _audit(conn, "turn-wrong", "check_stock", {"product_query": "Hadley Linen Shirt"}, guessed)
    finding = lab2.judge_2b(conn)
    assert finding.state == "CONTRADICTED"
    assert "does not match the catalog" in finding.observed


def test_the_2b_check_fails_the_starters_folded_answer(conn, tool_db) -> None:
    envelope = _ask(lab_variants.STARTER, NOT_CARRIED)
    _audit(conn, "turn-folded", "check_stock", {"product_query": NOT_CARRIED}, envelope)
    finding = lab2.judge_2b(conn)
    assert finding.state == "CONTRADICTED"
    assert any("no catalog product carries that name" in line for line in finding.evidence)


def test_no_stock_agent_turn_is_not_yet(conn, monkeypatch) -> None:
    monkeypatch.setattr(lab2, "MARCO_SESSION_PREFIX", "persona-nobody-")
    finding = lab2.judge_2b(conn)
    assert finding.state == "NOT YET"
    assert lab2.MARCO_STOCK_QUESTION in finding.next_step


# ---------------------------------------------------------------------------
# Task 2A as the export reads it: Marco's recorded check_stock calls
# ---------------------------------------------------------------------------


def test_the_recorded_2a_line_follows_marcos_latest_not_carried_question(conn, tool_db) -> None:
    _audit(conn, "turn-cape-starter", "check_stock", {"product_query": NOT_CARRIED},
           _ask(lab_variants.STARTER, NOT_CARRIED), grant=STARTER_GRANT)
    folded = lab2.judge_recorded_2a(conn)
    assert folded.state == "CONTRADICTED", folded
    assert f'not carried: "{NOT_CARRIED}" recorded success, 0 units' in folded.observed

    # Each case is judged by its latest call: the wrong Hadley count recorded above
    # contradicts until a later Hadley call reads the rows.
    _audit(conn, "turn-cape-solution", "check_stock", {"product_query": NOT_CARRIED},
           _ask(lab_variants.SOLUTION, NOT_CARRIED))
    assert "in stock: \"Hadley Linen Shirt\" recorded success, 21 units" in (
        lab2.judge_recorded_2a(conn).observed)
    _audit(conn, "turn-hadley", "check_stock", {"product_query": "Hadley Linen Shirt"},
           _ask(lab_variants.SOLUTION, "Hadley Linen Shirt"))
    fixed = lab2.judge_recorded_2a(conn)
    assert fixed.state == "PROVED", fixed
    assert fixed.observed.startswith(
        "2 of 2 recorded cases match (not asked yet: several, sold out)")
    assert any(f'check_stock("{NOT_CARRIED}") recorded not_found' in line
               for line in fixed.evidence)


def test_the_recorded_2a_line_waits_for_a_not_carried_question(conn, monkeypatch) -> None:
    monkeypatch.setattr(lab2, "MARCO_SESSION_PREFIX", "persona-nobody-")
    finding = lab2.judge_recorded_2a(conn)
    assert finding.state == "NOT YET"
    assert lab2.MARCO_CAPE_QUESTION in finding.next_step
