"""Tests for the owner-scoped read tools in services.agent_tools.

``get_orders`` and ``get_tickets`` read one customer's rows. The customer is the
verified shopper bound for the turn; a ``customer_id`` in model tool input is only
a consistency check and never chooses whose records to read. Both reads run as
``pellier_agent`` with the verified username named (``fetch_all_as``), so
row-level security holds them to that shopper too.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from services import agent_tools


class FakeDB:
    def __init__(
        self,
        *,
        orders: list[dict[str, Any]] | None = None,
        tickets: list[dict[str, Any]] | None = None,
    ) -> None:
        self.orders = orders or []
        self.tickets = tickets or []
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.bound_as: list[str | None] = []

    async def fetch_all_as(self, username: str | None, query: str, *params: Any) -> list[dict[str, Any]]:
        self.bound_as.append(username)
        return await self.fetch_all(query, *params)

    async def fetch_all(self, query: str, *params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        if "pellier.orders" in query:
            return self.orders
        if "pellier.support_tickets" in query or "tickets" in query:
            return self.tickets
        return []


def _call(tool_obj, *args: Any, **kwargs: Any) -> dict[str, Any]:
    fn = getattr(tool_obj, "__wrapped__", tool_obj)
    return json.loads(fn(*args, **kwargs))


def _bind_verified_scope(customer_id: str, principal_sub: str):
    from services.turn_identity import (
        authorized_customer_id_var, principal_sub_var, principal_username_var,
    )

    return (
        authorized_customer_id_var.set(customer_id),
        principal_sub_var.set(principal_sub),
        principal_username_var.set(customer_id.replace("CUST-", "").lower()),
    )


def _reset_verified_scope(tokens) -> None:
    from services.turn_identity import (
        authorized_customer_id_var, principal_sub_var, principal_username_var,
    )

    customer_token, principal_token, username_token = tokens
    authorized_customer_id_var.reset(customer_token)
    principal_sub_var.reset(principal_token)
    principal_username_var.reset(username_token)


_ORDER_ROW = {
    "order_id": 5,
    "product_id": "11",
    "name": "Italian Linen Camp Shirt",
    "brand": "Pellier",
    "category": "Clothing",
    "quantity": 1,
    "amount_paid_cents": 22800,
    "placed_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
}
_TICKET_ROW = {
    "ticket_id": "T-1",
    "subject": "Chipped mug",
    "status": "open",
    "channel": "chat",
    "last_note": "Photo received.",
    "opened_at": datetime(2026, 7, 2, tzinfo=timezone.utc),
    "resolved_at": None,
}


def test_get_orders_reads_the_verified_shoppers_orders() -> None:
    db = FakeDB(orders=[_ORDER_ROW])
    agent_tools.set_db_service(db)

    tokens = _bind_verified_scope("CUST-MARCO", "sub-marco")
    try:
        payload = _call(agent_tools.get_orders, customer_id="CUST-MARCO")
    finally:
        _reset_verified_scope(tokens)

    assert payload["status"] == "success"
    assert payload["customer_id"] == "CUST-MARCO"
    assert payload["orders"][0]["name"] == "Italian Linen Camp Shirt"
    assert payload["orders"][0]["amount_paid"] == 228.0
    assert db.calls[-1][1][0] == "CUST-MARCO"
    assert db.bound_as == ["marco"], "the read runs as pellier_agent with marco named"


def test_get_tickets_reads_the_verified_shoppers_tickets() -> None:
    db = FakeDB(tickets=[_TICKET_ROW])
    agent_tools.set_db_service(db)

    tokens = _bind_verified_scope("CUST-THEO", "sub-theo")
    try:
        payload = _call(agent_tools.get_tickets)
    finally:
        _reset_verified_scope(tokens)

    assert payload["status"] == "success"
    assert payload["customer_id"] == "CUST-THEO"
    assert payload["open_count"] == 1
    assert payload["tickets"][0]["subject"] == "Chipped mug"
    assert db.calls[-1][1][0] == "CUST-THEO"
    assert db.bound_as == ["theo"], "the read runs as pellier_agent with theo named"


@pytest.mark.parametrize("tool_name", ["get_orders", "get_tickets"])
def test_owner_reads_fail_closed_without_scope_or_on_mismatch(tool_name: str) -> None:
    db = FakeDB(orders=[_ORDER_ROW], tickets=[_TICKET_ROW])
    agent_tools.set_db_service(db)
    tool_obj = getattr(agent_tools, tool_name)

    anonymous = _call(tool_obj, customer_id="CUST-THEO")
    assert anonymous["status"] == "customer_scope_required"
    assert db.calls == []

    tokens = _bind_verified_scope("CUST-MARCO", "sub-marco")
    try:
        mismatch = _call(tool_obj, customer_id="CUST-THEO")
    finally:
        _reset_verified_scope(tokens)
    assert mismatch["status"] == "customer_scope_mismatch"
    assert db.calls == []
