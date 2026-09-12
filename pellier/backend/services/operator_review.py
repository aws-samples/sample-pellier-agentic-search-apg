"""The durable operator review: Pellier's handoff to a human.

Pellier reaches the consequential-action boundary and stops. This module makes
that prepared request survive the shopper closing the tab, so an operator can
discover it, see what was proposed, and decide.

Storage
-------

``pellier.approvals``, extended by migration 020. No new table: that row already
modelled "a pending human decision on a proposed tool call with its arguments"
and had been dormant since migration 002 described it as the identity-gated
sensitive-tool gate. Its status CHECK is already ``pending | approved |
rejected``, which is exactly the three human states.

What a review owns, and what it must never own
----------------------------------------------

It owns references and workflow state: which customer, which order, which turn,
what was proposed, with which parameters, and what the human decided.

It owns **no business truth**. Membership, spend, order contents, inventory,
return status, policy verdicts and database effects are hydrated from their
authoritative sources by :func:`hydrate_review`. A cached copy would fork the
truth, and six months later Pellier and Pellier Operator would disagree about
the same client.

Confirmation binding
--------------------

A confirmation binds to an exact parameter set through
``BusinessLogic.write_request_hash`` — the same function that produces
``write_operations.request_hash``. Change the reason or the amount and the
fingerprint changes, so the prior confirmation no longer matches and the review
returns to needing a human. Because both values come from one function, a later
governed write can be compared to the confirmation by hash rather than by trust.

What this module deliberately does not do
-----------------------------------------

It never performs the business mutation. Confirming a review records a human
decision and stops. The existing ``POST /api/operator/actions/*`` endpoints
combine confirmation and execution in one call, which is why this module does not
call them: driving the governed mutation from a confirmed review is the next
stage's work, and a confirmation that silently executed would make the four
assurance axes lie.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Mapping, Optional

logger = logging.getLogger(__name__)

# Set at app startup, the same way services.agent_tools and
# services.tool_audit_writer are wired. The async functions below all take `db`
# explicitly so tests can inject a stub; these globals exist only for
# `record_boundary_review`, which is called from a Strands hook running on a
# worker thread and therefore has no request scope to read a pool from.
_db_service: Any = None
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_db_service(db: Any) -> None:
    """App startup hook - wire the review writer to the live DB pool."""
    global _db_service
    _db_service = db


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """App startup hook - capture the uvicorn loop so a tool-lifecycle hook
    running on a worker thread can dispatch the review write back onto it."""
    global _main_loop
    _main_loop = loop

# The proposed actions a review may carry. These are governed mutations with a
# human-review workflow; anything else has no review workflow behind it and
# would be a review nobody can act on.
REVIEWABLE_ACTIONS = ("initiate_return", "issue_credit", "replace_damaged_item")

# Workflow states, mirroring the CHECK constraint on pellier.approvals.
STATUS_PENDING = "pending"
STATUS_CONFIRMED = "approved"
STATUS_DECLINED = "rejected"

# The material parameters per action: the values a human is actually agreeing to.
# Confirmation binds to exactly these, so adding a field here changes what a
# prior confirmation covers and correctly invalidates it.
MATERIAL_PARAMETERS: Dict[str, tuple[str, ...]] = {
    "initiate_return": ("customer_id", "product_id", "reason"),
    "issue_credit": ("customer_id", "amount_cents", "reason"),
    "replace_damaged_item": (
        "customer_id", "product_id", "order_id", "quantity", "reason", "disposition",
    ),
}


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

    Types are pinned to what ``BusinessLogic`` passes into the write, because the
    fingerprint is JSON: ``product_id`` as ``"37"`` and as ``37`` hash
    differently, and a mismatch there would read as a tampered confirmation.
    """
    names = MATERIAL_PARAMETERS.get(action)
    if not names:
        raise ReviewError("action_not_reviewable", 422)

    material: Dict[str, Any] = {}
    for name in names:
        if name not in args:
            raise ReviewError(f"missing_parameter:{name}", 422)
        value = args[name]
        if name in ("product_id", "amount_cents", "order_id", "quantity"):
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
    from services.business_logic import write_request_hash

    return write_request_hash(action, **_coerce_material(action, args))


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

# Who asked. `shopper` is a verified token, `operator` is the desk, `unverified`
# is an anonymous session whose customer is a storefront selection.
REQUESTER_SHOPPER = "shopper"
REQUESTER_OPERATOR = "operator"
REQUESTER_UNVERIFIED = "unverified"

_REQUESTER_KINDS = frozenset({REQUESTER_SHOPPER, REQUESTER_OPERATOR, REQUESTER_UNVERIFIED})

_INSERT_REVIEW = """
    INSERT INTO pellier.approvals
        (customer_id, tool, args, status, source_turn_id, order_id,
         issue, recommendation, action_hash, requested_by_sub, requester_kind)
    VALUES (%s, %s, %s::jsonb, 'pending', %s, %s, %s, %s::jsonb, %s, %s, %s)
    ON CONFLICT (customer_id, tool, action_hash) WHERE status = 'pending'
    DO NOTHING
    RETURNING id
"""

# The open review this proposal resolves to when the index refuses the insert.
# Keyed the same way as the index: one open decision per distinct proposed
# mutation, whichever turn asked for it.
_FIND_OPEN_FOR_ACTION = """
    SELECT id
      FROM pellier.approvals
     WHERE customer_id = %s
       AND tool = %s
       AND action_hash = %s
       AND status = 'pending'
     LIMIT 1
"""

_RESOLVE_ORDER = """
    SELECT id
      FROM pellier.orders
     WHERE customer_id = %s
       AND product_id = %s
     ORDER BY placed_at DESC, id DESC
     LIMIT 1
"""

# The authorization mapping, read to decide whether a signed-in requester is the
# customer the review names. It is the table RLS keys on: a subject with no row
# for this customer may well be a shopper, and is still not *this* shopper.
_PRINCIPAL_OWNS_CUSTOMER = """
    SELECT 1 AS owns
      FROM pellier.principal_customers
     WHERE principal_sub = %s
       AND customer_id = %s
     LIMIT 1
"""


async def requester_kind_for_principal(
    db: Any, principal_sub: Optional[str], customer_id: str
) -> str:
    """``shopper`` only when the verified subject maps to the review's customer.

    A signed-in shopper can ask for an action on any persona the storefront
    offers, so the token proves who asked and nothing about whose rows the
    review names. Unless the authorization mapping ties the subject to that
    customer, the request is recorded as unverified with the subject kept, so
    an operator can see that a known shopper asked about someone else's order.
    A lookup that fails is treated the same way: absence of proof is not proof.
    """
    sub = str(principal_sub or "").strip()
    if not sub:
        return REQUESTER_UNVERIFIED
    try:
        row = await db.fetch_one(_PRINCIPAL_OWNS_CUSTOMER, sub, str(customer_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("principal mapping lookup failed for %s: %s", customer_id, exc)
        return REQUESTER_UNVERIFIED
    return REQUESTER_SHOPPER if row else REQUESTER_UNVERIFIED


async def resolve_order_id(
    db: Any, customer_id: str, product_id: Any
) -> Optional[int]:
    """The order the review is about, resolved from Aurora rather than supplied.

    Theo's Wabi-Sabi Bowl exists twice: once under ``theo`` and once under
    ``CUST-THEO``, because the live shopper prompt passes the bare alias and
    ``initiate_return``'s ownership check has to succeed either way. Resolving
    against the canonical customer id therefore matters: it picks the row that
    belongs to the identity the operator will act as.
    """
    try:
        row = await db.fetch_one(_RESOLVE_ORDER, str(customer_id), str(product_id))
    except Exception as exc:  # noqa: BLE001
        logger.error("review order resolution failed for %s/%s: %s",
                     customer_id, product_id, exc)
        return None
    if not row:
        return None
    value = row["id"] if isinstance(row, Mapping) else row[0]
    return int(value) if value is not None else None


async def propose_review(
    db: Any,
    *,
    action: str,
    args: Mapping[str, Any],
    source_turn_id: Optional[str],
    issue: str = "",
    recommendation: Optional[Mapping[str, Any]] = None,
    requested_by_sub: Optional[str] = None,
    requester_kind: str = REQUESTER_UNVERIFIED,
) -> Optional[int]:
    """Record that a human must decide, exactly once per turn and action.

    ``requested_by_sub`` and ``requester_kind`` bind the review to the identity
    that asked, or to its explicit absence. The customer on the review is what
    the proposal names; on an anonymous session that is a persona the shopper
    picked, and an operator reading the queue must be able to tell the two
    apart before acting on it. A ``shopper`` kind is kept only when the
    authorization mapping ties the subject to that customer; otherwise the
    subject is recorded and the kind falls back to ``unverified``.

    Returns the review id, or ``None`` when the review could not be created.
    Never raises into the caller: this runs on a tool-refusal path, and a
    failure to open a review must not turn a clean boundary refusal into an
    error the shopper sees.

    Idempotency is enforced by the partial unique index from migration 020, so a
    retried tool call, a refreshed page, or a replayed turn resolves to the one
    open review rather than a second card.
    """
    if action not in REVIEWABLE_ACTIONS:
        logger.debug("review not opened: %s is not a reviewable action", action)
        return None

    try:
        material = _coerce_material(action, args)
        fingerprint = action_fingerprint(action, args)
    except ReviewError as exc:
        logger.warning("review not opened for %s: %s", action, exc.code)
        return None

    customer_id = material["customer_id"]
    if requester_kind == REQUESTER_SHOPPER:
        requester_kind = await requester_kind_for_principal(
            db, requested_by_sub, customer_id
        )
    order_id = None
    if action == "initiate_return":
        order_id = await resolve_order_id(db, customer_id, material["product_id"])
    elif action == "replace_damaged_item":
        order_id = material["order_id"]

    try:
        row = await db.fetch_one(
            _INSERT_REVIEW,
            customer_id,
            action,
            json.dumps(dict(material), sort_keys=True),
            source_turn_id,
            order_id,
            (issue or "").strip() or None,
            json.dumps(dict(recommendation or {}), sort_keys=True),
            fingerprint,
            (requested_by_sub or "").strip() or None,
            requester_kind if requester_kind in _REQUESTER_KINDS else REQUESTER_UNVERIFIED,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("review creation failed for %s/%s: %s", action, customer_id, exc)
        return None

    if row:
        value = row["id"] if isinstance(row, Mapping) else row[0]
        logger.info(
            "operator review %s opened: %s for %s (turn=%s)",
            value, action, customer_id, source_turn_id,
        )
        return int(value)

    # DO NOTHING fired: this exact mutation is already awaiting a person. Resolve
    # to that review rather than returning None, so a caller can tell "already
    # handled" from "failed to record".
    try:
        existing = await db.fetch_one(
            _FIND_OPEN_FOR_ACTION, customer_id, action, fingerprint
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("review lookup after conflict failed: %s", exc)
        return None
    if existing:
        value = existing["id"] if isinstance(existing, Mapping) else existing[0]
        logger.info(
            "operator review %s already open for %s/%s", value, action, customer_id
        )
        return int(value)
    return None


# ---------------------------------------------------------------------------
# The shopper-rail boundary: sync entry point for the tool-lifecycle hook
# ---------------------------------------------------------------------------

# The exact refusal a governed mutation returns on the shopper rail. Matching on
# this structured field rather than on model prose is what makes the handoff
# deterministic: the agent's wording can change freely and the review still opens.
MANAGED_RAIL_REFUSAL = "managed_rail_required"


def is_boundary_refusal(result: Any) -> bool:
    """True when a tool result is the governed boundary declining to execute."""
    payload = result
    if isinstance(payload, str):
        text = payload.strip()
        if not text.startswith("{"):
            return False
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return False
    return (
        isinstance(payload, Mapping)
        and str(payload.get("error") or "") == MANAGED_RAIL_REFUSAL
    )


def record_boundary_review(
    *,
    action: str,
    args: Mapping[str, Any],
    result: Any,
    source_turn_id: Optional[str],
    issue: str = "",
) -> Optional[int]:
    """Open a review because the governed boundary refused the mutation.

    Called from the after-tool hook, which runs on a Strands worker thread, so
    the coroutine is dispatched onto the captured uvicorn loop exactly as the
    audit writer does.

    Silent on every failure path. This runs after a *successful* boundary
    refusal: the shopper is already being told the request was prepared, and a
    review-write problem must not convert that into an error they see. The
    failure is logged, and the queue simply does not gain a card.
    """
    if not is_boundary_refusal(result):
        return None
    if action not in REVIEWABLE_ACTIONS:
        return None
    if _db_service is None or _main_loop is None:
        logger.debug("operator review not opened: writer not wired yet")
        return None

    recommendation = _default_recommendation(action, args)
    # The requester is the turn's verified principal, read from the identity
    # ContextVar the request bound, never from the tool arguments: a persona
    # choice puts a customer id in the arguments and proves nothing.
    from services.turn_identity import current_principal_sub

    requested_by_sub = current_principal_sub()
    requester_kind = REQUESTER_SHOPPER if requested_by_sub else REQUESTER_UNVERIFIED
    try:
        future = asyncio.run_coroutine_threadsafe(
            propose_review(
                _db_service,
                action=action,
                args=args,
                source_turn_id=source_turn_id,
                issue=issue,
                recommendation=recommendation,
                requested_by_sub=requested_by_sub,
                requester_kind=requester_kind,
            ),
            _main_loop,
        )
        return future.result(timeout=5.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("operator review not opened for %s: %s", action, exc)
        return None


# The reason clause, per canonical return reason. The rationale used to say
# "reported it damaged on arrival" for EVERY `initiate_return`, which was true only
# while `damaged` was the sole scenario: a not-as-described return rendered a
# rationale naming a reason the review does not carry, directly above the parameter
# table that carries the real one.
#
# The `damaged` clause is byte-identical to the previous sentence, so Theo's canonical
# workshop wording is unchanged.
_REASON_CLAUSES: Dict[str, str] = {
    "damaged": "reported it damaged on arrival",
    "wrong_size": "reported the size is wrong",
    "not_as_described": "reported the piece is not as described",
    "changed_mind": "has changed their mind about the piece",
    "other": "asked to return the piece",
}


def _default_recommendation(action: str, args: Mapping[str, Any]) -> Dict[str, Any]:
    """What Pellier proposes, and why, in a form the console can render.

    Deliberately thin. It names the action and the reason the agent had for it;
    it does not assert availability or entitlement. Whether a replacement can
    actually be sent is checked again during execution. A courtesy credit needs
    a separate, evidence-backed proposal and an explicit human decision.

    The rationale is derived from the return reason in ``args``. An unrecognised or
    absent reason gets the neutral clause rather than a borrowed one: stating the
    wrong reason is worse than stating none.
    """
    if action == "initiate_return":
        reason = str(args.get("reason") or "")
        clause = _REASON_CLAUSES.get(reason, "asked to return the piece")
        recommendation: Dict[str, Any] = {
            "primaryAction": "initiate_return",
            "rationale": (
                f"The client owns this piece and {clause}, "
                "which is a canonical return reason."
            ),
        }
        # A return reason establishes neither previous damage nor a credit
        # entitlement. Any discretionary credit needs its own grounded proposal.
        return recommendation
    if action == "issue_credit":
        return {
            "primaryAction": "issue_credit",
            "rationale": "Service recovery, proposed from the shopper conversation.",
        }
    return {"primaryAction": action}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

# Workflow state plus current client and product labels. Membership, spend,
# order state and inventory are resolved separately by hydrate_review.
_QUEUE_SELECT = """
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
        a.requested_by_sub AS requested_by_sub,
        a.requester_kind AS requester_kind,
        p.name          AS product_name,
        a.requested_at   AS requested_at,
        a.decided_at     AS decided_at
      FROM pellier.approvals a
      LEFT JOIN pellier.customers c ON c.id = a.customer_id
      LEFT JOIN pellier.product_catalog p ON p.product_id::text = a.args->>'product_id'
     -- Explicit casts: Postgres cannot infer a type for a bare placeholder used
     -- only in `IS NULL`, and raises IndeterminateDatatype before the query runs.
     WHERE (%s::text IS NULL OR a.status = %s::text)
     ORDER BY
        CASE WHEN a.status = 'pending' THEN 0 ELSE 1 END,
        a.requested_at DESC
     LIMIT %s
"""

_ONE_SELECT = """
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
        a.requested_by_sub AS requested_by_sub,
        a.requester_kind AS requester_kind,
        p.name          AS product_name,
        a.requested_at   AS requested_at,
        a.decided_at     AS decided_at
      FROM pellier.approvals a
      LEFT JOIN pellier.customers c ON c.id = a.customer_id
      LEFT JOIN pellier.product_catalog p ON p.product_id::text = a.args->>'product_id'
     WHERE a.id = %s
"""


def _parse_json(value: Any) -> Any:
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
           decided_by = %s
     WHERE id = %s
       AND status = 'pending'
    RETURNING id, status, decided_by, decided_at, action_hash
"""


async def decide_review(
    db: Any,
    *,
    review_id: int,
    decision: str,
    decided_by: str,
    action_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a human decision, bound to the parameters it was shown.

    ``action_hash`` is required to confirm and ignored to decline. Confirming
    means "I agree to *this* mutation", so the caller must echo the fingerprint
    it displayed; declining means "do not do this at all", which no parameter
    change can invalidate.

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
        # compare_digest rather than ==: same reason the commerce confirmation
        # path uses it, and it keeps the two confirmation checks identical.
        if not stored or not hmac.compare_digest(stored, supplied):
            raise ReviewError("parameters_changed", 409)

        # Re-derive from the stored args as well. If the row's args and its
        # fingerprint ever disagree, the stored hash is not evidence of anything.
        try:
            recomputed = action_fingerprint(
                str(review["action"]), _parse_json(review.get("args")) or {}
            )
        except ReviewError:
            raise ReviewError("stored_parameters_invalid", 409) from None
        if not hmac.compare_digest(stored, recomputed):
            raise ReviewError("stored_parameters_invalid", 409)

    row = await db.fetch_one(_DECIDE, decision, principal, int(review_id))
    if not row:
        # Lost a race with another operator between the read and the update.
        raise ReviewError("review_already_decided", 409)
    return dict(row)


# ---------------------------------------------------------------------------
# Authoritative hydration
# ---------------------------------------------------------------------------

_CUSTOMER_SELECT = """
    SELECT id, name, membership, spend_12mo, preferences_summary
      FROM pellier.customers
     WHERE id = %s
"""

_ORDER_SELECT = """
    SELECT o.id AS order_id, o.product_id, o.quantity, o.placed_at,
           p.name AS product_name, p.brand, p.price, p."imgUrl" AS image_url
      FROM pellier.orders o
      JOIN pellier.product_catalog p ON p."productId" = o.product_id
     WHERE o.id = %s
"""

_PRODUCT_SELECT = """
    SELECT "productId" AS product_id, name, brand, price, quantity,
           "imgUrl" AS image_url
      FROM pellier.product_catalog
     WHERE "productId" = %s
"""

# Replacement availability is a live question, so it is asked live. Storing
# "a replacement is available" on the review would be a promise that decays.
_WAREHOUSE_SELECT = """
    SELECT w.id AS warehouse_id, w.display_name, w.city,
           wi.quantity, w.ship_window_min, w.ship_window_max
      FROM pellier.warehouse_inventory wi
      JOIN pellier.warehouses w ON w.id = wi.warehouse_id
     WHERE wi.product_id = %s
     ORDER BY wi.quantity DESC, w.id
"""

# The return lifecycle lives in pellier.returns. pellier.orders has no status
# column, so an "order status" on this screen would be invented.
_RETURNS_SELECT = """
    SELECT id, product_id, reason, status, requested_at, resolved_at
      FROM pellier.returns
     WHERE customer_id = %s
     ORDER BY requested_at DESC
     LIMIT 10
"""


async def _safe_one(db: Any, sql: str, *args: Any, label: str) -> Optional[Dict[str, Any]]:
    try:
        row = await db.fetch_one(sql, *args)
        return dict(row) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.error("review hydration (%s) failed: %s", label, exc)
        return None


async def _safe_all(db: Any, sql: str, *args: Any, label: str) -> List[Dict[str, Any]]:
    try:
        rows = await db.fetch_all(sql, *args)
        return [dict(r) for r in (rows or [])]
    except Exception as exc:  # noqa: BLE001
        logger.error("review hydration (%s) failed: %s", label, exc)
        return []


async def hydrate_review(db: Any, review: Mapping[str, Any]) -> Dict[str, Any]:
    """Resolve current truth for a review, from the systems that own it.

    Every value here is read now. Nothing is copied onto the review row, which
    is why a review can be six weeks old and still render a client's correct
    standing.
    """
    import asyncio

    args = _parse_json(review.get("args")) or {}
    product_id = args.get("product_id")
    customer_id = str(review.get("customer_id") or "")

    async def _none() -> None:
        return None

    async def _empty() -> List[Dict[str, Any]]:
        return []

    # Five independent reads, run concurrently. Sequentially this cost five
    # Aurora round trips for one page, which is latency the operator pays for
    # nothing: none of these queries depends on another's result.
    customer, order, product, warehouses, returns = await asyncio.gather(
        _safe_one(db, _CUSTOMER_SELECT, customer_id, label="customer"),
        _safe_one(db, _ORDER_SELECT, int(review["order_id"]), label="order")
        if review.get("order_id")
        else _none(),
        _safe_one(db, _PRODUCT_SELECT, str(product_id), label="product")
        if product_id is not None
        else _none(),
        _safe_all(db, _WAREHOUSE_SELECT, str(product_id), label="warehouses")
        if product_id is not None
        else _empty(),
        _safe_all(db, _RETURNS_SELECT, customer_id, label="returns"),
    )

    return {
        "customer": customer,
        "order": order,
        "product": product,
        "warehouses": warehouses,
        "returns": returns,
    }
