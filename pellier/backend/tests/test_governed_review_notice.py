"""The shopper must be told a person will confirm, whatever the prose says.

The measured defect
-------------------

On the shopper rail a store credit is never written: ``ask_a_person`` opens an
operator review and the credit itself is ``give_store_credit``, staff only.
The Support agent is told to say that a person reviews the credit and that
nothing has changed yet. On 2026-08-27, against the live stack, a model said
it had "prepared the request" and dropped the second sentence, and a shopper
reading that reasonably concluded the action was done.

So the handoff payload carries the review id and the chat surface emits the
notice as its own ``review_pending`` event with the backend's sentence. No
shopper agent binds ``give_store_credit``, so there is no in-process credit
to refuse.
"""

from __future__ import annotations

import inspect
import json
from typing import Any, Dict, List

from pellier_copy import GOVERNED_REVIEW_PENDING
from services import chat as CHAT
from services import store_tools


def test_the_sentence_says_what_did_and_did_not_happen() -> None:
    """The refusal taxonomy in VOICE.md: what happened, what did not, who acts next."""
    text = GOVERNED_REVIEW_PENDING
    assert "nothing about your order has" in text.lower()
    assert "pellier specialist" in text.lower()
    assert "—" not in text
    for internal in ("managed_rail", "gateway", "Cedar", "policy", "rail", "tool"):
        assert internal.lower() not in text.lower(), internal
    assert "waiting" in text.lower()


def test_no_agent_can_reach_a_credit_write_in_process() -> None:
    """The boundary is structural: the wrapper does not exist, so no agent binds it."""
    from agents import shopping_agent, stock_agent, support_agent
    from services import agent_tools

    assert not hasattr(agent_tools, "give_store_credit")
    for module in (shopping_agent, stock_agent, support_agent):
        assert "give_store_credit" not in inspect.getsource(module), module.__name__


# ---------------------------------------------------------------------------
# The review is opened by the handoff, and only for a verified shopper
# ---------------------------------------------------------------------------


class _Run:
    def __init__(self, review_id: int | None = 44) -> None:
        self.review_id = review_id
        self.calls: List[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        self.calls.append((sql, tuple(params)))
        if "INSERT INTO pellier.approvals" in sql:
            return [{"id": self.review_id}] if self.review_id else []
        if "FROM pellier.approvals" in sql:
            return [{"id": 45}]
        return []


def test_a_credit_request_opens_exactly_one_pending_review() -> None:
    run = _Run()
    payload = store_tools.ask_a_person(
        run, reason="Two items went back.", customer_id="CUST-JESSICA", store_credit_cents=4500,
        source_turn_id="turn-" + "a" * 32, requested_by_sub="sub-j", requester_kind="shopper",
    )
    assert payload["credit_request"] == "review_opened" and payload["review_id"] == 44
    sql, params = run.calls[0]
    assert "ON CONFLICT (customer_id, tool, action_hash) WHERE status = 'pending'" in sql
    assert params[0] == "CUST-JESSICA" and params[2] == "turn-" + "a" * 32
    assert params[6] == store_tools.write_request_hash(
        "give_store_credit", customer_id="CUST-JESSICA", amount_cents=4500, reason="Two items went back.",
    )


def test_a_repeated_ask_resolves_to_the_open_review() -> None:
    run = _Run(review_id=None)
    payload = store_tools.ask_a_person(
        run, reason="Two items went back.", customer_id="CUST-JESSICA", store_credit_cents=4500,
    )
    assert payload["credit_request"] == "review_opened" and payload["review_id"] == 45
    assert len(run.calls) == 2


def test_a_credit_request_without_a_verified_shopper_opens_nothing() -> None:
    run = _Run()
    payload = store_tools.ask_a_person(run, reason="Credit please.", customer_id=None, store_credit_cents=4500)
    assert payload["credit_request"] == "sign_in_required"
    assert run.calls == []


def test_a_request_over_the_safety_ceiling_opens_nothing() -> None:
    run = _Run()
    payload = store_tools.ask_a_person(
        run, reason="Credit please.", customer_id="CUST-JESSICA",
        store_credit_cents=store_tools.MAX_CREDIT_CENTS + 1,
    )
    assert payload["credit_request"] == "over_ceiling"
    assert run.calls == []


def test_a_plain_handoff_is_not_a_credit_request() -> None:
    run = _Run()
    payload = store_tools.ask_a_person(run, reason="I want a person.", customer_id="CUST-THEO")
    assert "credit_request" not in payload and payload["status"] == "handed_off"
    assert run.calls == []


# ---------------------------------------------------------------------------
# The chat surface emits the sentence from the payload, not from the prose
# ---------------------------------------------------------------------------


def test_the_scanner_finds_the_handoff_payload() -> None:
    found = CHAT._scan_for_escalation(json.dumps({"type": "escalation", "review_id": 44}))
    assert found is not None and found["review_id"] == 44


def test_the_scanner_ignores_everything_else() -> None:
    for other in (
        "",
        "plain prose with no payload",
        json.dumps({"status": "success", "credit_id": 37}),
        json.dumps({"error": "managed_rail_required", "tool": "give_store_credit"}),
    ):
        assert CHAT._scan_for_escalation(other) is None


def test_the_emission_uses_the_canonical_sentence_and_suppresses_products() -> None:
    stream = inspect.getsource(CHAT)
    emission = stream[stream.index("if escalation_payload is not None:"):]
    emission = emission[: emission.index("# Now send buffered products")]
    assert '"type": "review_pending"' in emission
    assert '"tool": "give_store_credit"' in emission
    assert '"message": GOVERNED_REVIEW_PENDING' in emission
    assert "products_buffered = []" in emission
    assert 'parsed["products"] = []' in emission


def test_the_support_prompt_still_asks_for_the_sentence() -> None:
    """Belt and braces. The notice does not license removing the instruction."""
    from agents import support_agent

    prompt = support_agent._SUPPORT_SYSTEM_PROMPT
    assert "A person reviews every credit before anything changes" in prompt
    assert "nothing has changed yet" in prompt
    assert "never say a refund, return or credit was made unless a tool result says so" in prompt
