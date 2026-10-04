"""The step contract: one label table, fixed finding templates, a four-step budget."""

from __future__ import annotations

import json

import pytest

from services import turn_steps
from services.turn_steps import (
    MAX_STEPS,
    SKILL_LOAD_TOOL,
    STATUS_UNDERSTANDING,
    STATUS_WRITING,
    TurnSteps,
    finding_for,
    layer_tags,
    parse_result,
    step_label,
)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "label"),
    [
        ("search_products", "Searching the catalog in Aurora"),
        ("check_stock", "Checking stock in three warehouses"),
        ("get_tickets", "Reading your tickets"),
        ("get_orders", "Reading your orders"),
        ("ask_a_person", "Asking a person at Pellier"),
    ],
)
def test_tool_starts_map_to_plain_labels(tool: str, label: str) -> None:
    assert step_label(tool) == label


def test_the_skill_loader_names_the_skill_it_opens() -> None:
    assert step_label(SKILL_LOAD_TOOL, {"skill_name": "The Gift Table"}) == "Opening The Gift Table"
    assert step_label(SKILL_LOAD_TOOL, {}) == "Opening a skill"


def test_status_labels_are_the_two_the_spec_names() -> None:
    assert STATUS_UNDERSTANDING == "Understanding your request"
    assert STATUS_WRITING == "Writing your answer"
    assert turn_steps.status_event(STATUS_WRITING) == {"type": "status", "label": STATUS_WRITING}


# ---------------------------------------------------------------------------
# Findings, from fixture results
# ---------------------------------------------------------------------------


def _search(count: int, *, price=None, stock=False, exclusions=()) -> dict:
    return {
        "status": "success",
        "count": count,
        "products": [{"productId": str(index)} for index in range(count)],
        "search_plan": {
            "hard_constraints": {"price_max_usd": price, "in_stock_only": stock, "categories": []},
            "exclusions": list(exclusions),
        },
    }


def test_search_finding_says_what_the_number_is() -> None:
    parsed = _search(3, price=100, stock=True, exclusions=("candle",))
    assert finding_for("search_products", parsed, kept=23) == (
        "3 found from 23 that fit under $100 and in stock, candles left out"
    )
    # Without the filter counts (the managed rail) the found count still says so.
    assert finding_for("search_products", parsed) == (
        "3 found under $100 and in stock, candles left out"
    )


def test_search_finding_without_limits_and_when_empty() -> None:
    assert finding_for("search_products", _search(4)) == "4 found"
    assert finding_for("search_products", _search(4), kept=64) == "4 found from 64 that fit"
    assert finding_for("search_products", _search(0, price=50)) == "Nothing matched under $50"


def test_search_finding_names_the_limits_kept_from_earlier() -> None:
    parsed = _search(3, price=100, stock=True, exclusions=("candle",))
    carried = ("budget", "stock", "exclusions")
    assert finding_for("search_products", parsed, kept=23, carried=carried) == (
        "3 found from 23 that fit. Kept your limits from earlier: under $100, in stock, no candles"
    )
    # A new budget this turn, the rest carried.
    assert finding_for("search_products", _search(2, price=80, stock=True, exclusions=("candle",)),
                       kept=12, carried=("stock", "exclusions")) == (
        "2 found from 12 that fit under $80. Kept your limits from earlier: in stock, no candles"
    )
    assert finding_for("search_products", _search(0, price=100), carried=("budget",)) == (
        "Nothing matched. Kept your limits from earlier: under $100"
    )


def test_browse_finding_carries_the_limits_too() -> None:
    parsed = {
        "status": "success", "department": "Home", "count": 4,
        "search_plan": {
            "hard_constraints": {"price_max_usd": 100, "in_stock_only": True, "categories": []},
            "exclusions": ["candle"],
        },
    }
    assert finding_for("browse_department", parsed, carried=("budget", "stock", "exclusions")) == (
        "4 in Home, by rating. Kept your limits from earlier: under $100, in stock, no candles"
    )
    assert finding_for("browse_department", parsed) == (
        "4 in Home, by rating, under $100 and in stock, candles left out"
    )


def test_requirement_phrases_list_what_applied_and_what_was_kept() -> None:
    plan = {
        "hard_constraints": {"price_max_usd": 100, "in_stock_only": True, "categories": ["Home"]},
        "exclusions": ["candle", "wool"],
    }
    assert turn_steps.requirement_phrases(plan, ["budget", "exclusions"]) == {
        "applied": ["under $100", "in stock", "no candles or wools", "Home only"],
        "carried": ["under $100", "no candles or wools"],
    }
    assert turn_steps.requirement_phrases({"hard_constraints": {}, "exclusions": []}) is None


def test_stock_finding_reads_the_three_warehouses_in_order() -> None:
    parsed = {
        "status": "success",
        "total_units": 20,
        "warehouses": [
            {"city": "Portland", "quantity": 14},
            {"city": "Austin", "quantity": 6},
            {"city": "Brooklyn", "quantity": 0},
        ],
    }
    assert finding_for("check_stock", parsed) == "Brooklyn 0, Austin 6, Portland 14"


def test_stock_finding_distinguishes_zero_from_unknown() -> None:
    sold_out = {"status": "success", "total_units": 0, "warehouses": [{"city": "Austin", "quantity": 0}]}
    assert finding_for("check_stock", sold_out) == "Sold out in all three warehouses"
    assert finding_for("check_stock", {"status": "not_found"}) == "Not a piece Pellier carries"
    assert finding_for("check_stock", {"status": "ambiguous", "candidates": [1, 2]}) == "2 pieces match that name"


def test_ticket_and_order_findings() -> None:
    tickets = {"status": "success", "count": 3, "open_count": 2, "tickets": []}
    assert finding_for("get_tickets", tickets) == "2 open tickets, 1 closed"
    assert finding_for("get_tickets", {"status": "success", "count": 0}) == "No tickets on your account"
    assert finding_for("get_orders", {"status": "success", "count": 7}) == "7 orders on your account"
    assert finding_for("get_orders", {"status": "customer_scope_mismatch"}) == (
        "Only the signed-in account can be read"
    )


def test_policy_browse_compare_and_handoff_findings() -> None:
    policy = {"status": "success", "department": "Home", "return_window_days": 30}
    assert finding_for("get_return_policy", policy) == "30-day returns for Home"
    assert finding_for("browse_department", {"status": "success", "department": "Home", "count": 5}) == (
        "5 in Home, by rating"
    )
    compare = {
        "status": "success",
        "product_1": {"name": "Wabi-Sabi Bowl", "price": 24},
        "product_2": {"name": "Ceramic Tumblers", "price": 34},
    }
    assert finding_for("compare_products", compare) == "Wabi-Sabi Bowl $24 vs Ceramic Tumblers $34"
    handoff = {"type": "escalation", "status": "handed_off", "credit_request_status": "request_opened"}
    assert finding_for("ask_a_person", handoff) == "A store credit request is waiting for a person"
    assert finding_for("ask_a_person", {"type": "escalation", "status": "handed_off"}) == (
        "Handed to a person at Pellier"
    )
    standing = {"type": "escalation", "status": "handed_off", "credit_request_status": "already_requested"}
    assert finding_for("ask_a_person", standing) == (
        "A store credit request was already waiting for a person"
    )
    for outcome in (handoff, standing):
        assert "$" not in finding_for("ask_a_person", outcome), "a request names no amount"


@pytest.mark.parametrize(
    "tool",
    ["search_products", "check_stock", "get_orders", "get_tickets", "ask_a_person", "browse_department"],
)
def test_an_error_result_uses_the_error_template_and_never_the_raw_text(tool: str) -> None:
    finding = finding_for(tool, parse_result('{"error": "psycopg.OperationalError: connection refused"}'))
    assert finding == turn_steps.ERROR_FINDINGS[tool]
    assert "psycopg" not in finding


def test_prose_results_parse_to_text() -> None:
    assert parse_result("Skill 'x' not found. Available skills: a") == {
        "_text": "Skill 'x' not found. Available skills: a"
    }


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_layer_tags_follow_the_tool_and_the_outcome() -> None:
    assert layer_tags("get_tickets", {}) == ["Aurora", "Identity"]
    assert layer_tags("search_products", {}) == ["Aurora"]
    assert layer_tags("ask_a_person", {"credit_request_status": "request_opened"}) == ["Identity", "Approval"]
    standing = {"credit_request_status": "already_requested"}
    assert layer_tags("ask_a_person", standing) == ["Identity", "Approval"]
    assert layer_tags("ask_a_person", {"credit_request_status": "sign_in_required"}) == ["Identity"]
    assert layer_tags(SKILL_LOAD_TOOL, {}) == ["Skills"]


# ---------------------------------------------------------------------------
# The budget and the fold
# ---------------------------------------------------------------------------


def test_steps_never_exceed_the_budget() -> None:
    assert MAX_STEPS == 4, "the brief allows at most four steps per turn"
    steps = TurnSteps()
    ids = {
        steps.running(tool)["id"]
        for tool in ("search_products", "browse_department", "compare_products", "check_stock", "get_orders")
    }
    assert len(steps.order) == 4
    assert ids <= set(steps.order)
    assert steps.step_id("get_orders") == steps.order[-1]


def test_a_repeated_tool_reuses_its_step() -> None:
    steps = TurnSteps()
    first = steps.running("search_products")
    second = steps.running("search_products")
    assert first["id"] == second["id"] == "step-1"
    assert steps.order == ["route", "step-1"]
    assert second["builder"] == {"tool": "search_products"}


def test_skill_loads_fold_into_one_step_with_one_finding() -> None:
    names = {"the-gift-table": "The Gift Table", "the-proof-counter": "The Proof Counter"}
    paths = {
        "the-gift-table": "skills/the-gift-table/SKILL.md",
        "the-proof-counter": "skills/the-proof-counter/SKILL.md",
    }
    steps = TurnSteps(skill_names=names, skill_paths=paths)
    running = steps.running(SKILL_LOAD_TOOL, {"skill_name": "the-gift-table"})
    assert running["label"] == "Opening The Gift Table"
    done = steps.finished(SKILL_LOAD_TOOL, "# The Gift Table\n...", tool_input={"skill_name": "the-gift-table"})
    assert done["finding"] == "Loaded The Gift Table from skills/the-gift-table/SKILL.md"
    again = steps.finished(SKILL_LOAD_TOOL, "# The Proof Counter", tool_input={"skill_name": "the-proof-counter"})
    assert again["id"] == done["id"] == running["id"] == "step-1"
    assert again["finding"] == "Loaded The Gift Table and The Proof Counter from skills/"
    assert again["status"] == "done"
    assert [skill["name"] for skill in steps.loaded_skills] == ["the-gift-table", "the-proof-counter"]


def test_a_skill_opened_twice_is_loaded_once() -> None:
    names = {"the-gift-table": "The Gift Table"}
    steps = TurnSteps(skill_names=names, skill_paths={"the-gift-table": "skills/the-gift-table/SKILL.md"})
    steps.finished(SKILL_LOAD_TOOL, "# The Gift Table", tool_input={"skill_name": "the-gift-table"})
    again = steps.finished(SKILL_LOAD_TOOL, "# The Gift Table", tool_input={"skill_name": "the-gift-table"})
    assert [skill["name"] for skill in steps.loaded_skills] == ["the-gift-table"]
    assert again["finding"] == "Loaded The Gift Table from skills/the-gift-table/SKILL.md"
    assert again["builder"]["skills"] == steps.loaded_skills


def test_on_demand_mode_tags_the_router_step_before_any_load() -> None:
    route = TurnSteps().route(
        agent="Shopping agent", intent="shopping", finding="Sent to the Shopping agent",
        model_id="m", skills=[], skill_mode="on_demand",
    )
    assert route["tags"] == ["Router", "Skills (on demand)"]
    fixed = TurnSteps().route(
        agent="Shopping agent", intent="shopping", finding="Sent to the Shopping agent",
        model_id="m", skills=[], skill_mode="fixed",
    )
    assert fixed["tags"] == ["Router"]


def test_a_refused_skill_load_is_a_failed_step() -> None:
    steps = TurnSteps(skill_names={"the-care-card": "The Care Card"})
    done = steps.finished(
        SKILL_LOAD_TOOL,
        "Skill 'the-care-card' not found. Available skills: the-gift-table",
        tool_input={"skill_name": "the-care-card"},
    )
    assert done["status"] == "failed"
    assert done["finding"] == "No skill named the-care-card for this agent"
    assert steps.loaded_skills == []


def test_finished_step_carries_the_builder_payload_and_no_raw_result() -> None:
    steps = TurnSteps()
    result = json.dumps(_search(2, price=100))
    evidence = {
        "receipt_id": 412,
        "ranking": {"available": True, "rows": [], "filters": {"kept": 64, "of": 100, "removed": {}}},
        "requirements": {"carried": ["budget"]},
    }
    done = steps.finished("search_products", result, duration_ms=184, audit_id=9031, evidence=evidence)
    assert done["status"] == "done"
    assert done["finding"] == "2 found from 64 that fit. Kept your limits from earlier: under $100"
    assert done["builder"]["audit_id"] == 9031
    assert done["builder"]["receipt_id"] == 412
    assert done["builder"]["ranking"]["available"] is True
    assert done["builder"]["requirements"] == {"applied": ["under $100"], "carried": ["under $100"]}
    assert done["builder"]["tool"] == "search_products"
    shopper_view = {key: value for key, value in done.items() if key != "builder"}
    assert "search_products" not in json.dumps(shopper_view)
    assert "productId" not in json.dumps(done)


def test_route_step_names_the_agent_once_and_its_skills() -> None:
    steps = TurnSteps()
    route = steps.route(
        agent="Shopping agent",
        intent="shopping",
        finding="Sent to the Shopping agent",
        model_id="global.anthropic.claude-opus-5",
        skills=[{"name": "the-gift-table", "loaded": "fixed"}],
        skill_mode="fixed",
        memory={"facts": 3, "orders": 2, "source": "Aurora PostgreSQL"},
    )
    assert route["id"] == "route" and route["status"] == "done"
    assert route["label"] == STATUS_UNDERSTANDING
    assert route["tags"] == ["Router", "Memory", "Skills"]
    assert route["builder"]["agent"] == "Shopping agent"
    assert route["builder"]["stop_reason"] is None


def test_the_route_step_sent_again_carries_how_the_turn_ended() -> None:
    steps = TurnSteps()
    facts = {
        "agent": "Shopping agent", "intent": "shopping", "finding": "Sent to the Shopping agent",
        "model_id": "global.anthropic.claude-opus-5", "skills": [], "skill_mode": "fixed",
    }
    first = steps.route(**facts)
    again = steps.route(**facts, stop_reason="max_tokens")
    assert again["id"] == "route" and again["builder"]["stop_reason"] == "max_tokens"
    shopper_view = {key: value for key, value in again.items() if key != "builder"}
    assert shopper_view == {key: value for key, value in first.items() if key != "builder"}
    assert "max_tokens" not in json.dumps(shopper_view)


def test_managed_step_maps_identity_fields_from_the_runtime_event() -> None:
    event = {
        "tool": "get_tickets",
        "status": "success",
        "duration_ms": 90,
        "finding": "1 open ticket, 1 closed",
        "requested_customer": "CUST-JESSICA",
        "bound_customer": "CUST-THEO",
        "binding": "overwritten",
    }
    step = TurnSteps().managed(event)
    assert step["id"] == "step-1"
    assert step["label"] == "Reading your tickets"
    assert step["finding"] == "1 open ticket, 1 closed"
    assert step["builder"]["identity"] == {
        "binding": "overwritten",
        "requested_customer": "CUST-JESSICA",
        "bound_customer": "CUST-THEO",
        "authorized_customer": "CUST-THEO",
    }
    assert step["builder"]["rail"] == "gateway-mcp"
