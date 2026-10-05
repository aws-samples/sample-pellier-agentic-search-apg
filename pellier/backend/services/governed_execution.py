"""Governed execution of a confirmed operator review.

A person said yes. This module answers the next question, *is the system
allowed to do it?*, and keeps the answers separate.

The actor is the authenticated staff member (Nadia). Cedar decides whether
that person may attempt the credit; the customer, amount and reason come from
the approved review, never from the caller.

Three independent controls
--------------------------

    Cedar        may this principal attempt this action?
    Approval     does a confirmed review approve these exact arguments, is
                 this write under that review's own key, and does every order
                 it covers still lack a credit? (``pellier.apply_store_credit``)
    CHECK        is this mutation valid regardless of who asked?

Each can fail while the others pass. The assurance axes this module returns are
derived from separate artifacts, never from one another.

What this module will not do
----------------------------

It will not report a policy verdict that no policy engine produced. On the
in-process rail the policy axis says ``NOT_EVALUATED`` and carries the reason.
A convenient ``ALLOW`` there would be the single most damaging lie this surface
could tell.

"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

# The write key is derived in ``store_tools``; ``pellier.apply_store_credit``
# recomputes it and admits a write only under the key of the approved review.
# This module derives the same key for the Operator's execute path.
from services.store_tools import WRITE_GUARDS, execution_idempotency_key

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

RAIL_GATEWAY = "gateway-mcp"
RAIL_IN_PROCESS = "in-process"
# Not a rail that ran. The governed format requires the managed rail, so an
# execution that cannot reach it is refused before anything runs, rather than
# quietly downgraded to the in-process rail.
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

    Nothing ran, so nothing is written; the 409 names what is missing.
    """

    def __init__(self, missing: tuple[str, ...], *, reason: str) -> None:
        super().__init__("governed_rail_unavailable", 409)
        self.missing = tuple(missing)
        self.reason = reason

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
# The durable record: what store_credits and tool_audit hold for a key
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
        # Who wrote the first audit row: 'gateway' for the Lambda, the staff
        # member's subject for the in-process rail.
        "auditCaller": None,
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
    record["auditCaller"] = str(audits[0].get("caller") or "") or None if audits else None
    return record


# ---------------------------------------------------------------------------
# approvals.last_attempt: what the Gateway answered the desk, last time
# ---------------------------------------------------------------------------

ATTEMPT_ALLOWED = "allowed"  # the call got past authorization and the tool ran
ATTEMPT_DENIED = "denied"    # AgentCore Policy denied it before the tool ran
ATTEMPT_REFUSED = "refused"  # the desk sent nothing: the governed rail was not ready
ATTEMPT_FAILED = "failed"    # the call did not complete, so no answer came back

_ATTEMPT_DETAIL_LIMIT = 500

_RECORD_LAST_ATTEMPT = """
    UPDATE pellier.approvals
       SET last_attempt = %s::jsonb
     WHERE id = %s
    RETURNING id
"""


def last_attempt(
    outcome: str,
    *,
    idempotency_key: str,
    rail: str,
    policy: str,
    engine_state: Optional["PolicyEngineState"],
    detail: Optional[str] = None,
) -> Dict[str, Any]:
    """One execute attempt's answer, in the shape ``approvals.last_attempt`` stores.

    The engine fields are the attribution the control plane gave for this
    action at the time: its mode, the forbid policies naming the action, and
    a digest of the policy set. ``detail`` is the Gateway's words for a
    denial, the error for a failure, or what was missing for a refusal.
    """
    from datetime import datetime, timezone

    engine = engine_state
    return {
        "outcome": outcome,
        "at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": idempotency_key,
        "rail": rail,
        "policy": policy,
        "engine_mode": (engine.gateway_mode or None) if engine else None,
        "matching_forbids": list(engine.matching_forbids) if engine else [],
        "policy_engine_id": (engine.policy_engine_id or None) if engine else None,
        "policy_digest": (engine.policy_digest or None) if engine else None,
        "detail": str(detail)[:_ATTEMPT_DETAIL_LIMIT] if detail else None,
    }


async def record_last_attempt(db: Any, review_id: int, attempt: Mapping[str, Any]) -> None:
    """Overwrite the review's ``last_attempt``.

    Logged, never raised, when the write fails: the attempt's own answer still
    reaches the desk, and ``tool_audit`` and ``store_credits`` stay the
    evidence of what ran and what was paid.
    """
    try:
        await db.fetch_all(_RECORD_LAST_ATTEMPT, json.dumps(dict(attempt)), int(review_id))
    except Exception as exc:  # noqa: BLE001 - the answer is a record, not a gate
        logger.warning("last attempt not stored for review %s: %s", review_id, exc)


# A stored answer, read back after a reload, in the desk's words. Each sentence
# is labeled as what the Gateway answered, never as proof that anything ran.
_ATTEMPT_SENTENCES = {
    ATTEMPT_ALLOWED: "the call went through and the tool ran",
    ATTEMPT_DENIED: "AgentCore Policy denied it before the tool ran",
    ATTEMPT_REFUSED: "the desk sent nothing, because the governed rail was not ready",
    ATTEMPT_FAILED: "the call did not complete, so no verdict came back",
}


def attempt_note(attempt: Mapping[str, Any]) -> str:
    """One sentence for the desk about a stored ``last_attempt``."""
    at = str(attempt.get("at") or "")
    when = f"{at[:10]} {at[11:16]} UTC" if at else "an earlier attempt"
    evidence = "tool_audit and store_credits show what ran and what was paid."
    if attempt.get("rail") == RAIL_IN_PROCESS:
        return (f"Stored from the last attempt, {when}: it ran in process, so no policy "
                f"engine was asked. {evidence}")
    said = _ATTEMPT_SENTENCES.get(str(attempt.get("outcome")), "an unrecognized answer")
    return f"What the Gateway answered the desk, {when}: {said}{_attribution(attempt)}. {evidence}"


def _attribution(attempt: Mapping[str, Any]) -> str:
    """The engine's part of a stored answer: its mode, or the forbids naming the action."""
    outcome = attempt.get("outcome")
    if outcome == ATTEMPT_ALLOWED:
        if attempt.get("policy") == POLICY_ALLOW:
            return ", under ENFORCE, so AgentCore Policy permitted it"
        mode = attempt.get("engine_mode") or "unreadable"
        return f", but the attachment was {mode}, so that is not a decision"
    forbids = ", ".join(attempt.get("matching_forbids") or [])
    if outcome == ATTEMPT_DENIED and forbids:
        return f" (forbid policies naming this action: {forbids})"
    return ""


def attempt_payload(attempt: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """A stored ``last_attempt`` in the API's field names."""
    if attempt is None:
        return None
    return {
        "outcome": attempt.get("outcome"),
        "at": attempt.get("at"),
        "idempotencyKey": attempt.get("idempotency_key"),
        "rail": attempt.get("rail"),
        "policy": attempt.get("policy"),
        "engineMode": attempt.get("engine_mode"),
        "matchingForbids": list(attempt.get("matching_forbids") or []),
        "policyEngineId": attempt.get("policy_engine_id"),
        "policyDigest": attempt.get("policy_digest"),
        "detail": attempt.get("detail"),
    }


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

    ``pellier.apply_store_credit``'s own refusals (no matching approval, not
    this review's key, an order already credited) are DENIED: the call reached
    the database and its function refused before touching ``store_credits``.
    """
    status = str(result.get("status") or "")
    denied_by = str(result.get("denied_by") or "")

    if status == "output_suppressed":
        return AURORA_OUTCOME_UNKNOWN, (
            "The Gateway withheld the tool response. This does not roll back a write. "
            "Reconcile the existing operation key in Aurora before retrying."
        )
    if denied_by in WRITE_GUARDS:
        return AURORA_DENIED, (
            "pellier.apply_store_credit refused the write: "
            + (str(result.get("message") or "").strip() or "the approval does not admit it.")
            + " Nothing changed."
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
        # credit. The Gateway's decision is the artifact; Aurora holds only the
        # absence of rows for the key.
        return EVIDENCE_POLICY_PROOF
    if str(result.get("denied_by") or "") in WRITE_GUARDS:
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
            from services.gateway_errors import gateway_error_text

            return (
                POLICY_DENY,
                {
                    "status": "policy_denied",
                    "message": "AgentCore Policy denied the action before the tool ran.",
                    "denied_by": "agentcore_policy",
                    # The Gateway's own words, which name the policy that denied.
                    "gateway_message": gateway_error_text(exc)[:_ATTEMPT_DETAIL_LIMIT],
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
    # SHA-256 over every attached policy's name and Cedar (managed_policy.policy_digest).
    policy_digest: str = ""
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
            policy_digest=str(state.get("policy_digest") or ""),
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
      2. claim or reuse the execution turn;
      3. derive the deterministic write key;
      4. select the rail, and REFUSE when the governed format requires the
         managed rail and cannot have it;
      5. invoke the governed rail, and store its answer on the review
         (``approvals.last_attempt``), refusals and failures included;
      6. classify policy, Aurora, and evidence from what actually happened;
      7. read the durable record for the key.

    Nothing in that sequence reads an action parameter from a caller. A retry
    is a replay: the same key returns the first credit.

    Raises:
        GovernedRailUnavailable: The governed format requires the managed rail and
            an element of it is missing. Nothing was executed.
    """
    args = verify_confirmation(review)
    tool = str(review["action"])
    review_id = int(review["review_id"])
    action_hash = str(review["action_hash"])
    customer_id = str(args["customer_id"])

    execution_turn_id = await claim_execution_turn(db, review_id)
    idempotency_key = execution_idempotency_key(review_id, action_hash)

    selection = require_enforced_engine(select_rail(access_token), engine_state)
    rail = selection.rail

    attempt = functools.partial(
        last_attempt, idempotency_key=idempotency_key, rail=rail,
        engine_state=None if rail == RAIL_IN_PROCESS else engine_state,
    )

    if rail == RAIL_REFUSED:
        logger.warning(
            "governed execution refused for review %s: missing %s",
            review_id, ", ".join(selection.missing),
        )
        await record_last_attempt(db, review_id, attempt(
            ATTEMPT_REFUSED, policy=POLICY_NOT_EVALUATED,
            detail="Missing: " + ", ".join(selection.missing),
        ))
        raise GovernedRailUnavailable(selection.missing, reason=selection.refusal_reason)

    try:
        policy, result, notes = await _invoke_rail(
            db, rail, tool=tool, args=args, idempotency_key=idempotency_key,
            access_token=access_token, engine_state=engine_state,
            operator_sub=operator_sub, customer_id=customer_id,
        )
    except Exception as exc:
        await record_last_attempt(db, review_id, attempt(
            ATTEMPT_FAILED,
            policy=POLICY_EVALUATION_INCOMPLETE if rail == RAIL_GATEWAY else POLICY_NOT_EVALUATED,
            detail=getattr(exc, "code", None) or exc.__class__.__name__,
        ))
        raise

    await record_last_attempt(db, review_id, attempt(
        ATTEMPT_DENIED if policy == POLICY_DENY else ATTEMPT_ALLOWED,
        policy=policy, detail=result.get("gateway_message"),
    ))

    aurora, aurora_note = _classify_aurora_axis(policy, result)
    notes["aurora"] = aurora_note
    evidence = classify_evidence_for(policy, aurora, result)

    return ExecutionOutcome(
        rail=rail,
        execution_turn_id=execution_turn_id,
        idempotency_key=idempotency_key,
        operator_sub=operator_sub,
        policy=policy,
        aurora=aurora,
        evidence=evidence,
        tool=tool,
        result=dict(result),
        notes=notes,
        record=await evidence_for_key(db, idempotency_key),
    )


async def _invoke_rail(
    db: Any,
    rail: str,
    *,
    tool: str,
    args: Mapping[str, Any],
    idempotency_key: str,
    access_token: Optional[str],
    engine_state: Optional["PolicyEngineState"],
    operator_sub: str,
    customer_id: str,
) -> tuple[str, Dict[str, Any], Dict[str, str]]:
    """Run the selected rail: the Gateway, or the builders' in-process rail."""
    if rail == RAIL_GATEWAY:
        return await _run_gateway_rail(
            tool=tool, args=args, idempotency_key=idempotency_key,
            access_token=str(access_token), engine_state=engine_state,
        )
    return await _run_in_process_rail(
        db, tool=tool, args=args, idempotency_key=idempotency_key,
        operator_sub=operator_sub, customer_id=customer_id,
    )


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


def _classify_aurora_axis(policy: str, result: Mapping[str, Any]) -> tuple[str, str]:
    """The Aurora axis for one execution."""
    if policy == POLICY_DENY:
        return AURORA_NOT_REACHED, (
            "The tool was never entered, so no statement reached the database."
        )
    return classify_aurora(result)
