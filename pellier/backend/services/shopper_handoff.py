"""Durable context passed from a shopper turn to the operator workflow.

The handoff is context, never authority. It preserves what the shopper asked,
which specialist and tools ran, and the exact prepared-action fingerprint.
Current customer, order, inventory, policy, and execution state are always read
again from the tables that own them.

A shopper's store credit ask is recorded as a ``request``, never as an approval
``proposal``: it names no amount, carries no fingerprint, and nobody approves
it. A person answers it by investigating the case.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional

from services.store_tools import CREDIT_REQUEST

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1"
TRUST_LABEL = "UNTRUSTED_SHOPPER_CONTEXT"
WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
_TRANSCRIPT_MESSAGES = 6
_TRANSCRIPT_CHARS = 600
_ASSISTANT_CHARS = 1200

_REVIEW_FOR_TURN_SQL = """
    SELECT id AS review_id,
           customer_id,
           tool AS action,
           action_hash
      FROM pellier.approvals
     WHERE source_turn_id = %s
       AND customer_id = %s
     ORDER BY requested_at DESC, id DESC
     LIMIT 1
"""

_HANDOFF_FOR_REVIEW_SQL = """
    SELECT a.id AS review_id,
           a.customer_id,
           a.tool AS action,
           a.action_hash,
           a.source_turn_id,
           gtr.session_id,
           gtr.handoff_context
      FROM pellier.approvals a
      LEFT JOIN pellier.governed_turn_receipts gtr
        ON gtr.turn_id = a.source_turn_id
     WHERE a.id = %s
     LIMIT 1
"""

_LATEST_HANDOFF_SQL = """
    SELECT a.id AS review_id,
           a.customer_id,
           a.tool AS action,
           a.action_hash,
           a.source_turn_id,
           gtr.session_id,
           gtr.handoff_context
      FROM pellier.approvals a
      JOIN pellier.governed_turn_receipts gtr
        ON gtr.turn_id = a.source_turn_id
     WHERE a.customer_id = %s
       AND gtr.handoff_context <> '{}'::jsonb
     ORDER BY a.requested_at DESC, a.id DESC
     LIMIT 1
"""


class HandoffIntegrityError(RuntimeError):
    """The receipt and review disagree about the customer or prepared action."""


def _decode(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _bounded_transcript(history: Iterable[Mapping[str, Any]]) -> List[Dict[str, str]]:
    messages = list(history or [])[-_TRANSCRIPT_MESSAGES:]
    bounded: List[Dict[str, str]] = []
    for message in messages:
        role = str(message.get("role") or "")
        if role not in {"user", "assistant"}:
            continue
        content = str(message.get("content") or "")
        bounded.append(
            {
                "role": role,
                "content": content[:_TRANSCRIPT_CHARS],
                "truncated": str(len(content) > _TRANSCRIPT_CHARS).lower(),
            }
        )
    return bounded


def tool_names(tool_calls: Iterable[Any]) -> List[str]:
    """Normalize tool-call payloads without persisting arguments or results."""
    names: List[str] = []
    for call in tool_calls or []:
        if isinstance(call, str):
            name = call
        elif isinstance(call, Mapping):
            name = str(
                call.get("tool")
                or call.get("name")
                or call.get("tool_name")
                or call.get("toolName")
                or ""
            )
        else:
            name = ""
        name = name.strip()
        if name and name not in names:
            names.append(name)
    return names


async def build_handoff_context(
    db: Any,
    *,
    turn_id: str,
    session_id: Optional[str],
    customer_id: Optional[str],
    shopper_request: str,
    conversation_history: Iterable[Mapping[str, Any]],
    assistant_response: str,
    specialist_route: str,
    tool_calls: Iterable[Any],
) -> Dict[str, Any]:
    """Build the original immutable envelope when this turn opened a review or a request."""
    customer = str(customer_id or "").strip()
    if db is None or not customer:
        return {}
    try:
        row = await db.fetch_one(_REVIEW_FOR_TURN_SQL, turn_id, customer)
    except Exception as exc:  # noqa: BLE001 - receipt writer remains defensive
        logger.warning("shopper handoff review lookup failed for %s: %s", turn_id, exc)
        return {}
    if not row:
        return {}

    review = dict(row)
    review_customer = str(review.get("customer_id") or "")
    if review_customer != customer:
        logger.error(
            "shopper handoff customer mismatch for %s: %s != %s",
            turn_id,
            review_customer,
            customer,
        )
        return {}

    review_id = int(review.get("review_id") or 0)
    action = str(review.get("action") or "")
    action_hash = str(review.get("action_hash") or "")
    if action == CREDIT_REQUEST:
        reference: Dict[str, Any] = {"request": {"requestId": review_id, "action": action}}
        evidence = {"kind": "credit_request", "id": review_id}
    else:
        reference = {
            "proposal": {"reviewId": review_id, "action": action, "actionHash": action_hash},
        }
        evidence = {"kind": "approval", "id": review_id}
    return {
        "schemaVersion": SCHEMA_VERSION,
        "trust": TRUST_LABEL,
        "checkpoint": WAITING_FOR_HUMAN,
        "customerId": customer,
        "source": {
            "sessionId": session_id,
            "turnId": turn_id,
        },
        "shopperRequest": shopper_request,
        "transcriptExcerpt": _bounded_transcript(conversation_history),
        "assistantResponseExcerpt": str(assistant_response or "")[:_ASSISTANT_CHARS],
        "routing": {
            "specialist": str(specialist_route or ""),
            "tools": tool_names(tool_calls),
        },
        **reference,
        "evidenceRefs": [
            {"kind": "governed_turn_receipt", "id": turn_id},
            evidence,
        ],
    }


def attach_evidence_refs(
    handoff: Mapping[str, Any],
    *,
    retrieval_receipt_id: Optional[int],
    audit_rows: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Add only identifiers collected by the same receipt transaction."""
    if not handoff:
        return {}
    enriched = copy.deepcopy(dict(handoff))
    refs = list(enriched.get("evidenceRefs") or [])
    if retrieval_receipt_id is not None:
        refs.append({"kind": "retrieval_receipt", "id": retrieval_receipt_id})
    for row in audit_rows or []:
        audit_id = row.get("audit_id")
        if audit_id is not None:
            refs.append({"kind": "tool_audit", "id": audit_id})
    enriched["evidenceRefs"] = refs
    return enriched


def _validated_handoff(
    row: Mapping[str, Any], *, expected_customer_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    context = _decode(row.get("handoff_context"))
    if not context:
        return None

    row_customer = str(row.get("customer_id") or "")
    context_customer = str(context.get("customerId") or "")
    expected = str(expected_customer_id or row_customer)
    if str(row.get("action") or "") == CREDIT_REQUEST:
        request = _decode(context.get("request"))
        reference = (request.get("requestId"), request.get("action"), "")
    else:
        proposal = _decode(context.get("proposal"))
        reference = (proposal.get("reviewId"), proposal.get("action"), proposal.get("actionHash"))
    referenced_id, referenced_action, referenced_hash = reference
    mismatches = (
        context_customer != row_customer
        or row_customer != expected
        or int(referenced_id or 0) != int(row.get("review_id") or 0)
        or str(referenced_action or "") != str(row.get("action") or "")
        or str(referenced_hash or "") != str(row.get("action_hash") or "")
        or str((_decode(context.get("source"))).get("turnId") or "")
        != str(row.get("source_turn_id") or "")
    )
    if mismatches:
        raise HandoffIntegrityError("shopper_handoff_lineage_mismatch")
    return context


async def resolve_for_review(
    db: Any, *, review_id: int, expected_customer_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    row = await db.fetch_one(_HANDOFF_FOR_REVIEW_SQL, int(review_id))
    if not row:
        return None
    return _validated_handoff(dict(row), expected_customer_id=expected_customer_id)


async def resolve_latest_for_customer(
    db: Any, *, customer_id: str
) -> Optional[Dict[str, Any]]:
    row = await db.fetch_one(_LATEST_HANDOFF_SQL, str(customer_id))
    if not row:
        return None
    return _validated_handoff(dict(row), expected_customer_id=customer_id)
