"""Customer-scope tests for managed recommendation Gateway tools."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import boto3
import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY = REPO_ROOT / "scripts" / "deploy"
SERVER = DEPLOY / "pellier_recommend_server.py"


def _load_server(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    if str(DEPLOY) not in sys.path:
        sys.path.insert(0, str(DEPLOY))

    class _Client:
        pass

    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setattr(boto3, "client", lambda *_args, **_kwargs: _Client())
    spec = importlib.util.spec_from_file_location(
        "pellier_customer_scoped_recommendation_server",
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


def test_customer_scoped_schemas_require_customer_id_and_expose_no_persona(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _load_server(monkeypatch)

    for tool_name in ("get_customer_preferences", "get_audit_trail"):
        schema = server.TOOLS[tool_name]["inputSchema"]
        assert schema["required"] == ["customer_id"]
        assert "customer_id" in schema["properties"]
        assert "persona" not in schema["properties"]

    from gateway_tool_schemas import TOOL_SCHEMAS

    handoff_schema = next(
        tool["inputSchema"]
        for tool in TOOL_SCHEMAS["experience"]["tools"]
        if tool["name"] == "escalate_to_human"
    )
    assert handoff_schema["required"] == ["customer_id"]

    assert "persona" not in inspect.signature(server.get_customer_preferences).parameters
    with pytest.raises(TypeError):
        server.get_customer_preferences(persona="marco")


def test_get_customer_preferences_scopes_every_aurora_query_to_bound_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _load_server(monkeypatch)
    calls: list[tuple[str, list[dict[str, Any]]]] = []

    def _execute(
        sql: str,
        parameters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        calls.append((sql, parameters or []))
        if "FROM pellier.customers" in sql:
            return [{"id": "CUST-MARCO", "name": "Marco"}]
        return []

    monkeypatch.setattr(server, "_execute_sql", _execute)

    result = server.get_customer_preferences(customer_id="cust-marco", limit=20)

    assert result["status"] == "success"
    assert len(calls) == 3
    assert "WHERE id = :customer_id" in calls[0][0]
    assert "WHERE o.customer_id = :customer_id" in calls[1][0]
    assert "WHERE customer_id = :customer_id" in calls[2][0]
    for _, parameters in calls:
        assert _parameter_value(parameters, "customer_id") == "CUST-MARCO"
    assert _parameter_value(calls[1][1], "limit") == 10
    assert _parameter_value(calls[2][1], "limit") == 10


def test_get_audit_trail_filters_audit_rows_by_bound_customer_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _load_server(monkeypatch)
    calls: list[tuple[str, list[dict[str, Any]]]] = []

    def _execute(
        sql: str,
        parameters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        calls.append((sql, parameters or []))
        return []

    monkeypatch.setattr(server, "_execute_sql", _execute)

    result = server.get_audit_trail(
        customer_id="CUST-THEO",
        session_id="session-123",
        tool_name="initiate_return",
        caller="Gateway",
    )

    assert result["status"] == "no_allow_receipt"
    assert len(calls) == 1
    sql, parameters = calls[0]
    assert "args->>'customer_id' = :customer_id" in sql
    assert "session_id = :session_id" in sql
    assert "tool = :tool" in sql
    assert "caller = :caller" in sql
    assert _parameter_value(parameters, "customer_id") == "CUST-THEO"
    assert _parameter_value(parameters, "session_id") == "session-123"
    assert _parameter_value(parameters, "tool") == "initiate_return"
    assert _parameter_value(parameters, "caller") == "gateway"


def test_related_products_requires_a_named_source_and_verifies_any_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _load_server(monkeypatch)
    calls: list[tuple[str, list[dict[str, Any]]]] = []

    def _execute(
        sql: str,
        parameters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        calls.append((sql, parameters or []))
        if "LIMIT 2" in sql:
            return [
                {
                    "productId": "31",
                    "name": "Stoneware Pour-Over Set",
                    "brand": "Pellier",
                    "price": 138.0,
                    "embedding": "[0.1,0.2,0.3]",
                }
            ]
        return [
            {
                "productId": "36",
                "name": "Ceramic Tumblers",
                "brand": "Pellier",
                "color": "Bone",
                "price": 64.0,
                "rating": 4.9,
                "reviews": 18,
                "category": "Home",
                "imgUrl": "/products/ceramic-tumblers.png",
                "similarity_score": 0.91,
            }
        ]

    monkeypatch.setattr(server, "_execute_sql", _execute)

    result = server.get_related_products(
        source_product_name="pour-over set",
        product_id=31,
        limit=1,
    )

    assert result["source"]["productId"] == "31"
    assert result["matches"][0]["productId"] == "36"
    assert len(calls) == 2
    assert "source_product_name" in calls[0][0]
    assert _parameter_value(calls[0][1], "source_product_name") == "pour-over set"
    assert _parameter_value(calls[0][1], "source_product_pattern") == "%pour-over set%"

    mismatch = server.get_related_products(
        source_product_name="pour-over set",
        product_id=10,
    )
    assert mismatch["code"] == "source_product_mismatch"

    deployed_schema = server.TOOLS["get_related_products"]["inputSchema"]
    assert deployed_schema["required"] == ["source_product_name"]
    assert "product_id" in deployed_schema["properties"]

    from gateway_tool_schemas import TOOL_SCHEMAS

    managed_schema = next(
        tool["inputSchema"]
        for tool in TOOL_SCHEMAS["recommendation"]["tools"]
        if tool["name"] == "get_related_products"
    )
    assert managed_schema["required"] == ["source_product_name"]
    assert "product_id" in managed_schema["properties"]


def test_managed_related_products_escapes_like_metacharacters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _load_server(monkeypatch)
    captured: list[dict[str, Any]] = []

    def _execute(
        _sql: str,
        parameters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        captured.extend(parameters or [])
        return []

    monkeypatch.setattr(server, "_execute_sql", _execute)
    server.get_related_products(source_product_name=r"Studio_100% \ Edition")

    assert _parameter_value(captured, "source_product_pattern") == (
        r"%studio\_100\% \\ edition%"
    )


def test_get_trending_products_escapes_like_metacharacters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A category argument's own `%`/`_`/`\\` must not act as a LIKE wildcard.

    ``get_trending_products`` built its category predicate with a raw
    f-string while ``get_related_products`` in the same file used
    ``_prepare_like_pattern``; an untrusted ``%`` in the argument silently
    widened the filter to match every category instead of a literal
    substring.
    """
    server = _load_server(monkeypatch)
    captured: list[dict[str, Any]] = []

    def _execute(
        _sql: str,
        parameters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        captured.extend(parameters or [])
        return []

    monkeypatch.setattr(server, "_execute_sql", _execute)
    server.get_trending_products(category=r"Home_100% \ Decor")

    assert _parameter_value(captured, "category") == (
        server._prepare_like_pattern(r"Home_100% \ Decor")
    )
    assert _parameter_value(captured, "category") == r"%home\_100\% \\ decor%"
