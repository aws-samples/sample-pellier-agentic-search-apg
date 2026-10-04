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
    """Replace the Data API statement executor and record every call."""
    import common.dataapi as dataapi

    calls: list[tuple[str, list[dict[str, Any]]]] = []

    def _execute(sql: str, parameters: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        calls.append((sql, parameters or []))
        return list(rows or [])

    monkeypatch.setattr(dataapi, "execute_sql", _execute)
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
