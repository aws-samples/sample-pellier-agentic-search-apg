"""The durable operator review: Pellier's handoff to a person.

A credit proposal, from the shopper's ``ask_a_person`` or from the Operator's
Planner, becomes one ``pellier.approvals`` row through
``store_tools.open_credit_review``. This module reads those rows for the desk
and records the human decision on them.

What a review owns, and what it must never own
----------------------------------------------

It owns references and workflow state: which customer, what was proposed, with
which parameters, who asked, and what the person decided. It owns no business
truth. The customer's name and the orders a proposal refers to are hydrated
from their own tables by :func:`hydrate_review` on every read.

Confirmation binding
--------------------

A confirmation binds to an exact parameter set through
``store_tools.write_request_hash``, the same function that fingerprints the
credit write. Change the reason or the amount and the fingerprint changes, so
the prior confirmation no longer matches. ``give_store_credit`` compares its own
fingerprint with the approved rows before it writes, and admits the write only
under that review's own key (``store_tools.execution_idempotency_key``), so an
approval for one credit never admits another and never admits the same one
twice. Migration 020 keeps one live review (pending or approved) per exact
credit, so there is one approved row and one key to bind to.

A decision records two things about the person: ``decided_by``, the verified
token subject, which is the principal every other ledger carries; and
``decided_by_name``, the Cognito username, so a review record can say who
approved it to any staff member reading it.

Confirming records a decision and stops. Execution is the next request, and it
is the only path that calls the tool.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Optional

logger = logging.getLogger(__name__)

# The proposed actions a review may carry. One governed mutation has a
# human-review workflow; anything else has no review workflow behind it and
# would be a review nobody can act on.
REVIEWABLE_ACTIONS = ("give_store_credit",)

# Workflow states, mirroring the CHECK constraint on pellier.approvals.
STATUS_PENDING = "pending"
STATUS_CONFIRMED = "approved"
STATUS_DECLINED = "rejected"

# The material parameters per action: the values a human is actually agreeing to.
# Confirmation binds to exactly these, so adding a field here changes what a
# prior confirmation covers and correctly invalidates it.
MATERIAL_PARAMETERS: Dict[str, tuple[str, ...]] = {
    "give_store_credit": ("customer_id", "amount_cents", "reason"),
}

# Who asked. `shopper` is a verified token, `operator` is the desk's Planner,
# `unverified` is a session whose customer could not be tied to a subject.
REQUESTER_SHOPPER = "shopper"
REQUESTER_OPERATOR = "operator"
REQUESTER_UNVERIFIED = "unverified"


class ReviewError(Exception):
    """A review operation that failed for a reason the caller should surface."""

    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Parameter binding
# ---------------------------------------------------------------------------


def _coerce_material(action: str, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Extract and type-normalise the material parameters for `action`.

    Types are pinned to what ``store_tools.give_store_credit`` passes into the
    write, because the fingerprint is JSON: ``amount_cents`` as ``"2500"`` and
    as ``2500`` hash differently, and a mismatch there would read as a tampered
    confirmation.
    """
    names = MATERIAL_PARAMETERS.get(action)
    if not names:
        raise ReviewError("action_not_reviewable", 422)

    material: Dict[str, Any] = {}
    for name in names:
        if name not in args:
            raise ReviewError(f"missing_parameter:{name}", 422)
        value = args[name]
        if name == "amount_cents":
            try:
                material[name] = int(value)
            except (TypeError, ValueError, OverflowError):
                raise ReviewError(f"invalid_parameter:{name}", 422) from None
        else:
            material[name] = str(value)
    return material


def action_fingerprint(action: str, args: Mapping[str, Any]) -> str:
    """Canonical fingerprint of the material parameters of a proposed action.

    Delegates to the write-path hash so a confirmation and the write it
    authorises are comparable by value.
    """
    from services.store_tools import write_request_hash

    return write_request_hash(action, **_coerce_material(action, args))


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

_REVIEW_COLUMNS = """
    SELECT
        a.id             AS review_id,
        a.customer_id    AS customer_id,
        c.name           AS customer_name,
        a.tool           AS action,
        a.args           AS args,
        a.status         AS status,
        a.source_turn_id AS source_turn_id,
        -- Claimed when execution BEGINS. Present with no execution receipt means
        -- an attempt started and produced no verdict, which is its own fact.
        a.execution_turn_id AS execution_turn_id,
        a.order_id       AS order_id,
        a.issue          AS issue,
        a.recommendation AS recommendation,
        a.action_hash    AS action_hash,
        a.decided_by     AS decided_by,
        a.decided_by_name AS decided_by_name,
        a.requested_by_sub AS requested_by_sub,
        a.requester_kind AS requester_kind,
        a.requested_at   AS requested_at,
        a.decided_at     AS decided_at
      FROM pellier.approvals a
      LEFT JOIN pellier.customers c ON c.id = a.customer_id
"""

_QUEUE_SELECT = _REVIEW_COLUMNS + """
     -- Explicit casts: Postgres cannot infer a type for a bare placeholder used
     -- only in `IS NULL`, and raises IndeterminateDatatype before the query runs.
     WHERE (%s::text IS NULL OR a.status = %s::text)
     ORDER BY
        CASE WHEN a.status = 'pending' THEN 0 ELSE 1 END,
        a.requested_at DESC
     LIMIT %s
"""

_ONE_SELECT = _REVIEW_COLUMNS + """
     WHERE a.id = %s
"""

_FOR_CUSTOMER_SELECT = _REVIEW_COLUMNS + """
     WHERE a.customer_id = %s
       AND a.tool = 'give_store_credit'
     ORDER BY
        CASE WHEN a.status = 'pending' THEN 0 ELSE 1 END,
        a.requested_at DESC
     LIMIT %s
"""


def parse_json(value: Any) -> Any:
    """A JSONB column as the driver returned it, or parsed when it came as text."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if value is not None else {}


async def list_reviews(
    db: Any, *, status: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """The queue. Pending first, newest first within each group."""
    rows = await db.fetch_all(_QUEUE_SELECT, status, status, int(limit))
    return [dict(r) for r in (rows or [])]


async def list_reviews_for_customer(
    db: Any, customer_id: str, *, limit: int = 5
) -> List[Dict[str, Any]]:
    """This customer's credit reviews, open ones first, for the client record."""
    rows = await db.fetch_all(_FOR_CUSTOMER_SELECT, str(customer_id), int(limit))
    return [dict(r) for r in (rows or [])]


async def get_review(db: Any, review_id: int) -> Optional[Dict[str, Any]]:
    row = await db.fetch_one(_ONE_SELECT, int(review_id))
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

_DECIDE = """
    UPDATE pellier.approvals
       SET status = %s,
           decided_at = now(),
           decided_by = %s,
           decided_by_name = %s
     WHERE id = %s
       AND status = 'pending'
    RETURNING id, status, decided_by, decided_by_name, decided_at, action_hash
"""


async def decide_review(
    db: Any,
    *,
    review_id: int,
    decision: str,
    decided_by: str,
    action_hash: Optional[str] = None,
    decided_by_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a human decision, bound to the parameters it was shown.

    ``action_hash`` is required to confirm and ignored to decline. Confirming
    means "I agree to *this* mutation", so the caller must echo the fingerprint
    it displayed; declining means "do not do this at all", which no parameter
    change can invalidate. ``decided_by_name`` is the decider's username, kept
    beside the subject so the record can name the person to every reader.

    Raises :class:`ReviewError` with a machine-readable code rather than
    returning a status field, so a caller cannot mistake a refusal for a
    decision.
    """
    if decision not in (STATUS_CONFIRMED, STATUS_DECLINED):
        raise ReviewError("unknown_decision", 422)
    principal = str(decided_by or "").strip()
    if not principal:
        raise ReviewError("decider_required", 401)

    review = await get_review(db, review_id)
    if not review:
        raise ReviewError("review_not_found", 404)
    if review["status"] != STATUS_PENDING:
        raise ReviewError("review_already_decided", 409)

    if decision == STATUS_CONFIRMED:
        import hmac

        supplied = str(action_hash or "").strip()
        if not supplied:
            raise ReviewError("action_hash_required", 422)
        stored = str(review.get("action_hash") or "").strip()
        if not stored or not hmac.compare_digest(stored, supplied):
            raise ReviewError("parameters_changed", 409)

        # Re-derive from the stored args as well. If the row's args and its
        # fingerprint ever disagree, the stored hash is not evidence of anything.
        try:
            recomputed = action_fingerprint(
                str(review["action"]), parse_json(review.get("args")) or {}
            )
        except ReviewError:
            raise ReviewError("stored_parameters_invalid", 409) from None
        if not hmac.compare_digest(stored, recomputed):
            raise ReviewError("stored_parameters_invalid", 409)

    name = str(decided_by_name or "").strip() or None
    row = await db.fetch_one(_DECIDE, decision, principal, name, int(review_id))
    if not row:
        # Lost a race with another operator between the read and the update.
        raise ReviewError("review_already_decided", 409)
    return dict(row)


# ---------------------------------------------------------------------------
# Authoritative hydration
# ---------------------------------------------------------------------------

_CUSTOMER_SELECT = """
    SELECT c.id, c.name
      FROM pellier.customers c
     WHERE c.id = %s
"""

# The orders a proposal refers to: the one on the row, plus any the Planner
# listed. Read now, from the order table, never copied onto the review.
_ORDERS_SELECT = """
    SELECT o.id AS order_id, o.product_id, o.quantity, o.placed_at,
           o.amount_paid_cents / 100.0 AS price_paid,
           p.name AS product_name, p.brand, p.price AS current_price,
           p."imgUrl" AS image_url
      FROM pellier.orders o
      JOIN pellier.product_catalog p ON p."productId" = o.product_id
     WHERE o.customer_id = %s
       AND o.id = ANY(%s)
     ORDER BY o.placed_at DESC, o.id DESC
"""


def referenced_order_ids(review: Mapping[str, Any]) -> List[int]:
    """The order ids a review refers to, from its row and its recommendation."""
    ids: List[int] = []
    if review.get("order_id"):
        ids.append(int(review["order_id"]))
    recommendation = parse_json(review.get("recommendation")) or {}
    for value in recommendation.get("orderIds") or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number not in ids:
            ids.append(number)
    return ids


async def hydrate_review(db: Any, review: Mapping[str, Any]) -> Dict[str, Any]:
    """Resolve current truth for a review, from the tables that own it.

    Every value here is read now. Nothing is copied onto the review row, which
    is why a review can be six weeks old and still show the right orders.
    """
    customer_id = str(review.get("customer_id") or "")
    customer: Optional[Dict[str, Any]] = None
    orders: List[Dict[str, Any]] = []
    try:
        row = await db.fetch_one(_CUSTOMER_SELECT, customer_id)
        customer = dict(row) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.error("review hydration (customer) failed: %s", exc)
    order_ids = referenced_order_ids(review)
    if order_ids:
        try:
            rows = await db.fetch_all(_ORDERS_SELECT, customer_id, order_ids)
            orders = [dict(r) for r in (rows or [])]
        except Exception as exc:  # noqa: BLE001
            logger.error("review hydration (orders) failed: %s", exc)
    return {"customer": customer, "orders": orders}
