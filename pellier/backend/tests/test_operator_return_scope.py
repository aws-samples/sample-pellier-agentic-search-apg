"""Ticket return claims against return records: two facts, kept apart.

Lab 4's identity matrix (`scripts/prove_identity_boundary.py`) targets
CUST-JESSICA and, on its ALLOW case, writes a real `pellier.returns` row for
the lowest-id product she can return. The Operator service-recovery walkthrough
is built on her ticket asserting returns the authoritative table does not carry.

An unscoped `asserts_return and not returns` let any return row -- including
Lab 4's, on an unrelated product -- erase the human checkpoint. Scoping by
product fixed that collision. A second truth sits beside it: a return row is a
REQUEST. Pellier records no parcel arriving, so no row can confirm a ticket's
claim that goods were received. Which pieces lack a record is one fact; whether
the goods arrived is another, and it stays unverified.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routes.operator import _return_evidence, _ticket_named_product_ids  # noqa: E402

# The seeded Jessica case: migration 019 logs a return for the catchall and the
# robe; migration 018 gives her five orders.
JESSICA_TICKETS: List[Dict[str, Any]] = [
    {
        "ticketId": "TKT-2026-3015",
        "subject": "Return received, refund amount disputed",
        "lastNote": (
            "Return logged for the catchall and the robe. Client expected a "
            "full refund including original shipping."
        ),
        "status": "pending",
    }
]

JESSICA_ORDERS: List[Dict[str, Any]] = [
    {"productId": "P-001", "productName": "Leather Catchall Tray"},
    {"productId": "P-002", "productName": "Waffle Cotton Robe"},
    {"productId": "P-003", "productName": "Stoneware Pour-Over Set"},
    {"productId": "P-004", "productName": "Quilted Down Vest"},
    {"productId": "P-005", "productName": "Merino Crew Sweater"},
]


def _evidence(returns: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _return_evidence(JESSICA_TICKETS, JESSICA_ORDERS, returns)


class TestTicketScoping:
    def test_the_ticket_names_only_the_products_it_mentions(self) -> None:
        named = _ticket_named_product_ids(JESSICA_TICKETS, JESSICA_ORDERS)
        assert named == {"P-001", "P-002"}

    def test_resolved_tickets_do_not_name_products(self) -> None:
        """A closed ticket is history, not an open dispute."""
        closed = [dict(JESSICA_TICKETS[0], status="resolved")]
        assert _ticket_named_product_ids(closed, JESSICA_ORDERS) == set()

    def test_short_and_generic_tokens_do_not_match(self) -> None:
        """Matching on 'bath' or 'set' would pull in the whole catalog."""
        tickets = [
            {"subject": "Bath set query", "lastNote": "", "status": "open"}
        ]
        orders = [
            {"productId": "P-100", "productName": "Pellier Luxury Bath Set"},
            {"productId": "P-101", "productName": "Sage Bath Towel"},
        ]
        assert _ticket_named_product_ids(tickets, orders) == set()


class TestCollisionWithLabFour:
    def test_the_checkpoint_stands_at_baseline(self) -> None:
        assert _evidence([])["unconfirmedReturnAssertion"] is True

    def test_lab_four_return_on_an_unrelated_product_does_not_erase_it(self) -> None:
        """The regression this file exists for.

        Lab 4 writes a return for the lowest-id product Jessica owns. Under the
        old unscoped predicate this emptied the Operator checkpoint.
        """
        lab_four_row = {"productId": "P-003", "productName": "Stoneware Pour-Over Set"}
        assert _evidence([lab_four_row])["unconfirmedReturnAssertion"] is True

    def test_one_named_product_does_not_answer_for_the_other(self) -> None:
        """Recording the catchall says nothing about the robe the ticket also names."""
        catchall_row = {"productId": "P-001", "productName": "Leather Catchall Tray"}
        evidence = _evidence([catchall_row])
        assert evidence["unconfirmedReturnAssertion"] is True
        assert evidence["unrecordedDisputedProductIds"] == ["P-002"]

    def test_recorded_requests_do_not_confirm_receipt(self) -> None:
        """Every named piece recorded: no record gap, but receipt is still unverified."""
        rows = [
            {"productId": "P-001", "productName": "Leather Catchall Tray"},
            {"productId": "P-002", "productName": "Waffle Cotton Robe"},
        ]
        evidence = _evidence(rows)
        assert evidence["unrecordedDisputedProductIds"] == []
        assert evidence["unconfirmedReturnAssertion"] is True

    def test_several_unrelated_returns_still_do_not_resolve_it(self) -> None:
        rows = [
            {"productId": "P-003", "productName": "Stoneware Pour-Over Set"},
            {"productId": "P-004", "productName": "Quilted Down Vest"},
            {"productId": "P-005", "productName": "Merino Crew Sweater"},
        ]
        assert _evidence(rows)["unconfirmedReturnAssertion"] is True

    def test_the_surface_can_name_what_is_disputed(self) -> None:
        assert _evidence([])["disputedProductIds"] == ["P-001", "P-002"]


class TestFailureDirection:
    def test_an_unmatchable_ticket_names_no_record_gap(self) -> None:
        """Narrowing to an empty set must not claim any piece lacks a record.

        When the ticket names no recognisable product the scope is unknown. The
        receipt claim stays unconfirmed either way; no return row confirms it.
        """
        tickets = [
            {"subject": "Return question", "lastNote": "No item named.", "status": "open"}
        ]
        orders = JESSICA_ORDERS
        assert _ticket_named_product_ids(tickets, orders) == set()

        evidence = _return_evidence(tickets, orders, [{"productId": "P-003"}])
        assert evidence["unrecordedDisputedProductIds"] == []
        assert evidence["unconfirmedReturnAssertion"] is True

    def test_a_ticket_without_a_return_claim_asserts_nothing(self) -> None:
        tickets = [{"subject": "Delivery rescheduled", "lastNote": "", "status": "open"}]
        evidence = _return_evidence(tickets, JESSICA_ORDERS, [])
        assert evidence["unconfirmedReturnAssertion"] is False
