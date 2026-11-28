"""Lab 2's contract: the starters fail the way the guide's See it fail steps show.

Task 2A. The starter Stock agent is connected to the catalog tools only, so it
holds no tool that reads ``warehouse_inventory``: its prompt names ``check_stock``,
and the call is refused and does not run. The solution connects ``check_stock``
alone. The built agent's own registry is what the audit row records and the
Builder view shows; ``scripts/lab2_check.py --task 2A`` judges Marco's latest
Stock-agent turn by that recorded grant, its calls and its counts for the pieces
Pellier carries. It passes on the as-shipped ``pellier.check_stock``.

Task 2B. The as-shipped ``pellier.check_stock`` totals the stock of whatever
matched without testing that anything did: Marco asks about the Velvet Opera
Cape, which Pellier does not carry, and gets one row with 0 units, which the
Builder view reads as "Sold out in all three warehouses". The solution tests for
the product first, so the answer is not_found.

The functions run on the real schema and seed; the Stock agent is built by its
real factory.
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Sequence

import psycopg
import pytest
from psycopg.rows import dict_row

from services.turn_steps import finding_for, parse_result
from tests import lab_variants
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
lab2 = importlib.import_module("lab2_check")

NOT_CARRIED = "Velvet Opera Cape"
CATALOG_TOOLS = {"search_products", "browse_department", "compare_products"}
SOLUTION_WORKSHEET = lab_variants.LAB2_FUNCTION[lab_variants.SOLUTION]


@pytest.fixture(scope="module")
def conn(fresh_db: Any) -> Any:  # noqa: F811 - the imported fixture
    connection = psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                                 dbname="postgres", autocommit=True, row_factory=dict_row)
    try:
        yield connection
    finally:
        connection.close()


def _install(conn: Any, variant: str, *, stamp: bool = False) -> None:
    """Make ``variant``'s pellier.check_stock the live one, stamped as its worksheet would."""
    with conn.cursor() as cur:
        cur.execute(lab_variants.check_stock_function(variant))
        cur.execute("COMMENT ON FUNCTION pellier.check_stock(text) IS NULL")
        if stamp:
            sha = lab2._sha(lab2.function_body(SOLUTION_WORKSHEET.read_text(encoding="utf-8")))
            cur.execute(f"COMMENT ON FUNCTION pellier.check_stock(text) IS "
                        f"'{lab2.STAMP_PREFIX}{sha}'")


def _ask(conn: Any, variant: str, query: str) -> Dict[str, Any]:
    _install(conn, variant)
    return json.loads(lab2.live_tool(conn, {})(product_query=query))


# ---------------------------------------------------------------------------
# Task 2A: the Stock agent's grant
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
    """The See it fail step's evidence line: the prompt asks for check_stock; the grant decides."""
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
    held = _names(grant)[0]  # a call to a tool the agent does not hold writes no row
    before(SimpleNamespace(agent=agent, tool_use={
        "name": held, "toolUseId": "tu-1", "input": {"product_query": "Hadley"}}))
    assert rows[0]["args"]["agent"] == "stock"
    assert rows[0]["args"]["grant"] == _names(grant)


def test_a_tool_the_running_agent_does_not_hold_leaves_no_audit_row(monkeypatch) -> None:
    """The starter's prompt names check_stock; a call to it never runs, so no row is written."""
    from agents import stock_agent
    from services import chat as chat_module
    from services import tool_audit_writer

    monkeypatch.setattr(stock_agent, "_STOCK_TOOLS", lab_variants.stock_grant("starter"))
    agent = stock_agent.build_stock_agent()
    assert "check_stock" not in agent.tool_names
    rows: list = []
    monkeypatch.setattr(tool_audit_writer, "record_allow", lambda **kw: rows.append(kw))
    before, _after = chat_module.make_tool_audit_hooks(session_id="persona-marco-x",
                                                       turn_id="turn-x")
    before(SimpleNamespace(agent=agent, tool_use={
        "name": "check_stock", "toolUseId": "tu-1", "input": {"product_query": "Hadley"}}))
    assert rows == []
    before(SimpleNamespace(agent=agent, tool_use={
        "name": "search_products", "toolUseId": "tu-2", "input": {"query": "Hadley"}}))
    assert [row["tool_name"] for row in rows] == ["search_products"]


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
    """Also what a definition no turn has run with leaves: the running agent's grant."""
    _audit(conn, "turn-guess", "search_products", {"query": "Hadley Linen Shirt Brooklyn"},
           {"status": "success", "count": 1, "products": [{"productId": "2"}]},
           grant=STARTER_GRANT)
    finding = lab2.judge_2a(conn)
    assert finding.state == "NOT YET PASSED", finding
    assert "still held the tools it ships with: search_products" in finding.observed
    assert "none of which reads warehouse_inventory" in finding.observed
    # send restarts the backend itself when the agent file changed, so the hint is the send.
    assert "restart" not in finding.next_step.lower()
    assert "uv run scripts/lab_run.py send --lab 2" in finding.next_step
    assert lab2.STARTER_GRANT == tuple(_names(lab_variants.stock_grant(lab_variants.STARTER)))


def test_a_wider_grant_than_check_stock_is_contradicted(conn) -> None:
    _audit(conn, "turn-wide", "check_stock", {"product_query": "Hadley Linen Shirt"},
           {"status": "success"}, grant=("search_products", "check_stock"))
    finding = lab2.judge_2a(conn)
    assert finding.state == "FAILED"
    assert "was granted search_products, check_stock" in finding.observed


def _grounded_turn(conn: Any, turn: str) -> None:
    envelope = _ask(conn, lab_variants.STARTER, "Hadley Linen Shirt")
    _audit(conn, turn, "check_stock", {"product_query": "Hadley Linen Shirt"}, envelope)


def test_a_turn_from_before_the_edit_cannot_vouch_for_it(conn) -> None:
    """A refused call leaves no row, so an older answer must not stand in for the new edit."""
    _grounded_turn(conn, "turn-before-edit")
    later = datetime.now(timezone.utc) + timedelta(minutes=1)
    finding = lab2.judge_2a(conn, lab2.check.Timeline(later, later + timedelta(minutes=1)))
    assert finding.state == "NOT YET PASSED", finding
    assert "before your last change to stock_agent.py" in finding.observed
    assert "send --lab 2 --task 2A" in finding.next_step


def test_a_backend_started_before_the_edit_is_not_yet(conn) -> None:
    _grounded_turn(conn, "turn-old-backend")
    now = datetime.now(timezone.utc)
    finding = lab2.judge_2a(conn, lab2.check.Timeline(now, now - timedelta(minutes=1)))
    assert finding.state == "NOT YET PASSED", finding
    assert "the running agent is not your edit yet" in finding.observed
    assert finding.next_step.startswith("send Marco's Brooklyn count again")
    assert "lab_run.py restart" not in finding.next_step


def test_a_turn_after_the_edit_and_the_restart_is_judged(conn) -> None:
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    _grounded_turn(conn, "turn-after-edit")
    finding = lab2.judge_2a(conn, lab2.check.Timeline(past, past + timedelta(minutes=1)))
    assert finding.state == "PASSED", finding


def test_a_ship_window_the_tables_do_not_hold_is_contradicted(conn) -> None:
    """Marco asks for the recorded ship window, so the check holds it to the table too."""
    envelope = _ask(conn, lab_variants.STARTER, "Hadley Linen Shirt")
    envelope["warehouses"][0]["ship_window_max"] += 3
    _audit(conn, "turn-window", "check_stock", {"product_query": "Hadley Linen Shirt"}, envelope)
    finding = lab2.judge_2a(conn)
    assert finding.state == "FAILED", finding
    assert any("ship windows in business days" in line for line in finding.evidence)


def test_the_2a_check_passes_one_grounded_turn(conn) -> None:
    envelope = _ask(conn, lab_variants.STARTER, "Hadley Linen Shirt")
    _audit(conn, "turn-grounded", "check_stock", {"product_query": "Hadley Linen Shirt"}, envelope)
    finding = lab2.judge_2a(conn)
    assert finding.state == "PASSED", finding
    assert any("the Stock agent that answered held check_stock" in line
               for line in finding.evidence)
    assert any("warehouse_inventory for 2: ATX-02 6, BK-01 0, PDX-01 14" in line
               for line in finding.evidence)


def test_the_2a_check_leaves_the_as_shipped_cape_answer_to_2b(conn) -> None:
    """Once the grant is right, Marco's cape turn calls the as-shipped function: 0 in stock.

    That answer is Task 2B's to fix, so 2A passes and says so in its evidence.
    """
    cape = _ask(conn, lab_variants.STARTER, NOT_CARRIED)
    assert cape["status"] == "success" and cape["total_units"] == 0
    hadley = _ask(conn, lab_variants.STARTER, "Hadley Linen Shirt")
    _audit(conn, "turn-cape-2a", "check_stock", {"product_query": NOT_CARRIED}, cape)
    _audit(conn, "turn-cape-2a", "check_stock", {"product_query": "Hadley Linen Shirt"}, hadley)
    finding = lab2.judge_2a(conn)
    assert finding.state == "PASSED", finding
    assert any(f'check_stock("{NOT_CARRIED}") said success, 0 units' in line
               and "which Task 2B judges" in line for line in finding.evidence)


def test_a_catalog_turn_by_marco_does_not_change_the_verdict(conn) -> None:
    """Marco's own Goa question goes to the Catalog agent; 2A judges his stock turns only."""
    envelope = _ask(conn, lab_variants.STARTER, "Hadley Linen Shirt")
    _audit(conn, "turn-stock", "check_stock", {"product_query": "Hadley Linen Shirt"}, envelope)
    _audit(conn, "turn-goa", "search_products", {"query": "linen for Goa"},
           {"status": "success", "count": 1, "products": [{"productId": "11"}]},
           agent="catalog", grant=("search_products", "browse_department", "compare_products"))
    finding = lab2.judge_2a(conn)
    assert finding.state == "PASSED", finding
    assert "turn-stock" in finding.evidence[0]


def test_the_2a_check_fails_a_count_the_warehouse_rows_do_not_hold(conn) -> None:
    guessed = {"status": "success", "product": {"productId": "2", "name": "Hadley Linen Shirt"},
               "total_units": 21, "warehouses": [{"warehouse_code": "BK-01", "quantity": 8},
                                                 {"warehouse_code": "ATX-02", "quantity": 6},
                                                 {"warehouse_code": "PDX-01", "quantity": 7}]}
    _audit(conn, "turn-wrong", "check_stock", {"product_query": "Hadley Linen Shirt"}, guessed)
    finding = lab2.judge_2a(conn)
    assert finding.state == "FAILED"
    assert "does not match the catalog" in finding.observed


MARCO_PIECE = "Hadley Linen Shirt"
NO_COMPARISON = "no check_stock call compared Brooklyn's count and ship window"


OWN_SESSION = "persona-marcoown-"


@pytest.fixture
def own_audit_rows(monkeypatch, request) -> None:
    """Judge a session of this test's own: tool_audit is append-only, and 2A looks back to
    Marco's newest shirt turn, so each test needs a prefix no other test has written."""
    monkeypatch.setattr(lab2, "MARCO_SESSION_PREFIX", f"{OWN_SESSION}{request.node.name}-")


def _own_audit(conn: Any, turn: str, tool: str, args: Dict[str, Any],
               result: Dict[str, Any]) -> None:
    _audit(conn, turn, tool, args, result, session=lab2.MARCO_SESSION_PREFIX)


def _assert_asks_for_the_brooklyn_question_again(finding: Any) -> None:
    assert finding.state == "NOT YET PASSED", finding
    assert NO_COMPARISON in finding.observed
    assert MARCO_PIECE in finding.observed
    assert lab2.SEND_2A in finding.next_step
    assert finding.next_step.count("uv run") == 1


@pytest.mark.parametrize("query", [
    "Hadley Linen Shirts",   # the plural names no catalog product
    "Linen shirt",           # names several products
    "",                      # names nothing
])
def test_2a_is_not_yet_when_the_only_call_names_no_single_piece(
    conn, own_audit_rows, query,
) -> None:
    """A query the catalog cannot resolve to one piece compares nothing, so it cannot pass."""
    answer = _ask(conn, lab_variants.SOLUTION, query)
    _own_audit(conn, "turn-unjudged", "check_stock", {"product_query": query}, answer)
    _assert_asks_for_the_brooklyn_question_again(lab2.judge_2a(conn))


def test_2a_is_not_yet_when_the_only_judged_call_is_another_piece(conn, own_audit_rows) -> None:
    """A matching comparison for the Quilted Silk Vest does not stand in for Marco's shirt."""
    vest = _ask(conn, lab_variants.SOLUTION, "Quilted Silk Vest")
    _own_audit(conn, "turn-vest", "check_stock", {"product_query": "Quilted Silk Vest"}, vest)
    finding = lab2.judge_2a(conn)
    _assert_asks_for_the_brooklyn_question_again(finding)
    assert any("Quilted Silk Vest" in line for line in finding.evidence)


def test_2a_fails_a_shirt_answer_that_names_no_brooklyn_row(conn, own_audit_rows) -> None:
    """Marco's question is about Brooklyn, so an answer without its row does not match."""
    answer = _ask(conn, lab_variants.SOLUTION, MARCO_PIECE)
    answer["warehouses"] = [row for row in answer["warehouses"]
                            if row["warehouse_code"] != "BK-01"]
    _own_audit(conn, "turn-no-brooklyn", "check_stock", {"product_query": MARCO_PIECE}, answer)
    assert lab2.judge_2a(conn).state == "FAILED"


def test_2a_a_shirt_turn_with_an_unjudged_call_beside_it_passes(conn, own_audit_rows) -> None:
    several = _ask(conn, lab_variants.SOLUTION, "Linen shirt")
    shirt = _ask(conn, lab_variants.SOLUTION, MARCO_PIECE)
    _own_audit(conn, "turn-both", "check_stock", {"product_query": "Linen shirt"}, several)
    _own_audit(conn, "turn-both", "check_stock", {"product_query": MARCO_PIECE}, shirt)
    finding = lab2.judge_2a(conn)
    assert finding.state == "PASSED", finding
    assert "Brooklyn" in finding.observed and MARCO_PIECE in finding.observed


def test_2a_a_shirt_mismatch_stays_failed_beside_a_matching_other_piece(
    conn, own_audit_rows,
) -> None:
    vest = _ask(conn, lab_variants.SOLUTION, "Quilted Silk Vest")
    shirt = _ask(conn, lab_variants.SOLUTION, MARCO_PIECE)
    shirt["warehouses"][0]["quantity"] += 4
    _own_audit(conn, "turn-shirt-wrong", "check_stock",
               {"product_query": "Quilted Silk Vest"}, vest)
    _own_audit(conn, "turn-shirt-wrong", "check_stock", {"product_query": MARCO_PIECE}, shirt)
    finding = lab2.judge_2a(conn)
    assert finding.state == "FAILED", finding


def test_the_singular_name_resolves_to_one_piece_and_the_plural_to_none(conn) -> None:
    """Marco's question names the catalog's own singular name, which names exactly one piece."""
    singular = lab2.catalog_answer(conn, MARCO_PIECE)
    assert [row["product_id"] for row in singular["matches"]] == ["2"]
    assert {row["warehouse_code"] for row in singular["stock"]} >= {"BK-01"}
    envelope = _ask(conn, lab_variants.SOLUTION, MARCO_PIECE)
    assert envelope["status"] == "success" and str(envelope["product"]["productId"]) == "2"
    plural = lab2.catalog_answer(conn, "Hadley Linen Shirts")
    assert plural["matches"] == []
    assert _ask(conn, lab_variants.SOLUTION, "Hadley Linen Shirts")["status"] == "not_found"


def test_no_stock_agent_turn_is_not_yet(conn, monkeypatch) -> None:
    monkeypatch.setattr(lab2, "MARCO_SESSION_PREFIX", "persona-nobody-")
    finding = lab2.judge_2a(conn)
    assert finding.state == "NOT YET PASSED"
    assert "uv run scripts/lab_run.py send --lab 2" in finding.next_step
    assert ("apply Task 2A (uv run scripts/lab_run.py solution --lab 2 --task 2A)"
            in finding.next_step)


# ---------------------------------------------------------------------------
# Task 2B: pellier.check_stock
# ---------------------------------------------------------------------------


def test_the_starter_calls_a_piece_pellier_does_not_carry_sold_out(conn) -> None:
    envelope = _ask(conn, lab_variants.STARTER, NOT_CARRIED)
    assert envelope["status"] == "success"
    assert envelope["total_units"] == 0
    assert finding_for("check_stock", parse_result(json.dumps(envelope))) == (
        "Sold out in all three warehouses")


def test_the_solution_says_pellier_does_not_carry_it(conn) -> None:
    envelope = _ask(conn, lab_variants.SOLUTION, NOT_CARRIED)
    assert envelope["status"] == "not_found"
    assert "total_units" not in envelope
    assert finding_for("check_stock", parse_result(json.dumps(envelope))) == (
        "Not a piece Pellier carries")


@pytest.mark.parametrize("variant", [lab_variants.STARTER, lab_variants.SOLUTION])
def test_both_report_a_carried_piece_from_the_warehouse_rows(conn, variant) -> None:
    envelope = _ask(conn, variant, "Hadley Linen Shirt")
    counts = {row["warehouse_code"]: row["quantity"] for row in envelope["warehouses"]}
    assert counts == {"BK-01": 0, "ATX-02": 6, "PDX-01": 14}
    assert envelope["total_units"] == 20


@pytest.mark.parametrize("variant", [lab_variants.STARTER, lab_variants.SOLUTION])
def test_both_ask_which_when_several_pieces_match(conn, variant) -> None:
    envelope = _ask(conn, variant, "Linen shirt")
    assert envelope["status"] == "ambiguous" and len(envelope["candidates"]) >= 2


def _defaults() -> Dict[str, Any]:
    return {case: (lab2.DEFAULT_INPUTS[case], "the check") for case in lab2.CASES}


def test_the_2b_check_fails_the_starter_on_the_not_carried_case_alone(conn) -> None:
    _install(conn, lab_variants.STARTER)
    starter, rows = lab2.judge_2b(conn, lab2.live_tool(conn, {}), _defaults())
    assert starter.state == "FAILED"
    assert f'not carried: "{NOT_CARRIED}" came back success, 0 units' in starter.observed
    assert [row[-1] for row in rows] == ["does not match", "matches", "matches", "matches"]
    assert any("warehouse_inventory for 2 Hadley Linen Shirt" in line for line in starter.evidence)
    assert "Stock check - not carried" in starter.next_step


def test_the_2b_check_passes_the_committed_solution(conn) -> None:
    _install(conn, lab_variants.SOLUTION, stamp=True)
    solution, rows = lab2.judge_2b(conn, lab2.live_tool(conn, {}), _defaults(),
                                   worksheet=SOLUTION_WORKSHEET)
    assert solution.state == "PASSED", solution
    assert [row[-1] for row in rows] == ["matches"] * 4
    assert "the live function is the one your file committed" in solution.observed


def test_a_right_function_your_worksheet_did_not_commit_is_not_yet(conn) -> None:
    _install(conn, lab_variants.SOLUTION)
    finding, _rows = lab2.judge_2b(conn, lab2.live_tool(conn, {}), _defaults())
    assert finding.state == "NOT YET PASSED", finding
    assert "not the one in your file" in finding.observed
    assert "labs/02-ground/2B-check-stock.sql" in finding.next_step


def test_a_test_input_that_is_not_its_case_cannot_pass(conn) -> None:
    _install(conn, lab_variants.SOLUTION, stamp=True)
    inputs = _defaults()
    inputs["unknown"] = ("Hadley Linen Shirt", "your flag")
    finding, _rows = lab2.judge_2b(conn, lab2.live_tool(conn, {}), inputs,
                                   worksheet=SOLUTION_WORKSHEET)
    assert finding.state == "NOT YET PASSED"
    assert "is in stock" in finding.observed


# ---------------------------------------------------------------------------
# Task 2B as the export reads it: Marco's recorded check_stock calls
# ---------------------------------------------------------------------------


def test_the_recorded_2b_line_follows_marcos_latest_not_carried_question(conn) -> None:
    _audit(conn, "turn-cape-starter", "check_stock", {"product_query": NOT_CARRIED},
           _ask(conn, lab_variants.STARTER, NOT_CARRIED))
    folded = lab2.judge_recorded_2b(conn)
    assert folded.state == "FAILED", folded
    assert f'not carried: "{NOT_CARRIED}" recorded success, 0 units' in folded.observed

    # Each case is judged by its latest call: the wrong Hadley count recorded above
    # contradicts until a later Hadley call reads the rows.
    _audit(conn, "turn-cape-solution", "check_stock", {"product_query": NOT_CARRIED},
           _ask(conn, lab_variants.SOLUTION, NOT_CARRIED))
    assert "in stock: \"Hadley Linen Shirt\" recorded success, 21 units" in (
        lab2.judge_recorded_2b(conn).observed)
    _audit(conn, "turn-hadley", "check_stock", {"product_query": "Hadley Linen Shirt"},
           _ask(conn, lab_variants.SOLUTION, "Hadley Linen Shirt"))
    fixed = lab2.judge_recorded_2b(conn)
    assert fixed.state == "PASSED", fixed
    assert fixed.observed.startswith(
        "2 of 2 recorded cases match (not asked yet: several, sold out)")
    assert any(f'check_stock("{NOT_CARRIED}") recorded not_found' in line
               for line in fixed.evidence)


def test_the_recorded_2b_line_waits_for_a_not_carried_question(conn, monkeypatch) -> None:
    monkeypatch.setattr(lab2, "MARCO_SESSION_PREFIX", "persona-nobody-")
    finding = lab2.judge_recorded_2b(conn)
    assert finding.state == "NOT YET PASSED"
    assert "uv run scripts/lab_run.py send --lab 2" in finding.next_step


def _cape_turn(conn: Any, turn: str) -> None:
    """Task 2B's question, sent after 2A: a Stock turn about a piece Pellier does not carry."""
    _own_audit(conn, turn, "check_stock", {"product_query": "Velvet Opera Cape"},
               _ask(conn, lab_variants.SOLUTION, "Velvet Opera Cape"))


def test_2a_keeps_marcos_shirt_turn_when_his_cape_question_comes_after(  # noqa: F811
        conn, own_audit_rows) -> None:
    """Participant order: the 2A shirt turn, then the 2B cape turn. 2A still grades the shirt."""
    _own_audit(conn, "turn-own-2a-shirt", "check_stock", {"product_query": MARCO_PIECE},
               _ask(conn, lab_variants.SOLUTION, MARCO_PIECE))
    _cape_turn(conn, "turn-own-2b-cape")
    finding = lab2.judge_2a(conn)
    assert finding.state == "PASSED", finding
    assert "turn-own-2a-shirt" in " ".join(finding.evidence)


def test_2a_grades_the_newest_shirt_turn_not_an_older_passing_one(  # noqa: F811
        conn, own_audit_rows) -> None:
    good = _ask(conn, lab_variants.SOLUTION, MARCO_PIECE)
    _own_audit(conn, "turn-own-shirt-good", "check_stock", {"product_query": MARCO_PIECE}, good)
    wrong = json.loads(json.dumps(good))
    for row in wrong.get("warehouses") or []:
        row["available"] = int(row.get("available") or 0) + 7
        row["quantity"] = int(row.get("quantity") or 0) + 7
    _own_audit(conn, "turn-own-shirt-wrong", "check_stock", {"product_query": MARCO_PIECE}, wrong)
    _cape_turn(conn, "turn-own-cape-after")
    assert lab2.judge_2a(conn).state == "FAILED"


def test_2a_without_any_shirt_turn_still_asks_for_the_brooklyn_question(  # noqa: F811
        conn, own_audit_rows) -> None:
    _cape_turn(conn, "turn-own-cape-only")
    _assert_asks_for_the_brooklyn_question_again(lab2.judge_2a(conn))


@pytest.mark.parametrize("new_query", ["Linen shirt", None])
def test_current_2a_turn_cannot_borrow_an_older_shirt_answer(conn, own_audit_rows, tmp_path,
                                                              new_query) -> None:
    receipt = tmp_path / "lab-2a-turn.json"
    _own_audit(conn, "shirt-before", "check_stock", {"product_query": MARCO_PIECE},
               _ask(conn, lab_variants.SOLUTION, MARCO_PIECE))
    if new_query:
        _own_audit(conn, "shirt-now", "check_stock", {"product_query": new_query},
                   _ask(conn, lab_variants.SOLUTION, new_query))
    _cape_turn(conn, "cape-after")
    receipt.write_text(json.dumps({"session": lab2.MARCO_SESSION_PREFIX + "shirt-now",
                                   "turn": "shirt-now"}))
    finding = lab2.judge_2a(conn)
    assert finding.state == "NOT YET PASSED", finding
    assert lab2.SEND_2A in finding.next_step


def test_a_scoped_2a_retry_never_asks_to_send_the_cape(conn, own_audit_rows) -> None:
    _own_audit(conn, "turn-before-fix", "search_products", {"query": MARCO_PIECE}, {})
    finding = lab2.judge_2a(conn)
    assert finding.state == "FAILED"
    assert lab2.SEND_2A in finding.next_step


def test_saved_shirt_turn_survives_the_cape_until_reset(conn, own_audit_rows) -> None:
    turn = "turn-saved-shirt"
    _own_audit(conn, turn, "check_stock", {"product_query": MARCO_PIECE},
               _ask(conn, lab_variants.SOLUTION, MARCO_PIECE))
    receipt = lab2.check.lab2_shirt_turn_path()
    receipt.write_text(json.dumps({"session": lab2.MARCO_SESSION_PREFIX + turn, "turn": turn}))
    _cape_turn(conn, "turn-cape")
    assert lab2.judge_2a(conn).state == "PASSED"
    reset = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
    lab2.check.record_reset_point(2, reset)
    assert lab2.judge_2a(conn).state == "NOT YET PASSED"


def test_legacy_attempt_without_hadley_in_the_tool_arguments_still_supersedes_the_old_turn(
        conn, own_audit_rows) -> None:
    _own_audit(conn, "old-shirt", "check_stock", {"product_query": MARCO_PIECE},
               _ask(conn, lab_variants.SOLUTION, MARCO_PIECE))
    _own_audit(conn, "new-ambiguous", "check_stock", {"product_query": "Linen shirt"},
               _ask(conn, lab_variants.SOLUTION, "Linen shirt"))
    _cape_turn(conn, "cape-after-both")
    _assert_asks_for_the_brooklyn_question_again(lab2.judge_2a(conn))



def test_lab_2s_grid_row_reads_brooklyn_and_the_missing_product_live(  # noqa: F811
        conn, own_audit_rows) -> None:
    turn = "turn-grid-shirt"
    _own_audit(conn, turn, "check_stock", {"product_query": MARCO_PIECE},
               _ask(conn, lab_variants.SOLUTION, MARCO_PIECE))
    lab2.check.lab2_shirt_turn_path().write_text(
        json.dumps({"session": lab2.MARCO_SESSION_PREFIX + turn, "turn": turn}))
    assert lab2.lab_2_proof(conn, "Velvet Opera Cape") == (
        "Brooklyn had 0 shirts. The Velvet Opera Cape had no catalog entry.")


def test_lab_2s_grid_row_is_withheld_while_2a_does_not_pass(conn, own_audit_rows) -> None:
    _install(conn, lab_variants.SOLUTION)
    assert lab2.lab_2_proof(conn, "Velvet Opera Cape") is None
