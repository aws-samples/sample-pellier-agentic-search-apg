"""Governed proposals: preparing an exact consequential action for human review.

The boundary this module draws
------------------------------

Operator Concierge may INVESTIGATE, RECOMMEND, and PROPOSE. It may not EXECUTE.
The only path from a Concierge turn to a business effect is:

    Concierge turn
      -> propose_review(...)          this module, and nothing else
      -> pellier.approvals            the existing human-decision primitive
      -> human confirmation           the existing ReviewRecord surface
      -> existing governed execute route
      -> AgentCore Policy
      -> Aurora RLS and constraints
      -> business effect
      -> durable evidence

There is no second action store, no command queue, and no execution call reachable
from here. ``services/operator_concierge.py`` may call :func:`prepare_proposal`; a
test asserts it cannot call a governed write, the managed rail, or a Gateway invoke.

Five states that do not imply one another
-----------------------------------------

    PROPOSED     an exact action was prepared
    REVIEWED     a human recorded a decision
    AUTHORIZED   AgentCore Policy evaluated it — later, on execution
    PERMITTED    Aurora let the statement through — later
    EXECUTED     a business effect occurred — later

Creating a review means only the first. It does not mean the action is authorized,
executable, or that the customer is eligible. Availability is read from the
current deployment; a prepared review is workflow state, not a promise that
execution will be permitted.

What the model may and may not establish
----------------------------------------

Bedrock never reaches this module. Intent is classified deterministically from the
operator's own words, and every material parameter is established from Aurora:

    customer_id   the Concierge session's bound customer — never a browser payload
    product_id    resolved from pellier.orders through the shared grounding used by
                  Replacement Search, so a phrase narrows WHICH order line and the
                  order line supplies the identity
    reason        normalised from the operator's words against the write path's own
                  allow-list. Never guessed: it is part of what a human confirms, so
                  an absent reason blocks the proposal instead of being inferred.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# This proposal parser accepts returns only. The Gateway also publishes staff
# credits, but their availability does not extend this parser's action scope.
ACTION_INITIATE_RETURN = "initiate_return"
PROPOSABLE_ACTIONS: Tuple[str, ...] = (ACTION_INITIATE_RETURN,)

# Outcome states for a proposed action, as the artifact reports them.
STATE_REVIEW_REQUIRED = "review_required"
STATE_REVIEW_ALREADY_OPEN = "review_already_open"
STATE_NOT_ENABLED = "not_enabled"
STATE_COULD_NOT_PREPARE = "could_not_prepare_review"

# Consequential intent, in the operator's own words. A recommendation is not a
# request: the model saying "a return may be appropriate" must never open a review,
# so this list is matched against what the OPERATOR wrote and nothing else.
#
# Deliberately verb-led. "What should we do?" and "Investigate what happened" carry
# no instruction to prepare anything and match none of these.
_INTENT_PHRASES: Tuple[str, ...] = (
    "prepare the return", "prepare a return", "prepare the damaged",
    "prepare this return", "set up the return", "set up a return",
    "start the return", "start a return", "open a return", "open the return",
    "initiate the return", "initiate a return", "initiate return",
    "help me initiate", "raise a return", "log the return", "log a return",
    "process the return", "put the return", "return for review",
)

# Canonical reasons, mirroring `BusinessLogic.initiate_return`'s allow-list. A value
# outside it is refused by the write path, so proposing one would prepare an action
# that can never execute.
ALLOWED_REASONS: Tuple[str, ...] = (
    "damaged", "wrong_size", "not_as_described", "changed_mind", "other",
)

# Operator phrasing to canonical reason. Small and obvious on purpose: this is a
# deterministic mapping a reviewer can read, and the human sees the resulting
# canonical value before confirming anything.
_REASON_PHRASES: Tuple[Tuple[str, str], ...] = (
    ("damaged", "damaged"),
    ("broken", "damaged"),
    ("arrived damaged", "damaged"),
    ("wrong size", "wrong_size"),
    ("wrong-size", "wrong_size"),
    ("does not fit", "wrong_size"),
    ("doesn't fit", "wrong_size"),
    ("not as described", "not_as_described"),
    ("not-as-described", "not_as_described"),
    ("not as advertised", "not_as_described"),
    ("under-filled", "not_as_described"),
    ("underfilled", "not_as_described"),
    ("under filled", "not_as_described"),
    ("changed her mind", "changed_mind"),
    ("changed his mind", "changed_mind"),
    ("changed their mind", "changed_mind"),
    ("no longer wants", "changed_mind"),
)


@dataclass
class ProposalIntent:
    """Consequential intent found in the operator's request."""

    action: str
    reason: str = ""
    matched_phrase: str = ""


@dataclass
class ProposedAction:
    """One prepared action, exactly as the artifact and the UI carry it."""

    tool: str
    state: str
    customer: Dict[str, Any] = field(default_factory=dict)
    order: Dict[str, Any] = field(default_factory=dict)
    product: Dict[str, Any] = field(default_factory=dict)
    material: Dict[str, Any] = field(default_factory=dict)
    review_id: Optional[int] = None
    action_hash: str = ""
    execution_capability: Dict[str, Any] = field(default_factory=dict)
    # Set when this proposal resolved to a review a DIFFERENT turn had already
    # opened. The lineage on that row belongs to the turn that created it.
    review_source_turn_id: str = ""
    note: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "state": self.state,
            "reviewId": self.review_id,
            "customer": self.customer,
            "order": self.order,
            "product": self.product,
            "material": self.material,
            "actionHash": self.action_hash,
            "executionCapability": self.execution_capability,
            "reviewSourceTurnId": self.review_source_turn_id,
            "note": self.note,
        }


@dataclass
class ProposalOutcome:
    """What a proposal attempt established. ``blocked`` is an answer, not an error."""

    action: Optional[ProposedAction] = None
    blocked: str = ""
    grounding: Any = None


def classify_action_intent(request: str) -> Optional[ProposalIntent]:
    """Whether the OPERATOR asked for a consequential action to be prepared.

    Deterministic, and matched only against the operator's request. A model
    recommendation never reaches here, which is what keeps an exploratory
    investigation from acquiring a side effect.

    Returns None for every request that merely asks a question. The reason is
    reported when the operator named one and left empty when they did not — an
    absent reason blocks the proposal rather than being guessed, because it is part
    of the material a human is asked to confirm.
    """
    text = (request or "").lower()
    matched = next((phrase for phrase in _INTENT_PHRASES if phrase in text), "")
    if not matched:
        return None
    return ProposalIntent(
        action=ACTION_INITIATE_RETURN,
        reason=normalize_reason(text),
        matched_phrase=matched,
    )


def normalize_reason(text: str) -> str:
    """Map the operator's words to a canonical return reason, or "" if absent.

    Longest phrase first, so "not as described" is not shadowed by a shorter match,
    and an explicit canonical token the operator typed verbatim always wins.
    """
    lowered = (text or "").lower()
    for canonical in ALLOWED_REASONS:
        # The operator typed the canonical token itself.
        if re.search(rf"\b{re.escape(canonical)}\b", lowered):
            return canonical
    for phrase, canonical in sorted(
        _REASON_PHRASES, key=lambda pair: len(pair[0]), reverse=True
    ):
        if phrase in lowered:
            return canonical
    return ""


def capability_blocks_proposal(capability: Optional[Dict[str, Any]]) -> bool:
    """True when the capability is deliberately absent, so no review may be created.

    ``not_enabled`` means the capability is not published at all: preparing a review
    for it would queue a decision against something this deployment cannot do, and
    the future-action contract that would make that meaningful does not exist yet.

    ``temporarily_unavailable`` is different — the capability is published and the
    rail is closed. A review is legitimate workflow state, and the execution
    affordance is what gets disabled.

    An unreadable capability is NOT treated as absence. The control plane failing to
    answer is not evidence that a capability is unpublished, and conflating them is
    the distinction this surface exists to keep.
    """
    state = str((capability or {}).get("state") or "")
    return state == "not_enabled"


async def prepare_proposal(
    db: Any,
    *,
    customer_id: str,
    request: str,
    turn_id: str,
    intent: ProposalIntent,
    capability: Optional[Dict[str, Any]],
    issue: str = "",
    recommendation: Optional[Dict[str, Any]] = None,
    requested_by_sub: Optional[str] = None,
) -> ProposalOutcome:
    """Establish the exact action and open a review for it.

    ``requested_by_sub`` is the authenticated operator preparing the action; the
    review records it as an operator-prepared proposal so the queue never reads
    it as a shopper's own request.

    ``customer_id`` is the Concierge session's bound customer, resolved by the
    session gate before this is reached. It is never taken from a request body, from
    model prose, or from tool arguments the browser could shape.
    """
    from services import operator_review as rv
    from services import replacement_search as rs

    # 1. WHICH order line. The same grounding Replacement Search uses, so a phrase
    #    narrows the line and Aurora supplies the identity.
    grounding = await rs.resolve_order_item(
        db, customer_id=customer_id, request=request
    )
    if grounding.item is None:
        return ProposalOutcome(
            blocked=_grounding_block(grounding), grounding=grounding
        )
    item = grounding.item

    # 2. The reason. Refused rather than inferred: a human confirms this value.
    if not intent.reason:
        return ProposalOutcome(
            blocked=(
                "No return reason was stated, so no action was prepared. A reason is "
                "part of what a person confirms and is not inferred. Name one of: "
                + ", ".join(ALLOWED_REASONS).replace("_", " ")
                + "."
            ),
            grounding=grounding,
        )

    material = {
        "customer_id": customer_id,
        # int, matching `_coerce_material` and the write path's own hash inputs.
        "product_id": int(item.product_id),
        "reason": intent.reason,
        }
    action_hash = rv.action_fingerprint(intent.action, material)

    proposed = ProposedAction(
        tool=intent.action,
        state=STATE_REVIEW_REQUIRED,
        customer={"customerId": customer_id},
        order={"orderId": item.order_id, "placedAt": item.placed_at},
        product={
            "productId": item.product_id, "name": item.name,
            "category": item.category, "price": item.price, "imgUrl": item.img_url,
        },
        material=dict(material),
        action_hash=action_hash,
        execution_capability=_execution_capability(capability),
    )

    # 3. A deliberately unpublished capability gets no review.
    if capability_blocks_proposal(capability):
        proposed.state = STATE_NOT_ENABLED
        proposed.action_hash = ""
        proposed.note = (
            "This capability is not published in this deployment, so no review was "
            "prepared."
        )
        return ProposalOutcome(action=proposed, grounding=grounding)

    # 4. The review. The ONLY consequential-path call this module makes.
    review_id = await rv.propose_review(
        db,
        action=intent.action,
        args=material,
        source_turn_id=turn_id,
        issue=issue or item.name,
        # Supplied rather than defaulted. `_default_recommendation` is written for
        # Theo's shopper-rail story: it states the client "reported it damaged on
        # arrival", names a specific courtesy credit, and cites a previous damaged
        # piece. None of that is established here, and for a not-as-described return
        # the first clause is simply false.
        recommendation=recommendation or _recommendation_for(item, intent),
        requested_by_sub=requested_by_sub,
        requester_kind=rv.REQUESTER_OPERATOR,
    )
    if review_id is None:
        # The investigation still stands. Do not claim a review exists.
        proposed.state = STATE_COULD_NOT_PREPARE
        proposed.action_hash = ""
        proposed.note = (
            "The action was established but a review could not be recorded, so "
            "nothing is awaiting a decision."
        )
        return ProposalOutcome(action=proposed, grounding=grounding)

    proposed.review_id = review_id
    stored_turn = await _review_source_turn(db, review_id)
    if stored_turn and stored_turn != turn_id:
        # Migration 020's partial unique index resolved this to a review another turn
        # already opened. That row's lineage belongs to that turn, so this turn
        # reports the resolution rather than claiming authorship.
        proposed.state = STATE_REVIEW_ALREADY_OPEN
        proposed.review_source_turn_id = stored_turn
        proposed.note = (
            "This exact action was already awaiting a decision, so no second review "
            "was created."
        )
    return ProposalOutcome(action=proposed, grounding=grounding)


def _recommendation_for(item: Any, intent: ProposalIntent) -> Dict[str, Any]:
    """What Pellier proposes, from what this turn actually established.

    Names the action and the reason, and nothing else. No entitlement, no courtesy
    amount, no availability claim: whether a replacement exists is a live inventory
    question and whether a credit is warranted is the human's call.
    """
    reason = intent.reason.replace("_", " ")
    return {
        "primaryAction": intent.action,
        "rationale": (
            f"The operator asked to prepare a {reason} return for "
            f"{item.name} on order #{item.order_id}. The order line establishes the "
            "client, the product and the price; the reason is the operator's."
        ),
    }


def _execution_capability(capability: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The execution affordance state, failing closed when it could not be read."""
    if not capability:
        return {"state": "capability_state_unverified", "executable": False}
    state = str(capability.get("state") or "capability_state_unverified")
    return {
        "state": state,
        "reason": capability.get("reason") or "",
        # Fail closed. Only a positively available capability offers execution, and
        # an unreadable control plane never does.
        "executable": state == "available",
    }


_REVIEW_TURN_SQL = """
    SELECT source_turn_id FROM pellier.approvals WHERE id = %s
"""


async def _review_source_turn(db: Any, review_id: int) -> str:
    try:
        row = await db.fetch_one(_REVIEW_TURN_SQL, int(review_id))
    except Exception as exc:  # noqa: BLE001 - lineage reporting is best effort
        logger.info("review lineage read failed for %s: %s", review_id, exc)
        return ""
    if not row:
        return ""
    value = row["source_turn_id"] if isinstance(row, dict) else row[0]
    return str(value or "")


def _grounding_block(grounding: Any) -> str:
    """What to say when the item could not be established. Never a guess."""
    if getattr(grounding, "candidates", None):
        listed = "; ".join(
            f"#{c.order_id} {c.name}" for c in grounding.candidates[:5]
        )
        return (
            "More than one order line matches that description, so no action was "
            f"prepared. Name the one you mean: {listed}."
        )
    reason = getattr(grounding, "reason", "")
    if reason == "no_order_history":
        return "This client has no order history, so there is no item to return."
    if reason == "order_history_unavailable":
        return "Order history could not be read, so no action was prepared."
    return "The item to return could not be identified from that request."


def describe_execution(capability: Dict[str, Any]) -> str:
    """One restrained line about whether the governed rail can run this now."""
    state = str(capability.get("state") or "")
    if state == "available":
        return "Governed execution available."
    if state == "review_required":
        return "Human confirmation is required before requesting governed execution."
    if state == "temporarily_unavailable":
        return "Governed execution temporarily unavailable."
    if state == "not_enabled":
        return "This capability is not enabled in this deployment."
    return "Governed execution state could not be confirmed."
