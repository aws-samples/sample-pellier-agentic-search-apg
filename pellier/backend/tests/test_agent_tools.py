"""Tests for the ``@tool`` wrappers in `services.agent_tools`.

Each wrapper decides only what the in-process rail must decide (the bound
customer) and hands the query to
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


def test_exactly_the_eight_agent_tools_are_wrapped() -> None:
    """Every store tool an agent may call has one wrapper; the credit has none.

    `give_store_credit` is the Operator's write and reaches `store_tools` only
    through `services.governed_execution`, so no `@tool` exists for an agent to
    bind.
    """
    assert set(_wrappers()) == set(store_tools.TOOL_NAMES) - {"give_store_credit"}
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


# ---------------------------------------------------------------------------
# Identity evidence: the binding verdict comes from the binding code itself
# ---------------------------------------------------------------------------


def _identity_for(tool: str, *, authorized: str | None, customer_id: str = "", monkeypatch=None):
    from services import tool_evidence

    agent_tools._db_service = _SentinelDB()
    monkeypatch.setattr(agent_tools, "_run_sql", _FakeRun({}))
    token = authorized_customer_id_var.set(authorized)
    channel = tool_evidence.open_channel()
    try:
        kwargs = {"customer_id": customer_id} if customer_id else {}
        if tool == "ask_a_person":
            kwargs["reason"] = "The shopper asked for a person."
        parsed = _call(getattr(agent_tools, tool), **kwargs)
        evidence = tool_evidence.take(tool)
    finally:
        tool_evidence.close_channel(channel)
        authorized_customer_id_var.reset(token)
    return parsed, evidence.get("identity")


@pytest.mark.parametrize("tool", ["get_orders", "get_tickets"])
def test_theo_asking_for_jessica_is_refused_and_recorded(tool: str, monkeypatch: pytest.MonkeyPatch) -> None:
    parsed, identity = _identity_for(tool, authorized="CUST-THEO", customer_id="CUST-JESSICA", monkeypatch=monkeypatch)
    assert parsed["status"] == "customer_scope_mismatch"
    assert identity == {
        "requested_customer": "CUST-JESSICA",
        "authorized_customer": "CUST-THEO",
        "bound_customer": None,
        "binding": "refused",
    }


def test_the_same_customer_is_matched_and_no_customer_is_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    _, matched = _identity_for("get_tickets", authorized="CUST-THEO", customer_id="CUST-THEO", monkeypatch=monkeypatch)
    _, bound = _identity_for("get_tickets", authorized="CUST-THEO", monkeypatch=monkeypatch)
    assert matched["binding"] == "matched" and matched["bound_customer"] == "CUST-THEO"
    assert bound == {
        "requested_customer": None,
        "authorized_customer": "CUST-THEO",
        "bound_customer": "CUST-THEO",
        "binding": "bound",
    }


def test_an_unverified_shopper_is_refused_with_no_bound_customer(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed, identity = _identity_for("get_orders", authorized=None, customer_id="CUST-JESSICA", monkeypatch=monkeypatch)
    assert parsed["status"] == "customer_scope_required"
    assert identity["binding"] == "refused" and identity["authorized_customer"] is None


def test_the_handoff_runs_unbound_when_the_binding_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed, identity = _identity_for("ask_a_person", authorized="CUST-THEO", customer_id="CUST-JESSICA", monkeypatch=monkeypatch)
    assert parsed["type"] == "escalation" and parsed["customer_id"] is None
    assert identity == {
        "requested_customer": "CUST-JESSICA",
        "authorized_customer": "CUST-THEO",
        "bound_customer": None,
        "binding": "refused",
    }
    _, anonymous = _identity_for("ask_a_person", authorized=None, monkeypatch=monkeypatch)
    assert anonymous["binding"] == "unbound"
