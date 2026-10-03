"""Tests for read-only proof/memory tools in services.agent_tools."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from services import agent_tools


class FakeDB:
    def __init__(
        self,
        *,
        customer: dict[str, Any] | None = None,
        orders: list[dict[str, Any]] | None = None,
        facts: list[dict[str, Any]] | None = None,
        receipts: list[dict[str, Any]] | None = None,
        governed_receipts: list[dict[str, Any]] | None = None,
    ) -> None:
        self.customer = customer
        self.orders = orders or []
        self.facts = facts or []
        self.receipts = receipts or []
        self.governed_receipts = governed_receipts or []
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch_one(self, query: str, *params: Any) -> dict[str, Any] | None:
        self.calls.append((query, params))
        if "FROM pellier.customers" in query:
            return self.customer
        return None

    async def fetch_all(self, query: str, *params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        if "FROM pellier.orders" in query:
            return self.orders
        if "FROM pellier.customer_episodic_seed" in query:
            return self.facts
        if "FROM pellier.tool_audit" in query:
            return self.receipts
        if "FROM pellier.governed_receipts" in query:
            return self.governed_receipts
        return []


def _call(tool_obj, *args: Any, **kwargs: Any) -> dict[str, Any]:
    fn = getattr(tool_obj, "__wrapped__", tool_obj)
    return json.loads(fn(*args, **kwargs))


def _bind_verified_scope(customer_id: str, principal_sub: str):
    from services.turn_identity import authorized_customer_id_var, principal_sub_var

    return (
        authorized_customer_id_var.set(customer_id),
        principal_sub_var.set(principal_sub),
    )


def _reset_verified_scope(tokens) -> None:
    from services.turn_identity import authorized_customer_id_var, principal_sub_var

    customer_token, principal_token = tokens
    authorized_customer_id_var.reset(customer_token)
    principal_sub_var.reset(principal_token)


def test_get_customer_preferences_reads_safe_customer_memory() -> None:
    db = FakeDB(
        customer={
            "id": "CUST-MARCO",
            "name": "Marco",
            "preferences_summary": "Natural fibers and warm neutrals.",
        },
        orders=[
            {
                "product_id": "11",
                "name": "Italian Linen Camp Shirt",
                "brand": "Pellier",
                "category": "Clothing",
                "color": "Indigo",
                "price": 228,
                "quantity": 1,
                "placed_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
            }
        ],
        facts=[
            {
                "summary_text": "Asked about wrinkle-resistance.",
                "ts_offset_days": -9,
            }
        ],
    )
    agent_tools.set_db_service(db)

    tokens = _bind_verified_scope("CUST-MARCO", "sub-marco")
    try:
        payload = _call(agent_tools.get_customer_preferences, customer_id="CUST-MARCO")
    finally:
        _reset_verified_scope(tokens)

    assert payload["status"] == "success"
    assert payload["read_only"] is True
    assert payload["customer"]["id"] == "CUST-MARCO"
    assert payload["recent_orders"][0]["name"] == "Italian Linen Camp Shirt"
    assert payload["memory_facts"][0]["summary"] == "Asked about wrinkle-resistance."
    assert payload["sources"] == [
        "pellier.customers",
        "pellier.orders",
        "pellier.customer_episodic_seed",
    ]


def test_customer_preference_reads_fail_closed_without_scope_or_on_mismatch() -> None:
    db = FakeDB(customer={"id": "CUST-MARCO"})
    agent_tools.set_db_service(db)

    anonymous = _call(
        agent_tools.get_customer_preferences, customer_id="CUST-THEO"
    )
    assert anonymous["status"] == "customer_scope_required"
    assert db.calls == []

    tokens = _bind_verified_scope("CUST-MARCO", "sub-marco")
    try:
        mismatch = _call(
            agent_tools.get_customer_preferences, customer_id="CUST-THEO"
        )
    finally:
        _reset_verified_scope(tokens)
    assert mismatch["status"] == "customer_scope_mismatch"
    assert db.calls == []


def test_get_audit_trail_returns_allow_receipts_with_result_summary() -> None:
    db = FakeDB(
        receipts=[
            {
                "audit_id": 158,
                "session_id": "persona-theo-abc",
                "tool": "initiate_return",
                "caller": "gateway",
                "args": {"customer_id": "CUST-THEO", "reason": "damaged"},
                "result": {"status": "success", "return_id": 77},
                "latency_ms": 184,
                "created_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
            }
        ]
    )
    agent_tools.set_db_service(db)

    tokens = _bind_verified_scope("CUST-THEO", "sub-theo")
    try:
        payload = _call(
            agent_tools.get_audit_trail,
            tool_name="initiate_return",
            caller="gateway",
        )
    finally:
        _reset_verified_scope(tokens)

    assert payload["status"] == "success"
    assert payload["read_only"] is True
    receipt = payload["receipts"][0]
    assert receipt["decision"] == "ALLOW"
    assert receipt["tool"] == "initiate_return"
    assert receipt["caller"] == "gateway"
    assert receipt["result_summary"]["status"] == "success"
    assert receipt["created_at"] == "2026-07-01T00:00:00+00:00"

    sql, params = db.calls[-1]
    assert "gr.args->>'customer_id' = %s" in sql
    assert "gr.verified_subject = %s" in sql
    assert "gr.tool = %s" in sql
    assert "gr.caller = %s" in sql
    assert params == ("CUST-THEO", "sub-theo", "initiate_return", "gateway", 3)


def test_get_audit_trail_no_rows_reports_no_allow_boundary() -> None:
    db = FakeDB(receipts=[])
    agent_tools.set_db_service(db)

    tokens = _bind_verified_scope("CUST-MARCO", "sub-marco")
    try:
        payload = _call(
            agent_tools.get_audit_trail,
            session_id="persona-marco-none",
            tool_name="check_inventory",
        )
    finally:
        _reset_verified_scope(tokens)

    assert payload["status"] == "no_allow_receipt"
    assert payload["read_only"] is True
    assert payload["filters"] == {
        "session_id": "persona-marco-none",
        "tool_name": "check_inventory",
        "caller": None,
    }
    assert "no-row" in payload["interpretation"]


def test_audit_reads_require_the_verified_customer_scope_before_querying() -> None:
    db = FakeDB()
    agent_tools.set_db_service(db)

    payload = _call(agent_tools.get_audit_trail, tool_name="initiate_return")

    assert payload["status"] == "customer_scope_required"
    assert db.calls == []


def test_governed_receipt_output_redacts_identity_diagnostics() -> None:
    db = FakeDB(
        governed_receipts=[
            {
                "receipt_id": 9,
                "audit_id": 8,
                "session_id": "session-theo",
                "tool": "initiate_return",
                "caller": "gateway",
                "decision": "ALLOW",
                "args": {"customer_id": "CUST-THEO"},
                "policy_name": "identity_scope",
                "principal_id": "CUST-THEO",
                "token_fingerprint_sha256": "secret-diagnostic",
                "verified_subject": "sub-theo",
            }
        ]
    )
    agent_tools.set_db_service(db)

    tokens = _bind_verified_scope("CUST-THEO", "sub-theo")
    try:
        payload = _call(agent_tools.get_audit_trail)
    finally:
        _reset_verified_scope(tokens)

    receipt = payload["governed_receipts"][0]
    assert receipt["receipt_id"] == 9
    for sensitive_key in (
        "principal_id",
        "principal_label",
        "token_fingerprint_sha256",
        "verified_subject",
        "verified_username",
        "issuer",
        "client_id",
        "identity_source",
    ):
        assert sensitive_key not in receipt
