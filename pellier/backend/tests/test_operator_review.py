"""The durable operator review: the queue, the record, and the human decision.

Written around one question: can a confirmation ever be mistaken for an
authorization? A confirmed review must leave Policy PENDING, Aurora
NOT_EVALUATED, and every business table untouched. The review opener itself
lives in ``store_tools.open_credit_review`` and is covered with the handoff
tests; here the rows exist and a person reads and decides them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routes import operator as operator_module  # noqa: E402
from services import operator_review as rv  # noqa: E402
from services.store_tools import write_request_hash  # noqa: E402

JESSICA = {"customer_id": "CUST-JESSICA", "amount_cents": 10000, "reason": "Two items went back."}
JESSICA_HASH = write_request_hash("give_store_credit", **JESSICA)


class FakeReviewDb:
    """Records every statement so the tests can assert what was NOT written."""

    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None) -> None:
        self.rows: List[Dict[str, Any]] = list(rows or [])
        self.statements: List[str] = []
        self._next_id = max((r["review_id"] for r in self.rows), default=0) + 1

    def _find(self, review_id: int) -> Optional[Dict[str, Any]]:
        return next((r for r in self.rows if r["review_id"] == int(review_id)), None)

    def add_pending(self, **overrides: Any) -> Dict[str, Any]:
        row = {
            "review_id": self._next_id,
            "customer_id": JESSICA["customer_id"],
            "customer_name": "Jessica Nakamura",
            "action": "give_store_credit",
            "args": dict(JESSICA),
            "status": "pending",
            "source_turn_id": "turn-investigation-1",
            "execution_turn_id": None,
            "order_ids": [301, 302],
            "answered_turn_id": None,
            "answered_by_review_id": None,
            "issue": "Two items went back.",
            "recommendation": {"primaryAction": "give_store_credit",
                               "rationale": "Two items went back."},
            "action_hash": JESSICA_HASH,
            "decided_by": None,
            "decided_by_name": None,
            "requested_by_sub": "sub-nadia",
            "requester_kind": "operator",
            "requested_at": None,
            "decided_at": None,
        }
        row.update(overrides)
        self.rows.append(row)
        self._next_id += 1
        return row

    async def fetch_one(self, query: str, *params: Any) -> Optional[Dict[str, Any]]:
        self.statements.append(query)
        if query.strip().startswith("UPDATE pellier.approvals"):
            status, decider, decider_name, review_id = params
            row = self._find(review_id)
            if not row or row["status"] != "pending":
                return None
            row.update(status=status, decided_by=decider, decided_by_name=decider_name,
                       decided_at="2026-10-04T00:00:00Z")
            return {"id": row["review_id"], "status": status, "decided_by": decider,
                    "decided_by_name": decider_name, "decided_at": row["decided_at"],
                    "action_hash": row["action_hash"]}
        if "WHERE a.id = %s" in query:
            row = self._find(params[0])
            return dict(row) if row else None
        if "FROM pellier.customers c" in query:
            return {"id": "CUST-JESSICA", "name": "Jessica Nakamura"}
        return None

    async def fetch_all(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        self.statements.append(query)
        if "FROM pellier.approvals a" in query and "a.customer_id = %s" in query:
            return [dict(r) for r in self.rows
                    if r["customer_id"] == params[0] and r["action"] == params[1]]
        if "FROM pellier.approvals a" in query:
            tool, status = params[0], params[1]
            rows = [dict(r) for r in self.rows if r["action"] == tool]
            if status:
                rows = [r for r in rows if r["status"] == status]
            rows.sort(key=lambda r: 0 if r["status"] in ("pending", "open") else 1)
            return rows
        if "FROM pellier.orders o" in query:
            wanted = set(int(v) for v in params[1])
            return [
                {"order_id": 301, "product_id": "42", "quantity": 1, "placed_at": None, "price_paid": 64.0,
                 "product_name": "Waffle Bath Robe, Sage", "brand": "NestWell", "current_price": 64.0,
                 "image_url": "/products/house-waffle-bath-robe-sage.png"},
                {"order_id": 302, "product_id": "25", "quantity": 1, "placed_at": None, "price_paid": 36.0,
                 "product_name": "Reed Diffuser", "brand": "Pellier", "current_price": 36.0,
                 "image_url": "/products/anna-reed-diffuser.png"},
            ][: len(wanted)]
        return []

    def wrote_to(self, *tables: str) -> bool:
        for sql in self.statements:
            head = sql.strip().upper()
            if not head.startswith(("INSERT", "UPDATE", "DELETE", "SELECT PELLIER.")):
                continue
            if any(table.lower() in sql.lower() for table in tables):
                return True
        return False


NADIA: Dict[str, Any] = {"sub": "sub-nadia", "username": "nadia", "groups": ("pellier-operators",)}


def build_client(db: FakeReviewDb, operator: Optional[Dict[str, Any]] = None) -> TestClient:
    app = FastAPI()
    app.include_router(operator_module.router)
    app.dependency_overrides[operator_module.get_db_service] = lambda: db
    app.dependency_overrides[operator_module.require_operator] = lambda: operator or NADIA
    return TestClient(app)


def build_anonymous_client(db: FakeReviewDb) -> TestClient:
    """No auth override: the real dependency runs and must refuse."""
    app = FastAPI()
    app.include_router(operator_module.router)
    app.dependency_overrides[operator_module.get_db_service] = lambda: db
    return TestClient(app)


# ---------------------------------------------------------------------------
# Parameter binding
# ---------------------------------------------------------------------------


def test_only_the_credit_is_reviewable() -> None:
    assert rv.REVIEWABLE_ACTIONS == ("give_store_credit",)
    with pytest.raises(rv.ReviewError) as caught:
        rv.action_fingerprint("initiate_return", {"customer_id": "x"})
    assert caught.value.code == "action_not_reviewable"


def test_the_confirmation_fingerprint_is_the_write_path_hash() -> None:
    assert rv.action_fingerprint("give_store_credit", JESSICA) == JESSICA_HASH
    assert rv.action_fingerprint("give_store_credit", {**JESSICA, "amount_cents": "10000"}) == JESSICA_HASH


def test_the_credit_amount_customer_and_reason_are_material() -> None:
    for change in ({"amount_cents": 10001}, {"customer_id": "CUST-THEO"}, {"reason": "Other."}):
        assert rv.action_fingerprint("give_store_credit", {**JESSICA, **change}) != JESSICA_HASH


def test_a_missing_or_malformed_material_parameter_is_refused() -> None:
    with pytest.raises(rv.ReviewError) as missing:
        rv.action_fingerprint("give_store_credit", {"customer_id": "CUST-JESSICA", "reason": "x"})
    assert missing.value.code == "missing_parameter:amount_cents"
    with pytest.raises(rv.ReviewError) as invalid:
        rv.action_fingerprint("give_store_credit", {**JESSICA, "amount_cents": "ten"})
    assert invalid.value.code == "invalid_parameter:amount_cents"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_the_pending_review_appears_in_the_queue_first() -> None:
    db = FakeReviewDb()
    db.add_pending(status="approved", decided_by="sub-nadia")
    pending = db.add_pending()
    body = build_client(db).get("/api/operator/reviews").json()
    assert body["pendingCount"] == 1 and body["total"] == 2
    assert body["reviews"][0]["reviewId"] == pending["review_id"]
    assert body["reviews"][0]["humanState"] == "confirmation_required"
    assert body["reviews"][0]["amount"] == "100.00" and body["reviews"][0]["amountCents"] == 10000
    assert body["reviews"][0]["requesterKind"] == "operator"


def _request(db: FakeReviewDb, **overrides: Any) -> Dict[str, Any]:
    """Jessica's chat request for a store credit: no amount, no fingerprint."""
    fields: Dict[str, Any] = {
        "action": "store_credit_request", "args": {}, "action_hash": None, "order_ids": [],
        "status": "open", "recommendation": None,
        "issue": "Jessica asks for a store credit for two returns.",
        "requested_by_sub": "sub-jessica", "requester_kind": "shopper",
    }
    return db.add_pending(**{**fields, **overrides})


def test_the_queue_lists_a_credit_request_beside_the_reviews_with_no_amount() -> None:
    db = FakeReviewDb()
    pending = db.add_pending()
    request = _request(db)
    body = build_client(db).get("/api/operator/reviews").json()
    assert [r["reviewId"] for r in body["reviews"]] == [pending["review_id"]]
    assert body["total"] == 1 and body["pendingCount"] == 1 and body["openRequestCount"] == 1
    (shown,) = body["requests"]
    assert shown["requestId"] == request["review_id"] and shown["status"] == "open"
    assert shown["requesterKind"] == "shopper" and shown["answeredByReviewId"] is None
    assert not any("amount" in key.lower() for key in shown), shown


def test_an_answered_request_names_the_review_that_answered_it() -> None:
    db = FakeReviewDb()
    _request(db, status="answered", answered_turn_id="turn-" + "c" * 32, answered_by_review_id=7)
    body = build_client(db).get("/api/operator/reviews").json()
    assert body["openRequestCount"] == 0
    assert body["requests"][0]["status"] == "answered"
    assert body["requests"][0]["answeredByReviewId"] == 7


def test_a_credit_request_cannot_be_approved_declined_executed_or_opened_as_a_review() -> None:
    db = FakeReviewDb()
    request = _request(db)
    client = build_client(db)
    request_id = request["review_id"]
    for decision, body in (("confirm", {"actionHash": "a" * 64}), ("decline", None)):
        response = client.post(f"/api/operator/reviews/{request_id}/{decision}", json=body)
        assert response.status_code == 409 and response.json()["detail"] == "request_not_approvable"
    response = client.post(f"/api/operator/reviews/{request_id}/execute", json={})
    assert response.status_code == 409 and response.json()["detail"] == "request_not_approvable"
    assert client.get(f"/api/operator/reviews/{request_id}").status_code == 404
    assert db._find(request_id)["status"] == "open"
    assert not any(s.strip().startswith("UPDATE") for s in db.statements)


def test_the_lab4_probe_review_is_never_executed_from_the_desk(monkeypatch) -> None:
    """The check confirms its own probe; no person approved a credit, so Execute refuses it."""
    from services import governed_execution as ge

    async def must_not_run(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the probe review reached execution")

    monkeypatch.setattr(ge, "execute_confirmed_review", must_not_run)
    db = FakeReviewDb()
    probe = db.add_pending(issue=rv.POLICY_CHECK_PROBE_ISSUE, status="approved",
                           decided_by_name=rv.POLICY_CHECK_DECIDER)
    response = build_client(db).post(f"/api/operator/reviews/{probe['review_id']}/execute", json={})
    assert response.status_code == 409 and response.json()["detail"] == "probe_not_executable"


def test_the_queue_refuses_an_anonymous_read() -> None:
    db = FakeReviewDb()
    db.add_pending()
    response = build_anonymous_client(db).get("/api/operator/reviews")
    assert response.status_code == 401
    assert not any("FROM pellier.approvals" in s for s in db.statements)


def test_an_unknown_review_is_a_404_not_an_empty_page() -> None:
    assert build_client(FakeReviewDb()).get("/api/operator/reviews/99").status_code == 404


def test_the_record_hydrates_the_client_and_the_referenced_orders() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    body = build_client(db).get(f"/api/operator/reviews/{row['review_id']}").json()
    assert body["client"] == {"customerId": "CUST-JESSICA", "name": "Jessica Nakamura",
                              "slug": "jessica", "personaId": "jessica"}
    assert [o["orderId"] for o in body["orders"]] == [301, 302]
    assert body["orders"][0]["amountPaid"] == "64.00"
    assert body["review"]["orderIds"] == [301, 302]
    assert body["record"] is None, "no execution has been attempted"
    assert body["review"]["assurance"] == {
        "human": "CONFIRMATION_REQUIRED", "policy": "PENDING",
        "aurora": "NOT_EVALUATED", "evidence": "PENDING",
    }


def test_the_review_row_stores_no_business_truth() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    assert "product_name" not in row and "price" not in row and "membership" not in row
    assert rv.referenced_order_ids(row) == [301, 302]


def test_the_clients_credit_reviews_ride_with_the_record() -> None:
    db = FakeReviewDb()
    db.add_pending()
    rows = __import__("asyncio").run(rv.list_reviews_for_customer(db, "CUST-JESSICA"))
    assert [r["customer_id"] for r in rows] == ["CUST-JESSICA"]
    rows = __import__("asyncio").run(rv.list_reviews_for_customer(db, "CUST-THEO"))
    assert rows == []


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


def test_the_exact_proposed_credit_can_be_confirmed() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    response = build_client(db).post(
        f"/api/operator/reviews/{row['review_id']}/confirm", json={"actionHash": JESSICA_HASH},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["humanState"] == "confirmed" and body["decidedBy"] == "sub-nadia"
    assert body["decidedByName"] == "nadia"
    assert body["assurance"] == {"human": "CONFIRMED", "policy": "PENDING",
                                 "aurora": "NOT_EVALUATED", "evidence": "PENDING"}


def test_the_record_names_the_recorded_decider_to_every_reader() -> None:
    """"Approved by" is the review's own fact, not a match against the reader's token."""
    db = FakeReviewDb()
    row = db.add_pending()
    path = f"/api/operator/reviews/{row['review_id']}"
    build_client(db).post(f"{path}/confirm", json={"actionHash": JESSICA_HASH})
    other_staff = {"sub": "sub-other", "username": "other", "groups": ("pellier-operators",)}
    review = build_client(db, other_staff).get(path).json()["review"]
    assert review["decidedBy"] == "sub-nadia" and review["decidedByName"] == "nadia"


def test_a_changed_material_parameter_invalidates_a_prior_confirmation() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    stale = write_request_hash("give_store_credit", **{**JESSICA, "amount_cents": 9900})
    response = build_client(db).post(
        f"/api/operator/reviews/{row['review_id']}/confirm", json={"actionHash": stale},
    )
    assert response.status_code == 409 and response.json()["detail"] == "parameters_changed"
    assert db._find(row["review_id"])["status"] == "pending"


def test_confirming_without_a_fingerprint_is_refused() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    response = build_client(db).post(f"/api/operator/reviews/{row['review_id']}/confirm", json={})
    assert response.status_code == 422


def test_a_review_cannot_be_decided_twice() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    client = build_client(db)
    first = client.post(f"/api/operator/reviews/{row['review_id']}/confirm", json={"actionHash": JESSICA_HASH})
    second = client.post(f"/api/operator/reviews/{row['review_id']}/decline")
    assert first.status_code == 200 and second.status_code == 409
    assert second.json()["detail"] == "review_already_decided"


def test_declining_closes_the_review_and_needs_no_fingerprint() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    response = build_client(db).post(f"/api/operator/reviews/{row['review_id']}/decline")
    assert response.status_code == 200
    assert response.json()["assurance"] == {"human": "DECLINED", "policy": "NOT_EVALUATED",
                                            "aurora": "NOT_REACHED", "evidence": "NO_EXECUTION"}
    assert db._find(row["review_id"])["status"] == "rejected"


def test_confirmation_performs_no_business_mutation() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    build_client(db).post(f"/api/operator/reviews/{row['review_id']}/confirm", json={"actionHash": JESSICA_HASH})
    assert not db.wrote_to("store_credits", "tool_audit", "apply_store_credit")


@pytest.mark.asyncio
async def test_stored_parameters_that_disagree_with_the_hash_are_refused() -> None:
    db = FakeReviewDb()
    row = db.add_pending(args={**JESSICA, "amount_cents": 12345})  # hash still Jessica's
    with pytest.raises(rv.ReviewError) as caught:
        await rv.decide_review(db, review_id=row["review_id"], decision=rv.STATUS_CONFIRMED,
                               decided_by="sub-nadia", action_hash=JESSICA_HASH)
    assert caught.value.code == "stored_parameters_invalid"


def test_an_empty_decider_cannot_decide() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    response = build_client(db, operator={"sub": "", "groups": ("pellier-operators",)}).post(
        f"/api/operator/reviews/{row['review_id']}/confirm", json={"actionHash": JESSICA_HASH},
    )
    assert response.status_code == 401 and response.json()["detail"] == "decider_required"


def test_an_anonymous_caller_cannot_confirm_a_review() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    response = build_anonymous_client(db).post(
        f"/api/operator/reviews/{row['review_id']}/confirm", json={"actionHash": JESSICA_HASH},
    )
    assert response.status_code == 401
    assert db._find(row["review_id"])["status"] == "pending"


def test_every_desk_route_is_gated_by_the_routers_dependency() -> None:
    from services.auth import require_operator

    assert operator_module.router.routes
    for route in operator_module.router.routes:
        assert any(dep.call is require_operator for dep in route.dependant.dependencies), route.path


# ---------------------------------------------------------------------------
# The four axes
# ---------------------------------------------------------------------------


def test_no_human_state_ever_reports_an_allow_or_a_permitted() -> None:
    for state, axes in operator_module._ASSURANCE_BY_HUMAN_STATE.items():
        assert axes["policy"] not in ("ALLOW", "DENY"), state
        assert axes["aurora"] != "PERMITTED", state
        assert axes["evidence"] != "RECEIPTED", state


def test_the_review_payload_reads_arguments_stored_as_text() -> None:
    payload = operator_module._review_payload({
        "review_id": 5, "customer_id": "CUST-JESSICA", "action": "give_store_credit",
        "args": json.dumps(JESSICA), "status": "approved", "action_hash": JESSICA_HASH,
        "recommendation": json.dumps({"rationale": "Went back."}), "order_ids": "{301}",
    })
    assert payload["amountCents"] == 10000 and payload["reason"] == "Two items went back."
    assert payload["orderIds"] == [301]
    assert payload["humanState"] == "confirmed"
    assert payload["policyCheckProbe"] is False


def test_the_lab4_probe_review_is_flagged_so_the_desk_names_its_real_origin() -> None:
    """The Lab 4 check opens and confirms its own over-limit review: no person asked or approved."""
    from services import operator_review as rv

    payload = operator_module._review_payload({
        "review_id": 6, "customer_id": "CUST-JESSICA", "action": "give_store_credit",
        "args": json.dumps(JESSICA), "status": "approved", "action_hash": JESSICA_HASH,
        "issue": rv.POLICY_CHECK_PROBE_ISSUE, "order_ids": "{}", "requester_kind": "operator",
        "decided_by": rv.POLICY_CHECK_DECIDER, "decided_by_name": rv.POLICY_CHECK_DECIDER,
    })
    assert payload["policyCheckProbe"] is True
    assert payload["decidedByName"] == "lab4-policy-check"
