"""Tests for the ``@tool`` wrappers in `services.agent_tools`.

Each wrapper decides only what the in-process rail must decide (the bound
customer, the governed-format guard) and hands the query to
``services.store_tools`` through ``_run_sql``. These tests stub ``_run_sql``
and run offline: no database, no Bedrock.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

import services.agent_tools as agent_tools
from services import store_tools
from services.turn_identity import authorized_customer_id_var, principal_sub_var


@pytest.fixture(autouse=True)
def reset_module_globals():
    """Snapshot and restore `_db_service` / `_main_loop` so tests don't leak."""
    saved_db = agent_tools._db_service
    saved_loop = agent_tools._main_loop
    yield
    agent_tools._db_service = saved_db
    agent_tools._main_loop = saved_loop


class _SentinelDB:
    """Opaque placeholder; `_run_sql` is stubbed so it is never used."""


class _FakeRun:
    def __init__(self, rows_for: Dict[str, List[Dict[str, Any]]]) -> None:
        self.rows_for = rows_for
        self.calls: List[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        self.calls.append((sql, tuple(params)))
        for needle, rows in self.rows_for.items():
            if needle in sql:
                return [dict(row) for row in rows]
        return []


def _call(tool: Any, **kwargs: Any) -> Dict[str, Any]:
    """Invoke the underlying function of a Strands ``@tool`` and parse its JSON."""
    fn = getattr(tool, "__wrapped__", tool)
    return json.loads(fn(**kwargs))


def _wrappers() -> Dict[str, Any]:
    return {
        name: value for name, value in vars(agent_tools).items()
        if hasattr(value, "tool_spec") and hasattr(value, "tool_name")
    }


def test_exactly_the_nine_store_tools_are_wrapped() -> None:
    assert set(_wrappers()) == set(store_tools.TOOL_NAMES)
    for name, wrapper in _wrappers().items():
        assert wrapper.tool_name == name


@pytest.mark.parametrize(
    "tool, kwargs",
    [
        ("search_products", {"query": "linen"}),
        ("browse_department", {"department": "Home"}),
        ("compare_products", {"product_id_1": 1, "product_id_2": 2}),
        ("get_return_policy", {"department": "Home"}),
    ],
)
def test_a_missing_db_service_returns_the_error_envelope(tool: str, kwargs: Dict[str, Any]) -> None:
    agent_tools._db_service = None
    parsed = _call(getattr(agent_tools, tool), **kwargs)
    assert "error" in parsed and "not initialized" in parsed["error"].lower()


def test_browse_department_shapes_rows_through_store_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    agent_tools._db_service = _SentinelDB()
    run = _FakeRun({"FROM pellier.product_catalog": [
        {"productId": "21", "name": "Tall Stoneware Vase", "brand": "Pellier", "color": "Oat",
         "price": 64, "rating": 4.8, "reviews": 120, "category": "Home", "imgUrl": "/v.webp",
         "badge": None, "tags": '["home","gift"]'},
    ]})
    monkeypatch.setattr(agent_tools, "_run_sql", run)

    parsed = _call(agent_tools.browse_department, department="Home", limit=3)

    assert parsed["status"] == "success" and parsed["count"] == 1
    assert parsed["products"][0]["tags"] == ["home", "gift"]
    assert run.calls[0][1] == ("%home%", 3)


def test_a_raised_exception_returns_the_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    agent_tools._db_service = _SentinelDB()

    def _boom(_sql: str, _params: Any = ()) -> List[Dict[str, Any]]:
        raise RuntimeError("db connection refused")

    monkeypatch.setattr(agent_tools, "_run_sql", _boom)
    parsed = _call(agent_tools.get_return_policy, department="Home")
    assert parsed == {"error": "db connection refused"}


def test_check_stock_is_the_lab_2_stub_or_the_wired_read(monkeypatch: pytest.MonkeyPatch) -> None:
    agent_tools._db_service = _SentinelDB()
    monkeypatch.setattr(agent_tools, "_run_sql", _FakeRun({}))
    parsed = _call(agent_tools.check_stock, product_query="Hadley shirt")
    if "error" in parsed:
        assert parsed["error"] == "check_stock is in stub state"
        assert parsed["received_product_query"] == "Hadley shirt"
    else:
        assert parsed["status"] == "not_found"


@pytest.mark.parametrize("tool", ["get_orders", "get_tickets"])
def test_caller_bound_reads_refuse_an_unverified_shopper(tool: str, monkeypatch: pytest.MonkeyPatch) -> None:
    agent_tools._db_service = _SentinelDB()
    run = _FakeRun({})
    monkeypatch.setattr(agent_tools, "_run_sql", run)
    token = authorized_customer_id_var.set(None)
    try:
        parsed = _call(getattr(agent_tools, tool), customer_id="CUST-JESSICA")
    finally:
        authorized_customer_id_var.reset(token)
    assert parsed["status"] == "customer_scope_required"
    assert run.calls == []


@pytest.mark.parametrize("tool", ["get_orders", "get_tickets"])
def test_caller_bound_reads_bind_the_verified_customer_not_the_argument(
    tool: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_tools._db_service = _SentinelDB()
    run = _FakeRun({})
    monkeypatch.setattr(agent_tools, "_run_sql", run)
    token = authorized_customer_id_var.set("CUST-THEO")
    try:
        mismatch = _call(getattr(agent_tools, tool), customer_id="CUST-JESSICA")
        own = _call(getattr(agent_tools, tool))
    finally:
        authorized_customer_id_var.reset(token)
    assert mismatch["status"] == "customer_scope_mismatch"
    assert own["status"] == "success" and own["customer_id"] == "CUST-THEO"
    assert run.calls[-1][1][0] == "CUST-THEO"


def test_give_store_credit_is_refused_on_the_in_process_rail_in_the_governed_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import settings

    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "governed", raising=False)
    agent_tools._db_service = _SentinelDB()
    run = _FakeRun({})
    monkeypatch.setattr(agent_tools, "_run_sql", run)
    parsed = _call(
        agent_tools.give_store_credit,
        customer_id="CUST-JESSICA", amount_cents=2500, reason="late delivery", idempotency_key="k-1",
    )
    assert parsed["error"] == "managed_rail_required" and parsed["tool"] == "give_store_credit"
    assert run.calls == []


def test_give_store_credit_runs_the_shared_write_in_the_builders_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import settings

    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "builders", raising=False)
    agent_tools._db_service = _SentinelDB()
    run = _FakeRun({"apply_store_credit": [{"result": {"status": "success", "credit_id": 9}}]})
    monkeypatch.setattr(agent_tools, "_run_sql", run)
    parsed = _call(
        agent_tools.give_store_credit,
        customer_id="CUST-JESSICA", amount_cents=2500, reason="late delivery", idempotency_key="k-1",
    )
    assert parsed == {"status": "success", "credit_id": 9}
    sql, params = run.calls[0]
    assert "apply_store_credit" in sql and params[2:5] == ("CUST-JESSICA", 2500, "late delivery")
    assert params[5] is None, "no verified staff subject reaches a tool call"


def test_ask_a_person_hands_off_without_a_write() -> None:
    agent_tools._db_service = _SentinelDB()
    token = authorized_customer_id_var.set(None)
    try:
        parsed = _call(agent_tools.ask_a_person, reason="The shopper asked for a person.")
    finally:
        authorized_customer_id_var.reset(token)
    assert parsed["type"] == "escalation" and parsed["status"] == "handed_off"
    assert "credit_request" not in parsed


def test_ask_a_person_opens_a_credit_review_for_the_verified_shopper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_tools._db_service = _SentinelDB()
    run = _FakeRun({"INSERT INTO pellier.approvals": [{"id": 41}]})
    monkeypatch.setattr(agent_tools, "_run_sql", run)
    tokens = (authorized_customer_id_var.set("CUST-JESSICA"), principal_sub_var.set("sub-jessica"))
    try:
        parsed = _call(agent_tools.ask_a_person, reason="Two items went back.", store_credit_cents=4500)
    finally:
        authorized_customer_id_var.reset(tokens[0])
        principal_sub_var.reset(tokens[1])
    assert parsed["credit_request"] == "review_opened" and parsed["review_id"] == 41
    sql, params = run.calls[0]
    assert "give_store_credit" in sql
    assert json.loads(params[1]) == {"amount_cents": 4500, "customer_id": "CUST-JESSICA", "reason": "Two items went back."}
    assert params[-2:] == ("sub-jessica", "shopper")
