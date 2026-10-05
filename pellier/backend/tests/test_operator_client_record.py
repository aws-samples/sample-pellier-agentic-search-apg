"""The client list and the client record: what staff read before anything is proposed.

Two promises are kept here, on fakes; ``test_operator_credit_postgres.py``
proves the same reads against the real schema.

* Returned means the item came back. The order row carries its own return
  state: ``received`` or ``refunded`` marks it Returned; a ``requested`` return
  is a claim, not evidence of receipt.
* A partial record is not a record. If any of the concurrent reads fails, the
  route answers 503 instead of rendering a failed read as "nothing on file".
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi import HTTPException

from routes import operator as OP
from services import store_tools


@pytest.mark.parametrize(
    ("status", "returned"),
    [("received", True), ("refunded", True), ("requested", False), (None, False), ("", False)],
)
def test_only_a_received_return_marks_an_order_returned(status: Any, returned: bool) -> None:
    assert store_tools.is_returned(status) is returned
    row = {"order_id": 301, "product_id": "42", "product_name": "Waffle Bath Robe, Sage",
           "amount_paid_cents": 6400, "quantity": 1, "return_status": status,
           "store_credit_id": None}
    order = OP._order_row(row)
    assert order["returned"] is returned
    assert order["returnStatus"] == (status or None)
    assert order["creditId"] is None


def test_an_order_names_the_credit_that_covers_it() -> None:
    order = OP._order_row({"order_id": 20, "product_id": "42", "return_status": "received",
                           "store_credit_id": 3, "amount_paid_cents": 6400})
    assert order["returned"] is True and order["creditId"] == 3


def test_every_surface_reads_return_state_from_the_order_row() -> None:
    """The record, get_orders and the Planner cannot disagree about "returned"."""
    from services import operator_graph

    for sql in (OP._ORDERS_SELECT, store_tools._ORDERS_SQL, operator_graph._RETURNED_ORDERS_SQL):
        assert "o.return_status" in sql and "pellier.returns" not in sql


def test_a_client_row_carries_open_requests_and_the_last_order() -> None:
    client = OP._client_row({
        "customer_id": "CUST-JESSICA", "name": "Jessica Nakamura", "open_requests": 1,
        "open_request": "Two items went back, no credit yet", "open_request_status": "open",
        "last_order_name": "Oat Merino Crew", "last_order_at": None,
    })
    assert client == {
        "customerId": "CUST-JESSICA", "slug": "jessica", "name": "Jessica Nakamura",
        "personaId": "jessica", "openRequests": 1,
        "openRequest": "Two items went back, no credit yet", "openRequestStatus": "open",
        "lastOrder": {"productName": "Oat Merino Crew", "placedAt": None},
    }


class _Db:
    """Jessica's record, with one read made to fail."""

    def __init__(self, failing: str) -> None:
        self.failing = failing

    async def fetch_one(self, sql: str, *_args: Any) -> Dict[str, Any]:
        if self.failing in sql:
            raise RuntimeError(f"{self.failing} unavailable")
        return {"customer_id": "CUST-JESSICA", "name": "Jessica Nakamura"}

    async def fetch_all(self, sql: str, *_args: Any) -> List[Dict[str, Any]]:
        if self.failing in sql:
            raise RuntimeError(f"{self.failing} unavailable")
        return []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failing",
    ["pellier.support_tickets", "pellier.orders", "pellier.store_credits", "pellier.approvals",
     "FROM pellier.customers c"],
)
async def test_a_partial_record_is_a_503_never_an_empty_history(failing: str) -> None:
    """A failed tickets read rendered as [] would read as "no open request"."""
    with pytest.raises(HTTPException) as raised:
        await OP.get_client("CUST-JESSICA", db=_Db(failing))
    assert raised.value.status_code == 503
    assert "No absence claim was made" in str(raised.value.detail)


@pytest.mark.asyncio
async def test_an_unreadable_clients_list_is_a_503_not_an_empty_book() -> None:
    with pytest.raises(HTTPException) as raised:
        await OP.list_clients(db=_Db("pellier.customers"))
    assert raised.value.status_code == 503
