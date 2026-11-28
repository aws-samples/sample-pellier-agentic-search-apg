"""The Operator's credit card, in the terminal's words.

The Operator shows a credit as rows of ``label, status word, one plain sentence``
(``pellier/frontend/src/operator/components/ProposedCreditCard.tsx``). The lab checks and
the Wrap-up print the same rows with the same words, so a participant who read the card
reads the terminal without learning a second vocabulary. The card is TypeScript and this is
Python, so the two are held together by ``tests/test_terminal_redesign.py``, which fails when
a sentence here is no longer in the card.
"""

from __future__ import annotations

from typing import Tuple

APPROVAL, POLICY, RECORDED = "Approval", "Policy", "Recorded"

APPROVED_SENTENCE = "A person agreed to exactly this customer, amount and reason."
NO_APPROVAL_TAG = "No person approved it"
NO_APPROVAL_SENTENCE = "It exists to send one over-limit credit to Cedar."
GATEWAY_ANSWERED = "The Gateway answered: "
TOOL_NEVER_RAN = "The tool never ran."
NOT_WRITTEN_TAG = "Not written"
NOT_WRITTEN_SENTENCE = "No store_credits row and no tool_audit row for this key."
RECORDED_ONCE_TAG = "Recorded once"
RETRY_SENTENCE = "A retry keeps both at one."


def approved_by(name: str) -> Tuple[str, str]:
    """The Approval row of a credit a person confirmed."""
    return f"Approved by {name}", APPROVED_SENTENCE


def policy_row(decision: str, tool_ran: bool) -> Tuple[str, str]:
    """The Policy row for the Gateway's decision (``ALLOW`` or ``DENY``)."""
    allowed = decision == "ALLOW"
    sentence = f"{GATEWAY_ANSWERED}{'allowed' if allowed else 'denied'}."
    if not allowed and not tool_ran:
        sentence += f" {TOOL_NEVER_RAN}"
    return decision, sentence


def not_written() -> Tuple[str, str]:
    """The Recorded row of a credit that left no row in either table."""
    return NOT_WRITTEN_TAG, NOT_WRITTEN_SENTENCE


def recorded_once(credit_id: str, audit_id: str) -> Tuple[str, str]:
    """The Recorded row of a credit written exactly once."""
    return RECORDED_ONCE_TAG, (f"Credit #{credit_id} and tool_audit row #{audit_id}, once each. "
                               f"{RETRY_SENTENCE}")
