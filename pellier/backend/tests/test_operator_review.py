"""PROMPT 3 — the durable operator review.

Theo reaches the consequential-action boundary and Pellier stops. These tests
cover the object that makes the stop durable, and they are written around one
question: can a confirmation ever be mistaken for an authorization?

The load-bearing assertions are the negative ones. A confirmed review must leave
Policy PENDING, Aurora NOT_EVALUATED, and every business table untouched. If
those ever drift, the workshop teaches the opposite of its point — that a human
clicking confirm is the same event as a system being permitted to act.
"""

from __future__ import annotations

import json
import sqlite3
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
from services.business_logic import write_request_hash  # noqa: E402

REPO = BACKEND.parents[1]

# Theo's canonical relationships, frozen by Prompt 1 and verified against the
# live cluster: order 305 is the CUST-THEO row (304 is the same purchase under
# the bare `theo` alias the shopper prompt passes).
THEO = {
    "customer_id": "CUST-THEO",
    "product_id": 37,
    "reason": "damaged",
    "order_id": 305,
}

THEO_HASH = write_request_hash(
    "initiate_return",
    customer_id="CUST-THEO",
    product_id=37,
    reason="damaged",
)

BOUNDARY_REFUSAL = {
    "error": "managed_rail_required",
    "tool": "initiate_return",
    "required_rail": "gateway-mcp",
}


# ---------------------------------------------------------------------------
# Fake database — records every statement so the tests can assert what was
# NOT written as easily as what was.
# ---------------------------------------------------------------------------


class FakeReviewDb:
    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None) -> None:
        self.rows: List[Dict[str, Any]] = list(rows or [])
        self.statements: List[str] = []
        self.mappings: set = set()
        self._next_id = max((r["review_id"] for r in self.rows), default=0) + 1

    # -- helpers ---------------------------------------------------------
    def _find(self, review_id: int) -> Optional[Dict[str, Any]]:
        for row in self.rows:
            if row["review_id"] == int(review_id):
                return row
        return None

    def add_pending(self, **overrides: Any) -> Dict[str, Any]:
        row = {
            "review_id": self._next_id,
            "customer_id": THEO["customer_id"],
            "customer_name": "Theo",
            "action": "initiate_return",
            "args": {
                "customer_id": THEO["customer_id"],
                "product_id": THEO["product_id"],
                "reason": THEO["reason"],
            },
            "status": "pending",
            "source_turn_id": "turn-theo-1",
            "order_id": THEO["order_id"],
            "issue": "arrived damaged",
            "recommendation": {"primaryAction": "initiate_return"},
            "action_hash": THEO_HASH,
            "decided_by": None,
            "requested_at": None,
            "decided_at": None,
        }
        row.update(overrides)
        self.rows.append(row)
        self._next_id += 1
        return row

    # -- db surface ------------------------------------------------------
    async def fetch_one(self, query: str, *params: Any) -> Optional[Dict[str, Any]]:
        self.statements.append(query)
        if "FROM pellier.principal_customers" in query:
            return {"owns": 1} if tuple(params) in self.mappings else None
        if "FROM pellier.orders" in query and "WHERE customer_id" in query:
            return {"id": THEO["order_id"]}
        if query.strip().startswith("INSERT INTO pellier.approvals"):
            turn, tool, action_hash = params[3], params[1], params[7]
            customer = params[0]
            # Mirrors approvals_open_per_action_idx: one open decision per
            # (client, action, fingerprint), whichever turn asked.
            if any(
                r["customer_id"] == customer
                and r["action"] == tool
                and r["action_hash"] == action_hash
                and r["status"] == "pending"
                for r in self.rows
            ):
                return None  # the partial unique index refuses it
            row = self.add_pending(
                customer_id=params[0],
                action=params[1],
                args=json.loads(params[2]),
                source_turn_id=turn,
                order_id=params[4],
                issue=params[5],
                recommendation=json.loads(params[6]),
                requested_by_sub=params[8] if len(params) > 8 else None,
                requester_kind=params[9] if len(params) > 9 else "unverified",
                action_hash=params[7],
            )
            return {"id": row["review_id"]}
        if "AND action_hash = %s" in query:
            for row in self.rows:
                if (
                    row["customer_id"] == params[0]
                    and row["action"] == params[1]
                    and row["action_hash"] == params[2]
                    and row["status"] == "pending"
                ):
                    return {"id": row["review_id"]}
            return None
        if query.strip().startswith("UPDATE pellier.approvals"):
            status, decider, review_id = params
            row = self._find(review_id)
            if not row or row["status"] != "pending":
                return None
            row.update(status=status, decided_by=decider, decided_at="2026-08-26T00:00:00Z")
            return {
                "id": row["review_id"], "status": status,
                "decided_by": decider, "decided_at": row["decided_at"],
                "action_hash": row["action_hash"],
            }
        if "WHERE a.id = %s" in query:
            row = self._find(params[0])
            return dict(row) if row else None
        if "FROM pellier.customers" in query:
            return {
                "id": THEO["customer_id"], "name": "Theo",
                "membership": "registered", "spend_12mo": 940.00,
                "preferences_summary": "Slow craft.",
            }
        if "FROM pellier.orders o" in query:
            return {
                "order_id": THEO["order_id"], "product_id": "37", "quantity": 1,
                "placed_at": None, "product_name": "Wabi-Sabi Bowl",
                "brand": "Pellier Maison", "price": 65.00, "image_url": "/p/37.png",
            }
        if "FROM pellier.product_catalog" in query:
            return {
                "product_id": "37", "name": "Wabi-Sabi Bowl",
                "brand": "Pellier Maison", "price": 65.00, "quantity": 50,
                "image_url": "/p/37.png",
            }
        return None

    async def fetch_all(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        self.statements.append(query)
        if "FROM pellier.approvals a" in query:
            status = params[0] if params else None
            rows = [dict(r) for r in self.rows]
            if status:
                rows = [r for r in rows if r["status"] == status]
            rows.sort(key=lambda r: 0 if r["status"] == "pending" else 1)
            return rows
        if "FROM pellier.warehouse_inventory" in query:
            return [
                {"warehouse_id": "BK-01", "display_name": "Brooklyn",
                 "city": "Brooklyn, NY", "quantity": 20,
                 "ship_window_min": 1, "ship_window_max": 2},
                {"warehouse_id": "ATX-02", "display_name": "Austin",
                 "city": "Austin, TX", "quantity": 15,
                 "ship_window_min": 2, "ship_window_max": 4},
            ]
        if "FROM pellier.returns" in query:
            return [
                {"id": 28, "product_id": "31", "reason": "damaged",
                 "status": "approved", "requested_at": None, "resolved_at": None},
            ]
        return []

    def wrote_to(self, *tables: str) -> bool:
        """True when any recorded statement mutates one of `tables`."""
        for sql in self.statements:
            head = sql.strip().upper()
            if not head.startswith(("INSERT", "UPDATE", "DELETE", "SELECT PELLIER.")):
                continue
            for table in tables:
                if table.lower() in sql.lower():
                    return True
        return False



# Every route on the operator router is gated now, so a test that exercises route
# BEHAVIOUR has to be authenticated. Defaulting the override here keeps those tests about
# what they were about; `build_anonymous_client` is the deliberate opposite, and the
# boundary tests use it.
DEFAULT_OPERATOR: Dict[str, Any] = {
    "sub": "operator-sub-1",
    "username": "operator",
    "groups": ("pellier-operators",),
}

def build_client(
    db: FakeReviewDb, operator: Optional[Dict[str, Any]] = None
) -> TestClient:
    app = FastAPI()
    app.include_router(operator_module.router)
    app.dependency_overrides[operator_module.get_db_service] = lambda: db
    app.dependency_overrides[operator_module.require_operator] = (
        lambda: operator if operator is not None else DEFAULT_OPERATOR
    )
    return TestClient(app)


def build_anonymous_client(db: FakeReviewDb) -> TestClient:
    """No auth override: the real dependency runs and must refuse."""
    app = FastAPI()
    app.include_router(operator_module.router)
    app.dependency_overrides[operator_module.get_db_service] = lambda: db
    return TestClient(app)


# ---------------------------------------------------------------------------
# A. Creation from the shopper boundary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_boundary_refusal_opens_exactly_one_review() -> None:
    db = FakeReviewDb()
    review_id = await rv.propose_review(
        db,
        action="initiate_return",
        args={"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"},
        source_turn_id="turn-theo-1",
        issue="arrived damaged",
    )
    assert review_id is not None
    assert len(db.rows) == 1
    row = db.rows[0]
    assert row["customer_id"] == "CUST-THEO"
    assert row["action"] == "initiate_return"
    assert row["status"] == "pending"
    assert row["source_turn_id"] == "turn-theo-1"


@pytest.mark.asyncio
async def test_a_review_records_who_asked_or_that_nobody_verified_did() -> None:
    """The customer on the review is a proposal; the requester is a fact."""
    db = FakeReviewDb()
    db.mappings.add(("f4981468-theo", "CUST-THEO"))
    await rv.propose_review(
        db,
        action="initiate_return",
        args={"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"},
        source_turn_id="turn-theo-signed-in",
        requested_by_sub="f4981468-theo",
        requester_kind=rv.REQUESTER_SHOPPER,
    )
    await rv.propose_review(
        db,
        action="initiate_return",
        args={"customer_id": "CUST-THEO", "product_id": 38, "reason": "damaged"},
        source_turn_id="turn-anon-persona",
    )
    signed_in, anonymous = db.rows
    assert signed_in["requested_by_sub"] == "f4981468-theo"
    assert signed_in["requester_kind"] == "shopper"
    assert anonymous["requested_by_sub"] is None
    assert anonymous["requester_kind"] == "unverified"


@pytest.mark.asyncio
async def test_an_unknown_requester_kind_is_stored_as_unverified() -> None:
    db = FakeReviewDb()
    await rv.propose_review(
        db,
        action="initiate_return",
        args={"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"},
        source_turn_id="turn-x",
        requested_by_sub="someone",
        requester_kind="admin",
    )
    assert db.rows[0]["requester_kind"] == "unverified"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mapped_customer", "expected_kind"),
    [("CUST-THEO", "shopper"), ("CUST-MARCO", "unverified"), (None, "unverified")],
)
async def test_a_signed_in_requester_is_a_shopper_only_for_their_own_customer(
    mapped_customer: Optional[str], expected_kind: str
) -> None:
    """The token proves who asked; the mapping proves whose order it is.

    A verified subject filing for a persona the storefront let them pick is
    recorded with the subject kept and the kind downgraded, never as a shopper
    whose token names the customer on the review.
    """
    db = FakeReviewDb()
    if mapped_customer:
        db.mappings.add(("f4981468-theo", mapped_customer))
    await rv.propose_review(
        db,
        action="initiate_return",
        args={"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"},
        source_turn_id="turn-x",
        requested_by_sub="f4981468-theo",
        requester_kind="shopper",
    )
    assert db.rows[0]["requester_kind"] == expected_kind
    assert db.rows[0]["requested_by_sub"] == "f4981468-theo"


@pytest.mark.asyncio
async def test_a_failed_mapping_lookup_never_upgrades_a_requester() -> None:
    db = FakeReviewDb()

    async def _boom(query: str, *params: Any):
        if "principal_customers" in query:
            raise RuntimeError("mapping unavailable")
        return await FakeReviewDb.fetch_one(db, query, *params)

    db.fetch_one = _boom  # type: ignore[method-assign]
    await rv.propose_review(
        db,
        action="initiate_return",
        args={"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"},
        source_turn_id="turn-x",
        requested_by_sub="f4981468-theo",
        requester_kind="shopper",
    )
    assert db.rows[0]["requester_kind"] == "unverified"


def test_the_boundary_handoff_reads_the_requester_from_the_turn_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persona in the tool arguments never becomes the requester."""
    import asyncio

    from services.turn_identity import principal_sub_var

    captured: dict = {}

    async def _fake_propose(_db, **kwargs):
        captured.update(kwargs)
        return 41

    loop = asyncio.new_event_loop()
    import threading

    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(rv, "propose_review", _fake_propose)
        monkeypatch.setattr(rv, "_db_service", object())
        monkeypatch.setattr(rv, "_main_loop", loop)
        refusal = json.dumps({"error": rv.MANAGED_RAIL_REFUSAL, "message": "governed"})
        assert rv.is_boundary_refusal(refusal)

        token = principal_sub_var.set("f4981468-theo")
        try:
            assert rv.record_boundary_review(
                action="initiate_return",
                args={"customer_id": "CUST-MARCO", "product_id": 1, "reason": "damaged"},
                result=refusal,
                source_turn_id="turn-1",
            ) == 41
        finally:
            principal_sub_var.reset(token)
        assert captured["requested_by_sub"] == "f4981468-theo"
        assert captured["requester_kind"] == "shopper"

        captured.clear()
        rv.record_boundary_review(
            action="initiate_return",
            args={"customer_id": "CUST-THEO", "product_id": 1, "reason": "damaged"},
            result=refusal,
            source_turn_id="turn-2",
        )
        assert captured["requested_by_sub"] is None
        assert captured["requester_kind"] == "unverified"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        loop.close()


@pytest.mark.asyncio
async def test_the_review_resolves_the_order_from_aurora_rather_than_the_caller() -> None:
    """Theo's bowl exists under both `theo` and `CUST-THEO`.

    The order is looked up, not passed in, so the review references the row that
    belongs to the canonical identity the operator will act as.
    """
    db = FakeReviewDb()
    await rv.propose_review(
        db,
        action="initiate_return",
        args={"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"},
        source_turn_id="turn-theo-order",
    )
    assert db.rows[0]["order_id"] == 305


@pytest.mark.asyncio
async def test_the_source_turn_id_is_preserved_and_no_new_identifier_is_minted() -> None:
    db = FakeReviewDb()
    await rv.propose_review(
        db,
        action="initiate_return",
        args={"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"},
        source_turn_id="turn-abc-123",
    )
    row = db.rows[0]
    assert row["source_turn_id"] == "turn-abc-123"
    # The review's own id is workflow identity and must not be reused as a
    # correlation key, so the two must be distinguishable.
    assert str(row["review_id"]) != row["source_turn_id"]


def test_only_governed_mutations_are_reviewable() -> None:
    """A review for a read would be a card no operator can act on."""
    assert set(rv.REVIEWABLE_ACTIONS) == {"initiate_return", "issue_credit", "replace_damaged_item"}
    assert "check_inventory" not in rv.REVIEWABLE_ACTIONS
    assert "search_products" not in rv.REVIEWABLE_ACTIONS


def test_the_handoff_keys_off_the_structured_refusal_not_model_prose() -> None:
    """The agent's wording may change freely; the envelope may not."""
    assert rv.is_boundary_refusal(BOUNDARY_REFUSAL) is True
    assert rv.is_boundary_refusal(json.dumps(BOUNDARY_REFUSAL)) is True
    # A successful write is not a boundary refusal.
    assert rv.is_boundary_refusal({"status": "success", "return_id": 9}) is False
    # Neither is prose that merely talks about one.
    assert rv.is_boundary_refusal(
        "I prepared the request and an operator will confirm it."
    ) is False
    assert rv.is_boundary_refusal({"error": "policy_blocked"}) is False


def test_a_successful_write_never_opens_a_review() -> None:
    """Belt and braces: the creation entry point refuses non-refusals."""
    assert rv.record_boundary_review(
        action="initiate_return",
        args={"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"},
        result={"status": "success", "return_id": 9},
        source_turn_id="turn-x",
    ) is None


# ---------------------------------------------------------------------------
# B. Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_replaying_the_same_turn_does_not_create_a_second_review() -> None:
    db = FakeReviewDb()
    args = {"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"}
    first = await rv.propose_review(
        db, action="initiate_return", args=args, source_turn_id="turn-replay"
    )
    second = await rv.propose_review(
        db, action="initiate_return", args=args, source_turn_id="turn-replay"
    )
    assert first == second
    assert len(db.rows) == 1


def test_the_open_review_uniqueness_is_enforced_by_the_database() -> None:
    """A uniqueness rule that lives only in Python is a race, not a rule.

    The partial index is what makes two concurrent tool retries safe; asserting
    the application check alone would pass while duplicates still appeared under
    load.

    Keyed on (client, action, fingerprint) rather than on the source turn. A live
    smoke run disproved the turn-scoped version: every HTTP request mints its own
    turn_id, so asking twice produced two turns and the index allowed two
    identical pending cards for the same client and the same piece.
    """
    sql = (REPO / "scripts" / "migrations" / "020_operator_review.sql").read_text()
    assert "CREATE UNIQUE INDEX IF NOT EXISTS approvals_open_per_action_idx" in sql
    assert "ON pellier.approvals (customer_id, tool, action_hash)" in sql
    assert "WHERE status = 'pending'" in sql
    # The retired key must not come back: it looks stricter and is weaker.
    assert "approvals_open_per_turn_action_idx\n" not in sql.replace(
        "DROP INDEX IF EXISTS pellier.approvals_open_per_turn_action_idx;", ""
    )


@pytest.mark.asyncio
async def test_a_second_turn_asking_the_same_thing_resolves_to_the_open_review() -> None:
    """Two turns, one decision. The operator must not see the same card twice."""
    db = FakeReviewDb()
    args = {"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"}
    first = await rv.propose_review(
        db, action="initiate_return", args=args, source_turn_id="turn-one"
    )
    second = await rv.propose_review(
        db, action="initiate_return", args=args, source_turn_id="turn-two"
    )
    assert first == second, "a different turn opened a duplicate review"
    assert len(db.rows) == 1
    # The first turn stays as provenance; it is not overwritten by the second.
    assert db.rows[0]["source_turn_id"] == "turn-one"


@pytest.mark.asyncio
async def test_a_materially_different_proposal_gets_its_own_review() -> None:
    """Dedup must not collapse two genuinely different decisions."""
    db = FakeReviewDb()
    first = await rv.propose_review(
        db,
        action="initiate_return",
        args={"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"},
        source_turn_id="turn-one",
    )
    other_piece = await rv.propose_review(
        db,
        action="initiate_return",
        args={"customer_id": "CUST-THEO", "product_id": 31, "reason": "damaged"},
        source_turn_id="turn-one",
    )
    assert first != other_piece
    assert len(db.rows) == 2


# ---------------------------------------------------------------------------
# C. Discovery
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("read", ["queue", "detail"])
@pytest.mark.parametrize(
    ("kind", "subject"),
    [("shopper", "shopper-sub"), ("operator", "operator-sub"),
     ("unverified", "other-shopper-sub"), ("unverified", None)],
)
async def test_review_reads_preserve_requester_identity_and_product(
    read: str, kind: str, subject: Optional[str]
) -> None:
    """Execute the real SELECT projection, which a full-row mock cannot check."""
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            ATTACH DATABASE ':memory:' AS pellier;
            CREATE TABLE pellier.approvals (
                id INTEGER, customer_id TEXT, tool TEXT, args TEXT, status TEXT,
                source_turn_id TEXT, execution_turn_id TEXT, order_id INTEGER,
                issue TEXT, recommendation TEXT, action_hash TEXT, decided_by TEXT,
                requested_by_sub TEXT, requester_kind TEXT,
                requested_at TEXT, decided_at TEXT
            );
            CREATE TABLE pellier.customers (id TEXT, name TEXT);
            CREATE TABLE pellier.product_catalog (product_id INTEGER, name TEXT);
            INSERT INTO pellier.customers VALUES ('CUST-THEO', 'Theo');
            INSERT INTO pellier.product_catalog VALUES (37, 'Wabi-Sabi Bowl');
        """)
        conn.execute("""
            INSERT INTO pellier.approvals
              (id, customer_id, tool, args, status, requested_by_sub, requester_kind)
            VALUES (1, 'CUST-THEO', 'initiate_return', '{"product_id":37}', 'pending', ?, ?)
        """, (subject, kind))

        class QueryDb:
            async def fetch_all(self, query: str, *params: Any) -> list[dict]:
                # SQLite supports the same joins and JSON extraction. Only the
                # driver placeholders and PostgreSQL cast spelling differ here.
                sql = query.replace("::text", "").replace("%s", "?")
                return [dict(row) for row in conn.execute(sql, params)]

            async def fetch_one(self, query: str, *params: Any) -> Optional[dict]:
                rows = await self.fetch_all(query, *params)
                return rows[0] if rows else None

        db = QueryDb()
        row = (await rv.list_reviews(db))[0] if read == "queue" else await rv.get_review(db, 1)
        payload = operator_module._review_payload(row)
        assert payload["requesterKind"] == kind
        assert payload["requestedBySub"] == subject
        assert payload["productName"] == "Wabi-Sabi Bowl"


def test_the_pending_review_appears_in_the_operator_queue() -> None:
    db = FakeReviewDb()
    db.add_pending()
    body = build_client(db).get("/api/operator/reviews").json()

    assert body["total"] == 1
    assert body["pendingCount"] == 1
    review = body["reviews"][0]
    assert review["customerName"] == "Theo"
    assert review["action"] == "initiate_return"
    assert review["humanState"] == "confirmation_required"


def test_theo_is_discoverable_without_knowing_to_open_his_client_record() -> None:
    """The queue is the entry point. An operator must not have to guess a name."""
    db = FakeReviewDb()
    db.add_pending()
    body = build_client(db).get("/api/operator/reviews").json()
    assert body["reviews"][0]["customerId"] == "CUST-THEO"
    # And it links back to the authoritative client record.
    assert body["reviews"][0]["slug"] == "theo"


def test_the_queue_refuses_an_anonymous_read() -> None:
    """This test asserted the opposite, and the opposite was the vulnerability.

    "A blank 401 on the queue would hide the one thing needing attention" was the stated
    reason reads were open. It is a real concern and it is outweighed: the queue exposes
    the governance verdicts and their lineage, and the client book behind it exposes
    standing, preferences and order history. Reliability comes from seeding the operator
    group deterministically, not from letting anyone read customer data.
    """
    db = FakeReviewDb()
    db.add_pending()
    assert build_anonymous_client(db).get("/api/operator/reviews").status_code == 401


def test_decided_reviews_sort_below_pending_ones() -> None:
    db = FakeReviewDb()
    db.add_pending(status="approved", decided_by="op-1", source_turn_id="turn-old")
    db.add_pending(source_turn_id="turn-new")
    body = build_client(db).get("/api/operator/reviews").json()
    assert body["reviews"][0]["humanState"] == "confirmation_required"
    assert body["pendingCount"] == 1


def test_an_unknown_review_is_a_404_not_an_empty_page() -> None:
    assert build_client(FakeReviewDb()).get("/api/operator/reviews/999").status_code == 404


# ---------------------------------------------------------------------------
# D. Authority — the review holds references, not truth
# ---------------------------------------------------------------------------

def test_the_review_row_stores_no_business_truth() -> None:
    """Membership, spend, stock and return status must not be columns here.

    A cached membership is the exact fork this arc forbids: Pellier Operator
    would keep showing Theo as Registered after the house promoted him.

    Asserted on the column names the migration actually adds. An earlier version
    scanned the whole ALTER block including its comments and tripped on the word
    "inventory" inside a comment explaining why inventory is *not* stored - a
    guard that fails on the explanation of the rule it enforces.
    """
    import re

    sql = (REPO / "scripts" / "migrations" / "020_operator_review.sql").read_text()
    added = set(re.findall(r"ADD COLUMN IF NOT EXISTS (\w+)", sql))

    assert added == {
        "source_turn_id", "order_id", "issue", "recommendation",
        "action_hash", "decided_by", "updated_at",
    }, f"migration 020's added columns drifted: {sorted(added)}"

    forbidden = {
        "membership", "spend_12mo", "order_status", "return_status",
        "inventory_quantity", "stock", "policy_verdict", "cedar_decision",
        "rls_outcome", "result",
    }
    assert not (added & forbidden), (
        f"migration 020 adds business-truth columns: {sorted(added & forbidden)}. "
        "Those values must be hydrated from their owning tables, never copied "
        "onto the review."
    )


def test_rendering_hydrates_current_values_from_their_owning_tables() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    body = build_client(db).get(f"/api/operator/reviews/{row['review_id']}").json()

    # Standing comes from pellier.customers, now.
    assert body["client"]["membership"] == "registered"
    assert body["client"]["spend12mo"] == 940.00
    # The order comes from pellier.orders joined to the catalog.
    assert body["order"]["orderId"] == 305
    assert body["order"]["productName"] == "Wabi-Sabi Bowl"
    # Replacement availability is derived from live warehouse rows.
    assert body["fulfilment"]["totalUnits"] == 35
    assert body["fulfilment"]["replacementAvailable"] is True
    # And the prior return history is real, so the UI cannot imply a first offence.
    assert [r["productId"] for r in body["returns"]] == ["31"]
    assert body["returns"][0]["status"] == "approved"


def test_replacement_availability_is_never_stored_on_the_review() -> None:
    """It decays. A review written today must not promise stock next month."""
    db = FakeReviewDb()
    row = db.add_pending()
    body = build_client(db).get(f"/api/operator/reviews/{row['review_id']}").json()
    assert "replacementAvailable" not in body["review"]
    assert "replacementAvailable" in body["fulfilment"]


def test_the_review_response_reports_no_order_status_because_there_is_none() -> None:
    """`pellier.orders` has no status column, so inventing one would be fiction.

    The authoritative lifecycle for this piece is its return history, which the
    response carries instead.
    """
    db = FakeReviewDb()
    row = db.add_pending()
    body = build_client(db).get(f"/api/operator/reviews/{row['review_id']}").json()
    assert "status" not in body["order"]
    assert "returns" in body


# ---------------------------------------------------------------------------
# E. Confirmation binding
# ---------------------------------------------------------------------------

def test_the_exact_proposed_action_can_be_confirmed() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    client = build_client(db, operator={"sub": "operator-sub-1"})

    response = client.post(
        f"/api/operator/reviews/{row['review_id']}/confirm",
        json={"actionHash": THEO_HASH},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["humanState"] == "confirmed"
    assert body["decidedBy"] == "operator-sub-1"
    assert body["decidedAt"]


def test_the_confirmation_fingerprint_is_the_write_path_hash() -> None:
    """One function produces both, so a later write can be compared by value.

    If the review invented its own scheme, "the operator confirmed what
    executed" would be an assertion rather than something checkable.
    """
    assert rv.action_fingerprint(
        "initiate_return",
        {"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"},
    ) == write_request_hash(
        "initiate_return", customer_id="CUST-THEO", product_id=37, reason="damaged"
    )
    assert len(THEO_HASH) == 64


def test_a_changed_material_parameter_invalidates_a_prior_confirmation() -> None:
    """The operator agreed to a damaged return, not to whatever it became."""
    changed = write_request_hash(
        "initiate_return", customer_id="CUST-THEO", product_id=37, reason="changed_mind"
    )
    assert changed != THEO_HASH

    db = FakeReviewDb()
    row = db.add_pending()
    client = build_client(db, operator={"sub": "operator-sub-1"})
    response = client.post(
        f"/api/operator/reviews/{row['review_id']}/confirm",
        json={"actionHash": changed},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "parameters_changed"
    # And the review is still waiting on a human.
    assert db.rows[0]["status"] == "pending"


def test_the_credit_amount_is_material_to_the_fingerprint() -> None:
    """Confirming $25 must not authorise $250."""
    low = rv.action_fingerprint(
        "issue_credit",
        {"customer_id": "CUST-THEO", "amount_cents": 2500, "reason": "courtesy"},
    )
    high = rv.action_fingerprint(
        "issue_credit",
        {"customer_id": "CUST-THEO", "amount_cents": 25000, "reason": "courtesy"},
    )
    assert low != high


def test_confirming_without_a_fingerprint_is_refused() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    client = build_client(db, operator={"sub": "operator-sub-1"})
    response = client.post(f"/api/operator/reviews/{row['review_id']}/confirm", json={})
    assert response.status_code == 422


def test_a_review_cannot_be_decided_twice() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    client = build_client(db, operator={"sub": "operator-sub-1"})
    first = client.post(
        f"/api/operator/reviews/{row['review_id']}/confirm",
        json={"actionHash": THEO_HASH},
    )
    assert first.status_code == 200
    second = client.post(f"/api/operator/reviews/{row['review_id']}/decline")
    assert second.status_code == 409
    assert second.json()["detail"] == "review_already_decided"


def test_the_database_refuses_a_decision_with_no_decider() -> None:
    """Attribution is a constraint, not a convention."""
    sql = (REPO / "scripts" / "migrations" / "020_operator_review.sql").read_text()
    assert "approvals_decision_complete_check" in sql
    assert "decided_by IS NOT NULL" in sql


# ---------------------------------------------------------------------------
# F. Decline
# ---------------------------------------------------------------------------

def test_declining_closes_the_review_and_records_who_declined() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    client = build_client(db, operator={"sub": "operator-sub-2"})

    response = client.post(f"/api/operator/reviews/{row['review_id']}/decline")
    assert response.status_code == 200
    body = response.json()
    assert body["humanState"] == "declined"
    assert body["decidedBy"] == "operator-sub-2"
    assert db.rows[0]["status"] == "rejected"


def test_declining_needs_no_fingerprint() -> None:
    """"Do not do this" cannot be invalidated by a parameter change."""
    db = FakeReviewDb()
    row = db.add_pending()
    client = build_client(db, operator={"sub": "op"})
    assert client.post(
        f"/api/operator/reviews/{row['review_id']}/decline"
    ).status_code == 200


def test_a_declined_action_never_reaches_policy_or_aurora() -> None:
    """A human refusal precedes policy evaluation.

    Pushing a declined action through the governed path to harvest a Cedar DENY
    would manufacture evidence for a decision nobody submitted.
    """
    db = FakeReviewDb()
    row = db.add_pending()
    client = build_client(db, operator={"sub": "op"})
    body = client.post(f"/api/operator/reviews/{row['review_id']}/decline").json()

    assert body["assurance"] == {
        "human": "DECLINED",
        "policy": "NOT_EVALUATED",
        "aurora": "NOT_REACHED",
        "evidence": "NO_EXECUTION",
    }
    assert not db.wrote_to("pellier.returns", "pellier.store_credits",
                           "pellier.write_operations", "pellier.inventory_ledger")


# ---------------------------------------------------------------------------
# G. Security
# ---------------------------------------------------------------------------

def test_an_anonymous_caller_cannot_confirm_a_review() -> None:
    """No operator dependency override, so the real gate runs."""
    db = FakeReviewDb()
    row = db.add_pending()
    client = build_anonymous_client(db)

    confirm = client.post(
        f"/api/operator/reviews/{row['review_id']}/confirm",
        json={"actionHash": THEO_HASH},
    )
    decline = client.post(f"/api/operator/reviews/{row['review_id']}/decline")
    assert confirm.status_code == 401
    assert decline.status_code == 401
    assert db.rows[0]["status"] == "pending"


def test_an_authenticated_shopper_cannot_confirm_a_review() -> None:
    """The finding this closes: a verified token was the whole check.

    This test did not exist. Its predecessor sent NO credentials, so it proved only that
    an anonymous caller is refused, and the far more likely attacker was a shopper who
    already has a valid token from the storefront. `marco` could confirm, decline and
    execute any review, and call `issue_credit`, because `require_operator` stopped at
    "the token verifies and carries a subject".

    Asserted through the real dependency with a real token shape rather than through an
    override, because an override of `require_operator` is precisely the thing under test.
    """
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException, Request

    from services import auth as auth_module

    shopper = SimpleNamespace(
        user_id="cognito-sub-marco",
        email="marco@pellier.example.com",
        given_name="Marco",
        username="marco",
        access_token="header.payload.signature",
        groups=(),  # a storefront shopper is in no group
    )

    class _FakeService:
        async def extract_user(self, request):  # noqa: ANN001, D102
            return shopper

    import services.cognito_auth as cognito_module

    saved = cognito_module.get_cognito_auth_service
    cognito_module.get_cognito_auth_service = lambda: _FakeService()
    try:
        request = Request(
            {
                "type": "http",
                "headers": [(b"authorization", b"Bearer header.payload.signature")],
                "method": "POST",
                "path": "/api/operator/reviews/1/confirm",
                "query_string": b"",
            }
        )
        try:
            asyncio.run(auth_module.require_operator(request))
        except HTTPException as exc:
            assert exc.status_code == 403, (
                f"an authenticated shopper got {exc.status_code}, not 403"
            )
            assert exc.detail == "operator_group_required"
        else:
            raise AssertionError(
                "require_operator accepted a shopper with no group membership"
            )

        # The same identity WITH the group is accepted, so the check is membership and
        # not an accidental blanket refusal.
        shopper.groups = (auth_module.OPERATOR_GROUP,)
        payload = asyncio.run(auth_module.require_operator(request))
        assert payload["sub"] == "cognito-sub-marco"
        assert auth_module.OPERATOR_GROUP in payload["groups"]
    finally:
        cognito_module.get_cognito_auth_service = saved


def test_the_decision_endpoints_are_gated_by_the_routers_dependency_graph() -> None:
    """Asserted against the real graph, not the source text.

    A docstring mentioning `require_operator` proves nothing about what the
    handler depends on.
    """
    from services.auth import require_operator

    review_routes = [
        r for r in operator_module.router.routes if "/reviews" in getattr(r, "path", "")
    ]
    assert review_routes, "the review routes disappeared"
    for route in review_routes:
        gated = any(
            dep.call is require_operator for dep in route.dependant.dependencies
        )
        # Reads are gated too now. This branch used to assert the opposite, which is
        # how "reads are open" survived as a policy nobody re-examined: the test
        # enforced it.
        assert gated, f"{route.path} is reachable without require_operator"


def test_an_empty_operator_subject_cannot_decide() -> None:
    """A verified-but-anonymous token would attribute a decision to nobody."""
    db = FakeReviewDb()
    row = db.add_pending()
    client = build_client(db, operator={"sub": "   "})
    response = client.post(
        f"/api/operator/reviews/{row['review_id']}/confirm",
        json={"actionHash": THEO_HASH},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "decider_required"


def test_confirming_another_clients_review_by_id_still_binds_to_that_reviews_hash() -> None:
    """ID manipulation cannot smuggle in different parameters.

    Walking to another review's id is possible by design - an operator sees the
    whole queue - but the fingerprint is the review's own, so a confirmation
    aimed at review B with review A's hash is refused.
    """
    db = FakeReviewDb()
    theo = db.add_pending(source_turn_id="turn-theo")
    other = db.add_pending(
        customer_id="CUST-JESSICA",
        customer_name="Jessica Nakamura",
        source_turn_id="turn-jessica",
        args={"customer_id": "CUST-JESSICA", "product_id": 42, "reason": "damaged"},
        action_hash=write_request_hash(
            "initiate_return", customer_id="CUST-JESSICA", product_id=42,
            reason="damaged",
        ),
    )
    client = build_client(db, operator={"sub": "op"})

    crossed = client.post(
        f"/api/operator/reviews/{other['review_id']}/confirm",
        json={"actionHash": theo["action_hash"]},
    )
    assert crossed.status_code == 409
    assert crossed.json()["detail"] == "parameters_changed"
    assert db.rows[1]["status"] == "pending"


@pytest.mark.asyncio
async def test_stored_parameters_that_disagree_with_the_hash_are_refused() -> None:
    """If args and fingerprint ever diverge, the hash proves nothing.

    Confirming would then bind a human decision to a value the row no longer
    holds, so the confirmation is refused rather than trusted.
    """
    db = FakeReviewDb()
    row = db.add_pending()
    row["args"] = {
        "customer_id": "CUST-THEO", "product_id": 37, "reason": "changed_mind",
    }
    with pytest.raises(rv.ReviewError) as excinfo:
        await rv.decide_review(
            db, review_id=row["review_id"], decision="approved",
            decided_by="op", action_hash=row["action_hash"],
        )
    assert excinfo.value.code == "stored_parameters_invalid"


# ---------------------------------------------------------------------------
# H. No premature governance
# ---------------------------------------------------------------------------

def test_a_confirmed_review_leaves_policy_pending_and_aurora_not_evaluated() -> None:
    """The load-bearing assertion of Prompt 3.

    A human has said yes. Nothing has asked Cedar, and no statement has reached
    the database. If this ever reports ALLOW or PERMITTED, the workshop teaches
    that human intent is authorization.
    """
    db = FakeReviewDb()
    row = db.add_pending()
    client = build_client(db, operator={"sub": "op"})
    body = client.post(
        f"/api/operator/reviews/{row['review_id']}/confirm",
        json={"actionHash": THEO_HASH},
    ).json()

    assert body["assurance"] == {
        "human": "CONFIRMED",
        "policy": "PENDING",
        "aurora": "NOT_EVALUATED",
        "evidence": "PENDING",
    }


def test_confirmation_performs_no_business_mutation() -> None:
    db = FakeReviewDb()
    row = db.add_pending()
    client = build_client(db, operator={"sub": "op"})
    client.post(
        f"/api/operator/reviews/{row['review_id']}/confirm",
        json={"actionHash": THEO_HASH},
    )
    assert not db.wrote_to(
        "pellier.returns", "pellier.store_credits",
        "pellier.write_operations", "pellier.inventory_ledger",
        "process_return_idempotent", "apply_store_credit",
    )


def test_the_confirmation_route_does_not_call_business_logic() -> None:
    """Structural, because the existing action endpoints DO couple the two.

    `/actions/resolve-return` confirms and executes in one call. Reusing it here
    to make the screen feel finished would collapse the two decisions the four
    axes exist to separate.
    """
    source = (BACKEND / "routes" / "operator.py").read_text()
    confirm_block = source.split("async def confirm_review(", 1)[1].split(
        "@router.post(\"/reviews/{review_id}/decline\")", 1
    )[0]
    assert "BusinessLogic" not in confirm_block
    assert "initiate_return(" not in confirm_block
    assert "issue_credit(" not in confirm_block

    decline_block = source.split("async def decline_review(", 1)[1].split(
        "# The four axes", 1
    )[0]
    assert "BusinessLogic" not in decline_block


def test_the_four_axes_are_independent_states_not_a_boolean() -> None:
    """A single `governed: true` would let one axis imply another."""
    for state, expected_keys in operator_module._ASSURANCE_BY_HUMAN_STATE.items():
        assert set(expected_keys) == {"human", "policy", "aurora", "evidence"}, state
    source = (BACKEND / "routes" / "operator.py").read_text()
    assert '"governed": True' not in source
    assert '"governed":True' not in source


def test_no_human_state_ever_reports_an_allow_or_a_permitted() -> None:
    """Prompt 3 cannot produce those states, so none may be spelled here."""
    for state, axes in operator_module._ASSURANCE_BY_HUMAN_STATE.items():
        assert axes["policy"] in ("PENDING", "NOT_EVALUATED"), state
        assert axes["aurora"] in ("NOT_EVALUATED", "NOT_REACHED"), state
        assert "ALLOW" not in axes.values(), state
        assert "PERMITTED" not in axes.values(), state


# ---------------------------------------------------------------------------
# Creation point — the guard Prompt 2 established must survive
# ---------------------------------------------------------------------------

def test_the_review_opens_from_the_refusal_branch_after_the_guard_decides() -> None:
    """The guard runs first; the handoff is its consequence.

    A tool-lifecycle hook was tried first and did not work: the audit hooks are
    attached to the outer orchestrator, and on the Agents-as-Tools path a
    specialist's inner tool calls never reach them, so `POST /api/chat` opened no
    review at all. A live smoke run proved it - the turn produced one `support`
    audit row and nothing else. The refusal branch is the only place that runs on
    every rail and every path, with the exact arguments.
    """
    tools = (BACKEND / "services" / "agent_tools.py").read_text()
    return_block = tools.split("def initiate_return(", 1)[1].split("\n@tool", 1)[0]

    guard_at = return_block.index('_managed_rail_required("initiate_return")')
    review_at = return_block.index("_open_operator_review(")
    assert guard_at < review_at, (
        "the review is opened before the rail guard decides; the guard must run "
        "first and the handoff must be its consequence"
    )
    assert "_open_operator_review(" in return_block
    assert "operator_review.record_boundary_review(" in tools


def test_the_refusal_branch_never_touches_the_business_pool() -> None:
    """The Prompt 2 guarantee, restated for the new creation point.

    `initiate_return`'s refusal path must not reach `_db_service`, which is the
    handle every business write goes through. The review writes workflow state
    through its own pool reference, so the tripwire in
    `test_shopper_arc_prompt2` remains meaningful rather than being satisfied on
    a technicality: no business table is reachable from this branch.
    """
    tools = (BACKEND / "services" / "agent_tools.py").read_text()
    return_block = tools.split("def initiate_return(", 1)[1].split("\n@tool", 1)[0]
    refusal_branch = return_block.split("return governed_error", 1)[0]

    assert "_db_service" not in refusal_branch, (
        "the refusal branch reaches the business database pool"
    )
    assert "BusinessLogic" not in refusal_branch


def test_the_creation_point_reads_structured_arguments_not_the_models_text() -> None:
    """The agent's prose may change freely; the arguments and envelope may not."""
    tools = (BACKEND / "services" / "agent_tools.py").read_text()
    helper = tools.split("def _open_operator_review(", 1)[1].split("\ndef ", 1)[0]

    # Keyed off the structured refusal envelope and the tool's own parameters.
    assert "record_boundary_review(" in helper
    assert "result=refusal_envelope" in helper
    assert "args=args" in helper
    assert "current_turn_id()" in helper

    # And the arguments passed in are the tool's typed parameters, not text.
    return_block = tools.split("def initiate_return(", 1)[1].split("\n@tool", 1)[0]
    for parameter in ('"customer_id"', '"product_id"', '"reason"'):
        assert parameter in return_block, parameter


def test_both_governed_mutations_open_a_review_when_refused() -> None:
    """`issue_credit` is refused on the same boundary and must not go silent."""
    tools = (BACKEND / "services" / "agent_tools.py").read_text()
    credit_block = tools.split("def issue_credit(", 1)[1].split("\n@tool", 1)[0]
    assert "_open_operator_review(" in credit_block
    assert '"amount_cents"' in credit_block
