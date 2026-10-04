"""Governed execution of a confirmed operator review.

A person said yes. This module answers the next question, *is the system
allowed to do it?*, and keeps the answers separate.

Two principals, two boundaries
------------------------------

    ACTOR PRINCIPAL     the authenticated staff member (Nadia)
                        -> what AgentCore Policy / Cedar authorizes
                        -> "may this person attempt this operation?"

    CUSTOMER SUBJECT    the client whose rows the action touches
                        -> what Aurora Row-Level Security scopes
                        -> "may this operation touch these rows?"

The customer subject is resolved server-side from the approved review, never
accepted from the caller: a client that could name its own RLS principal could
reach any customer's rows while still passing every other check.

Three independent controls
--------------------------

    Cedar        may this principal attempt this action?
    Approval     does a confirmed review fingerprint these exact arguments,
                 and is this write under that review's own key?
    CHECK        is this mutation valid regardless of who asked?

Each can fail while the others pass. The assurance axes this module returns are
derived from separate artifacts, never from one another.

What this module will not do
----------------------------

It will not report a policy verdict that no policy engine produced. On the
in-process rail the policy axis says ``NOT_EVALUATED`` and carries the reason.
A convenient ``ALLOW`` there would be the single most damaging lie this surface
could tell.

Seams for cut 4 (tables)
------------------------

``pellier.execution_receipts`` (the per-attempt verdict record),
``pellier.principal_customers`` (the customer subject) and
``pellier.write_operations`` (inside ``apply_store_credit``) are all tables cut
4 deletes. ``record_receipt``, ``latest_receipt(s)`` and
``resolve_customer_subject`` are the three functions that read or write them;
``evidence_for_key`` reads only the two tables that stay.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

# The write key is derived in ``store_tools`` because the approval guard there
# recomputes it: the tool admits a write only under the key of the review that
# fingerprints it, on both rails. This module derives the same key for the
# Operator's execute path.
from services.store_tools import APPROVAL_GUARD, execution_idempotency_key

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

RAIL_GATEWAY = "gateway-mcp"
RAIL_IN_PROCESS = "in-process"
# Not a rail that ran. The governed format requires the managed rail, so an
# execution that cannot reach it is refused before anything runs, and the receipt
# records the refusal rather than a quiet downgrade.
RAIL_REFUSED = "refused"

# Policy axis, four values and each from a different kind of source:
#
#   ALLOW / DENY            an enforced decision the engine produced
#   EVALUATION_INCOMPLETE   an engine was involved and its answer is unreadable
#   NOT_EVALUATED           no engine was asked at all (the in-process rail)
#
# The last two are deliberately distinct. "Nobody asked" and "the answer could
# not be read" are different facts, and collapsing them hides a broken managed
# rail behind an expected in-process one.
POLICY_ALLOW = "ALLOW"
POLICY_DENY = "DENY"
POLICY_EVALUATION_INCOMPLETE = "EVALUATION_INCOMPLETE"
POLICY_NOT_EVALUATED = "NOT_EVALUATED"

# Aurora axis.
AURORA_PERMITTED = "PERMITTED"
AURORA_DENIED = "DENIED"
AURORA_NOT_REACHED = "NOT_REACHED"
AURORA_OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"

# Evidence axis. Each value names what actually exists.
EVIDENCE_RECEIPTED = "RECEIPTED"
EVIDENCE_POLICY_PROOF = "POLICY_PROOF"
EVIDENCE_ATTEMPT_RECEIPT = "ATTEMPT_RECEIPT"
EVIDENCE_NO_EXECUTION = "NO_EXECUTION"
EVIDENCE_PENDING = "PENDING"


class ExecutionError(Exception):
    """An execution refused before any governed call was attempted."""

    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class GovernedRailUnavailable(ExecutionError):
    """The governed format requires the managed rail and it is not usable.

    Carries the receipt this refusal already recorded, so the route reports a
    refusal that is provable after the response is gone rather than a bare error.
    """

    def __init__(
        self,
        missing: tuple[str, ...],
        *,
        reason: str,
        receipt_id: Optional[int] = None,
    ) -> None:
        super().__init__("governed_rail_unavailable", 409)
        self.missing = tuple(missing)
        self.reason = reason
        self.receipt_id = receipt_id

    def as_detail(self) -> Dict[str, Any]:
        """The HTTP 409 body: the machine code plus what is missing."""
        return {"error": self.code, "missing": list(self.missing)}


@dataclass
class ExecutionOutcome:
    """One governed execution attempt, with each axis resolved separately."""

    rail: str
    execution_turn_id: str
    idempotency_key: str
    operator_sub: str
    customer_subject: Optional[str]
    policy: str
    aurora: str
    evidence: str
    tool: str
    result: Dict[str, Any] = field(default_factory=dict)
    # Human-readable reason per axis, so a surface never has to infer why.
    notes: Dict[str, str] = field(default_factory=dict)
    # What the two durable tables hold for this write key, read after the call.
    record: Dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> Dict[str, Any]:
        return {
            "rail": self.rail,
            "executionTurnId": self.execution_turn_id,
            "idempotencyKey": self.idempotency_key,
            "actorPrincipal": self.operator_sub,
            "customerSubject": self.customer_subject,
            "assurance": {
                "human": "CONFIRMED",
                "policy": self.policy,
                "aurora": self.aurora,
                "evidence": self.evidence,
            },
            "notes": dict(self.notes),
            "tool": self.tool,
            "result": self.result,
            "record": dict(self.record),
        }


# ---------------------------------------------------------------------------
# Trusted customer-subject resolution
# ---------------------------------------------------------------------------

_SUBJECT_SELECT = """
    SELECT principal_sub
      FROM pellier.principal_customers
     WHERE customer_id = %s
     ORDER BY principal_sub
     LIMIT 1
"""


async def resolve_customer_subject(db: Any, customer_id: str) -> Optional[str]:
    """The RLS subject for a customer, from the authorization mapping table.

    Returning ``None`` when a customer has no mapping is deliberate and is not
    an error: RLS then resolves no scope and denies, which is the correct
    fail-closed outcome for a client whose identity was never linked.

    This is the ONLY way an execution obtains an RLS subject. Nothing reads it
    from a request body.
    """
    try:
        row = await db.fetch_one(_SUBJECT_SELECT, str(customer_id))
    except Exception as exc:  # noqa: BLE001
        logger.error("customer-subject resolution failed for %s: %s", customer_id, exc)
        return None
    if not row:
        logger.info(
            "customer %s has no principal_customers mapping; RLS will fail closed",
            customer_id,
        )
        return None
    value = row["principal_sub"] if isinstance(row, Mapping) else row[0]
    return str(value) if value else None


# ---------------------------------------------------------------------------
# Confirmation integrity
# ---------------------------------------------------------------------------


def verify_confirmation(review: Mapping[str, Any]) -> Dict[str, Any]:
    """Recompute the fingerprint from the persisted args and require a match.

    The stored hash is what a human was shown and agreed to. Re-deriving it from
    the row's own arguments proves the two still agree, so the action about to
    execute is materially the action that was confirmed. A mismatch means the row
    was edited after confirmation, and no policy or database call may follow.

    Returns the material parameters to execute with. Those come from the review,
    never from the caller.
    """
    import hmac

    from services import operator_review as rv

    status = str(review.get("status") or "")
    if status == rv.STATUS_PENDING:
        raise ExecutionError("review_not_confirmed", 409)
    if status != rv.STATUS_CONFIRMED:
        raise ExecutionError("review_declined", 409)

    action = str(review.get("action") or "")
    if action not in rv.REVIEWABLE_ACTIONS:
        raise ExecutionError("action_not_executable", 422)

    args = review.get("args")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            raise ExecutionError("stored_parameters_invalid", 409) from None
    if not isinstance(args, Mapping):
        raise ExecutionError("stored_parameters_invalid", 409)

    stored = str(review.get("action_hash") or "").strip()
    if not stored:
        raise ExecutionError("confirmation_missing_fingerprint", 409)

    try:
        recomputed = rv.action_fingerprint(action, args)
    except rv.ReviewError:
        raise ExecutionError("stored_parameters_invalid", 409) from None

    if not hmac.compare_digest(stored, recomputed):
        raise ExecutionError("confirmation_invalid", 409)

    return dict(args)


# ---------------------------------------------------------------------------
# execution_turn_id: assigned once, reused on retry
# ---------------------------------------------------------------------------

_CLAIM_EXECUTION_TURN = """
    UPDATE pellier.approvals
       SET execution_turn_id = %s
     WHERE id = %s
       AND status = 'approved'
       AND execution_turn_id IS NULL
    RETURNING execution_turn_id
"""

_READ_EXECUTION_TURN = """
    SELECT execution_turn_id
      FROM pellier.approvals
     WHERE id = %s
"""


async def claim_execution_turn(db: Any, review_id: int) -> str:
    """Return this review's execution turn, assigning one on first execution.

    Assign-once semantics live in the UPDATE's ``WHERE execution_turn_id IS
    NULL``, so two concurrent executes cannot mint two turns for one confirmed
    action: the loser reads the winner's value.
    """
    from services.turn_identity import new_turn_id

    candidate = new_turn_id()
    row = await db.fetch_one(_CLAIM_EXECUTION_TURN, candidate, int(review_id))
    if row:
        value = row["execution_turn_id"] if isinstance(row, Mapping) else row[0]
        if value:
            return str(value)

    existing = await db.fetch_one(_READ_EXECUTION_TURN, int(review_id))
    if existing:
        value = (
            existing["execution_turn_id"]
            if isinstance(existing, Mapping)
            else existing[0]
        )
        if value:
            return str(value)
    # The review is not approved, or vanished. Both are refusals, not turns.
    raise ExecutionError("execution_turn_unavailable", 409)


# ---------------------------------------------------------------------------
# The policy artifact
# ---------------------------------------------------------------------------

_RECORD_RECEIPT = """
INSERT INTO pellier.execution_receipts
    (execution_turn_id, review_id, tool, gateway_action_id, rail,
     actor_principal, customer_subject, policy_outcome, aurora_outcome,
     evidence_outcome, policy_engine_id, gateway_mode, matching_forbids,
     idempotency_key, notes)
VALUES
    (%(execution_turn_id)s, %(review_id)s, %(tool)s, %(gateway_action_id)s,
     %(rail)s, %(actor_principal)s, %(customer_subject)s, %(policy_outcome)s,
     %(aurora_outcome)s, %(evidence_outcome)s, %(policy_engine_id)s,
     %(gateway_mode)s, %(matching_forbids)s, %(idempotency_key)s, %(notes)s)
RETURNING receipt_id
"""


async def record_receipt(
    db: Any,
    outcome: "ExecutionOutcome",
    *,
    review_id: int,
    engine_state: Optional["PolicyEngineState"] = None,
) -> Optional[int]:
    """Persist the verdicts for one governed execution attempt.

    A Cedar DENY produces no audit row by design, claims no idempotency key and
    touches no domain table, so without this row a denial is provable only from
    the HTTP response the operator happened to be looking at. Append-only, one
    row per attempt.

    An infrastructure failure is logged and swallowed: the receipt is evidence
    ABOUT an execution that has already happened, and a lost connection must not
    turn a successful governed write into an error the operator sees. A
    constraint violation is different. It means the vocabulary this module
    writes and the table's CHECK disagree, which is a defect, and swallowing it
    once hid two receipt shapes that were never stored. It raises.

    Raises:
        ExecutionError: ``execution_receipt_rejected`` when the database refused
            the receipt on a constraint (SQLSTATE class 23).
    """
    from services.managed_policy import policy_engine_id

    params = {
        "execution_turn_id": outcome.execution_turn_id,
        "review_id": int(review_id),
        "tool": outcome.tool,
        "gateway_action_id": gateway_action_id(outcome.tool),
        "rail": outcome.rail,
        "actor_principal": outcome.operator_sub,
        "customer_subject": outcome.customer_subject,
        "policy_outcome": outcome.policy,
        "aurora_outcome": outcome.aurora,
        "evidence_outcome": outcome.evidence,
        # Attribution for the verdict. Both are None on the in-process rail, which is
        # correct: that rail consults no policy engine and its NOT_EVALUATED means
        # something different from an unreadable engine on the Gateway rail.
        "policy_engine_id": policy_engine_id() if outcome.rail == RAIL_GATEWAY else None,
        "gateway_mode": getattr(engine_state, "gateway_mode", "") or None,
        "matching_forbids": list(getattr(engine_state, "matching_forbids", ()) or ()),
        "idempotency_key": outcome.idempotency_key,
        "notes": json.dumps(outcome.notes or {}),
    }
    try:
        # Cursor rather than `db.fetch_one`, which forwards `*params` as a tuple and so
        # reports "15 placeholders but 1 parameters" for a named-placeholder statement.
        async with db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_RECORD_RECEIPT, params)
                row = await cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - classified: a defect raises, an outage is logged
        if _is_constraint_violation(exc):
            logger.error(
                "execution receipt REJECTED by a constraint for review %s turn %s "
                "(policy=%s aurora=%s evidence=%s rail=%s): %s",
                review_id, outcome.execution_turn_id, outcome.policy, outcome.aurora,
                outcome.evidence, outcome.rail, exc,
            )
            raise ExecutionError("execution_receipt_rejected", 500) from exc
        logger.warning(
            "execution receipt not recorded for review %s turn %s: %s",
            review_id, outcome.execution_turn_id, exc,
        )
        return None
    if not row:
        return None
    value = row["receipt_id"] if isinstance(row, Mapping) else row[0]
    return int(value) if value is not None else None


def _is_constraint_violation(exc: BaseException) -> bool:
    """SQLSTATE class 23: the statement ran and a CHECK, unique or FK refused it."""
    import psycopg

    sqlstate = str(getattr(exc, "sqlstate", "") or "")
    return sqlstate.startswith("23") or isinstance(exc, psycopg.IntegrityError)


_RECEIPT_COLUMNS = """
SELECT receipt_id, execution_turn_id, review_id, tool, gateway_action_id, rail,
       actor_principal, customer_subject, policy_outcome, aurora_outcome,
       evidence_outcome, policy_engine_id, gateway_mode, matching_forbids,
       idempotency_key, notes, created_at
  FROM pellier.execution_receipts
"""

_LATEST_RECEIPT = _RECEIPT_COLUMNS + """
 WHERE review_id = %s
 ORDER BY receipt_id DESC
 LIMIT 1
"""

_LATEST_RECEIPTS_BATCH = """
SELECT DISTINCT ON (review_id)
       receipt_id, execution_turn_id, review_id, tool, gateway_action_id, rail,
       actor_principal, customer_subject, policy_outcome, aurora_outcome,
       evidence_outcome, policy_engine_id, gateway_mode, matching_forbids,
       idempotency_key, notes, created_at
  FROM pellier.execution_receipts
 WHERE review_id = ANY(%s)
 ORDER BY review_id, receipt_id DESC
"""


async def latest_receipts(db: Any, review_ids: Any) -> Dict[int, Dict[str, Any]]:
    """The newest attempt per review, in one round trip, keyed by review id.

    Never raises: an unreadable receipt table must leave the queue listable. An
    empty mapping then reads as "no execution recorded".
    """
    ids = [int(r) for r in (review_ids or [])]
    if not ids:
        return {}
    try:
        rows = await db.fetch_all(_LATEST_RECEIPTS_BATCH, ids)
    except Exception as exc:  # noqa: BLE001 - the queue must stay listable
        logger.warning("execution receipt batch read failed: %s", exc)
        return {}
    return {int(row["review_id"]): dict(row) for row in (rows or [])}


async def latest_receipt(db: Any, review_id: int) -> Optional[Dict[str, Any]]:
    """The newest execution attempt for this review, or None if none was attempted.

    None is a real answer, and the caller must render it as "not yet attempted"
    rather than as any particular verdict. Never raises.
    """
    try:
        return await db.fetch_one(_LATEST_RECEIPT, int(review_id))
    except Exception as exc:  # noqa: BLE001 - a review must stay viewable
        logger.warning("execution receipt read failed for review %s: %s", review_id, exc)
        return None


# ---------------------------------------------------------------------------
# The durable record: what the two tables that outlive cut 4 hold for a key
# ---------------------------------------------------------------------------

# The Lambda records the ``idempotency_key`` it was called with inside the audit
# row's arguments, and the in-process writer does the same, so one key joins
# both tables with no timestamp heuristic.
_AUDIT_FOR_KEY = """
SELECT audit_id, caller, created_at
  FROM pellier.tool_audit
 WHERE tool = 'give_store_credit'
   AND args->>'idempotency_key' = %s
 ORDER BY audit_id
"""

_CREDITS_FOR_KEY = """
SELECT credit_id, customer_id, amount_cents, reason, issued_by, created_at
  FROM pellier.store_credits
 WHERE idempotency_key = %s
 ORDER BY credit_id
"""


async def evidence_for_key(db: Any, idempotency_key: str) -> Dict[str, Any]:
    """The ``store_credits`` and ``tool_audit`` rows for one write key.

    This is Lab 4's count: one credit and one audit row after an executed
    credit, both still one after a retry, and zero of each for a key Cedar
    refused. Read from the tables, never inferred from the response.

    Never raises: an unreadable table reports itself rather than a zero that
    would read as a keyed-absence proof.
    """
    key = str(idempotency_key or "")
    record: Dict[str, Any] = {
        "idempotencyKey": key,
        "creditRows": 0,
        "creditIds": [],
        "amountCents": None,
        "auditRows": 0,
        "auditIds": [],
        "readable": True,
    }
    if not key:
        record["readable"] = False
        return record
    try:
        credits = [dict(r) for r in (await db.fetch_all(_CREDITS_FOR_KEY, key) or [])]
        audits = [dict(r) for r in (await db.fetch_all(_AUDIT_FOR_KEY, key) or [])]
    except Exception as exc:  # noqa: BLE001 - absence must never be invented
        logger.warning("evidence read failed for key %s: %s", key, exc)
        record["readable"] = False
        return record
    record["creditRows"] = len(credits)
    record["creditIds"] = [int(c["credit_id"]) for c in credits if c.get("credit_id") is not None]
    record["amountCents"] = int(credits[0]["amount_cents"]) if credits else None
    record["auditRows"] = len(audits)
    record["auditIds"] = [int(a["audit_id"]) for a in audits if a.get("audit_id") is not None]
    return record


# ---------------------------------------------------------------------------
# Rail selection
# ---------------------------------------------------------------------------


def gateway_action_id(tool: str) -> str:
    """The Gateway-qualified Cedar action id for a published tool."""
    from services.agentcore_gateway import GATEWAY_TARGET_FOR_TOOL

    target = GATEWAY_TARGET_FOR_TOOL.get(tool)
    if not target:
        raise ExecutionError(f"tool_not_published:{tool}", 422)
    return f"{target}___{tool}"


def _missing_managed_rail_parts(
    gateway_url: str, access_token: Optional[str]
) -> List[str]:
    """Which elements of the managed rail this request cannot supply.

    Named individually rather than reported as one boolean: "the managed rail is
    unavailable" sends an operator looking at the Gateway when the actual gap may
    be an unconfigured policy engine or a token the browser never sent.
    """
    from services.managed_policy import policy_engine_id

    missing: List[str] = []
    if not gateway_url:
        missing.append("AGENTCORE_GATEWAY_URL")
    if not access_token:
        missing.append("access_token")
    if not policy_engine_id():
        missing.append("AGENTCORE_POLICY_ENGINE_ID")
    return missing


@dataclass(frozen=True)
class RailSelection:
    """Which rail will run this execution, and why it cannot be the managed one."""

    rail: str
    refusal_reason: str = ""
    missing: tuple[str, ...] = ()


def select_rail(access_token: Optional[str]) -> RailSelection:
    """Gateway when it is usable; refused in the governed format when it is not.

    Identity passthrough is the point of the managed rail: the Gateway must see
    the staff member's own JWT so Cedar authorizes a person rather than a
    service. Without a token there is nothing to authorize.

    On this lineage ``WORKSHOP_FORMAT`` is ``governed``, which means a governed
    write is managed-rail-only, and the managed rail is all three of a Gateway
    URL, the caller's token, and a policy engine to evaluate the call. Any one of
    them missing is a refusal, checked before the Gateway is considered. The
    builders lineage keeps the in-process rail, because there it is the intended
    path rather than a silent downgrade.
    """
    from config import settings

    gateway_url = str(getattr(settings, "AGENTCORE_GATEWAY_URL", "") or "").strip()
    governed = str(getattr(settings, "WORKSHOP_FORMAT", "") or "").lower() == "governed"

    if not governed:
        if gateway_url and access_token:
            return RailSelection(rail=RAIL_GATEWAY)
        return RailSelection(rail=RAIL_IN_PROCESS)

    missing = _missing_managed_rail_parts(gateway_url, access_token)
    if not missing:
        return RailSelection(rail=RAIL_GATEWAY)
    return RailSelection(
        rail=RAIL_REFUSED,
        refusal_reason=(
            "This deployment runs the governed format, where a write executes only "
            "through the managed Gateway rail under AgentCore Policy. Missing: "
            + ", ".join(missing)
            + ". Nothing was executed."
        ),
        missing=tuple(missing),
    )


def require_enforced_engine(
    selection: RailSelection, engine_state: Optional["PolicyEngineState"]
) -> RailSelection:
    """Refuse the managed rail unless the Gateway attachment is verified ENFORCE.

    A configured engine id proves an engine exists, not that the Gateway is
    enforcing it. ``LOG_ONLY`` at the gateway scope means every verdict is an
    observation and the write commits regardless; an unreadable engine means
    the mode is unknown. Both fail closed for a governed write.
    """
    if selection.rail != RAIL_GATEWAY:
        return selection
    from config import settings

    governed = str(getattr(settings, "WORKSHOP_FORMAT", "") or "").lower() == "governed"
    if not governed:
        return selection
    if engine_state is not None and engine_state.enforcement_is_on:
        return selection
    observed = (engine_state.gateway_mode if engine_state else "") or "unreadable"
    missing = f"policy_engine_mode=ENFORCE (observed: {observed})"
    return RailSelection(
        rail=RAIL_REFUSED,
        refusal_reason=(
            "This deployment runs the governed format, where a write executes only "
            "under an enforcing policy engine. The Gateway attachment is "
            f"{observed}, so no enforced verdict was possible. Missing: {missing}. "
            "Nothing was executed."
        ),
        missing=(missing,),
    )


# ---------------------------------------------------------------------------
# Policy-denial classification
# ---------------------------------------------------------------------------

# Verbatim Gateway deny markers, box-verified 2026-06-12 and reused here rather
# than re-derived: "Tool call not allowed due to policy enforcement [Policy
# evaluation denied due to <policy>-...]".
#
# Deliberately NOT matched: bare AccessDenied / Unauthorized / Forbidden. Those
# describe IAM, JWT, or target failures, and treating them as Cedar denials would
# make a broken Gateway look like a successful governance proof.
_DENIAL_MARKERS = (
    "authorizeactionexception",
    "not allowed due to policy",
    "policy enforcement",
    "policy evaluation denied",
)


def is_output_suppression(error: BaseException | str) -> bool:
    """Recognize explicit response suppression, never infer it from an HTTP code."""
    if isinstance(error, BaseException) and getattr(error, "exceptions", None):
        return any(is_output_suppression(child) for child in error.exceptions)
    from services.gateway_errors import gateway_error_text

    text = gateway_error_text(error).lower()
    return ("suppress" in text and ("output" in text or "response" in text) and "policy" in text) or text.startswith("output blocked by policy:")


def is_policy_denial(error: BaseException | str) -> bool:
    """True only for a Gateway/Cedar authorization denial."""
    if is_output_suppression(error):
        return False
    if isinstance(error, BaseException):
        children = getattr(error, "exceptions", None)
        if children:
            return any(is_policy_denial(child) for child in children)
        from services.gateway_errors import gateway_error_text

        haystack = f"{error.__class__.__name__}: {gateway_error_text(error)}".lower()
    else:
        haystack = str(error).lower()
    return any(marker in haystack for marker in _DENIAL_MARKERS)


# ---------------------------------------------------------------------------
# Aurora outcome classification
# ---------------------------------------------------------------------------

# The RDS Data API stringifies a database error as one sentence ending in
# "; SQLState: 23514", and the Gateway Lambda forwards that string verbatim in a
# status:error envelope. The in-process rail attaches the code as an explicit
# ``sqlstate`` field instead. Both spellings resolve here.
_SQLSTATE_IN_MESSAGE = re.compile(r"SQLState:\s*([0-9A-Z]{5})", re.IGNORECASE)


def extract_sqlstate(result: Mapping[str, Any]) -> str:
    """The five-character SQLSTATE a database error carried, or ``''``."""
    explicit = str(result.get("sqlstate") or "").strip().upper()
    if len(explicit) == 5:
        return explicit
    match = _SQLSTATE_IN_MESSAGE.search(str(result.get("message") or ""))
    return match.group(1).upper() if match else ""


def classify_aurora(result: Mapping[str, Any]) -> tuple[str, str]:
    """Map a tool envelope onto the Aurora axis, with a reason.

    Only ``denied_by: database_row_level_security`` counts as an RLS denial. A
    database error in SQLSTATE class 23 is also a denial: an integrity-constraint
    violation means the statement executed INSIDE Aurora and a database guard
    (CHECK, trigger, foreign key, unique) refused the mutation. Every other
    SQLSTATE class stays on the fallthrough: a syntax error or a cancelled query
    is a failure, not a governance verdict.

    The tool's own approval guard is NOT_REACHED: it refuses before any
    statement touches ``store_credits``, so the database decided nothing.
    """
    status = str(result.get("status") or "")
    denied_by = str(result.get("denied_by") or "")

    if status == "output_suppressed":
        return AURORA_OUTCOME_UNKNOWN, (
            "The Gateway withheld the tool response. This does not roll back a write. "
            "Reconcile the existing operation key in Aurora before retrying."
        )
    if denied_by == APPROVAL_GUARD:
        return AURORA_NOT_REACHED, (
            "The tool refused before any statement reached the database: no "
            "confirmed review fingerprints these exact arguments under this write "
            "key. Nothing changed."
        )
    if denied_by == "database_row_level_security":
        return AURORA_DENIED, (
            "Row-Level Security refused the read the write depends on, so "
            "nothing changed."
        )
    if status == "success":
        replay = bool(result.get("idempotent_replay"))
        return AURORA_PERMITTED, (
            "The write already applied under this key; this call replayed it."
            if replay
            else "The runtime role was in scope and the transaction committed."
        )
    if status == "idempotency_conflict":
        detail = str(result.get("message") or "").strip()
        return AURORA_DENIED, (
            "The call reached Aurora, but the idempotency guard refused this "
            "different write because the key already belongs to another request. "
            "Nothing changed." + (f" Database: {detail}" if detail else "")
        )
    if status == "policy_blocked":
        # A business-rule refusal from the tool itself, for example the $500
        # safety ceiling. Not a database authorization outcome.
        return AURORA_NOT_REACHED, (
            "The tool refused on a business rule before reaching the "
            "protected statement."
        )
    sqlstate = extract_sqlstate(result)
    if sqlstate.startswith("23"):
        detail = str(result.get("message") or "").strip()
        return AURORA_DENIED, (
            "The statement reached Aurora and a database integrity guard "
            f"refused it (SQLSTATE {sqlstate}); the transaction rolled back, "
            "so nothing changed." + (f" Database: {detail}" if detail else "")
        )
    return AURORA_NOT_REACHED, str(result.get("message") or "The write did not run.")


def classify_evidence_for(policy: str, aurora: str, result: Mapping[str, Any]) -> str:
    """The evidence axis names what artifact exists, never what we hoped for."""
    if policy == POLICY_DENY:
        # The tool was never entered, so there is no `tool_audit` row and no
        # idempotency claim. The policy decision itself is the artifact, durable
        # in `pellier.execution_receipts`.
        return EVIDENCE_POLICY_PROOF
    if str(result.get("denied_by") or "") == APPROVAL_GUARD:
        # The tool WAS entered and refused, and both rails leave one attempt row
        # on the ledger for that (the Lambda's independent receipt, the
        # in-process writer's row). The artifact is the attempt, not an absence,
        # so the axis reads the same whichever rail refused.
        return EVIDENCE_ATTEMPT_RECEIPT
    if aurora == AURORA_DENIED:
        return EVIDENCE_ATTEMPT_RECEIPT
    if aurora == AURORA_OUTCOME_UNKNOWN:
        return EVIDENCE_ATTEMPT_RECEIPT
    if aurora == AURORA_PERMITTED and str(result.get("status")) in (
        "success",
        "idempotency_conflict",
    ):
        return EVIDENCE_RECEIPTED
    if aurora == AURORA_NOT_REACHED:
        return EVIDENCE_NO_EXECUTION
    return EVIDENCE_PENDING


# ---------------------------------------------------------------------------
# The two executors
# ---------------------------------------------------------------------------


async def _run_store_tool(db: Any, fn: Any, **arguments: Any) -> Dict[str, Any]:
    """Run one synchronous ``store_tools`` function against the async pool.

    ``store_tools`` functions take a plain ``run(sql, params) -> rows`` so the
    Gateway Lambda can call them too. Here that runner hands each statement to
    the pool on the event loop that owns it, from the worker thread the tool
    runs on, exactly as ``services.agent_tools._run_sql`` does for the agents.
    """
    loop = asyncio.get_running_loop()

    def run(sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        future = asyncio.run_coroutine_threadsafe(db.fetch_all(sql, *params), loop)
        return [dict(row) for row in future.result(timeout=30) or []]

    return await asyncio.to_thread(fn, run, **arguments)


async def _execute_in_process(
    db: Any,
    *,
    tool: str,
    args: Mapping[str, Any],
    idempotency_key: str,
    operator_sub: str,
) -> Dict[str, Any]:
    """Run the governed write locally.

    ``issued_by`` on a credit is the **actor**. That is attribution, and it is
    the staff member, because a credit must record which person authorised the
    money movement.

    Cedar is not consulted on this rail. The caller reports the policy axis as
    NOT_EVALUATED; this function never claims a verdict.

    An integrity-constraint violation raises out of psycopg here rather than
    returning an envelope: the database is the enforcer. It is converted into
    the same status:error envelope the Gateway Lambda produces, with the
    SQLSTATE attached explicitly, so ``classify_aurora`` reads one vocabulary on
    both rails. Every other database error still raises: a connection failure
    is an infrastructure problem, not an Aurora verdict.
    """
    import psycopg

    from services import store_tools

    if tool != "give_store_credit":
        raise ExecutionError(f"action_not_executable:{tool}", 422)
    try:
        return await _run_store_tool(
            db,
            store_tools.give_store_credit,
            customer_id=str(args["customer_id"]),
            amount_cents=int(args["amount_cents"]),
            reason=str(args["reason"]),
            idempotency_key=idempotency_key,
            issued_by=operator_sub or None,
        )
    except psycopg.IntegrityError as exc:
        return {
            "status": "error",
            "message": str(exc),
            "sqlstate": getattr(exc, "sqlstate", None) or "23000",
        }


async def _execute_through_gateway(
    *,
    tool: str,
    args: Mapping[str, Any],
    idempotency_key: str,
    access_token: str,
) -> tuple[str, Dict[str, Any], str]:
    """Invoke the published tool through AgentCore Gateway, deterministically.

    No model in the loop. The arguments come from the confirmed review, and the
    call names the tool directly, so Cedar authorizes exactly the action a human
    approved rather than whatever a model decided to attempt.

    Returns ``(policy_state, result_envelope, note)``. A Cedar denial raises
    inside the MCP session before the Lambda target runs, which is why a denial
    leaves no ``tool_audit`` execution row: the tool was never entered.
    """
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    from config import settings

    gateway_url = str(settings.AGENTCORE_GATEWAY_URL).strip()
    from services.gateway_errors import read_gateway_error_response
    action = gateway_action_id(tool)
    payload = {**{k: v for k, v in args.items()}, "idempotency_key": idempotency_key}

    timeout = httpx.Timeout(30.0, read=300.0)
    try:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
            follow_redirects=False,
            event_hooks={"response": [read_gateway_error_response]},
        ) as http_client:
            async with streamable_http_client(
                gateway_url, http_client=http_client
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    raw = await session.call_tool(action, payload)
    except Exception as exc:  # noqa: BLE001 - classified, not swallowed
        if is_output_suppression(exc):
            return POLICY_ALLOW, {"status": "output_suppressed"}, (
                "The Gateway reported output suppression after authorization. "
                "Execution and commit require separate Aurora evidence."
            )
        if is_policy_denial(exc):
            return (
                POLICY_DENY,
                {
                    "status": "policy_denied",
                    "message": "AgentCore Policy denied the action before the tool ran.",
                    "denied_by": "agentcore_policy",
                },
                "Cedar denied the action; the tool was never entered.",
            )
        # A transport, token, or target failure is NOT a governance proof.
        raise ExecutionError(f"gateway_unavailable:{type(exc).__name__}", 502) from exc

    # The Gateway returned, so Cedar permitted the action (the caller confirms
    # the engine was enforcing from the engine's own mode, never from this
    # response).
    envelope: Dict[str, Any] = {}
    if getattr(raw, "isError", False) and is_output_suppression(str(raw)):
        return POLICY_ALLOW, {"status": "output_suppressed"}, (
            "The Gateway reported output suppression; reconcile the existing operation key."
        )
    for item in getattr(raw, "content", None) or []:
        text = getattr(item, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            envelope = parsed
            break
    if not envelope:
        envelope = {"status": "error", "message": "Gateway returned no tool envelope."}
    return POLICY_ALLOW, envelope, "AgentCore Policy permitted the action."


# ---------------------------------------------------------------------------
# The engine's declared state: a call that returned is an ALLOW only under ENFORCE
# ---------------------------------------------------------------------------


@dataclass
class PolicyEngineState:
    """The engine's own declared state, as the control plane reports it.

    Enforcement is the conjunction of two scopes with different vocabularies: a
    *policy* is ``ACTIVE`` or ``LOG_ONLY``, a *gateway attachment* is ``ENFORCE``
    or ``LOG_ONLY``. Either one in LOG_ONLY means no denial is enforced.
    """

    gateway_mode: str = ""
    # policy name -> (effect, enforcement_mode)
    policies: Dict[str, tuple[str, str]] = field(default_factory=dict)
    # Forbid policies whose Cedar statement names this action.
    matching_forbids: tuple[str, ...] = ()
    # policy name -> control-plane policy id, for attribution.
    policy_ids: Dict[str, str] = field(default_factory=dict)
    policy_engine_id: str = ""
    # Always true for a control-plane read: this is configuration, not a decision.
    inferred: bool = True

    @classmethod
    def from_engine_read(
        cls, state: Optional[Mapping[str, Any]]
    ) -> Optional["PolicyEngineState"]:
        """Build one from what ``managed_policy.engine_state_for_action`` returns."""
        if state is None:
            return None
        if isinstance(state, cls):
            return state
        return cls(
            gateway_mode=str(state.get("gateway_mode") or ""),
            policies=dict(state.get("policies") or {}),
            matching_forbids=tuple(state.get("matching") or ()),
            policy_ids=dict(state.get("policy_ids") or {}),
            policy_engine_id=str(state.get("policy_engine_id") or ""),
            inferred=bool(state.get("inferred", True)),
        )

    @property
    def enforcement_is_on(self) -> bool:
        return str(self.gateway_mode).upper() == "ENFORCE"


def resolve_permissive_policy_state(
    engine: Optional[PolicyEngineState],
) -> tuple[str, str]:
    """Classify a Gateway call that RETURNED, from the engine's declared state.

    Only enforcement makes the return itself informative: under ENFORCE a call
    that came back was genuinely permitted. Anything else is not a decision,
    and matching policy text is not one either.
    """
    if engine is None:
        return POLICY_EVALUATION_INCOMPLETE, (
            "The policy engine state could not be read, so no verdict is claimed."
        )
    if engine.enforcement_is_on:
        return POLICY_ALLOW, "AgentCore Policy evaluated the action and permitted it."
    return POLICY_EVALUATION_INCOMPLETE, (
        f"The gateway is {engine.gateway_mode or 'not in ENFORCE'}, so the call "
        "returning is not a decision."
    )


# ---------------------------------------------------------------------------
# The execution boundary
# ---------------------------------------------------------------------------


async def execute_confirmed_review(
    db: Any,
    review: Mapping[str, Any],
    *,
    operator_sub: str,
    access_token: Optional[str] = None,
    engine_state: Optional[PolicyEngineState] = None,
) -> ExecutionOutcome:
    """Execute the action a human confirmed, and report each axis separately.

    The ordering is the contract:

      1. verify the confirmation against the persisted parameters;
      2. resolve the customer subject server-side;
      3. claim or reuse the execution turn;
      4. derive the deterministic write key;
      5. select the rail, and REFUSE when the governed format requires the
         managed rail and cannot have it;
      6. invoke the governed rail;
      7. classify policy, Aurora, and evidence from what actually happened;
      8. read the durable record for the key, and store the verdicts.

    Nothing in that sequence reads an action parameter from a caller. Step 8 is
    best-effort ABOUT an execution that already happened when the database is
    unreachable; a receipt the database refuses on a constraint is a defect
    and raises (see :func:`record_receipt`). A retry is then a replay.

    Raises:
        GovernedRailUnavailable: The governed format requires the managed rail and
            an element of it is missing. Nothing was executed, and a refused
            receipt records that.
        ExecutionError: ``execution_receipt_rejected`` when the receipt table
            refused the verdicts this module wrote.
    """
    args = verify_confirmation(review)
    tool = str(review["action"])
    review_id = int(review["review_id"])
    action_hash = str(review["action_hash"])
    customer_id = str(args["customer_id"])

    customer_subject = await resolve_customer_subject(db, customer_id)
    execution_turn_id = await claim_execution_turn(db, review_id)
    idempotency_key = execution_idempotency_key(review_id, action_hash)

    selection = require_enforced_engine(select_rail(access_token), engine_state)
    rail = selection.rail

    if rail == RAIL_REFUSED:
        raise await _refuse_governed_execution(
            db,
            review_id=review_id,
            tool=tool,
            selection=selection,
            operator_sub=operator_sub,
            customer_subject=customer_subject,
            execution_turn_id=execution_turn_id,
            idempotency_key=idempotency_key,
        )

    if rail == RAIL_GATEWAY:
        policy, result, notes = await _run_gateway_rail(
            tool=tool, args=args, idempotency_key=idempotency_key,
            access_token=str(access_token), engine_state=engine_state,
        )
    else:
        policy, result, notes = await _run_in_process_rail(
            db, tool=tool, args=args, idempotency_key=idempotency_key,
            operator_sub=operator_sub, customer_id=customer_id,
        )

    aurora, aurora_note = _classify_aurora_axis(policy, result)
    notes["aurora"] = aurora_note
    evidence = classify_evidence_for(policy, aurora, result)

    outcome = ExecutionOutcome(
        rail=rail,
        execution_turn_id=execution_turn_id,
        idempotency_key=idempotency_key,
        operator_sub=operator_sub,
        customer_subject=customer_subject,
        policy=policy,
        aurora=aurora,
        evidence=evidence,
        tool=tool,
        result=dict(result),
        notes=notes,
        record=await evidence_for_key(db, idempotency_key),
    )
    return await _record(db, outcome, review_id=review_id, engine_state=engine_state)


async def _record(
    db: Any,
    outcome: ExecutionOutcome,
    *,
    review_id: int,
    engine_state: Optional["PolicyEngineState"],
) -> ExecutionOutcome:
    """Step 8, ABOUT an execution that already happened.

    A Cedar DENY writes no tool_audit row, claims no idempotency key and touches
    no domain table, so without the receipt the only proof of a refusal is the
    response body. It is written after classification, so the stored receipt and
    the returned payload carry the same axes. An unreachable receipt table is
    reported in the outcome; a receipt the table refuses raises from
    :func:`record_receipt`.
    """
    receipt_id = await record_receipt(
        db, outcome, review_id=review_id, engine_state=engine_state
    )
    if receipt_id is None:
        # The call returned but its durable classification does not exist. Keep the
        # business result and report the evidence gap, rather than claiming
        # RECEIPTED.
        outcome.evidence = EVIDENCE_PENDING
        outcome.notes["evidence"] = (
            "The governed call returned, but its execution receipt could not be "
            "recorded. Inspect the tool audit and the store credits before relying "
            "on this attempt as durable proof."
        )
    return outcome


async def _run_gateway_rail(
    *,
    tool: str,
    args: Mapping[str, Any],
    idempotency_key: str,
    access_token: str,
    engine_state: Optional["PolicyEngineState"],
) -> tuple[str, Dict[str, Any], Dict[str, str]]:
    """Invoke the managed rail and resolve its policy axis from real evidence.

    The Gateway's response is the first reading; the engine's declared mode is
    the second. A DENY stands on its own. A call that returned is an ALLOW only
    when the engine was enforcing at the time.

    Returns:
        ``(policy_state, tool_envelope, notes)``.
    """
    policy, result, policy_note = await _execute_through_gateway(
        tool=tool,
        args=args,
        idempotency_key=idempotency_key,
        access_token=access_token,
    )
    if policy == POLICY_ALLOW:
        policy, policy_note = resolve_permissive_policy_state(engine_state)
    notes: Dict[str, str] = {"policy": policy_note}
    if result.get("status") == "output_suppressed":
        notes["output"] = "The Gateway reported output suppression. Reconcile the operation in Aurora."
    return policy, dict(result), notes


async def _run_in_process_rail(
    db: Any,
    *,
    tool: str,
    args: Mapping[str, Any],
    idempotency_key: str,
    operator_sub: str,
    customer_id: str,
) -> tuple[str, Dict[str, Any], Dict[str, str]]:
    """Run the write locally, claim no policy verdict, and leave one audit row.

    Reached only in the builders format: ``select_rail`` refuses this path in
    the governed one rather than downgrading to it.

    The audit row matches the Gateway Lambda's: one per executed credit,
    including a refused attempt, and none on an idempotent replay, because
    Aurora applied nothing then and the first row stays the receipt for the key.

    Returns:
        ``(POLICY_NOT_EVALUATED, tool_envelope, notes)``.
    """
    from services import tool_audit_writer

    notes = {
        "rail": (
            "This deployment runs the builders format, where the in-process rail "
            "is the intended path for a governed write."
        ),
        "policy": (
            "This execution ran in process, so AgentCore Policy was not "
            "consulted. Only the managed Gateway rail produces a Cedar verdict."
        ),
    }
    started = time.monotonic()
    result = await _execute_in_process(
        db,
        tool=tool,
        args=args,
        idempotency_key=idempotency_key,
        operator_sub=operator_sub,
    )
    if not bool(result.get("idempotent_replay")):
        audit_id = await tool_audit_writer.record_executed_credit(
            db,
            args={**dict(args), "idempotency_key": idempotency_key},
            result=dict(result),
            latency_ms=int((time.monotonic() - started) * 1000),
            operator_sub=operator_sub,
            customer_id=customer_id,
        )
        if audit_id is not None:
            notes["audit"] = f"tool_audit row {audit_id} records this attempt."
    else:
        notes["audit"] = (
            "Idempotent replay: Aurora applied nothing, so the first attempt's "
            "tool_audit row stays the one receipt for this key."
        )
    return POLICY_NOT_EVALUATED, dict(result), notes


async def _refuse_governed_execution(
    db: Any,
    *,
    review_id: int,
    tool: str,
    selection: RailSelection,
    operator_sub: str,
    customer_subject: Optional[str],
    execution_turn_id: str,
    idempotency_key: str,
) -> "GovernedRailUnavailable":
    """Record that the managed rail was required and unusable, and refuse.

    A refusal is evidence in its own right: it is the moment the system declined
    to write rather than writing without a verdict, and it must survive the HTTP
    response like every other governance outcome.
    """
    outcome = ExecutionOutcome(
        rail=RAIL_REFUSED,
        execution_turn_id=execution_turn_id,
        idempotency_key=idempotency_key,
        operator_sub=operator_sub,
        customer_subject=customer_subject,
        policy=POLICY_EVALUATION_INCOMPLETE,
        aurora=AURORA_NOT_REACHED,
        evidence=EVIDENCE_NO_EXECUTION,
        tool=tool,
        result={
            "status": "refused",
            "message": selection.refusal_reason,
            "missing": list(selection.missing),
        },
        notes={
            "rail": "The managed rail was required and could not be used.",
            "refusal_reason": selection.refusal_reason,
            "policy": (
                "No policy engine was consulted, because the call was never made. "
                "That is not an ALLOW and not a NOT_EVALUATED: the governed rail "
                "was required here and its verdict is missing."
            ),
            "aurora": "No statement reached the database.",
            "evidence": (
                "This refusal is the artifact. There is no tool audit row and no "
                "idempotency claim, because nothing executed."
            ),
        },
    )
    receipt_id = await record_receipt(db, outcome, review_id=review_id)
    logger.warning(
        "governed execution refused for review %s: missing %s",
        review_id, ", ".join(selection.missing),
    )
    return GovernedRailUnavailable(
        selection.missing, reason=selection.refusal_reason, receipt_id=receipt_id
    )


def _classify_aurora_axis(policy: str, result: Mapping[str, Any]) -> tuple[str, str]:
    """The Aurora axis for one execution."""
    if policy == POLICY_DENY:
        return AURORA_NOT_REACHED, (
            "The tool was never entered, so no statement reached the database."
        )
    return classify_aurora(result)
