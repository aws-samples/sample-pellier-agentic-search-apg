"""``/api/operator`` routes: the staff desk where Jessica's case is decided.

  * ``GET  /clients``                      the clients: open requests, last order
  * ``GET  /clients/{id}``                 one record: ticket, orders, credits
  * ``POST /clients/{id}/investigate``     the Investigator, then the Planner (SSE)
  * ``GET  /reviews``, ``GET /reviews/{id}``   the queue and the record
  * ``POST /reviews/{id}/confirm|decline|execute``  the decision and the write

Design notes
------------

**Every route is gated, reads included.** Anonymous callers get ``401``,
authenticated shoppers get ``403``, and members of ``auth.OPERATOR_GROUP`` get
access. A client record carries order history, tickets and credits; a review
record carries the governance verdicts. Neither is public.

**Aurora is the source of truth.** Every field is selected from the tables that
own it. There is no committed frontend copy of the clients, because UI state is
not evidence.

**One governed action, one execution path.** Giving a store credit calls
``store_tools.give_store_credit``. It has no direct action endpoint. The
Planner opens one review, a person confirms the exact review, and
``POST /reviews/{id}/execute`` runs the credit with the review's idempotency
key, so a replay applies exactly once and produces the same durable evidence:
one ``pellier.store_credits`` row and one ``pellier.tool_audit`` row. The tool
itself refuses a write no confirmed review fingerprints, on either rail.

The Gateway publishes ``give_store_credit`` with a staff-only permit; the Lab 4
forbid a participant authors adds the per-credit amount limit on top. The
pre-token trigger derives ``custom:staff_scope`` from membership in the
operator group, which is the same fact ``require_operator`` checks here.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.auth import require_operator
from services.data_source import database_source_label

logger = logging.getLogger(__name__)

# ONE authorization boundary for the whole prefix. Declared on the router rather than
# annotated per handler so a new route inherits it instead of being forgotten.
router = APIRouter(
    prefix="/api/operator",
    tags=["operator"],
    dependencies=[Depends(require_operator)],
)


async def get_db_service() -> Any:
    """FastAPI dependency returning the shared ``DatabaseService``.

    Imported lazily so the router can be collected by pytest without
    triggering ``app.py``'s lifespan, which expects a live cluster. Tests
    override this dependency with a stub.
    """
    from app import get_db_service as _app_get_db_service

    return await _app_get_db_service()


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------

# The four shoppers have portraits and a storefront sign-in. The desk uses the
# id to pick the portrait and to offer "open her storefront".
_PERSONA_CUSTOMER_IDS = {
    "CUST-MARCO": "marco",
    "CUST-ANNA": "anna",
    "CUST-THEO": "theo",
    "CUST-JESSICA": "jessica",
}

_CLIENTS_SELECT = """
    SELECT
        c.id   AS customer_id,
        c.name AS name,
        -- What staff act on: the open requests, and the newest one's subject.
        (SELECT COUNT(*) FROM pellier.support_tickets t
          WHERE t.customer_id = c.id AND t.status IN ('open', 'pending')) AS open_requests,
        t.subject   AS open_request,
        t.status    AS open_request_status,
        o.product_name AS last_order_name,
        o.placed_at    AS last_order_at
      FROM pellier.customers c
      LEFT JOIN LATERAL (
            SELECT subject, status
              FROM pellier.support_tickets
             WHERE customer_id = c.id
               AND status IN ('open', 'pending')
             ORDER BY opened_at DESC
             LIMIT 1
      ) t ON TRUE
      LEFT JOIN LATERAL (
            SELECT p.name AS product_name, o.placed_at
              FROM pellier.orders o
              JOIN pellier.product_catalog p ON p."productId" = o.product_id
             WHERE o.customer_id = c.id
             ORDER BY o.placed_at DESC, o.id DESC
             LIMIT 1
      ) o ON TRUE
     -- left() rather than a LIKE prefix match: psycopg parses a bare percent
     -- sign as a placeholder even when no parameters are bound.
     WHERE left(c.id, 5) = 'CUST-'
       AND c.id <> 'CUST-FRESH'
     ORDER BY open_requests DESC, c.name ASC
"""

_CLIENT_SELECT = """
    SELECT c.id AS customer_id, c.name AS name
      FROM pellier.customers c
     WHERE c.id = %s
"""

# An order's return state comes from pellier.returns, the authoritative record
# of a return. The ticket may say two items went back; the rows make it a fact.
_ORDERS_SELECT = """
    SELECT
        o.id            AS order_id,
        o.product_id    AS product_id,
        o.quantity      AS quantity,
        o.placed_at     AS placed_at,
        p.name          AS product_name,
        p.brand         AS brand,
        o.amount_paid_cents AS amount_paid_cents,
        p."imgUrl"      AS image_url,
        r.status        AS return_status
      FROM pellier.orders o
      JOIN pellier.product_catalog p
             ON p."productId" = o.product_id
      LEFT JOIN LATERAL (
            SELECT status
              FROM pellier.returns
             WHERE customer_id = o.customer_id
               AND product_id = o.product_id
             ORDER BY requested_at DESC
             LIMIT 1
      ) r ON TRUE
     WHERE o.customer_id = %s
     ORDER BY o.placed_at DESC, o.id DESC
"""

_TICKETS_SELECT = """
    SELECT ticket_id, subject, status, channel, last_note, opened_at, resolved_at
      FROM pellier.support_tickets
     WHERE customer_id = %s
     ORDER BY opened_at DESC
"""

_CREDITS_SELECT = """
    SELECT credit_id, amount_cents, currency, reason, issued_by, idempotency_key, created_at
      FROM pellier.store_credits
     WHERE customer_id = %s
     ORDER BY created_at DESC
"""

# A return that went back and was accepted reads as Returned on the record.
_RETURNED_STATUSES = frozenset({"approved", "refunded"})


def _client_slug(customer_id: str) -> str:
    """`CUST-JESSICA` -> `jessica`. Drives the portrait filename."""
    return str(customer_id or "").replace("CUST-", "", 1).lower()


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def _money(cents: Any) -> str:
    return f"{int(cents or 0) / 100:.2f}"


def _client_row(row: Dict[str, Any]) -> Dict[str, Any]:
    customer_id = str(row.get("customer_id") or "")
    last_order = None
    if row.get("last_order_name") or row.get("last_order_at"):
        last_order = {
            "productName": row.get("last_order_name") or "",
            "placedAt": _iso(row.get("last_order_at")),
        }
    return {
        "customerId": customer_id,
        "slug": _client_slug(customer_id),
        "name": row.get("name") or customer_id,
        "personaId": _PERSONA_CUSTOMER_IDS.get(customer_id),
        "openRequests": int(row.get("open_requests") or 0),
        "openRequest": row.get("open_request") or None,
        "openRequestStatus": row.get("open_request_status") or None,
        "lastOrder": last_order,
    }


def _order_row(row: Dict[str, Any]) -> Dict[str, Any]:
    cents = int(row.get("amount_paid_cents") or 0)
    return_status = row.get("return_status") or None
    return {
        "orderId": int(row.get("order_id") or 0),
        "productId": str(row.get("product_id") or ""),
        "productName": row.get("product_name") or "",
        "brand": row.get("brand") or "",
        "amountPaidCents": cents,
        "amountPaid": _money(cents),
        "quantity": int(row.get("quantity") or 1),
        "placedAt": _iso(row.get("placed_at")),
        "imageUrl": row.get("image_url") or "",
        "returnStatus": return_status,
        "returned": return_status in _RETURNED_STATUSES,
    }


def _ticket_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ticketId": row.get("ticket_id") or "",
        "subject": row.get("subject") or "",
        "status": row.get("status") or "open",
        "channel": row.get("channel") or "",
        "lastNote": row.get("last_note") or "",
        "openedAt": _iso(row.get("opened_at")),
        "resolvedAt": _iso(row.get("resolved_at")),
    }


def _credit_row(row: Dict[str, Any]) -> Dict[str, Any]:
    cents = int(row.get("amount_cents") or 0)
    return {
        "creditId": int(row.get("credit_id") or 0),
        "amountCents": cents,
        # Formatted once, here, so no surface re-derives currency from cents.
        "amount": _money(cents),
        "currency": row.get("currency") or "USD",
        "reason": row.get("reason") or "",
        "issuedBy": row.get("issued_by"),
        "idempotencyKey": row.get("idempotency_key") or "",
        "createdAt": _iso(row.get("created_at")),
    }


async def _read_one(db: Any, sql: str, *args: Any, label: str) -> Optional[Dict[str, Any]]:
    try:
        row = await db.fetch_one(sql, *args)
        return dict(row) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Operator %s query failed", label)
        raise RuntimeError(f"Operator {label} query failed") from exc


async def _read_rows(db: Any, sql: str, *args: Any, label: str) -> List[Dict[str, Any]]:
    """Read record rows, retaining database failures.

    A partial client record cannot support an action: treating a failed
    tickets read as ``[]`` turns unavailable evidence into a false "nothing on
    file". The route translates a failed fan-out into an explicit 503.
    """
    try:
        rows = await db.fetch_all(sql, *args)
        return [dict(r) for r in (rows or [])]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Operator %s query failed", label)
        raise RuntimeError(f"Operator {label} query failed") from exc


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


@router.get("/clients")
async def list_clients(db: Any = Depends(get_db_service)) -> Dict[str, Any]:
    """The clients, open requests first.

    Returns an empty list rather than a 500 when nothing is seeded, so the desk
    can render an honest "no clients" state instead of an error.
    """
    try:
        rows = await db.fetch_all(_CLIENTS_SELECT)
    except Exception as exc:  # noqa: BLE001 - surfaced as an explicit state
        logger.error("Operator clients query failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="clients_unavailable: could not read pellier.customers.",
        ) from exc

    clients = [_client_row(dict(r)) for r in (rows or [])]
    return {
        "clients": clients,
        "total": len(clients),
        "openRequests": sum(c["openRequests"] for c in clients),
    }


@router.get("/clients/{client_id}")
async def get_client(
    client_id: str = Path(..., min_length=1, max_length=64),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """One record: the ticket, the orders with their return state, the credits.

    The five reads are independent, so they run concurrently. The client's
    credit reviews ride along so the record can say "waiting for approval"
    after a refresh, with a link to the review.
    """
    from services import operator_review as rv

    outcomes = await asyncio.gather(
        _read_one(db, _CLIENT_SELECT, client_id, label="client"),
        _read_rows(db, _ORDERS_SELECT, client_id, label="orders"),
        _read_rows(db, _TICKETS_SELECT, client_id, label="tickets"),
        _read_rows(db, _CREDITS_SELECT, client_id, label="credits"),
        rv.list_reviews_for_customer(db, client_id),
        return_exceptions=True,
    )
    failure = next((o for o in outcomes if isinstance(o, Exception)), None)
    if failure is not None:
        logger.error("Operator client record is unavailable for %s: %s", client_id, failure)
        raise HTTPException(
            status_code=503,
            detail=(
                "client_record_unavailable: the complete client record could not "
                "be read. No absence claim was made."
            ),
        ) from failure
    row, order_rows, ticket_rows, credit_rows, review_rows = outcomes
    if not row:
        raise HTTPException(status_code=404, detail=f"Unknown client: {client_id}")

    orders = [_order_row(r) for r in (order_rows or [])]
    tickets = [_ticket_row(r) for r in (ticket_rows or [])]
    credits = [_credit_row(r) for r in (credit_rows or [])]
    credit_cents = sum(c["amountCents"] for c in credits)
    record = {
        "customerId": str(row.get("customer_id") or client_id),
        "slug": _client_slug(str(row.get("customer_id") or client_id)),
        "name": row.get("name") or client_id,
        "personaId": _PERSONA_CUSTOMER_IDS.get(str(row.get("customer_id") or "")),
        "openTicketCount": sum(1 for t in tickets if t["status"] in ("open", "pending")),
        "returnedCount": sum(1 for o in orders if o["returned"]),
        "creditBalanceCents": credit_cents,
        "creditBalance": _money(credit_cents),
    }
    return {
        "client": record,
        "orders": orders,
        "tickets": tickets,
        "credits": credits,
        "reviews": [_review_payload(r, None) for r in (review_rows or [])],
        # Which database answered: the same build serves local PostgreSQL in
        # development and Aurora in the workshop.
        "dataSource": database_source_label(),
    }


# ---------------------------------------------------------------------------
# The investigation: Investigator, then Planner, streamed
# ---------------------------------------------------------------------------


def _sse(kind: str, data: Dict[str, Any]) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/clients/{client_id}/investigate")
async def investigate_client(
    client_id: str = Path(..., min_length=1, max_length=64),
    db: Any = Depends(get_db_service),
    operator: Dict[str, Any] = Depends(require_operator),
) -> StreamingResponse:
    """Run the two-node graph for this client and stream its steps.

    SSE, like the shopper's turn: ``step`` events as each read and each node
    finishes, one ``answer`` with the brief and the proposal, then ``complete``.
    Every event follows work that actually finished.

    The graph is read-only except for the one review the Planner opens. It
    runs on a worker thread; the request's pool serves its statements through
    the loop that owns it, exactly as the agents' tools are served.
    """
    from services import operator_graph
    from services.turn_identity import new_turn_id

    client = await _read_one(db, _CLIENT_SELECT, client_id, label="client")
    if not client:
        raise HTTPException(status_code=404, detail=f"Unknown client: {client_id}")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    turn_id = new_turn_id()
    operator_sub = str(operator.get("sub") or "").strip()

    def run(sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        future = asyncio.run_coroutine_threadsafe(db.fetch_all(sql, *params), loop)
        return [dict(r) for r in future.result(timeout=30) or []]

    def emit(event: Dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("step", event))

    async def investigate() -> None:
        try:
            result = await asyncio.to_thread(
                operator_graph.run_investigation,
                run=run,
                customer_id=client_id,
                customer_name=str(client.get("name") or ""),
                operator_sub=operator_sub,
                turn_id=turn_id,
                emit=emit,
            )
            payload = result.as_payload()
            queue.put_nowait(("answer", payload))
            queue.put_nowait(("complete", {**payload, "type": "complete"}))
        except Exception as exc:  # noqa: BLE001 - the stream must close cleanly
            logger.warning("investigation stream failed: %s", exc)
            queue.put_nowait(("error", {"detail": "investigation_failed", "turnId": turn_id}))
        finally:
            queue.put_nowait((None, {}))

    task = asyncio.create_task(investigate())

    async def events() -> Any:
        yield _sse("status", {"type": "status", "turnId": turn_id, "label": "Investigator reads the case"})
        try:
            while True:
                kind, data = await queue.get()
                if kind is None:
                    break
                yield _sse(kind, data)
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Reviews: the durable handoff to a person
# ---------------------------------------------------------------------------


def _review_payload(
    row: Dict[str, Any], receipt: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Shape one review for the desk.

    Workflow state, plus the verdicts of its latest execution attempt when one
    exists. ``receipt`` is passed in so the queue can batch one round trip.
    """
    from services import operator_review as rv

    status = str(row.get("status") or rv.STATUS_PENDING)
    args = rv.parse_json(row.get("args")) or {}
    recommendation = rv.parse_json(row.get("recommendation")) or {}
    human_state = {
        rv.STATUS_PENDING: "confirmation_required",
        rv.STATUS_CONFIRMED: "confirmed",
        rv.STATUS_DECLINED: "declined",
    }.get(status, "confirmation_required")
    amount_cents = args.get("amount_cents")
    customer_id = str(row.get("customer_id") or "")

    return {
        "reviewId": int(row.get("review_id") or 0),
        "customerId": customer_id,
        "customerName": row.get("customer_name") or customer_id,
        "slug": _client_slug(customer_id),
        "personaId": _PERSONA_CUSTOMER_IDS.get(customer_id),
        "action": str(row.get("action") or ""),
        "parameters": args,
        "amountCents": int(amount_cents) if amount_cents is not None else None,
        "amount": _money(amount_cents) if amount_cents is not None else None,
        "reason": str(args.get("reason") or ""),
        "status": status,
        "humanState": human_state,
        # Resolved server-side so no surface can infer one axis from another.
        "assurance": _assurance_from_receipt(human_state, receipt),
        # What produced the verdicts. A surface can show ALLOW without it, but
        # not defend it.
        "execution": _receipt_payload(receipt),
        "sourceTurnId": row.get("source_turn_id"),
        "executionTurnId": row.get("execution_turn_id"),
        "orderId": int(row["order_id"]) if row.get("order_id") else None,
        "orderIds": rv.referenced_order_ids(row),
        "issue": row.get("issue") or "",
        "recommendation": recommendation,
        # Echoed so the desk can send it back on confirm. It is a fingerprint
        # of the parameters the person was shown, not a secret.
        "actionHash": row.get("action_hash") or "",
        "decidedBy": row.get("decided_by"),
        # Who asked, kept apart from the customer and from who decides.
        "requestedBySub": row.get("requested_by_sub") or None,
        "requesterKind": str(row.get("requester_kind") or "unverified"),
        "requestedAt": _iso(row.get("requested_at")),
        "decidedAt": _iso(row.get("decided_at")),
    }


@router.get("/reviews")
async def list_reviews(
    status: Optional[str] = None,
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """The review queue. Pending first, so the desk opens on what needs a person."""
    from services import governed_execution as ge
    from services import operator_review as rv

    try:
        rows = await rv.list_reviews(db, status=status)
    except Exception as exc:  # noqa: BLE001
        logger.error("Operator review queue query failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="review_queue_unavailable: could not read pellier.approvals.",
        ) from exc

    receipts = await ge.latest_receipts(
        db, [row.get("review_id") for row in rows if row.get("review_id")]
    )
    reviews = [
        _review_payload(row, receipts.get(int(row.get("review_id") or 0)))
        for row in rows
    ]
    return {
        "reviews": reviews,
        "total": len(reviews),
        "pendingCount": sum(1 for r in reviews if r["status"] == rv.STATUS_PENDING),
    }


def _hydrated_order(order: Dict[str, Any]) -> Dict[str, Any]:
    cents = int(round(float(order.get("price_paid") or 0) * 100))
    return {
        "orderId": int(order.get("order_id") or 0),
        "productId": str(order.get("product_id") or ""),
        "productName": order.get("product_name") or "",
        "brand": order.get("brand") or "",
        "amountPaidCents": cents,
        "amountPaid": _money(cents),
        "quantity": int(order.get("quantity") or 1),
        "placedAt": _iso(order.get("placed_at")),
        "imageUrl": order.get("image_url") or "",
    }


@router.get("/reviews/{review_id}")
async def get_review(
    review_id: int = Path(..., ge=1),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """One review, with current truth resolved from the tables that own it.

    The review row supplies references and workflow state. The client's name
    and the orders the proposal refers to are read now. Once an execution has
    been attempted, the durable record for its write key is read too: the
    ``store_credits`` and ``tool_audit`` rows, counted from the tables.
    """
    from services import governed_execution as ge
    from services import operator_review as rv

    try:
        row = await rv.get_review(db, review_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Operator review query failed for %s: %s", review_id, exc)
        raise HTTPException(status_code=503, detail="review_unavailable") from exc
    if not row:
        raise HTTPException(status_code=404, detail=f"Unknown review: {review_id}")

    receipt = await ge.latest_receipt(db, review_id)
    hydrated = await rv.hydrate_review(db, row)
    customer = hydrated.get("customer") or {}
    customer_id = str(row.get("customer_id") or "")
    record = None
    if receipt is not None:
        record = await ge.evidence_for_key(db, str(receipt.get("idempotency_key") or ""))
    return {
        "review": _review_payload(row, receipt),
        "client": {
            "customerId": customer.get("id") or customer_id,
            "name": customer.get("name") or "",
            "slug": _client_slug(customer_id),
            "personaId": _PERSONA_CUSTOMER_IDS.get(customer_id),
        },
        "orders": [_hydrated_order(o) for o in (hydrated.get("orders") or [])],
        "record": record,
    }


class ReviewDecisionRequest(BaseModel):
    """A human decision on a prepared request.

    ``actionHash`` is required to confirm and ignored to decline. Confirming
    means "I agree to this exact credit", so the desk echoes the fingerprint
    it displayed; if any material parameter changed in the meantime the
    fingerprints disagree and the confirmation is refused.
    """

    actionHash: Optional[str] = Field(default=None, min_length=64, max_length=64)


def _decision_payload(decided: Dict[str, Any], human_state: str) -> Dict[str, Any]:
    return {
        "reviewId": int(decided["id"]),
        "status": decided["status"],
        "humanState": human_state,
        "decidedBy": decided["decided_by"],
        "decidedAt": _iso(decided["decided_at"]),
        "assurance": _assurance(human_state),
    }


@router.post("/reviews/{review_id}/confirm")
async def confirm_review(
    request: ReviewDecisionRequest,
    review_id: int = Path(..., ge=1),
    operator: Dict[str, Any] = Depends(require_operator),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """Record that a person confirmed this exact proposed credit.

    This performs no business mutation. It writes one row's workflow state and
    returns the assurance axes as they stand: the person has decided, and
    nothing else has happened yet.
    """
    from services import operator_review as rv

    principal_sub = str(operator.get("sub") or "").strip()
    try:
        decided = await rv.decide_review(
            db,
            review_id=review_id,
            decision=rv.STATUS_CONFIRMED,
            decided_by=principal_sub,
            action_hash=request.actionHash,
        )
    except rv.ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Operator review confirm failed for %s: %s", review_id, exc)
        raise HTTPException(status_code=500, detail="review_confirm_failed") from exc
    return _decision_payload(decided, "confirmed")


@router.post("/reviews/{review_id}/decline")
async def decline_review(
    review_id: int = Path(..., ge=1),
    operator: Dict[str, Any] = Depends(require_operator),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """Record that a person declined. Nothing is sent anywhere.

    A declined credit is deliberately NOT pushed through the governed path to
    demonstrate a denial: human refusal precedes policy evaluation, so a Cedar
    DENY here would be invented evidence.
    """
    from services import operator_review as rv

    principal_sub = str(operator.get("sub") or "").strip()
    try:
        decided = await rv.decide_review(
            db,
            review_id=review_id,
            decision=rv.STATUS_DECLINED,
            decided_by=principal_sub,
        )
    except rv.ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Operator review decline failed for %s: %s", review_id, exc)
        raise HTTPException(status_code=500, detail="review_decline_failed") from exc
    return _decision_payload(decided, "declined")


class ReviewExecuteRequest(BaseModel):
    """Execute a confirmed review.

    Carries no action parameters, deliberately. The customer, reason and
    amount all come from the persisted review; a browser that could supply
    them could execute a different credit than the one a person confirmed.

    ``expectedActionHash`` is optional stale-view protection, never a source
    of execution parameters.
    """

    expectedActionHash: Optional[str] = Field(default=None, min_length=64, max_length=64)


@router.post("/reviews/{review_id}/execute")
async def execute_review(
    request: ReviewExecuteRequest,
    review_id: int = Path(..., ge=1),
    operator: Dict[str, Any] = Depends(require_operator),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """Run the credit a person confirmed, through the configured rail.

    Managed rail: ``give_store_credit`` runs through the Gateway with the staff
    member's own token, so Cedar authorizes a person. Local rail: it runs in
    process through the same ``store_tools`` function. Either way the result is
    one ``store_credits`` row and one ``tool_audit`` row for the review's key,
    and a retry keeps both counts at one.
    """
    from services import governed_execution as ge
    from services import operator_review as rv

    principal_sub = str(operator.get("sub") or "").strip()
    if not principal_sub:
        raise HTTPException(status_code=401, detail="actor_required")

    try:
        row = await rv.get_review(db, review_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Operator review load failed for %s: %s", review_id, exc)
        raise HTTPException(status_code=503, detail="review_unavailable") from exc
    if not row:
        raise HTTPException(status_code=404, detail=f"Unknown review: {review_id}")

    # Stale-view check before anything else, so a desk showing old terms never
    # starts an execution it would misreport.
    if request.expectedActionHash:
        import hmac

        if not hmac.compare_digest(
            str(row.get("action_hash") or ""), request.expectedActionHash
        ):
            raise HTTPException(status_code=409, detail="parameters_changed")

    try:
        outcome = await ge.execute_confirmed_review(
            db,
            row,
            operator_sub=principal_sub,
            access_token=str(operator.get("access_token") or "") or None,
            engine_state=await _policy_engine_state(row),
        )
    except ge.GovernedRailUnavailable as exc:
        # Not a failure to execute: a refusal to execute ungoverned. The body names
        # what is missing so the operator can fix the deployment rather than retry.
        logger.warning("governed rail unavailable for review %s: %s", review_id, exc.reason)
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
    except ge.ExecutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Governed execution failed for review %s: %s", review_id, exc)
        raise HTTPException(status_code=500, detail="execution_failed") from exc

    payload = outcome.as_payload()
    payload["reviewId"] = review_id
    return payload


async def _policy_engine_state(row: Dict[str, Any]):
    """Read the policy engine's declared state, or None when unavailable.

    Returning None is honest: without the engine's mode, a Gateway call that
    returned cannot be classified as ALLOW rather than an unenforced
    observation, so the policy axis reports EVALUATION_INCOMPLETE instead of
    guessing.
    """
    from services import governed_execution as ge

    try:
        from services.managed_policy import engine_state_for_action

        state = await engine_state_for_action(ge.gateway_action_id(str(row["action"])))
        return ge.PolicyEngineState.from_engine_read(state)
    except Exception as exc:  # noqa: BLE001
        logger.info("policy engine state unavailable: %s", exc)
        return None


# The four axes, resolved from what has actually happened. They are independent
# on purpose: a single `governed: true` boolean would let a human decision imply
# an authorization decision, which is the confusion this desk exists to dismantle.
#
# These are the PRE-EXECUTION readings. They are superseded the moment an
# execution produces verdicts, in `_assurance_from_receipt`.
_ASSURANCE_BY_HUMAN_STATE = {
    "confirmation_required": {
        "human": "CONFIRMATION_REQUIRED",
        "policy": "PENDING",
        "aurora": "NOT_EVALUATED",
        "evidence": "PENDING",
    },
    "confirmed": {
        "human": "CONFIRMED",
        "policy": "PENDING",
        "aurora": "NOT_EVALUATED",
        "evidence": "PENDING",
    },
    "declined": {
        "human": "DECLINED",
        "policy": "NOT_EVALUATED",
        "aurora": "NOT_REACHED",
        "evidence": "NO_EXECUTION",
    },
}


def _assurance(human_state: str) -> Dict[str, str]:
    return dict(
        _ASSURANCE_BY_HUMAN_STATE.get(
            human_state, _ASSURANCE_BY_HUMAN_STATE["confirmation_required"]
        )
    )


def _assurance_from_receipt(
    human_state: str, receipt: Optional[Dict[str, Any]]
) -> Dict[str, str]:
    """The four axes once an execution has produced verdicts.

    The human axis stays the human axis: a confirmation is not revised by what
    the governance layers went on to decide. The other three come from the
    stored receipt and from nowhere else.
    """
    if not receipt:
        return _assurance(human_state)
    base = _assurance(human_state)
    return {
        "human": base["human"],
        "policy": str(receipt.get("policy_outcome") or base["policy"]),
        "aurora": str(receipt.get("aurora_outcome") or base["aurora"]),
        "evidence": str(receipt.get("evidence_outcome") or base["evidence"]),
    }


def _receipt_payload(receipt: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The execution receipt, for a surface that reconstructs what happened.

    Carries the attribution the axes need: which rail ran, which engine
    answered, in what mode, and under which two principals.
    """
    if not receipt:
        return None
    from services import operator_review as rv

    return {
        "receiptId": int(receipt.get("receipt_id") or 0),
        "executionTurnId": receipt.get("execution_turn_id") or "",
        "tool": receipt.get("tool") or "",
        "gatewayActionId": receipt.get("gateway_action_id") or "",
        "rail": receipt.get("rail") or "",
        "actorPrincipal": receipt.get("actor_principal") or "",
        "customerSubject": receipt.get("customer_subject"),
        "policyEngineId": receipt.get("policy_engine_id") or "",
        "gatewayMode": receipt.get("gateway_mode") or "",
        "matchingForbids": list(receipt.get("matching_forbids") or []),
        "idempotencyKey": receipt.get("idempotency_key") or "",
        "notes": rv.parse_json(receipt.get("notes")) or {},
        "recordedAt": _iso(receipt.get("created_at")),
    }
