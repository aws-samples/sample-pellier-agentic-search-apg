"""Customer-scope tests for the managed store-tools Gateway Lambda."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY = REPO_ROOT / "scripts" / "deploy"
SERVER = DEPLOY / "pellier_store_tools.py"

if str(DEPLOY) not in sys.path:
    sys.path.insert(0, str(DEPLOY))


def _load_server() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "pellier_customer_scoped_store_tools",
        SERVER,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parameter_value(parameters: list[dict[str, Any]], name: str) -> Any:
    parameter = next(item for item in parameters if item["name"] == name)
    value = parameter["value"]
    return next(iter(value.values()))


def _capture(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]] | None = None):
    """Replace the Data API executors and record every business statement.

    A customer's own read runs in a transaction whose first two statements
    switch to ``pellier_agent`` and name the customer; those are recorded in
    ``calls.binding`` and the read itself in the returned list.
    """
    import common.dataapi as dataapi

    class Calls(list):
        binding: list[tuple[str, str, list[dict[str, Any]]]] = []
        transactions: list[str] = []

    calls = Calls()
    calls.binding = []
    calls.transactions = []

    def _execute(sql: str, parameters: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        calls.append((sql, parameters or []))
        return list(rows or [])

    def _in_transaction(tx: str, sql: str, parameters: list[dict[str, Any]] | None = None):
        if "SET LOCAL ROLE" in sql or "set_config(" in sql:
            calls.binding.append((tx, sql, parameters or []))
            return []
        return _execute(sql, parameters)

    monkeypatch.setattr(dataapi, "execute_sql", _execute)
    monkeypatch.setattr(dataapi, "execute_in_transaction", _in_transaction)
    monkeypatch.setattr(dataapi, "begin_transaction", lambda: "tx-1")
    monkeypatch.setattr(dataapi, "commit_transaction", lambda tx: calls.transactions.append(f"commit {tx}"))
    monkeypatch.setattr(dataapi, "rollback_transaction", lambda tx: calls.transactions.append(f"rollback {tx}"))
    return calls


def test_customer_scoped_schemas_require_customer_id_and_expose_no_persona() -> None:
    from gateway_tool_schemas import TOOL_SCHEMAS

    tools = {tool["name"]: tool["inputSchema"] for tool in TOOL_SCHEMAS["store"]["tools"]}
    for tool_name in ("get_orders", "get_tickets"):
        schema = tools[tool_name]
        assert schema["required"] == ["customer_id"]
        assert "customer_id" in schema["properties"]
        assert "persona" not in schema["properties"]

    handoff = tools["ask_a_person"]
    assert handoff["required"] == ["reason"]
    assert "customer_id" in handoff["properties"]
    assert "persona" not in handoff["properties"]

    from services import store_tools

    assert "persona" not in inspect.signature(store_tools.get_orders).parameters
    with pytest.raises(TypeError):
        store_tools.get_orders(lambda sql, params: [], customer_id="CUST-MARCO", persona="marco")


def test_get_orders_scopes_the_aurora_query_to_the_bound_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _load_server()
    calls = _capture(monkeypatch, [{
        "order_id": 9, "product_id": "42", "name": "Tumbler", "brand": "Pellier",
        "category": "Home", "quantity": 1, "amount_paid_cents": 6400,
        "placed_at": "2026-01-02 03:04:05",
    }])

    result = server.lambda_handler(
        {"name": "get_orders", "arguments": {"customer_id": "CUST-MARCO", "limit": 50}}, None
    )

    assert len(calls) == 1
    sql, parameters = calls[0]
    assert "WHERE o.customer_id = :p0" in sql
    assert _parameter_value(parameters, "p0") == "CUST-MARCO"
    assert _parameter_value(parameters, "p1") == 20, "the row bound is part of the contract"
    assert '"amount_paid": 64.0' in result["text"]
    # Row-level security: the read ran as pellier_agent with Marco named, then committed.
    (_, role_sql, _), (_, name_sql, name_params) = calls.binding
    assert role_sql == "SET LOCAL ROLE pellier_agent;"
    assert "pellier.principal_username" in name_sql and "cognito_username" in name_sql
    assert _parameter_value(name_params, "customer") == "CUST-MARCO"
    assert calls.transactions == ["commit tx-1"]


def test_get_tickets_scopes_the_aurora_query_to_the_bound_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _load_server()
    calls = _capture(monkeypatch)

    result = server.lambda_handler(
        {"name": "get_tickets", "arguments": {"customer_id": "CUST-THEO", "limit": 3}}, None
    )

    assert len(calls) == 1
    sql, parameters = calls[0]
    assert "FROM pellier.support_tickets" in sql
    assert "WHERE customer_id = :p0" in sql
    assert _parameter_value(parameters, "p0") == "CUST-THEO"
    assert _parameter_value(parameters, "p1") == 3
    assert '"count": 0' in result["text"]
    assert [sql for _, sql, _ in calls.binding][0] == "SET LOCAL ROLE pellier_agent;"
    assert _parameter_value(calls.binding[1][2], "customer") == "CUST-THEO"


def test_a_missing_customer_id_binds_an_empty_customer_not_every_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _load_server()
    calls = _capture(monkeypatch)

    server.lambda_handler({"name": "get_orders", "arguments": {}}, None)

    sql, parameters = calls[0]
    assert "WHERE o.customer_id = :p0" in sql
    assert _parameter_value(parameters, "p0") == ""


def test_browse_department_escapes_like_metacharacters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A department argument's own `%`/`_`/`\\` must not act as a LIKE wildcard.

    An untrusted ``%`` in the argument would silently widen the filter to match every
    department instead of a literal substring.
    """
    server = _load_server()
    calls = _capture(monkeypatch)

    server.lambda_handler(
        {"name": "browse_department", "arguments": {"department": r"Home_100% \ Decor"}}, None
    )

    sql, parameters = calls[0]
    assert "ESCAPE" in sql
    assert _parameter_value(parameters, "p0") == r"%home\_100\% \\ decor%"


def test_check_stock_escapes_like_metacharacters_per_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _load_server()
    calls = _capture(monkeypatch)

    server.lambda_handler(
        {"name": "check_stock", "arguments": {"product_query": "Studio_100% Edition"}}, None
    )

    sql, parameters = calls[0]
    assert sql.count("ESCAPE") == 2
    assert _parameter_value(parameters, "p0") == r"%studio\_100\%%"
    assert _parameter_value(parameters, "p1") == "%edition%"
