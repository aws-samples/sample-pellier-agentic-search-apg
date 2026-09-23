"""One Operator Concierge turn, end to end.

Three workflows, one path
-------------------------

    client_summary          what this relationship looks like right now
    investigate_resolution  what the records establish, kept apart from what a
                            source reports
    draft_client_note       customer-facing copy, plus the evidence behind it
    replacement_search      a real order item, hybrid retrieval over Aurora, and
                            availability reconciled against the inventory ledger

They differ in their contract with the model, in how the result is labelled, and —
for one of them — in the extra evidence a declared context stage contributes before
synthesis. They share the turn lifecycle, the evidence loader, the memory contract,
the persistence and the failure handling, because four copies of that would mean four
places for the FACT/CONTEXT discipline to rot. Which one runs is derived from the
request text by `classify_workflow`, so a suggestion chip and an equivalent typed
question reach the same code.

Every model workflow here is a READ. A separate deterministic context stage may
prepare one exact action when the operator explicitly asks for it; the graph
never authors material parameters, confirms a review, or performs a business
mutation.

Three state classes, kept apart
-------------------------------

    AgentCore Memory    what the agent should remember about this conversation
    PostgreSQL          what is true now (Aurora PostgreSQL when deployed)
    Amazon Bedrock      synthesis over the other two
    Strands Graph       investigator -> resolution planner orchestration

The load-bearing rule is that the model never becomes a source of facts. It receives
structured evidence and returns prose; every identifier, count, amount, membership
rung and status in the response is carried through from the Aurora read. Nothing is
parsed back out of model output, because a summary that invents an order id is
indistinguishable from one that reports a real one.

Why Jessica is the test case
---------------------------

Her evidence does not agree with itself. ``pellier.support_tickets`` holds
TKT-2026-3015, "Return received, refund amount disputed", while
``pellier.returns`` holds no row for her. A weak implementation says "Jessica
returned an order". A correct one distinguishes:

    FACT       five orders exist; the returns table has zero rows for her
    CONTEXT    a support ticket states a return was received
    INFERENCE  the dispute should be reviewed before responding

So evidence carries an epistemic role, and the roles survive into the artifact where
the UI can render them differently. Correctness is asserted on the structured facts,
not on the model's wording.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.data_source import database_source_label

logger = logging.getLogger(__name__)

# Epistemic roles. Flattening these into "facts" is how an assertion becomes a claim.
ROLE_FACT = "fact"
ROLE_CONTEXT = "context"
ROLE_INFERENCE = "inference"

# Source labels shown in the UI. Professional names, not tracing identifiers.
SOURCE_MEMORY = "AgentCore Memory"
SOURCE_BEDROCK = "Amazon Bedrock"
SOURCE_STRANDS_GRAPH = "Strands Graph"
SOURCE_HANDOFF = "Storefront handoff"
# The control plane that publishes capability. NOT "AgentCore Policy": no policy has
# been evaluated when a capability is merely read, and listing Policy as a
# participating source would imply an authorization decision that has not happened.
SOURCE_POLICY_PLANE = "AgentCore control plane"


# Kept under the established name because it marks the authoritative database role
# throughout this module. The value is runtime truth, not a hard-coded product claim.
SOURCE_AURORA = database_source_label()

# Workflow kinds this orchestrator can actually run. The config route publishes this
# so the UI offers only what exists.
WORKFLOW_CLIENT_SUMMARY = "client_summary"
WORKFLOW_INVESTIGATE = "investigate_resolution"
WORKFLOW_DRAFT_NOTE = "draft_client_note"
WORKFLOW_REPLACEMENT = "replacement_search"

# Bounded conversation context. Unlimited history to a model is a cost and a
# relevance problem, not a feature.
_MEMORY_TURN_LIMIT = 8

_MAX_SYNTHESIS_TOKENS = 700


@dataclass
class Step:
    """One observable operation. Never a reasoning step."""

    kind: str
    label: str
    source: str
    status: str = "complete"
    duration_ms: Optional[int] = None
    result: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "source": self.source,
            "status": self.status,
            "durationMs": self.duration_ms,
            "result": self.result,
            "metadata": self.metadata,
        }


@dataclass
class Evidence:
    """A fact, an assertion, or an inference — with which one it is attached."""

    kind: str
    role: str
    status: str
    source: str
    label: str
    detail: str = ""
    record_id: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "role": self.role,
            "status": self.status,
            "source": self.source,
            "label": self.label,
            "note": self.detail,
            "recordId": self.record_id,
            "data": self.data,
        }


def _money(value: Any) -> str:
    """USD, formatted the way the client record beside it formats the same figure.

    The record shows `$3,940.00`; an evidence row reading `3940.0` for the same number
    in the same viewport reads as a different, less trustworthy system. Non-numeric
    input passes through unchanged rather than raising: an evidence detail must never
    be the thing that fails a turn.
    """
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


class _Timer:
    """Real measured duration. An invented one would be a lie in a proof surface."""

    def __init__(self) -> None:
        self.ms: int = 0

    def __enter__(self) -> "_Timer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.ms = int((time.perf_counter() - self._t0) * 1000)
        return False


# ---------------------------------------------------------------------------
# Aurora evidence
# ---------------------------------------------------------------------------


async def load_client_evidence(
    db: Any, customer_id: str
) -> Tuple[Dict[str, Any], List[Step], List[Evidence]]:
    """Current business truth for a client summary, read concurrently.

    Reuses the Operator client-record read so there is one definition of what a
    client record is. That read already fans five independent queries out with
    `asyncio.gather`; duplicating the SQL here would let the two drift.
    """
    from routes.operator import get_client

    steps: List[Step] = []
    evidence: List[Evidence] = []

    with _Timer() as timer:
        try:
            record = await get_client(client_id=customer_id, db=db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("client evidence load failed for %s: %s", customer_id, exc)
            steps.append(
                Step("client", "Client record", SOURCE_AURORA, status="failed")
            )
            return {}, steps, evidence
    duration = timer.ms

    client = record.get("client") or {}
    orders = record.get("orders") or []
    tickets = record.get("tickets") or []
    credits = record.get("credits") or []
    returns = record.get("returns") or []
    return_evidence = client.get("returnEvidence") or {}

    # One read produced all of it, so one step per logical source rather than one
    # per SQL statement: the operator cares which kinds of evidence were consulted.
    steps.append(Step("client", "Client record loaded", SOURCE_AURORA,
                      duration_ms=duration, result=client.get("name", "")))
    steps.append(Step("order", "Order history loaded", SOURCE_AURORA,
                      result=f"{len(orders)} {'order' if len(orders) == 1 else 'orders'}"))
    steps.append(Step("ticket", "Service context loaded", SOURCE_AURORA,
                      result=f"{len(tickets)} {'ticket' if len(tickets) == 1 else 'tickets'}"))
    steps.append(Step("return", "Return records checked", SOURCE_AURORA,
                      result=f"{len(returns)} {'return' if len(returns) == 1 else 'returns'}"))

    evidence.append(Evidence(
        kind="client", role=ROLE_FACT, status="verified", source=SOURCE_AURORA,
        label="Client standing", record_id=str(client.get("customerId") or ""),
        detail=f"{client.get('membership', '')} · "
               f"{_money(client.get('spend12mo', 0))} in 12-month spend",
        data={
            "membership": client.get("membership"),
            "spend12mo": client.get("spend12mo"),
            "name": client.get("name"),
        },
    ))
    evidence.append(Evidence(
        kind="order", role=ROLE_FACT, status="verified", source=SOURCE_AURORA,
        label="Order history",
        detail=(
            f"{len(orders)} orders totalling "
            f"{_money(client.get('orderValue', 0))}. Order lines: "
            + "; ".join(
                f"#{order.get('orderId')} {order.get('productName')}: "
                f"{_money(
                    float(order.get('price') or 0)
                    * int(order.get('quantity') or 1)
                )}"
                for order in orders[:10]
            )
        ),
        data={"orderCount": len(orders),
              "orderIds": [o.get("orderId") for o in orders][:10]},
    ))
    evidence.append(Evidence(
        kind="credit", role=ROLE_FACT, status="verified", source=SOURCE_AURORA,
        label="Store credit",
        detail=f"{_money(client.get('creditBalance', '0.00'))} on file",
        data={"creditBalanceCents": client.get("creditBalanceCents", 0)},
    ))

    # The authoritative return position, stated as a fact even when it is zero.
    # The graph needs item-level evidence, not just a count. Otherwise it asks
    # the operator to retrieve records this request has already loaded.
    return_lines = [
        f"Return #{row.get('returnId')}: "
        f"{row.get('productName') or 'product ' + str(row.get('productId') or 'unidentified')}, "
        f"status {row.get('status') or 'not recorded'}, "
        f"reason {str(row.get('reason') or 'not recorded').replace('_', ' ')}"
        for row in returns[:10]
    ]
    evidence.append(Evidence(
        kind="return", role=ROLE_FACT, status="verified", source=SOURCE_AURORA,
        label="Return records",
        detail=(
            f"{len(returns)} authoritative return "
            f"{'record' if len(returns) == 1 else 'records'}. "
            + "; ".join(return_lines)
            if returns else "No authoritative return record is currently present"
        ),
        data={"authoritativeReturnCount": len(returns), "returns": returns[:10]},
    ))

    # A ticket is a source REPORTING something. That is context, not fact, and the
    # distinction is the whole point of this workflow.
    for ticket in tickets:
        last_note = " ".join(str(ticket.get("lastNote") or "").split())[:400]
        ticket_detail = (
            f"{ticket.get('subject', '')} ({ticket.get('status', '')})"
        )
        if last_note:
            ticket_detail += f". Source note: {last_note}"
        evidence.append(Evidence(
            kind="ticket", role=ROLE_CONTEXT, status="unverified",
            source=SOURCE_AURORA, label="Service context",
            record_id=str(ticket.get("ticketId") or ""),
            detail=ticket_detail,
            data={"lastNote": ticket.get("lastNote", "")},
        ))

    if return_evidence.get("unconfirmedReturnAssertion"):
        # Two separate facts. Which named pieces have no return record at all, and
        # the receipt claim, which no return record can confirm: Pellier stores
        # return requests, not parcels arriving.
        def _names(ids: Any) -> List[str]:
            wanted = {str(value) for value in (ids or [])}
            return list(dict.fromkeys(
                str(order.get("productName"))
                for order in orders
                if str(order.get("productId") or "") in wanted
                and order.get("productName")
            ))

        unrecorded_ids = return_evidence.get("unrecordedDisputedProductIds") or []
        unrecorded = _names(unrecorded_ids)
        recorded = _names(
            set(return_evidence.get("disputedProductIds") or []) - set(unrecorded_ids)
        )
        parts = ["A support ticket reports that returned goods were received."]
        if unrecorded:
            parts.append(f"No return record exists for {', '.join(unrecorded)}.")
        if recorded:
            parts.append(
                f"A return request is recorded for {', '.join(recorded)}; a request "
                "does not show that the parcel arrived."
            )
        parts.append(
            "Pellier holds no receiving record, so the claim that goods were "
            "received remains unverified. A return for a different item does not "
            "confirm this report."
        )
        evidence.append(Evidence(
            kind="return_conflict", role=ROLE_CONTEXT, status="unverified",
            source=SOURCE_AURORA, label="Unconfirmed assertion",
            detail=" ".join(parts),
        ))

    if client.get("personaId") == "theo":
        from services.replacement_recovery import read_replacements
        try:
            care = await read_replacements(db, customer_id)
        except Exception:
            care = {"available": False, "replacements": []}
        if care["available"]:
            steps.append(Step("replacement", "Replacement records checked", SOURCE_AURORA,
                              result=f"{len(care['replacements'])} recorded operations"))
            for replacement in care["replacements"]:
                follow_up = (
                    "Operator follow-up is required. "
                    if replacement.get("workflowResolution") == "operator_review_required" else ""
                )
                evidence.append(Evidence(
                    kind="replacement_operation", role=ROLE_FACT, status="verified",
                    source=SOURCE_AURORA, label="Replacement recovery",
                    record_id=replacement["replacementId"],
                    detail=(
                        f"Order #{replacement['orderId']}, {replacement['productName']}, "
                        f"quantity {replacement['quantity']}. Recorded state: {replacement['state']}. "
                        f"{follow_up}"
                        f"Approval #{replacement['reviewId']}. Fulfillment uses a workshop simulator, "
                        "not a real carrier. Reconcile this operation before proposing another remedy."
                    ),
                    data=replacement,
                ))
        else:
            evidence.append(Evidence(
                kind="replacement_operation", role=ROLE_FACT, status="unavailable",
                source=SOURCE_AURORA, label="Replacement recovery",
                detail="Replacement records are unavailable. Do not infer reservation, approval, or shipment from conversation memory.",
            ))

    return record, steps, evidence


# ---------------------------------------------------------------------------
# AgentCore Memory
# ---------------------------------------------------------------------------


async def load_memory_context(
    *, operator_sub: str, session_id: str
) -> Tuple[List[Dict[str, Any]], Optional[Step]]:
    """Bounded conversational context. Returns no step when Memory was not used.

    A source row for a system that did not participate is architecture theatre, so
    an unconfigured Memory yields `(none, None)` and the Investigation simply has one
    fewer row rather than a decorative one.

    A read served by the process-local fallback is reported as `unavailable`, not as a
    successful empty read. AgentCore Memory was not reached, so it did not participate,
    so it must not appear as an evidence source — and "the managed store holds nothing"
    is a different fact from "the managed store was never asked".
    """
    from services import operator_concierge_sessions as sessions

    try:
        from services.agentcore_memory import AgentCoreMemory
    except Exception:  # noqa: BLE001
        return [], None

    identity = sessions.memory_identity(
        operator_sub=operator_sub, session_id=session_id
    )
    with _Timer() as timer:
        try:
            memory = AgentCoreMemory()
            # The GENERIC reader, matching the generic writer's identity pair.
            # `get_session_history` is the shopper reader and would look up
            # actor=session_id, which is not where an operator turn was written.
            turns, backend = await memory.get_memory_events(
                actor_id=identity["actor_id"],
                session_id=identity["session_id"],
            )
        except Exception as exc:  # noqa: BLE001 - context is best effort
            logger.info("AgentCore Memory read unavailable: %s", exc)
            return [], Step(
                "memory", "Conversation memory unavailable", SOURCE_MEMORY,
                status="unavailable",
            )
    from services.agentcore_memory import BACKEND_AGENTCORE

    if backend != BACKEND_AGENTCORE:
        # The managed store was not reached. Whatever the fallback dict holds is
        # process-local state, not remembered context, so none of it is offered to
        # the model and the row says the service is unavailable.
        return [], Step(
            "memory", "Conversation memory unavailable", SOURCE_MEMORY,
            status="unavailable", duration_ms=timer.ms,
            result="AgentCore Memory was not reached",
        )

    recent = list(turns or [])[-_MEMORY_TURN_LIMIT:]
    # "Loaded ... 0 prior turns" reads as a successful retrieval of nothing. The
    # read genuinely happened, so the row stays — but it says what it found.
    if not recent:
        return recent, Step(
            "memory", "Conversation context checked", SOURCE_MEMORY,
            duration_ms=timer.ms, result="No prior conversation context",
        )
    plural = "turn" if len(recent) == 1 else "turns"
    return recent, Step(
        "memory", "Conversation context loaded", SOURCE_MEMORY,
        duration_ms=timer.ms, result=f"{len(recent)} prior {plural}",
    )


async def record_memory_event(
    *, operator_sub: str, session_id: str, request: str, answer: str
) -> str:
    """Mirror the observable turn into Memory, after Aurora has the durable copy.

    Returns which store took the write, so the caller can report durable memory
    separately from a process-local fallback that dies with the worker.

    Only conversational content: no chain-of-thought, no system prompt, no Cedar,
    no credentials. A failure here never rolls back the durable turn — Aurora is the
    transcript and Memory is context.
    """
    from services import operator_concierge_sessions as sessions

    try:
        from services.agentcore_memory import AgentCoreMemory
    except Exception:  # noqa: BLE001
        return ""

    try:
        return await sessions.append_operator_memory(
            AgentCoreMemory(),
            operator_sub=operator_sub,
            session_id=session_id,
            turns=[
                {"role": "user", "content": request},
                {"role": "assistant", "content": answer},
            ],
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("AgentCore Memory write unavailable: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Storefront handoff
# ---------------------------------------------------------------------------


async def load_shopper_handoff(
    db: Any, *, customer_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[Step], List[Evidence]]:
    """Read the latest immutable shopper handoff without treating it as truth."""
    from services import shopper_handoff

    try:
        handoff = await shopper_handoff.resolve_latest_for_customer(
            db, customer_id=customer_id
        )
    except shopper_handoff.HandoffIntegrityError:
        raise
    except Exception as exc:  # noqa: BLE001 - no handoff is safer than guessed context
        logger.info("shopper handoff unavailable for %s: %s", customer_id, exc)
        return None, Step(
            "handoff",
            "Storefront handoff unavailable",
            SOURCE_HANDOFF,
            status="unavailable",
        ), []
    if not handoff:
        return None, None, []

    source = handoff.get("source") or {}
    proposal = handoff.get("proposal") or {}
    route = handoff.get("routing") or {}
    step = Step(
        "handoff",
        "Storefront handoff loaded",
        SOURCE_HANDOFF,
        result=(
            f"turn {source.get('turnId', '')} · "
            f"{route.get('specialist') or 'specialist not recorded'} · "
            f"review {proposal.get('reviewId', '')}"
        ),
    )
    evidence = [
        Evidence(
            kind="shopper_handoff",
            role=ROLE_CONTEXT,
            status="unverified",
            source=SOURCE_HANDOFF,
            label="What the shopper asked Pellier",
            record_id=str(source.get("turnId") or ""),
            detail=str(handoff.get("shopperRequest") or ""),
            data=handoff,
        )
    ]
    requester = await _requester_evidence(db, proposal.get("reviewId"))
    if requester is not None:
        evidence.append(requester)
    return handoff, step, evidence


_REQUESTER_SELECT = """
    SELECT requested_by_sub, requester_kind
      FROM pellier.approvals
     WHERE id = %s
"""


async def _requester_evidence(db: Any, review_id: Any) -> Optional[Evidence]:
    """Who opened the review, as a fact the investigator must weigh.

    The customer on a review is what the proposal names. Whether the person
    who asked was that customer is a separate fact, recorded on the review when
    it opened: a verified shopper token, the desk itself, or an anonymous
    session that chose a persona. The last is a gap, not a client.
    """
    try:
        review_id = int(review_id or 0)
    except (TypeError, ValueError):
        return None
    if not review_id:
        return None
    try:
        row = await db.fetch_one(_REQUESTER_SELECT, review_id)
    except Exception as exc:  # noqa: BLE001 - absence of the fact is reported below
        logger.info("requester lookup failed for review %s: %s", review_id, exc)
        row = None
    if not row:
        return None
    kind = str(row.get("requester_kind") or "unverified")
    subject = str(row.get("requested_by_sub") or "")
    if kind == "shopper" and subject:
        detail = (
            f"Requested by a signed-in shopper, subject {subject[:8]}…, whose "
            "token maps to the customer named on the review."
        )
    elif kind == "operator":
        detail = "Prepared on the desk by staff; no shopper asked for this action."
    elif subject:
        detail = (
            f"Requested by a signed-in shopper, subject {subject[:8]}…, whose "
            "ownership of the customer named on the review was not verified."
        )
    else:
        detail = (
            "No verified requester identity was saved with this request. This "
            "does not describe the current operator's sign-in."
        )
    return Evidence(
        kind="requester",
        role=ROLE_FACT,
        status="verified" if kind in ("shopper", "operator") else "unverified",
        source=SOURCE_AURORA,
        label="Who asked for this action",
        record_id=f"review-{review_id}",
        detail=detail,
        data={"requesterKind": kind, "requestedBySub": subject or None},
    )


# ---------------------------------------------------------------------------
# Strands graph synthesis
# ---------------------------------------------------------------------------

# Shared preamble. Every workflow inherits the same evidence discipline; only the
# deliverable changes. Duplicating these rules per workflow is how one of the three
# quietly loses the FACT/CONTEXT distinction.
_EVIDENCE_RULES = """You are writing for a Pellier retail operator. Internal use.

Rules:
- Use ONLY the evidence supplied. Never introduce an order id, amount, count,
  membership rung, product, date or status that is not in it.
- Evidence carries a role. FACT is established. CONTEXT is something a source
  reports that the authoritative record does not confirm. Never state a CONTEXT
  item as though it were a FACT.
- If a ticket reports a return and the return records show none, say both: what the
  ticket states, and that no authoritative record is present. Do not resolve the
  disagreement.
- No greetings, no enthusiasm, no "I". Do not describe your own process.
"""

_CLIENT_SUMMARY_CONTRACT = f"""{_EVIDENCE_RULES}
Return ONLY minified JSON, no prose outside it, matching exactly:
{{"summary": "...", "recommendation": "..."}}

- summary: at most three sentences, calm and factual.
- recommendation: one sentence, an operational next step. If nothing is warranted,
  say what to confirm first.
"""

# The epistemic split moves into the SHAPE of the answer rather than living only in
# the evidence rail. An operator reading two separately labelled blocks cannot
# accidentally carry an unconfirmed report forward as established fact.
_INVESTIGATE_CONTRACT = f"""{_EVIDENCE_RULES}
Return ONLY minified JSON, no prose outside it, matching exactly:
{{"established": "...", "reported": "...", "recommendation": "..."}}

- established: what the authoritative records establish about this issue. FACT
  evidence only. At most three sentences and 90 words.
- reported: what a source reports that the authoritative records do not confirm,
  attributed to that source. CONTEXT evidence only. Use an empty string if there is
  no such item. Never present it as settled and never resolve it. At most 60 words.
- recommendation: one sentence naming the next fair step for the operator. Recommend
  only investigation, confirmation or a decision the operator makes; never state that
  an action has been taken or will be taken. At most 45 words.
- Do not ask the operator to retrieve a record already supplied in FACT evidence.
  Name the unresolved item or missing fact. Do not use membership or spending alone
  as authority for a refund, shipping refund, or credit.
"""

# A draft is customer-facing copy, so the constraints are stricter: it can be pasted
# into a real message, and anything it promises Pellier has to honour.
_DRAFT_NOTE_CONTRACT = f"""{_EVIDENCE_RULES}
Return ONLY minified JSON, no prose outside it, matching exactly:
{{"draft": "...", "operatorContext": "..."}}

- draft: copy addressed to the client, at most 90 words, warm but restrained. It must
  not offer or imply a discount, credit, refund amount, voucher, gift, loyalty
  points, free shipping, upgrade or any other compensation, and it must not promise a
  date, an outcome or a resolution. It must not state an unconfirmed report as fact.
  Plain sentences only: no subject line, no signature block, no placeholders in
  brackets.
- operatorContext: for the operator only, never shown to the client. Name the
  evidence the draft relied on and anything to confirm before sending. At most three
  sentences.
"""


# A replacement recommendation is where a model is most tempted to invent a price or
# an availability claim, so the contract says twice that it may not, and the artifact
# does not carry model-authored structured fields for it to land in.
_REPLACEMENT_CONTRACT = f"""{_EVIDENCE_RULES}
Return ONLY minified JSON, no prose outside it, matching exactly:
{{"summary": "...", "comparison": "...", "next_step": "..."}}

- summary: at most three sentences. What was found for the item being replaced, and
  why these options fit. Refer to products ONLY by the names supplied below.
- comparison: one or two sentences on how the options differ from each other.
- next_step: one sentence naming what the operator does next. This surface cannot
  modify an order, so never state or imply that a swap, exchange or reservation has
  been or will be made.

Additional rules for this workflow:
- Never state a price, a unit count, a stock status or a product identifier. Those are
  supplied as facts and are rendered from the record, not from your text.
- Never call an option an upgrade, an improvement or better quality. No supplied
  attribute establishes that.
- Never promise availability. If an option's availability is unverified, you may say
  it has not been confirmed; you may not say it is in stock.
"""


@dataclass(frozen=True)
class WorkflowSpec:
    """What differs between workflows, and nothing else.

    One orchestration path runs all three. A workflow contributes its contract, the
    prose fields it expects back, and how those fields are labelled — never its own
    persistence, its own evidence loader, or its own turn lifecycle. That is what
    keeps "Investigate" and "Draft" from drifting into three half-maintained copies
    of the same function.
    """

    kind: str
    contract: str
    # Step copy. Named per workflow because "Summary synthesized" under a draft would
    # describe work that did not happen.
    running_label: str
    done_label: str
    # The model key whose prose becomes the durable answer.
    primary_key: str
    # Label above that prose. Empty means unlabelled, which is right for a summary and
    # wrong for a draft: unlabelled customer-facing copy invites being treated as sent.
    primary_label: str
    # A standing caveat rendered with the primary block. Empty for most workflows.
    primary_note: str
    # Additional labelled blocks: (model key, heading, tone).
    sections: Tuple[Tuple[str, str, str], ...]
    # The model key holding the one-line next step, or "" when the workflow has none.
    recommendation_key: str
    # Whether this workflow contributes extra evidence before synthesis through a
    # context stage in `_CONTEXT_STAGES`. Declared here so the spec describes the
    # whole workflow; `test_a_declared_context_stage_is_implemented` keeps the two
    # from drifting apart.
    has_context_stage: bool = False


WORKFLOWS: Dict[str, WorkflowSpec] = {
    WORKFLOW_CLIENT_SUMMARY: WorkflowSpec(
        kind=WORKFLOW_CLIENT_SUMMARY,
        contract=_CLIENT_SUMMARY_CONTRACT,
        running_label="Synthesizing response",
        done_label="Summary synthesized",
        primary_key="summary",
        primary_label="",
        primary_note="",
        sections=(),
        recommendation_key="recommendation",
    ),
    WORKFLOW_INVESTIGATE: WorkflowSpec(
        kind=WORKFLOW_INVESTIGATE,
        contract=_INVESTIGATE_CONTRACT,
        running_label="Investigating service issue",
        done_label="Investigation synthesized",
        primary_key="established",
        primary_label="Established by the records",
        primary_note="",
        sections=(("reported", "Reported, not confirmed", "context"),),
        recommendation_key="recommendation",
        # Only this workflow may cross from reading into proposing, and only when the
        # operator's own words ask for it.
        has_context_stage=True,
    ),
    WORKFLOW_REPLACEMENT: WorkflowSpec(
        kind=WORKFLOW_REPLACEMENT,
        contract=_REPLACEMENT_CONTRACT,
        running_label="Preparing recommendations",
        done_label="Recommendations prepared",
        primary_key="summary",
        primary_label="",
        primary_note="",
        sections=(("comparison", "How these compare", "neutral"),),
        recommendation_key="next_step",
        has_context_stage=True,
    ),
    WORKFLOW_DRAFT_NOTE: WorkflowSpec(
        kind=WORKFLOW_DRAFT_NOTE,
        contract=_DRAFT_NOTE_CONTRACT,
        running_label="Drafting client note",
        done_label="Draft prepared",
        primary_key="draft",
        primary_label="Draft — not sent",
        # Stated by the surface, not by the model, because it is a property of the
        # deployment: there is no send capability here to offer.
        primary_note=(
            "Pellier does not send messages from this surface. Review the draft and "
            "copy it into your own channel if you choose to use it."
        ),
        sections=(("operatorContext", "Operator context", "context"),),
        # A draft's next step is the operator's own judgement about sending it. A
        # recommendation line here would only restate the caveat above.
        recommendation_key="",
    ),
}

SUPPORTED_WORKFLOWS: Tuple[str, ...] = tuple(WORKFLOWS)

# Commitments a draft may not make. Checked rather than merely requested: an
# unauthorised offer in copy an operator can paste into a real message is a business
# liability, and "the prompt said not to" is not a control.
_UNAUTHORIZED_COMMITMENTS: Tuple[str, ...] = (
    "discount",
    "% off",
    "percent off",
    "voucher",
    "coupon",
    "promo",
    "gift card",
    "store credit",
    "loyalty points",
    "reward points",
    "free shipping",
    "complimentary",
    "on the house",
    "waive",
    "no charge",
    "refund of",
    "will refund",
    "we will replace",
    "guarantee",
)

# Words that route a request to a workflow, in priority order. Deliberately keyed to
# the DELIVERABLE, so "draft a note about the ticket" produces a draft rather than an
# investigation: the operator asked for copy.
_ROUTING_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (WORKFLOW_DRAFT_NOTE, ("draft", "write a note", "write to", "compose", "reply to")),
    (
        WORKFLOW_REPLACEMENT,
        ("replacement", "replace ", "instead of", "alternative to", "swap",
         "similar product", "similar option", "comparable item"),
    ),
    (
        WORKFLOW_INVESTIGATE,
        ("investigate", "service issue", "ticket", "dispute", "complaint",
         "what happened", "why was", "why did", "look into",
         # Consequential intent is a resolution request by definition. Checked AFTER
         # draft and replacement, so "draft a note about the return" is still copy and
         # "find a replacement" is still a read.
         "prepare the return", "prepare a return", "prepare this return",
         "prepare the damaged", "set up the return", "set up a return",
         "start the return", "start a return", "open a return", "open the return",
         "initiate the return", "initiate a return", "initiate return",
         "help me initiate", "raise a return", "log the return", "log a return",
         "process the return", "put the return", "return for review",
         # The guided Jessica investigation remains read-only. These phrases keep
         # turns two and three on the investigation graph without matching the
         # narrower action-intent classifier that may prepare a review.
         "authoritative for this decision", "fairest next step for human review"),
    ),
)


# Explicit historical-similarity intent, in the OPERATOR's words. Episode recall is
# NOT run on every turn: it is a Bedrock embedding call plus a vector scan, and a
# "prior resolution" card that appears unbidden beside every summary would train an
# operator to ignore it. Asked for, it is the one thing the client record cannot answer.
#
# Deliberately question-led. "Prepare the return" is a consequential instruction and
# matches none of these; "have we handled something like this?" is a question about the
# past and matches.
_HISTORY_PHRASES: Tuple[str, ...] = (
    "handled something similar",
    "handled anything similar",
    "handled something like this",
    "handled a similar",
    "seen something similar",
    "seen anything like this",
    "seen this before",
    "seen a return denied",
    "similar before",
    "like this before",
    "happened before",
    "prior resolution",
    "prior resolutions",
    "previous resolution",
    "past resolution",
    "how did we resolve",
    "how have we resolved",
    "what did we do last time",
    "last time this happened",
)


def classify_history_intent(request: str) -> bool:
    """Whether the operator asked what happened in comparable situations before.

    Deterministic, and matched only against the operator's request. Orthogonal to
    :func:`classify_workflow`: recall attaches to whichever workflow runs, because
    "have we seen a return denied like this?" is a question about history whether it
    arrives during an investigation or a summary.
    """
    text = (request or "").lower()
    return any(phrase in text for phrase in _HISTORY_PHRASES)


def classify_workflow(request: str) -> str:
    """Which workflow a request asks for. Deterministic, and the ONLY router.

    A template is a shortcut into this same classifier rather than a private channel
    with its own routing: if selecting "Draft a client note" ran a workflow that a
    typed request for a draft could never reach, the surface would be demonstrating
    something the product cannot do. So the browser submits text and only text, and
    the workflow kind — a claim about what should run — stays server-derived.

    Unmatched requests fall back to a client summary, which is the read that is always
    defensible: it makes no claim beyond what the record already shows.
    """
    text = (request or "").lower()
    for kind, needles in _ROUTING_RULES:
        if any(needle in text for needle in needles):
            return kind
    return WORKFLOW_CLIENT_SUMMARY


def unauthorized_commitments(draft: str) -> List[str]:
    """Terms in a draft that would commit Pellier to something it has not approved."""
    text = (draft or "").lower()
    return [term for term in _UNAUTHORIZED_COMMITMENTS if term in text]


def _evidence_for_prompt(evidence: List[Evidence]) -> str:
    lines = []
    for item in evidence:
        lines.append(
            f"[{item.role.upper()}] {item.label}: {item.detail}"
            + (f" (record {item.record_id})" if item.record_id else "")
        )
    return "\n".join(lines)


def synthesize(
    *,
    request: str,
    evidence: List[Evidence],
    memory_turns: List[Dict[str, Any]],
    spec: WorkflowSpec,
    context_block: str = "",
    shopper_handoff: Optional[Dict[str, Any]] = None,
    checkpoint_state: str = "READ_ONLY_COMPLETE",
    review_id: Optional[int] = None,
    action_hash: str = "",
) -> Tuple[Optional[Dict[str, str]], Optional[Step], str]:
    """Run the operator Strands graph. Returns (fields, step, model_id).

    The model may fail, return unusable output, or — for a draft — produce copy that
    commits Pellier to something it has not authorised. Each of those yields no fields
    and a failed step, and the caller renders a failed turn rather than substituting
    invented prose.
    """
    memory_block = ""
    if memory_turns:
        rendered = "\n".join(
            f"{t.get('role', '')}: {str(t.get('content', ''))[:400]}"
            for t in memory_turns
        )
        # Labelled so the model cannot mistake remembered conversation for current
        # state. Memory is context; Aurora is authority.
        memory_block = (
            "\nCONVERSATION CONTEXT (prior turns; NOT current business truth):\n"
            + rendered
        )

    # The graph task keeps ESTABLISHED FACTS FOR THIS WORKFLOW separate from the
    # conversation block above. That label is assembled in operator_graph._task.
    from services.operator_graph import run_operator_graph

    result = run_operator_graph(
        request=request,
        evidence_text=_evidence_for_prompt(evidence),
        memory_text=memory_block,
        contract=spec.contract,
        context_block=context_block,
        shopper_handoff=shopper_handoff,
        checkpoint_state=checkpoint_state,
        review_id=review_id,
        action_hash=action_hash,
    )

    def failed(duration: Optional[int] = None, note: str = "") -> Step:
        return Step(
            "graph", spec.running_label, SOURCE_STRANDS_GRAPH, status="failed",
            duration_ms=duration, result=note, metadata=result.metadata,
        )

    fields = _parse_synthesis(result.raw, spec)
    if fields is None:
        return None, failed(
            result.metadata.get("durationMs"),
            result.error or "The graph returned no usable structured result.",
        ), result.model_id

    # A draft that offers compensation is discarded, not shown with a warning: an
    # operator scanning a well-formed note is exactly who would paste it.
    if spec.kind == WORKFLOW_DRAFT_NOTE:
        offending = unauthorized_commitments(fields.get(spec.primary_key, ""))
        if offending:
            logger.warning(
                "draft discarded, unauthorised commitment: %s", ", ".join(offending)
            )
            return None, failed(
                result.metadata.get("durationMs"),
                "Draft discarded: it committed Pellier to something this surface "
                "cannot authorise.",
            ), result.model_id

    return fields, Step(
        "graph",
        spec.done_label,
        SOURCE_STRANDS_GRAPH,
        duration_ms=result.metadata.get("durationMs"),
        metadata=result.metadata,
    ), result.model_id


async def synthesize_async(
    *,
    request: str,
    evidence: List[Evidence],
    memory_turns: List[Dict[str, Any]],
    spec: WorkflowSpec,
    context_block: str = "",
    shopper_handoff: Optional[Dict[str, Any]] = None,
    checkpoint_state: str = "READ_ONLY_COMPLETE",
    review_id: Optional[int] = None,
    action_hash: str = "",
) -> Tuple[Optional[Dict[str, str]], Optional[Step], str]:
    """Run blocking Strands/Bedrock synthesis without blocking the API event loop."""
    return await asyncio.to_thread(
        synthesize,
        request=request,
        evidence=evidence,
        memory_turns=memory_turns,
        spec=spec,
        context_block=context_block,
        shopper_handoff=shopper_handoff,
        checkpoint_state=checkpoint_state,
        review_id=review_id,
        action_hash=action_hash,
    )


def _parse_synthesis(raw: str, spec: WorkflowSpec) -> Optional[Dict[str, str]]:
    """Extract this workflow's prose fields, and nothing else.

    Only the keys the spec declares are read. Extra keys the model volunteers are
    discarded: the model is not allowed to contribute structured facts, so there is
    nothing else here worth reading. A missing primary field is a failure, because the
    deliverable is absent; a missing section is allowed, because "no unconfirmed report
    exists" is a legitimate answer.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None

    wanted = [spec.primary_key, *(key for key, _label, _tone in spec.sections)]
    if spec.recommendation_key:
        wanted.append(spec.recommendation_key)
    fields = {key: str(payload.get(key) or "").strip() for key in wanted}
    if not fields.get(spec.primary_key):
        return None
    return fields


# ---------------------------------------------------------------------------
# Workflow context stages
# ---------------------------------------------------------------------------


@dataclass
class WorkflowContext:
    """Extra evidence one workflow contributes before synthesis.

    A declared extension point rather than a branch in the turn: a stage yields its
    own observable steps as the work completes, adds evidence rows, hands the model a
    prompt block of established facts, and attaches structured material to the
    artifact. It may also refuse to proceed — `blocked` carries the answer to give
    when the request cannot be grounded, which is a legitimate outcome and not a
    failure.
    """

    steps: List[Step] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    prompt_block: str = ""
    artifact: Dict[str, Any] = field(default_factory=dict)
    blocked: str = ""


async def _replacement_context(db: Any, *, customer_id: str, request: str,
                               turn_id: str = "", operator_sub: str = "") -> Any:
    """Ground the order item, retrieve, reconcile inventory. An async generator.

    Yields ``("step", payload)`` as each stage actually finishes and finally
    ``("context", WorkflowContext)``. Nothing is announced before it has happened, and
    the model is handed only facts this stage established.
    """
    from services import replacement_search as RS
    from services.structured_extract import get_structured_extractor

    ctx = WorkflowContext()

    with _Timer() as t_ground:
        grounding = await RS.resolve_order_item(
            db, customer_id=customer_id, request=request
        )

    if grounding.item is None:
        # Ambiguous or ungroundable. Say so, list what it could have meant, and stop
        # before spending a retrieval on a guess.
        step = Step(
            "order", "Order item not resolved", SOURCE_AURORA, status="unavailable",
            duration_ms=t_ground.ms,
            result=grounding.reason or "no matching order line",
        )
        ctx.steps.append(step)
        yield "step", step.to_payload()
        ctx.blocked = _clarification(grounding)
        ctx.artifact = {
            "replacement": {
                "grounding": {
                    "resolved": False,
                    "reason": grounding.reason,
                    "candidates": [c.to_payload() for c in grounding.candidates],
                }
            }
        }
        yield "context", ctx
        return

    item = grounding.item
    step = Step(
        "order", "Order item resolved", SOURCE_AURORA, duration_ms=t_ground.ms,
        result=f"#{item.order_id} · {item.name}",
    )
    ctx.steps.append(step)
    yield "step", step.to_payload()
    ctx.evidence.append(Evidence(
        kind="order_item", role=ROLE_FACT, status="verified", source=SOURCE_AURORA,
        label="Item being replaced", record_id=str(item.product_id),
        detail=f"{item.name} · {item.category} · {_money(item.price)} "
               f"(order #{item.order_id}, matched on {grounding.matched_on})",
        data=item.to_payload(),
    ))

    with _Timer() as t_plan:
        extracted = get_structured_extractor().extract(request)
        plan = RS.build_replacement_plan(
            original=item, request=request, extracted=extracted
        )
    step = Step(
        "constraints", "Replacement constraints extracted", SOURCE_BEDROCK,
        duration_ms=t_plan.ms, result=" · ".join(plan.describe_hard_controls()),
    )
    ctx.steps.append(step)
    yield "step", step.to_payload()
    # The plan is a CONTEXT row, not a fact: a model proposed it and deterministic
    # code validated it. What makes it safe is that PostgreSQL enforces the hard
    # half, which the detail states.
    ctx.evidence.append(Evidence(
        kind="retrieval_plan", role=ROLE_CONTEXT, status="verified",
        source=SOURCE_BEDROCK, label="Retrieval controls",
        detail=(
            "Hard constraints enforced in PostgreSQL before ranking: "
            + " · ".join(plan.describe_hard_controls())
        ),
        data=plan.to_payload(),
    ))

    with _Timer() as t_search:
        result = await RS.find_replacements(db, plan)
    step = Step(
        "retrieval", "Candidates retrieved and reranked", SOURCE_AURORA,
        duration_ms=t_search.ms,
        result=f"{result.pool_size} candidates · {result.reranked} reranked",
    )
    ctx.steps.append(step)
    yield "step", step.to_payload()

    step = Step(
        "inventory", "Inventory reconciled against the ledger", SOURCE_AURORA,
        result=(
            f"{result.reconciled_count} of {result.reranked} candidates reconciled"
            if result.reranked else "no candidates to reconcile"
        ),
    )
    ctx.steps.append(step)
    yield "step", step.to_payload()

    for rec in result.available:
        ctx.evidence.append(Evidence(
            kind="availability", role=ROLE_FACT, status="verified",
            source=SOURCE_AURORA, label=f"Availability · {rec.name}",
            record_id=rec.product_id,
            detail=_describe_availability(rec.inventory),
            data={"status": rec.inventory.status,
                  "availableQuantity": rec.inventory.available_quantity},
        ))
    for rec in result.close_matches:
        ctx.evidence.append(Evidence(
            kind="availability", role=ROLE_CONTEXT, status="unverified",
            source=SOURCE_AURORA, label=f"Availability · {rec.name}",
            record_id=rec.product_id,
            detail=_describe_availability(rec.inventory),
            data={"status": rec.inventory.status},
        ))

    ctx.prompt_block = _replacement_prompt_block(result)
    ctx.artifact = {"replacement": {**result.to_payload(),
                                    "grounding": {"resolved": True,
                                                  "matchedOn": grounding.matched_on}}}
    if not result.available and not result.close_matches:
        ctx.blocked = (
            "No catalog option satisfied the constraints for this item. "
            + (result.coverage_note or "")
        ).strip()
    yield "context", ctx


def _describe_availability(evidence: Any) -> str:
    from services.inventory_evidence import describe_availability

    return describe_availability(evidence)


def _clarification(grounding: Any) -> str:
    """What to say when the order item could not be established.

    Never a guess. Two order lines that fit a phrase equally well are listed back to
    the operator, because choosing between them is a business decision about which
    record is meant and a model's confidence is not authority over that.
    """
    if grounding.candidates:
        listed = "; ".join(
            f"#{c.order_id} {c.name} ({_money(c.price)})"
            for c in grounding.candidates[:5]
        )
        return (
            "More than one order line matches that description, so no replacement "
            f"search was run. Name the one you mean: {listed}."
        )
    if grounding.reason == "no_order_history":
        return "This client has no order history, so there is no item to replace."
    if grounding.reason == "order_history_unavailable":
        return "Order history could not be read, so no item could be resolved."
    return "The item to replace could not be identified from that request."


def _replacement_prompt_block(result: Any) -> str:
    """The facts the model may write prose about. Prices and counts included so it
    can reason, and forbidden in its output so it cannot restate them wrongly."""
    lines = [
        "ITEM BEING REPLACED: "
        f"{result.plan.original.name} ({result.plan.original.category}, "
        f"{_money(result.plan.original.price)})",
        "HARD CONSTRAINTS APPLIED IN POSTGRESQL: "
        + " · ".join(result.plan.describe_hard_controls()),
    ]
    if result.available:
        lines.append("OPTIONS WITH RECONCILED AVAILABILITY:")
        for rec in result.available:
            lines.append(
                f"  - {rec.name} ({_money(rec.price)}) — "
                f"{_describe_availability(rec.inventory)} "
                f"Fit: {'; '.join(rec.fit_reasons) or 'none recorded'}"
            )
    if result.close_matches:
        lines.append("OPTIONS WHOSE AVAILABILITY IS NOT VERIFIED:")
        for rec in result.close_matches:
            lines.append(
                f"  - {rec.name} ({_money(rec.price)}) — availability not verified. "
                f"Fit: {'; '.join(rec.fit_reasons) or 'none recorded'}"
            )
    if result.coverage_note:
        lines.append("INVENTORY COVERAGE: " + result.coverage_note)
    return "\n".join(lines)


async def _investigate_context(db: Any, *, customer_id: str, request: str,
                               turn_id: str, operator_sub: str = "") -> Any:
    """Prepare a consequential action, but only when the operator asked for one.

    An investigation with no consequential intent contributes nothing: no steps, no
    evidence, no artifact, and the workflow behaves exactly as it did before this
    stage existed. That is the point — an exploratory question must not acquire a
    side effect because a model thought an action sounded appropriate.

    The intent classification is deterministic and reads the OPERATOR's words. The
    model's recommendation, however emphatic, never opens a review.
    """
    from services import operator_proposals as prop

    ctx = WorkflowContext()
    intent = prop.classify_action_intent(request)
    if intent is None:
        yield "context", ctx
        return

    # Capability first: whether a review may be created at all, and whether execution
    # can be offered, are both properties of live control-plane state.
    with _Timer() as t_cap:
        capability = _capability_for(intent.action)
    step = Step(
        "capability", "Governed capability checked", SOURCE_POLICY_PLANE,
        duration_ms=t_cap.ms,
        result=prop.describe_execution(prop._execution_capability(capability)),
    )
    ctx.steps.append(step)
    yield "step", step.to_payload()

    with _Timer() as t_prepare:
        outcome = await prop.prepare_proposal(
            db, customer_id=customer_id, request=request, turn_id=turn_id,
            intent=intent, capability=capability,
            requested_by_sub=operator_sub or None,
        )

    if outcome.action is None:
        # Ambiguous item, or no stated reason. A question, not a failure — and no
        # review was created.
        step = Step(
            "action", "Action parameters not established", SOURCE_AURORA,
            status="unavailable", duration_ms=t_prepare.ms,
            result=getattr(outcome.grounding, "reason", "") or "reason_not_stated",
        )
        ctx.steps.append(step)
        yield "step", step.to_payload()
        ctx.blocked = outcome.blocked
        ctx.artifact = {"proposedActions": []}
        yield "context", ctx
        return

    action = outcome.action
    step = Step(
        "action", "Action parameters established", SOURCE_AURORA,
        duration_ms=t_prepare.ms,
        result=f"{action.tool} · order #{action.order.get('orderId')} · "
               f"{action.material.get('reason')}",
    )
    ctx.steps.append(step)
    yield "step", step.to_payload()

    # "Review prepared" is emitted only when a review actually exists. No fake
    # action progress: the three failure states each get their own honest row.
    if action.review_id is not None:
        step = Step(
            "review", "Review prepared", SOURCE_AURORA,
            result=f"review {action.review_id} · awaiting a person",
        )
    else:
        step = Step(
            "review", "No review prepared", SOURCE_AURORA, status="unavailable",
            result=action.state,
        )
    ctx.steps.append(step)
    yield "step", step.to_payload()

    ctx.evidence.append(Evidence(
        kind="proposed_action", role=ROLE_FACT, status="verified",
        source=SOURCE_AURORA, label="Action prepared for review",
        record_id=str(action.review_id or ""),
        detail=(
            f"{action.tool} for order #{action.order.get('orderId')} "
            f"({action.product.get('name')}), reason "
            f"{action.material.get('reason')}. "
            + prop.describe_execution(action.execution_capability)
        ),
        data=action.to_payload(),
    ))
    ctx.prompt_block = _proposal_prompt_block(action)
    ctx.artifact = {"proposedActions": [action.to_payload()]}
    yield "context", ctx


def _capability_for(action: str) -> Optional[Dict[str, Any]]:
    """The live capability entry for one tool, or None when it could not be read.

    Synchronous, because `get_capabilities` is — and it is cached for 60 seconds, so
    the control-plane call happens at most once a minute. Same shape as the
    synchronous `synthesize` call this orchestrator already makes.

    None means the snapshot itself was unreadable. It is NOT the same as a capability
    reporting `not_enabled`, and the caller must keep those apart.
    """
    try:
        from services.operator_capabilities import get_capabilities

        snapshot = get_capabilities()
        return (snapshot.get("capabilities") or {}).get(action)
    except Exception as exc:  # noqa: BLE001 - unreadable is a state, not a crash
        logger.info("capability read unavailable for %s: %s", action, exc)
        return None


def _proposal_prompt_block(action: Any) -> str:
    """The facts about the prepared action the model may write prose about.

    It is told what was prepared and, explicitly, that nothing has been authorized
    or executed — so it cannot narrate a consequence that has not happened.
    """
    from services import operator_proposals as prop

    lines = [
        f"ACTION PREPARED FOR HUMAN REVIEW: {action.tool}",
        f"  order #{action.order.get('orderId')} · "
        f"{action.product.get('name')} · reason {action.material.get('reason')}",
        f"  state: {action.state}",
        "  " + prop.describe_execution(action.execution_capability),
        "NOTHING HAS BEEN AUTHORIZED OR EXECUTED. A person has not decided yet, "
        "AgentCore Policy has not been asked, and no statement has reached Aurora.",
    ]
    if action.note:
        lines.append("  note: " + action.note)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Episode recall: what happened in comparable situations before
# ---------------------------------------------------------------------------

# Bounded. Three prior outcomes is enough to inform a judgment; a page of them is a
# relevance problem dressed as thoroughness.
_MAX_PRIOR_EPISODES = 3


async def _prior_resolutions(
    db: Any, *, customer_id: str, request: str
) -> Tuple[List[Step], List[Evidence], Dict[str, Any], str]:
    """Recall this client's prior governed outcomes. Read-only, and never raises.

    Runs ONLY when :func:`classify_history_intent` matched the operator's own words.
    This is the question the client record genuinely cannot answer: the orders, tickets
    and returns tables say what the state is, and `pellier.operator_episodes` says how
    comparable situations ended.

    Semantic where an embedding is available and recency-ordered where it is not, and
    the difference is reported rather than hidden: an operator told "3 similar" deserves
    to know whether similarity was measured or assumed.

    Returns ``(steps, evidence, artifact, prompt_block)``. An empty recall is an answer:
    a client with no prior governed resolutions has none, and the surface says so
    instead of implying the search was inadequate.
    """
    from services import operator_episodes as ep

    steps: List[Step] = []
    embedding: Optional[List[float]] = None
    mode = "recent"
    try:
        from services.embeddings import EmbeddingService

        # `embed_query`, the asymmetric counterpart of the `embed_document` call that
        # stored the situation. Using the same input type for both would measure every
        # recall against the wrong half of the model.
        vector = await asyncio.to_thread(EmbeddingService().embed_query, request)
        if vector:
            embedding = list(vector)
            mode = "semantic"
    except Exception as exc:  # noqa: BLE001 - recall degrades, it does not fail
        logger.info("episode recall embedding unavailable: %s", exc)

    with _Timer() as t:
        episodes = await ep.retrieve_episodes(
            db, customer_id=customer_id, embedding=embedding,
            limit=_MAX_PRIOR_EPISODES,
        )
    steps.append(Step(
        "episode_recall",
        f"Prior resolutions recalled ({len(episodes)})",
        SOURCE_AURORA,
        duration_ms=t.ms,
        result=(
            f"{mode} retrieval over pellier.operator_episodes"
            if episodes else
            "no prior governed resolutions on record"
        ),
    ))
    if not episodes:
        return steps, [], {"priorResolutions": {"episodes": [], "retrieval": {
            "mode": mode, "matched": 0,
        }}}, ""

    evidence = [
        Evidence(
            kind="prior_resolution",
            role="fact",
            status="recorded",
            source=SOURCE_AURORA,
            label=_episode_label(e),
            detail=e.resolution,
            record_id=str(e.episode_id or ""),
        )
        for e in episodes
    ]
    artifact = {
        "priorResolutions": {
            "episodes": [e.to_payload() for e in episodes],
            "retrieval": {"mode": mode, "matched": len(episodes)},
        }
    }
    # What the model may say about them, and nothing more. The outcomes are rendered
    # from the artifact; the prose refers to them.
    block = "PRIOR RESOLUTIONS FOR THIS CLIENT (Aurora episodic memory):\n" + "\n".join(
        f"- {_episode_label(e)}: {e.resolution}" for e in episodes
    )
    return steps, evidence, artifact, block


def _episode_label(episode: Any) -> str:
    """One line naming the kind of situation and how the three layers answered."""
    kind = str(getattr(episode, "episode_type", "")).replace("_", " ")
    human = str(getattr(episode, "human_outcome", ""))
    policy = str(getattr(episode, "policy_outcome", ""))
    aurora = str(getattr(episode, "aurora_outcome", ""))
    return (
        f"{kind} - human {human}, policy {policy}, Aurora {aurora}"
    )


# Which workflows contribute a context stage. A side table rather than a callable on
# the frozen spec, so the spec stays a plain literal; `has_context_stage` on the spec
# declares it and a test proves the two agree.
_CONTEXT_STAGES: Dict[str, Any] = {
    WORKFLOW_REPLACEMENT: _replacement_context,
    WORKFLOW_INVESTIGATE: _investigate_context,
}


# ---------------------------------------------------------------------------
# The turn
# ---------------------------------------------------------------------------


async def run_turn(
    db: Any,
    *,
    customer_id: str,
    session_id: str,
    operator_sub: str,
    request: str,
    transport_key: str = "",
    workflow: str = "",
) -> Dict[str, Any]:
    """Non-streaming entry point: drain the generator and return the final payload."""
    final: Dict[str, Any] = {}
    async for kind, data in stream_turn(
        db, customer_id=customer_id, session_id=session_id,
        operator_sub=operator_sub, request=request,
        transport_key=transport_key, workflow=workflow,
    ):
        if kind == "complete":
            final = data
    return final


async def stream_turn(
    db: Any,
    *,
    customer_id: str,
    session_id: str,
    operator_sub: str,
    request: str,
    transport_key: str = "",
    workflow: str = "",
) -> Any:
    """One Concierge turn: persist, gather, synthesize, persist, mirror.

    Order matters. The operator's request is durable BEFORE any model call, so a
    synthesis failure leaves a recoverable turn rather than losing what was asked.
    The assistant artifact is durable BEFORE the Memory event, so Memory can never be
    the only record of an answer.

    All three workflows run this one path. `workflow` is normally left empty and
    derived from the request, so a template and an equivalent typed question route
    identically; passing an explicit kind is for tests that pin one workflow.
    """
    from services import operator_concierge_sessions as sessions

    spec = WORKFLOWS.get(workflow) or WORKFLOWS[classify_workflow(request)]

    # 1. Durable request first, and the canonical turn id with it.
    with _Timer() as t_request:
        turn = await sessions.append_operator_turn(
            db,
            session_id=session_id,
            customer_id=customer_id,
            operator_sub=operator_sub,
            message=request,
            transport_key=transport_key,
        )
    turn_id = turn["turnId"]
    # Real progress, not a simulated sequence: each event follows the work.
    yield "step", {"kind": "request", "label": "Request saved",
                   "source": SOURCE_AURORA, "status": "complete",
                   "durationMs": t_request.ms}

    # A replayed transport key whose turn already completed returns the stored
    # answer rather than paying for synthesis again.
    if turn.get("replayed"):
        history = await sessions.load_history(
            db, session_id=session_id, customer_id=customer_id
        )
        existing = next(
            (
                m for m in reversed(history["messages"])
                if m["role"] == "assistant" and m["turnId"] == turn_id
            ),
            None,
        )
        if existing is not None:
            replay = {
                "turnId": turn_id,
                "sessionId": session_id,
                "status": existing["turnState"] or "complete",
                "replayed": True,
                "summary": existing["content"],
                **(existing.get("artifact") or {}),
            }
            yield "answer", replay
            yield "complete", replay
            return

    steps: List[Step] = []
    timings: Dict[str, int] = {"requestPersistMs": t_request.ms}

    # 2 + 3. Conversation context, current business truth, and the latest durable
    # storefront handoff are independent, so they run concurrently.
    import asyncio

    with _Timer() as t_gather:
        memory_result, evidence_result, handoff_result = await asyncio.gather(
            load_memory_context(operator_sub=operator_sub, session_id=session_id),
            load_client_evidence(db, customer_id),
            load_shopper_handoff(db, customer_id=customer_id),
            return_exceptions=True,
        )
    timings["contextAndEvidenceMs"] = t_gather.ms

    if isinstance(memory_result, BaseException):
        logger.info("memory context failed: %s", memory_result)
        memory_turns, memory_step = [], Step(
            "memory", "Conversation memory unavailable", SOURCE_MEMORY,
            status="unavailable",
        )
    else:
        memory_turns, memory_step = memory_result
    if memory_step is not None:
        steps.append(memory_step)
        timings["memoryReadMs"] = memory_step.duration_ms or 0
        yield "step", memory_step.to_payload()

    if isinstance(evidence_result, BaseException):
        logger.warning("client evidence failed: %s", evidence_result)
        record, evidence_steps, evidence = {}, [
            Step("client", "Client record", SOURCE_AURORA, status="failed")
        ], []
    else:
        record, evidence_steps, evidence = evidence_result
    steps.extend(evidence_steps)
    for step in evidence_steps:
        yield "step", step.to_payload()

    shopper_handoff: Optional[Dict[str, Any]] = None
    if isinstance(handoff_result, BaseException):
        logger.warning("shopper handoff failed: %s", handoff_result)
        handoff_step = Step(
            "handoff",
            "Storefront handoff rejected",
            SOURCE_HANDOFF,
            status="failed",
        )
        handoff_evidence: List[Evidence] = []
    else:
        shopper_handoff, handoff_step, handoff_evidence = handoff_result
    if handoff_step is not None:
        steps.append(handoff_step)
        yield "step", handoff_step.to_payload()
    evidence.extend(handoff_evidence)

    if not record:
        artifact = _artifact(spec, steps, evidence, {}, [])
        await sessions.append_assistant_artifact(
            db, session_id=session_id, customer_id=customer_id, turn_id=turn_id,
            summary="Client evidence could not be loaded.", artifact=artifact,
            state=sessions.TURN_FAILED,
        )
        failed_answer = {
            **artifact,
            "turnId": turn_id, "sessionId": session_id, "status": "failed",
            # After the spread, not before: the artifact's `summary` is empty when
            # synthesis produced nothing, and it must not overwrite the sentence
            # that says so.
            "summary": "Client evidence could not be loaded.",
            "timings": timings,
        }
        yield "answer", failed_answer
        yield "complete", failed_answer
        return

    # 3b. The workflow's own context stage, when it declares one. Its steps are
    # yielded as its work completes, so a retrieval-backed workflow shows progress
    # for the part that actually takes the time.
    workflow_context: Optional[WorkflowContext] = None
    stage = _CONTEXT_STAGES.get(spec.kind)
    if stage is not None:
        with _Timer() as t_stage:
            async for stage_kind, stage_data in stage(
                db, customer_id=customer_id, request=request, turn_id=turn_id,
                operator_sub=operator_sub,
            ):
                if stage_kind == "step":
                    yield "step", stage_data
                else:
                    workflow_context = stage_data
        timings["workflowContextMs"] = t_stage.ms
        if workflow_context is not None:
            steps.extend(workflow_context.steps)
            evidence.extend(workflow_context.evidence)

    # 3c. Episode recall, when the operator asked about comparable situations. Keyed to
    # the request rather than to the workflow, because "have we seen a return denied like
    # this?" is a question about history whichever workflow is running. Not run
    # otherwise: it costs an embedding call, and a prior-resolution card that turns up
    # beside every summary is one an operator learns to skip.
    recall_artifact: Dict[str, Any] = {}
    recall_block = ""
    if classify_history_intent(request):
        with _Timer() as t_recall:
            recall_steps, recall_evidence, recall_artifact, recall_block = (
                await _prior_resolutions(db, customer_id=customer_id, request=request)
            )
        timings["episodeRecallMs"] = t_recall.ms
        for step in recall_steps:
            steps.append(step)
            yield "step", step.to_payload()
        evidence.extend(recall_evidence)

    # A stage may refuse to proceed — an ambiguous item reference, or nothing that
    # satisfies the constraints. That is an answer, not a failure: the turn completes
    # with what the stage established and no model call is made, because there is
    # nothing for a model to add and inventing an option would be the whole risk.
    if workflow_context is not None and workflow_context.blocked:
        artifact = _artifact(
            spec, steps, evidence, {spec.primary_key: workflow_context.blocked},
            _sources(steps),
        )
        artifact.update(workflow_context.artifact)
        with _Timer() as t_blocked:
            await sessions.append_assistant_artifact(
                db, session_id=session_id, customer_id=customer_id, turn_id=turn_id,
                summary=workflow_context.blocked, artifact=artifact,
                state=sessions.TURN_COMPLETE,
            )
        timings["answerPersistMs"] = t_blocked.ms
        blocked_answer = {
            **artifact,
            "turnId": turn_id, "sessionId": session_id, "status": "complete",
            "replayed": False, "summary": workflow_context.blocked,
            "workflow": spec.kind, "memoryContextUsed": bool(memory_turns),
            "memoryPersisted": False, "memoryStore": "", "timings": timings,
        }
        yield "answer", blocked_answer
        yield "complete", blocked_answer
        return

    # Announce that synthesis has begun. The only in-flight event, and it is a real
    # state: the request is with Bedrock. Marked `running`, never `complete`.
    yield "step", {"kind": "graph", "label": spec.running_label,
                   "source": SOURCE_STRANDS_GRAPH, "status": "running"}

    proposed = (
        (workflow_context.artifact.get("proposedActions") or [None])[0]
        if workflow_context is not None
        else None
    )
    handoff_proposal = (
        (shopper_handoff or {}).get("proposal") or {}
        if shopper_handoff
        else {}
    )
    active_proposal = proposed or handoff_proposal
    checkpoint_state = (
        "WAITING_FOR_HUMAN"
        if active_proposal and active_proposal.get("reviewId")
        else "READ_ONLY_COMPLETE"
    )

    # 4. Two-agent graph. The model contributes prose and a bounded case brief,
    # never structured business truth.
    fields, synth_step, model_id = await synthesize_async(
        request=request, evidence=evidence, memory_turns=memory_turns, spec=spec,
        context_block="\n\n".join(
            b for b in (
                (workflow_context.prompt_block if workflow_context else ""),
                recall_block,
            ) if b
        ),
        shopper_handoff=shopper_handoff,
        checkpoint_state=checkpoint_state,
        review_id=active_proposal.get("reviewId") if active_proposal else None,
        action_hash=active_proposal.get("actionHash", "") if active_proposal else "",
    )
    if synth_step is not None:
        steps.append(synth_step)
        timings["synthesisMs"] = synth_step.duration_ms or 0
        yield "step", synth_step.to_payload()

    failed = fields is None
    sources = _sources(steps)
    artifact = _artifact(spec, steps, evidence, fields or {}, sources)
    artifact["modelId"] = model_id
    artifact["shopperHandoff"] = shopper_handoff
    artifact["orchestration"] = (
        synth_step.metadata if synth_step is not None else {}
    )
    if workflow_context is not None:
        # Structured material from the stage. Backend-owned: product identity, price
        # and availability live here, and the model's prose sits beside them rather
        # than restating them.
        artifact.update(workflow_context.artifact)
    if recall_artifact:
        # Same rule for prior outcomes: the three axes are rendered from the episode
        # rows, so the card and the prose cannot disagree about how something ended.
        artifact.update(recall_artifact)

    state = sessions.TURN_FAILED if failed else sessions.TURN_COMPLETE
    # The failure sentence names the deliverable that is missing, and the failed step
    # carries the reason. "Investigation could not be completed" under a draft request
    # would describe work the operator did not ask for.
    answer = (fields or {}).get(spec.primary_key) or _FAILURE_COPY[spec.kind]

    # 5. Durable answer BEFORE the memory mirror.
    with _Timer() as t_answer:
        await sessions.append_assistant_artifact(
            db, session_id=session_id, customer_id=customer_id, turn_id=turn_id,
            summary=answer, artifact=artifact, state=state,
        )
    timings["answerPersistMs"] = t_answer.ms

    # The browser may reveal this immediately because the answer and its structured
    # artifact are already durable in PostgreSQL. This is not a synthetic typewriter
    # event or an uncommitted model token.
    yield "answer", {
        **artifact,
        "turnId": turn_id,
        "sessionId": session_id,
        "status": "failed" if failed else "complete",
        "replayed": False,
        "summary": answer,
        "workflow": spec.kind,
    }

    # 6. Memory mirror. Never gates the response.
    from services.agentcore_memory import BACKEND_AGENTCORE

    memory_store = ""
    if not failed:
        with _Timer() as t_memory:
            memory_store = await record_memory_event(
                operator_sub=operator_sub, session_id=session_id,
                request=request, answer=answer,
            )
        timings["memoryWriteMs"] = t_memory.ms

    yield "complete", {
        **artifact,
        "turnId": turn_id,
        "sessionId": session_id,
        "status": "failed" if failed else "complete",
        "replayed": False,
        # After the spread. On a failed turn the artifact's `summary` is empty, and
        # spreading it last would silently blank the failure sentence on the wire
        # while Aurora kept the correct one.
        "summary": answer,
        "workflow": spec.kind,
        "memoryContextUsed": bool(memory_turns),
        # True ONLY for the managed store. A process-local dict accepts every write
        # and loses it on restart, so reporting that as persisted would be the
        # surface claiming durability it does not have.
        "memoryPersisted": memory_store == BACKEND_AGENTCORE,
        "memoryStore": memory_store,
        "timings": timings,
    }


# What to say when a workflow produced nothing. One line per workflow, because the
# missing deliverable differs and a generic sentence would misdescribe two of three.
_FAILURE_COPY: Dict[str, str] = {
    WORKFLOW_CLIENT_SUMMARY: "Summary could not be completed.",
    WORKFLOW_INVESTIGATE: "Investigation could not be completed.",
    WORKFLOW_DRAFT_NOTE: "No draft was produced.",
    WORKFLOW_REPLACEMENT: "No replacement recommendation was produced.",
}


def _artifact(
    spec: WorkflowSpec,
    steps: List[Step],
    evidence: List[Evidence],
    fields: Dict[str, str],
    sources: List[Dict[str, str]],
) -> Dict[str, Any]:
    """The persisted model artifact starts with no proposed action.

    `summary` keeps its name across workflows because it is the durable primary prose
    and every existing reader looks for it. What changes is how it is LABELLED: a draft
    carries "Draft - not sent" and a caveat, so customer-facing copy can never be
    mistaken for something Pellier sent.
    """
    primary = fields.get(spec.primary_key, "")
    recommendation = (
        fields.get(spec.recommendation_key, "") if spec.recommendation_key else ""
    )
    return {
        "workflow": spec.kind,
        "investigation": [s.to_payload() for s in steps],
        "evidence": [e.to_payload() for e in evidence],
        "summary": primary,
        "primaryLabel": spec.primary_label,
        "primaryNote": spec.primary_note,
        # Empty sections are dropped: a heading over nothing reads as missing data
        # rather than as the legitimate answer "there is no unconfirmed report".
        "sections": [
            {"id": key, "label": label, "tone": tone, "body": fields[key]}
            for key, label, tone in spec.sections
            if fields.get(key)
        ],
        "recommendation": {"body": recommendation} if recommendation else None,
        "products": [],
        # Consequential proposals are attached only by the deterministic action
        # context after it establishes exact material parameters and review state.
        "proposedActions": [],
        "sources": sources,
    }


def _sources(steps: List[Step]) -> List[Dict[str, str]]:
    """Only systems that actually participated, with what each contributed."""
    contributions: Dict[str, List[str]] = {}
    for step in steps:
        if step.status == "unavailable":
            continue
        contributions.setdefault(step.source, [])
        if step.kind not in contributions[step.source]:
            contributions[step.source].append(step.kind)
    return [
        {"source": source, "detail": " · ".join(kinds)}
        for source, kinds in contributions.items()
    ]
