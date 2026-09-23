"""``/api/operator`` routes — the Pellier Operator clienteling desk.

  * ``GET  /api/operator/clients``            the book: every client, one row each
  * ``GET  /api/operator/clients/{id}``       one client record with order history
  * ``POST /api/operator/reviews/{id}/execute``    the only governed write path

Design notes
------------

**Every route is gated, reads included.** Anonymous callers get ``401``,
authenticated shoppers get ``403``, and members of ``auth.OPERATOR_GROUP`` get
access. `require_operator` still guarantees a verified non-empty ``sub`` to
attribute a mutation to; an optional-auth write handler is an unauthenticated
write path wearing an authenticated signature, so this module does not have one.

Reads used to be open, and the stated reason was real: a ``GET`` that needs no
token means the desk is never a blank ``401`` on a fresh box or a clone with no
Cognito wired. That reliability argument does not survive what the reads
return. ``GET /clients`` enumerates every client's standing, preferences and
order history; ``GET /reviews/{id}`` returns the governance verdicts and their
lineage. Workshop reliability has to come from deterministic group and user
seeding plus a bootstrap smoke test, not from anonymous access to customer
data. A workshop about governance cannot teach an internally inconsistent
security model, and the sign-in prompt is the honest failure.

**Aurora is the source of truth.** Every field here is selected from
``pellier.customers``, ``pellier.orders``, and ``pellier.product_catalog``.
There is no committed frontend copy of the client book, because UI state is
not evidence.

**Two governed actions, one execution path.** Resolving a return calls
``BusinessLogic.initiate_return``; issuing a goodwill credit calls
``BusinessLogic.issue_credit``. Neither has a direct action endpoint.
The Operator Concierge prepares one proposal, a person confirms the exact
review, and ``POST /reviews/{id}/execute`` claims the idempotency key in
``pellier.write_operations`` before touching domain state. A replay therefore
applies exactly once and produces the same durable evidence shape: write event,
Aurora rows, and a ``pellier.tool_audit`` record.

A credit is a money movement, so it has its own table rather than being
recorded as a note on a return. A return is not a credit, and an auditor
asking what was paid out cannot answer it from the returns table. The $500
ceiling is enforced by a CHECK constraint on ``pellier.store_credits``, not by
prompt text.

The Gateway publishes ``issue_credit`` with a staff-only permit. Shopper tokens
have no permit for it; the absence of shopper permission is distinct from an
unpublished tool. On the desk, ``require_operator`` checks group membership.
The pre-token trigger derives ``custom:staff_scope`` from that membership, and
both ``initiate_return_staff_scope`` and ``issue_credit_staff_scope`` require it.
The Lab 4 ownership forbid applies to customer-claim holders, not staff.
A direct staff Gateway call does not pass through the desk's human-review
workflow; the Gateway policy must not be described as proof of human approval.
See the `baseline_policies` docstring in
`scripts/deploy/render_agentcore_project.py`.

**Ownership is enforced in SQL, not here.** ``initiate_return`` joins
``orders`` against the customer and product before it writes, so an operator
cannot resolve a return for an item a client never bought. This module does not
re-check that; duplicating the gate would let the two drift.
"""

from __future__ import annotations

import json
import logging
import uuid
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.auth import require_operator
from services.data_source import database_source_label

logger = logging.getLogger(__name__)

# ONE authorization boundary for the whole prefix. Declared on the router rather than
# annotated per handler for two reasons: a new route inherits it instead of being
# forgotten, and there is no per-route judgement call about whether a read is "sensitive
# enough". A client record carries standing, preferences, order history, tickets and
# credits; a review record carries the governance verdicts. Neither is public.
router = APIRouter(
    prefix="/api/operator",
    tags=["operator"],
    dependencies=[Depends(require_operator)],
)

# The three rungs, mirroring the CHECK constraint in migration 018.
MEMBERSHIP_RUNGS = ("registered", "circle", "maison")

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

# The hero personas are shoppers who also appear in the book. Flagging them
# lets the console offer "view what they see" only where a storefront handoff
# genuinely exists, instead of promising one for every client.
_HERO_CUSTOMER_IDS = {"CUST-MARCO": "marco", "CUST-ANNA": "anna", "CUST-THEO": "theo"}

_BOOK_SELECT = """
    SELECT
        c.id                                   AS customer_id,
        c.name                                 AS name,
        c.membership                           AS membership,
        c.spend_12mo                           AS spend_12mo,
        c.preferences_summary                  AS preferences_summary,
        COUNT(o.id)                            AS order_count,
        COALESCE(SUM(p.price * o.quantity), 0) AS order_value,
        MAX(o.placed_at)                       AS last_order_at,
        -- The client's live service request, if one is open. The book row
        -- otherwise has to describe a case from `preferences_summary`, which
        -- is a free-text brief and not a statement of what is happening.
        t.subject                              AS open_case,
        t.status                               AS open_case_status
      FROM pellier.customers c
      LEFT JOIN pellier.orders o
             ON o.customer_id = c.id
      LEFT JOIN pellier.product_catalog p
             ON p."productId" = o.product_id
      LEFT JOIN LATERAL (
            SELECT subject, status
              FROM pellier.support_tickets
             WHERE customer_id = c.id
               AND status IN ('open', 'pending')
             ORDER BY opened_at DESC
             LIMIT 1
      ) t ON TRUE
     -- left() rather than a LIKE prefix match: psycopg parses a bare percent
     -- sign as a placeholder even when no parameters are bound, and it does
     -- not skip comments, so a percent anywhere in this string raises before
     -- the query reaches Postgres.
     WHERE left(c.id, 5) = 'CUST-'
       AND c.id <> 'CUST-FRESH'
     GROUP BY c.id, c.name, c.membership, c.spend_12mo, c.preferences_summary,
              t.subject, t.status
     ORDER BY c.spend_12mo DESC, c.name ASC
"""

_CLIENT_SELECT = """
    SELECT
        c.id                  AS customer_id,
        c.name                AS name,
        c.membership          AS membership,
        c.spend_12mo          AS spend_12mo,
        c.preferences_summary AS preferences_summary
      FROM pellier.customers c
     WHERE c.id = %s
"""

_ORDERS_SELECT = """
    SELECT
        o.id            AS order_id,
        o.product_id    AS product_id,
        o.quantity      AS quantity,
        o.placed_at     AS placed_at,
        p.name          AS product_name,
        p.brand         AS brand,
        p.price         AS price,
        p."imgUrl"      AS image_url
      FROM pellier.orders o
      JOIN pellier.product_catalog p
             ON p."productId" = o.product_id
     WHERE o.customer_id = %s
     ORDER BY o.placed_at DESC
"""


_TICKETS_SELECT = """
    SELECT ticket_id, subject, status, channel, last_note, opened_at, resolved_at
      FROM pellier.support_tickets
     WHERE customer_id = %s
     ORDER BY opened_at DESC
"""

_CREDITS_SELECT = """
    SELECT credit_id, amount_cents, currency, reason, issued_by, created_at
      FROM pellier.store_credits
     WHERE customer_id = %s
     ORDER BY created_at DESC
"""

# Authoritative return state. Deliberately separate from the support ticket that
# may *assert* a return happened: Jessica's TKT-2026-3015 says a return was
# received and its refund disputed, while `pellier.returns` holds no row for her.
# Those are different kinds of evidence and the console must be able to show the
# disagreement rather than resolve it by guessing.
_RETURNS_SELECT = """
    SELECT r.id,
           r.product_id,
           p.name AS product_name,
           r.reason,
           r.status,
           r.requested_at
      FROM pellier.returns r
      LEFT JOIN pellier.product_catalog p ON p."productId" = r.product_id
     WHERE r.customer_id = %s
     ORDER BY r.requested_at DESC
"""


# Tokens too generic to identify a product; matching on them would pull in
# every item the client owns and defeat the scoping.
_TICKET_MATCH_STOPWORDS = frozenset({"pellier", "luxury", "bath", "sage"})
_TICKET_MIN_TOKEN = 4


def _ticket_named_product_ids(
    tickets: List[Dict[str, Any]], orders: List[Dict[str, Any]]
) -> set[str]:
    """Product ids the open tickets name, by token overlap with product names.

    Mirrors the candidate matcher the Operator checkpoint uses, so the flag the
    backend computes and the list the desk offers cannot disagree.

    Returns an empty set when nothing matches, which callers must read as "the
    ticket does not identify a product" rather than "no products". Narrowing to
    an empty set would resolve every dispute automatically, which is the
    opposite of the intended failure direction.
    """
    ticket_text = " ".join(
        f"{t.get('subject', '')} {t.get('lastNote', '')}"
        for t in tickets
        if t.get("status") in {"open", "pending"}
    ).lower()
    if not ticket_text.strip():
        return set()

    named: set[str] = set()
    for order in orders:
        name = str(order.get("productName") or "").lower()
        tokens = re.split(r"[^a-z0-9]+", name)
        if any(
            len(token) >= _TICKET_MIN_TOKEN
            and token not in _TICKET_MATCH_STOPWORDS
            and token in ticket_text
            for token in tokens
        ):
            named.add(str(order.get("productId") or ""))
    return named


def _return_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """One authoritative return record.

    `pellier.returns` has `requested_at` and `status`; it has never had `created_at`.
    A prior query selected `r.created_at` and converted the resulting
    ``UndefinedColumn`` into an empty list. That made the authoritative return
    count zero for every client. Client evidence reads now fail the whole record
    explicitly instead: an unavailable ledger must never look like an empty one.
    """
    requested = row.get("requested_at")
    return {
        "returnId": int(row.get("id") or 0),
        "productId": str(row.get("product_id") or ""),
        "productName": row.get("product_name") or "",
        "reason": row.get("reason") or "",
        # Lifecycle state is the authoritative thing about a return; a bare timestamp
        # cannot tell an operator whether it was approved.
        "status": row.get("status") or "",
        "requestedAt": (
            requested.isoformat() if hasattr(requested, "isoformat") else requested
        ),
    }


def _client_slug(customer_id: str) -> str:
    """`CUST-JESSICA` -> `jessica`. Drives the portrait filename."""
    return str(customer_id or "").replace("CUST-", "", 1).lower()


def _normalise_membership(value: Any) -> str:
    """Never let an unrecognised rung reach the console as a label."""
    text = str(value or "").strip().lower()
    return text if text in MEMBERSHIP_RUNGS else "registered"


def _as_float(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def _book_row(row: Dict[str, Any]) -> Dict[str, Any]:
    customer_id = str(row.get("customer_id") or "")
    return {
        "customerId": customer_id,
        "slug": _client_slug(customer_id),
        "name": row.get("name") or customer_id,
        "membership": _normalise_membership(row.get("membership")),
        "spend12mo": _as_float(row.get("spend_12mo")),
        "orderCount": int(row.get("order_count") or 0),
        "orderValue": _as_float(row.get("order_value")),
        "lastOrderAt": _iso(row.get("last_order_at")),
        "note": row.get("preferences_summary") or "",
        "personaId": _HERO_CUSTOMER_IDS.get(customer_id),
        # What is actually happening for this client, when something is. `note`
        # is a preferences brief and cannot answer that: reading a case out of
        # it means parsing prose and calling the result a fact.
        "openCase": row.get("open_case") or None,
        "openCaseStatus": row.get("open_case_status") or None,
    }


def _order_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "orderId": int(row.get("order_id") or 0),
        "productId": str(row.get("product_id") or ""),
        "productName": row.get("product_name") or "",
        "brand": row.get("brand") or "",
        "price": _as_float(row.get("price")),
        "quantity": int(row.get("quantity") or 1),
        "placedAt": _iso(row.get("placed_at")),
        "imageUrl": row.get("image_url") or "",
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
        "amount": f"{cents / 100:.2f}",
        "currency": row.get("currency") or "USD",
        "reason": row.get("reason") or "",
        "issuedBy": row.get("issued_by"),
        "createdAt": _iso(row.get("created_at")),
    }


async def _read_one(db: Any, sql: str, *args: Any, label: str) -> Optional[Dict[str, Any]]:
    """Read one client-record row, retaining database failures."""
    try:
        row = await db.fetch_one(sql, *args)
        return dict(row) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Operator %s query failed", label)
        raise RuntimeError(f"Operator {label} query failed") from exc


async def _read_rows(db: Any, sql: str, *args: Any, label: str) -> List[Dict[str, Any]]:
    """Read client-record rows, retaining database failures.

    A partial client record cannot support an action. In particular, treating a
    failed returns or tickets read as ``[]`` turns unavailable evidence into a
    false "nothing on file" claim. The route translates a failed fan-out into
    an explicit 503 rather than returning a mixture of facts and invented zeroes.
    """
    try:
        rows = await db.fetch_all(sql, *args)
        return [dict(r) for r in (rows or [])]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Operator %s query failed", label)
        raise RuntimeError(f"Operator {label} query failed") from exc


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Operator Concierge sessions
# ---------------------------------------------------------------------------


class ConciergeTurnRequest(BaseModel):
    """The ONLY thing a browser may submit for a Concierge turn.

    Deliberately one field plus a transport key. Everything that constitutes a claim
    about what happened — the role, the turn id, the client binding, the operator
    identity, evidence, sources, review links, assurance state — is server-derived.
    A body that could carry `role: assistant` is a forgery surface, not an API.
    """

    message: str = Field(..., min_length=1, max_length=4000)
    # Transport idempotency, NOT domain lineage: it stops a network retry creating a
    # second turn. `turn_id` remains the only lineage identity and the browser
    # cannot supply it.
    transportKey: Optional[str] = Field(default=None, max_length=128)


@router.post("/clients/{client_id}/concierge/sessions")
async def create_concierge_session(
    client_id: str = Path(..., min_length=1, max_length=64),
    db: Any = Depends(get_db_service),
    operator: Dict[str, Any] = Depends(require_operator),
) -> Dict[str, Any]:
    """Open a Concierge thread bound to this client and this operator.

    Not a consequential action, so no review: it records who is looking at whose
    record. The client comes from the path and the operator from the verified token;
    neither is accepted from a body.
    """
    from services import operator_concierge_sessions as sessions

    try:
        return await sessions.create_session(
            db, customer_id=client_id, operator_sub=str(operator.get("sub") or "")
        )
    except sessions.SessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc


@router.get("/clients/{client_id}/concierge/sessions/latest")
async def latest_concierge_session(
    client_id: str = Path(..., min_length=1, max_length=64),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """The most recent operator-gated Concierge session for this client."""
    from services import operator_concierge_sessions as sessions

    session_id = await sessions.latest_session(db, customer_id=client_id)
    return {"sessionId": session_id}


@router.get("/clients/{client_id}/concierge/sessions/{session_id}")
async def read_concierge_session(
    client_id: str = Path(..., min_length=1, max_length=64),
    session_id: str = Path(..., min_length=1, max_length=128),
    limit: int = 40,
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """Bounded replay, ordered by the serial primary key.

    `require_session` proves the session belongs to BOTH this surface and this
    client, so a session id from another client's record cannot be read here.
    """
    from services import operator_concierge_sessions as sessions

    try:
        return await sessions.load_history(
            db, session_id=session_id, customer_id=client_id, limit=limit
        )
    except sessions.SessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc


@router.post("/clients/{client_id}/concierge/sessions/{session_id}/turns")
async def start_concierge_turn(
    payload: ConciergeTurnRequest,
    client_id: str = Path(..., min_length=1, max_length=64),
    session_id: str = Path(..., min_length=1, max_length=128),
    db: Any = Depends(get_db_service),
    operator: Dict[str, Any] = Depends(require_operator),
) -> Dict[str, Any]:
    """Run one read-only Concierge turn.

    The operator's request is durable before any model call, so a synthesis failure
    leaves a recoverable turn rather than losing what was asked. Read-only: no
    review is proposed and no governed write is attempted.
    """
    from services import operator_concierge, operator_concierge_sessions as sessions

    try:
        return await operator_concierge.run_turn(
            db,
            customer_id=client_id,
            session_id=session_id,
            operator_sub=str(operator.get("sub") or ""),
            request=payload.message,
            transport_key=(payload.transportKey or ""),
        )
    except sessions.SessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc


@router.get("/concierge/config")
async def concierge_config() -> Dict[str, Any]:
    """Whether the Concierge composer may submit a development turn.

    Separate from `/capabilities`, which reports governed business capability. This
    reports build state: whether orchestration exists to answer a question yet.
    Conflating the two would let a governance state look like a missing feature.
    """
    from config import settings
    from services import operator_concierge

    # Orchestration availability is a property of the code, not a flag: the
    # orchestrator either implements a workflow or it does not. The flag remains a
    # separate release control so the interactive composer can be held back even
    # once orchestration exists.
    workflows = list(operator_concierge.SUPPORTED_WORKFLOWS)
    orchestration_available = bool(workflows)
    flag = bool(getattr(settings, "OPERATOR_CONCIERGE_COMPOSER_ENABLED", False))
    enabled = orchestration_available and flag
    return {
        "composerEnabled": enabled,
        "orchestrationAvailable": orchestration_available,
        "supportedWorkflowKinds": workflows,
        "orchestration": "available" if orchestration_available else "pending",
        "dataSource": operator_concierge.database_source_label(),
        "note": (
            "Ask about this client's recent activity, orders, or service history."
            if enabled
            else "Investigation is not yet available on this surface."
        ),
    }


@router.post("/clients/{client_id}/concierge/sessions/{session_id}/turns/stream")
async def stream_concierge_turn(
    payload: ConciergeTurnRequest,
    client_id: str = Path(..., min_length=1, max_length=64),
    session_id: str = Path(..., min_length=1, max_length=128),
    db: Any = Depends(get_db_service),
    operator: Dict[str, Any] = Depends(require_operator),
) -> StreamingResponse:
    """The same turn, with real progress as each step completes.

    SSE rather than polling because this deployment already streams
    `text/event-stream` from `routes/agent.py` through the workshop proxy, so the
    topology is proven and no queue, websocket or extra service is introduced.

    Every event follows work that actually finished. The one exception is a single
    `running` event when the request goes to Bedrock, which is a real state rather
    than a simulated tick — nothing is ever reported `complete` before it is.
    """
    from services import operator_concierge

    async def events() -> Any:
        try:
            async for kind, data in operator_concierge.stream_turn(
                db,
                customer_id=client_id,
                session_id=session_id,
                operator_sub=str(operator.get("sub") or ""),
                request=payload.message,
                transport_key=(payload.transportKey or ""),
            ):
                yield f"event: {kind}\ndata: {json.dumps(data, default=str)}\n\n"
        except Exception as exc:  # noqa: BLE001 - the stream must close cleanly
            detail = getattr(exc, "code", None) or "operator_unavailable"
            logger.warning("concierge stream failed: %s", exc)
            yield f"event: error\ndata: {json.dumps({'detail': detail})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            # Same proxy hints the agent stream already relies on.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/capabilities")
async def get_capabilities_route(refresh: bool = False) -> Dict[str, Any]:
    """What the Operator can actually do right now.

    Derived from live Gateway and policy state, not from the source tool registry:
    `initiate_return` is currently published and has zero matching permits, while
    `issue_credit` is not published at all. Those are different causes with
    different futures, and a frontend constant cannot tell them apart.

    Cached for a short TTL so a page load never triggers a control-plane call, and
    fail-closed: if live state cannot be read, governed writes report
    `temporarily_unavailable`, never `available`.
    """
    from services import operator_capabilities

    return operator_capabilities.get_capabilities(force_refresh=refresh)


@router.get("/clients")
async def list_clients(db: Any = Depends(get_db_service)) -> Dict[str, Any]:
    """The book. One row per client, richest standing first.

    Returns an empty list rather than a 500 when the client book has not been
    seeded, so the console can render an honest "no clients seeded" state
    instead of an error the operator cannot act on.
    """
    try:
        rows = await db.fetch_all(_BOOK_SELECT)
    except Exception as exc:  # noqa: BLE001 - surfaced as an explicit state
        logger.error("Operator book query failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "client_book_unavailable: could not read pellier.customers. "
                "Confirm migration 018_client_book.sql has been applied."
            ),
        ) from exc

    clients = [_book_row(dict(r)) for r in (rows or [])]
    by_rung: Dict[str, int] = {rung: 0 for rung in MEMBERSHIP_RUNGS}
    for client in clients:
        by_rung[client["membership"]] += 1

    return {
        "clients": clients,
        "total": len(clients),
        "byMembership": by_rung,
    }


@router.get("/clients/{client_id}")
async def get_client(
    client_id: str = Path(..., min_length=1, max_length=64),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """One client record: standing plus the order history behind it."""
    # All four reads are independent, so they run concurrently.
    #
    # Sequentially they cost four Aurora round trips — measured at ~2.5s against
    # the workshop cluster, against ~0.65s for the book, which does one. The
    # queries were never slow; waiting for them one at a time was.
    import asyncio

    client_task = asyncio.create_task(_read_one(db, _CLIENT_SELECT, client_id, label="client"))
    orders_task = asyncio.create_task(_read_rows(db, _ORDERS_SELECT, client_id, label="orders"))
    tickets_task = asyncio.create_task(_read_rows(db, _TICKETS_SELECT, client_id, label="tickets"))
    credits_task = asyncio.create_task(_read_rows(db, _CREDITS_SELECT, client_id, label="credits"))
    # Returns joins the same fan-out rather than adding a fifth round trip in
    # series. Adding it sequentially would have undone the 2.5s -> 0.65s win.
    returns_task = asyncio.create_task(_read_rows(db, _RETURNS_SELECT, client_id, label="returns"))
    outcomes = await asyncio.gather(
        client_task,
        orders_task,
        tickets_task,
        credits_task,
        returns_task,
        return_exceptions=True,
    )
    failure = next(
        (outcome for outcome in outcomes if isinstance(outcome, Exception)),
        None,
    )
    if failure is not None:
        logger.error("Operator client record evidence is unavailable for %s", client_id)
        raise HTTPException(
            status_code=503,
            detail=(
                "client_record_evidence_unavailable: the complete client record "
                "could not be read from Aurora. No absence claim was made."
            ),
        ) from failure
    row, order_rows, ticket_rows, credit_rows, return_rows = outcomes

    if not row:
        raise HTTPException(status_code=404, detail=f"Unknown client: {client_id}")

    orders: List[Dict[str, Any]] = [_order_row(dict(r)) for r in (order_rows or [])]
    record = _book_row(dict(row))
    # The book query aggregates these; a single-client read derives them from
    # the order rows it already has rather than issuing a second aggregate.
    record["orderCount"] = len(orders)
    record["orderValue"] = round(
        sum(o["price"] * o["quantity"] for o in orders), 2
    )
    record["lastOrderAt"] = orders[0]["placedAt"] if orders else None

    tickets = [_ticket_row(r) for r in (ticket_rows or [])]
    credits = [_credit_row(r) for r in (credit_rows or [])]

    credit_cents = sum(c["amountCents"] for c in credits)
    record["openTicketCount"] = sum(
        1 for t in tickets if t["status"] in ("open", "pending")
    )
    record["creditBalanceCents"] = credit_cents
    record["creditBalance"] = f"{credit_cents / 100:.2f}"

    returns = [_return_row(dict(r)) for r in (return_rows or [])]
    record["returnCount"] = len(returns)

    # Three evidence kinds about returns, kept apart on purpose:
    #
    #   returns          authoritative domain state
    #   tickets          a service assertion, which may claim a return that has no row
    #   preferences      prose context, never authoritative
    #
    # Jessica is the live case: TKT-2026-3015 states a return was received and its
    # refund disputed, `returns` holds nothing, and her preferences_summary mentions
    # a dispute. Collapsing those into "she returned it" would invent a fact. The
    # flag below lets a surface show the disagreement instead of resolving it.
    asserts_return = any(
        "return" in (t_.get("subject", "") + " " + t_.get("lastNote", "")).lower()
        for t_ in tickets
    )
    # Scope the conflict to the products the ticket actually names.
    #
    # This used to read `asserts_return and not returns` -- any return row for
    # this customer resolved the dispute. Two problems with that. It is not
    # true: a return for an unrelated product says nothing about a disputed
    # refund on the catchall. And it made the Operator demonstration erasable
    # from another lab, because Lab 4's identity matrix writes a real
    # `pellier.returns` row for this same customer on whichever product she
    # ordered first. Running the matrix before the Operator walkthrough
    # silently emptied the human checkpoint -- not replayed, absent -- and only
    # a full governed reset brought it back.
    disputed_products = _ticket_named_product_ids(tickets, orders)
    unresolved = [
        r for r in returns
        if not disputed_products or r.get("productId") in disputed_products
    ]
    record["returnEvidence"] = {
        "authoritativeReturnCount": len(returns),
        "supportAssertsReturn": asserts_return,
        "unconfirmedReturnAssertion": asserts_return and not unresolved,
        # Named so a surface can say which products the disagreement is about,
        # rather than implying the client's whole history is in dispute.
        "disputedProductIds": sorted(disputed_products),
    }

    return {
        "client": record,
        "orders": orders,
        "tickets": tickets,
        "credits": credits,
        "returns": returns,
        # Which database answered. The record surface contrasts what a ticket
        # CLAIMS against what the authoritative store HOLDS, and that column
        # has to name the store it read rather than assume Aurora: the same
        # build serves local PostgreSQL in development.
        "dataSource": database_source_label(),
    }


# ---------------------------------------------------------------------------
# Reviews - the durable handoff from Pellier
# ---------------------------------------------------------------------------
#
# The router-level dependency gates reads and writes alike. Decision handlers
# still request the verified operator payload directly because attribution is
# part of the row they write.
#
# Note what confirming does NOT do: it does not call ``BusinessLogic``. A
# confirmed review is a person saying yes; whether the system is then
# authorised to act is a separate event with its own evidence, initiated only
# by the execute endpoint.


def _review_payload(
    row: Dict[str, Any], receipt: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Shape one review for the console.

    Workflow state, plus the verdicts of its latest execution attempt when one exists.
    ``receipt`` is passed in rather than read here so the queue can batch a single
    round trip instead of one read per row.
    """
    from services import operator_review as rv

    status = str(row.get("status") or rv.STATUS_PENDING)
    args = row.get("args")
    if isinstance(args, str):
        import json as _json

        try:
            args = _json.loads(args)
        except ValueError:
            args = {}
    recommendation = row.get("recommendation")
    if isinstance(recommendation, str):
        import json as _json

        try:
            recommendation = _json.loads(recommendation)
        except ValueError:
            recommendation = {}

    # The human axis, named rather than derived in the UI so every surface agrees
    # on what a status means.
    human_state = {
        rv.STATUS_PENDING: "confirmation_required",
        rv.STATUS_CONFIRMED: "confirmed",
        rv.STATUS_DECLINED: "declined",
    }.get(status, "confirmation_required")

    return {
        "reviewId": int(row.get("review_id") or 0),
        "customerId": str(row.get("customer_id") or ""),
        "customerName": row.get("customer_name") or row.get("customer_id") or "",
        "slug": _client_slug(str(row.get("customer_id") or "")),
        # Resolved here for the same reason the client payloads resolve it: the
        # three heroes keep their portraits in the persona maps, not the client
        # maps, and a surface that has only a slug cannot tell the two apart
        # without guessing. Without this the review queue showed Marco as a
        # monogram while his artwork sat in the repository.
        "personaId": _HERO_CUSTOMER_IDS.get(str(row.get("customer_id") or "")),
        "action": str(row.get("action") or ""),
        "parameters": args or {},
        "status": status,
        "humanState": human_state,
        # Resolved server-side so no surface can infer one axis from another.
        "assurance": _assurance_from_receipt(human_state, receipt),
        # Named separately from the axes: the axes are the verdicts, this is what
        # produced them. A surface can show ALLOW without it, but not defend it.
        "execution": _receipt_payload(receipt),
        "sourceTurnId": row.get("source_turn_id"),
        "executionTurnId": row.get("execution_turn_id"),
        "orderId": int(row["order_id"]) if row.get("order_id") else None,
        "productName": row.get("product_name") or None,
        "issue": row.get("issue") or "",
        "recommendation": recommendation or {},
        # Echoed so the console can send it back on confirm. It is a fingerprint
        # of parameters the operator was shown, not a secret.
        "actionHash": row.get("action_hash") or "",
        "decidedBy": row.get("decided_by"),
        # Three identities kept apart: who asked, who decides, and the customer
        # the write runs as. A persona chosen in the storefront is not an asker.
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
    """The review queue. Pending first, so the desk opens on what needs a human.

    Returns an empty queue rather than a 503 when the table is unreachable: an
    operator who sees "nothing waiting" because a query failed is misinformed,
    so the count and the list come from the same read and the failure is loud in
    the log and visible as an explicit unavailable flag.
    """
    from services import operator_review as rv

    try:
        rows = await rv.list_reviews(db, status=status)
    except Exception as exc:  # noqa: BLE001
        logger.error("Operator review queue query failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "review_queue_unavailable: could not read pellier.approvals. "
                "Confirm migration 020_operator_review.sql has been applied."
            ),
        ) from exc

    from services import governed_execution as ge

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


@router.get("/reviews/{review_id}")
async def get_review(
    review_id: int = Path(..., ge=1),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """One review, with current truth resolved from the systems that own it.

    The review row supplies references and workflow state. Membership, spend,
    the order, the product, live warehouse stock, and prior returns are read now,
    which is why a six-week-old review still renders a correct client standing.
    """
    from services import operator_review as rv

    try:
        row = await rv.get_review(db, review_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Operator review query failed for %s: %s", review_id, exc)
        raise HTTPException(status_code=503, detail="review_unavailable") from exc

    if not row:
        raise HTTPException(status_code=404, detail=f"Unknown review: {review_id}")

    from services import governed_execution as ge

    # The verdicts of the latest execution attempt, if there was one. Read here rather
    # than derived in `_review_payload`, so the queue can batch the same lookup.
    receipt = await ge.latest_receipt(db, review_id)

    hydrated = await rv.hydrate_review(db, row)
    customer = hydrated.get("customer") or {}
    product = hydrated.get("product") or {}
    warehouses = hydrated.get("warehouses") or []

    total_units = sum(int(w.get("quantity") or 0) for w in warehouses)
    from services import shopper_handoff

    try:
        handoff = await shopper_handoff.resolve_for_review(
            db,
            review_id=review_id,
            expected_customer_id=str(row.get("customer_id") or ""),
        )
    except shopper_handoff.HandoffIntegrityError as exc:
        logger.error("Shopper handoff integrity failed for review %s", review_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "review": _review_payload(row, receipt),
        "shopperHandoff": handoff,
        # Authoritative, current, and labelled as such.
        "client": {
            "customerId": customer.get("id") or row.get("customer_id"),
            "name": customer.get("name") or "",
            "membership": _normalise_membership(customer.get("membership")),
            "spend12mo": _as_float(customer.get("spend_12mo")),
            "note": customer.get("preferences_summary") or "",
            "personaId": _HERO_CUSTOMER_IDS.get(str(row.get("customer_id") or "")),
        },
        "order": _review_order(hydrated.get("order")),
        "product": {
            "productId": str(product.get("product_id") or ""),
            "name": product.get("name") or "",
            "brand": product.get("brand") or "",
            "price": _as_float(product.get("price")),
            "catalogQuantity": int(product.get("quantity") or 0),
            "imageUrl": product.get("image_url") or "",
        }
        if product
        else None,
        # Replacement availability is derived here, from live rows, and never
        # stored on the review. A stored "replacement available" decays silently.
        "fulfilment": {
            "totalUnits": total_units,
            "replacementAvailable": total_units > 0,
            # Whether there is any per-location evidence at all. Without this the
            # surface reported "No replacement stock is available right now" for a
            # product that simply has no warehouse rows — 960 of 1,000 catalog rows —
            # which states an inventory fact the database never established. The
            # distinction is the same one `services/inventory_evidence.py` draws
            # between an observed zero and an unverified absence.
            "availabilityVerified": bool(warehouses),
            "warehouses": [
                {
                    "warehouseId": w.get("warehouse_id"),
                    "displayName": w.get("display_name"),
                    "city": w.get("city"),
                    "quantity": int(w.get("quantity") or 0),
                    "shipWindowMin": int(w.get("ship_window_min") or 0),
                    "shipWindowMax": int(w.get("ship_window_max") or 0),
                }
                for w in warehouses
            ],
        },
        # pellier.orders has no status column, so the only authoritative
        # lifecycle state for this piece is its return history.
        "returns": [
            {
                "returnId": int(r.get("id") or 0),
                "productId": str(r.get("product_id") or ""),
                "reason": r.get("reason") or "",
                "status": r.get("status") or "",
                "requestedAt": _iso(r.get("requested_at")),
                "resolvedAt": _iso(r.get("resolved_at")),
            }
            for r in (hydrated.get("returns") or [])
        ],
    }


def _review_order(order: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not order:
        return None
    return {
        "orderId": int(order.get("order_id") or 0),
        "productId": str(order.get("product_id") or ""),
        "productName": order.get("product_name") or "",
        "brand": order.get("brand") or "",
        "price": _as_float(order.get("price")),
        "quantity": int(order.get("quantity") or 1),
        "placedAt": _iso(order.get("placed_at")),
        "imageUrl": order.get("image_url") or "",
    }


class ReplacementRequest(BaseModel):
    orderId: int = Field(ge=1)
    quantity: int = Field(default=1, ge=1, le=100)
    issue: str = Field(min_length=1, max_length=500)


@router.get("/clients/{client_id}/replacements")
async def client_replacements(
    client_id: str,
    replacement_id: uuid.UUID | None = None,
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    from services.replacement_recovery import read_replacements

    try:
        return await read_replacements(db, client_id, str(replacement_id) if replacement_id else None)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="replacement_evidence_unavailable") from exc


@router.post("/clients/{client_id}/replacements/prepare")
async def prepare_replacement(
    client_id: str, request: ReplacementRequest,
    operator: Dict[str, Any] = Depends(require_operator),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    from services import operator_review as rv
    from services.replacement_recovery import prepare

    try:
        review_id = await prepare(
            db, customer_id=client_id, order_id=request.orderId,
            quantity=request.quantity, issue=request.issue.strip(),
            operator_sub=str(operator["sub"]),
        )
    except rv.ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    return {"reviewId": review_id}


class ReviewDecisionRequest(BaseModel):
    """A human decision on a prepared request.

    ``actionHash`` is required to confirm and ignored to decline. Confirming
    means "I agree to this exact mutation", so the console echoes the
    fingerprint it displayed; if any material parameter changed in the meantime
    the fingerprints disagree and the confirmation is refused rather than
    silently applied to different values.

    Declining needs no fingerprint: "do not do this" cannot be invalidated by a
    parameter change.
    """

    actionHash: Optional[str] = Field(default=None, min_length=64, max_length=64)


@router.post("/reviews/{review_id}/confirm")
async def confirm_review(
    request: ReviewDecisionRequest,
    review_id: int = Path(..., ge=1),
    operator: Dict[str, Any] = Depends(require_operator),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """Record that a human confirmed this exact proposed action.

    This performs no business mutation. It writes one row's workflow state and
    returns the four assurance axes as they actually stand: the human has
    decided, and nothing else has happened yet.
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

    return {
        "reviewId": int(decided["id"]),
        "status": decided["status"],
        "humanState": "confirmed",
        "decidedBy": decided["decided_by"],
        "decidedAt": _iso(decided["decided_at"]),
        "assurance": _assurance("confirmed"),
    }


@router.post("/reviews/{review_id}/decline")
async def decline_review(
    review_id: int = Path(..., ge=1),
    operator: Dict[str, Any] = Depends(require_operator),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """Record that a human declined. Nothing is sent anywhere.

    A declined action is deliberately NOT pushed through the governed mutation
    path to demonstrate a denial. Human refusal precedes policy evaluation, so
    manufacturing a Cedar DENY here would invent evidence for a decision that was
    never submitted.
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

    return {
        "reviewId": int(decided["id"]),
        "status": decided["status"],
        "humanState": "declined",
        "decidedBy": decided["decided_by"],
        "decidedAt": _iso(decided["decided_at"]),
        "assurance": _assurance("declined"),
    }


class ReviewExecuteRequest(BaseModel):
    """Execute a confirmed review.

    Carries no action parameters, deliberately. The customer, tool, order,
    reason, and amount all come from the persisted review; a browser that could
    supply them could execute a different mutation than the one a human
    confirmed, while every other check still passed.

    ``expectedActionHash`` is optional stale-view protection: if the console is
    showing an older version of the proposal, the mismatch is caught here rather
    than after the write. It is never a source of execution parameters.
    """

    expectedActionHash: Optional[str] = Field(default=None, min_length=64, max_length=64)


@router.post("/reviews/{review_id}/execute")
async def execute_review(
    request: ReviewExecuteRequest,
    review_id: int = Path(..., ge=1),
    operator: Dict[str, Any] = Depends(require_operator),
    db: Any = Depends(get_db_service),
) -> Dict[str, Any]:
    """Run the governed action a human confirmed, through the managed rail.

    Two principals, and they are not interchangeable:

      * the **operator** is the actor AgentCore Policy authorizes;
      * the **customer subject** is resolved server-side from the review and is
        what Aurora Row-Level Security scopes.

    Every axis in the response comes from a separate artifact. A policy verdict
    appears only when a policy engine produced one.
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

    # Stale-view check before anything else, so a console showing old terms never
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
        logger.warning(
            "governed rail unavailable for review %s: %s", review_id, exc.reason
        )
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

    Returning None is honest: without the engine's mode and policy set, a
    Gateway call that returned cannot be classified as ALLOW rather than an
    unenforced observation, so the policy axis reports NOT_EVALUATED instead of
    guessing.

    Swallowed here, but not forgotten. ``engine_state_for_action`` records the
    failure for the rest of this request, so the decision collector on the
    post-write path declines to repeat the read rather than running the same slow
    control-plane call a second time, and its receipt says the evaluation was
    incomplete and why. The read is also bounded and runs off the event loop, so
    a wedged control plane cannot hold this handler or any other one open.
    """
    from services import governed_execution as ge

    try:
        from services.managed_policy import engine_state_for_action

        state = await engine_state_for_action(ge.gateway_action_id(str(row["action"])))
        # The reader returns the engine's own mapping, which is configuration and
        # explicitly `inferred`. The typed form carries that label through, so a
        # verdict can never be derived from it by accident.
        return ge.PolicyEngineState.from_engine_read(state)
    except Exception as exc:  # noqa: BLE001
        logger.info("policy engine state unavailable: %s", exc)
        return None


# The four axes, resolved from what has actually happened. They are independent
# on purpose: a single `governed: true` boolean would let a human decision imply
# an authorization decision, which is the confusion this whole arc exists to
# dismantle.
#
# These are the PRE-EXECUTION readings. Policy stays PENDING and Aurora stays
# NOT_EVALUATED after a confirmation, because at that point no policy artifact exists
# and no statement has reached the database.
#
# They are superseded the moment an execution produces verdicts. That handoff is
# `_assurance_from_receipt` below — and it was missing for a week: `_assurance` was
# keyed on the human state alone, so all three of the live 6B executions (a written
# return, a Cedar DENY and an RLS refusal) reported an identical
# `policy: PENDING, aurora: NOT_EVALUATED` on this surface. The comment above
# described the handoff; nothing performed it.
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

    The human axis stays the human axis: a confirmation is not revised by what the
    governance layers went on to decide, and a DECLINED review has no execution to
    read. The other three come from the stored receipt and from nowhere else — they
    are not recomputed from domain rows, because a policy verdict is not derivable
    from them and re-deriving the Aurora axis here would be a second implementation
    of `classify_aurora` that can disagree with the first.

    No receipt means no execution was attempted, which is the overwhelmingly common
    case and returns the pre-execution reading unchanged.
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

    Carries the attribution the axes need to mean anything: which rail ran, which
    engine answered, in what mode, and under which two principals. An ALLOW without
    the gateway mode cannot be distinguished from an unenforced observation.
    """
    if not receipt:
        return None
    notes = receipt.get("notes")
    if isinstance(notes, str):
        import json as _json

        try:
            notes = _json.loads(notes)
        except ValueError:
            notes = {}
    return {
        "receiptId": int(receipt.get("receipt_id") or 0),
        # The domain row this execution produced, or None. Joined on the write key in
        # `latest_receipt`, so a surface can tell the return this review created apart
        # from the client's prior history instead of inferring it from a timestamp.
        "producedReturnId": (
            int(receipt["produced_return_id"])
            if receipt.get("produced_return_id") is not None
            else None
        ),
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
        "notes": notes or {},
        "recordedAt": _iso(receipt.get("created_at")),
    }
