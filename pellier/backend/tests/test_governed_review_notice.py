"""The shopper must be told a person will confirm, whatever the prose says.

The measured defect
-------------------

On the shopper rail a store credit is never written: ``ask_a_person`` opens an
operator review and the credit itself is ``give_store_credit``, staff only.
The Support agent is told to say that a person reviews the credit and that
nothing has changed yet. On 2026-08-27, against the live stack, a model said
it had "prepared the request" and dropped the second sentence, and a shopper
reading that reasonably concluded the action was done.

So the handoff payload carries the review id, the chat surface emits the
notice as its own ``review_pending`` event with the backend's sentence, and
the in-process guard on ``give_store_credit`` promises nothing at all.
"""

from __future__ import annotations

import inspect
import json
from typing import Any, Dict, List

import pytest

from pellier_copy import GOVERNED_ACTION_NOT_PERFORMED, GOVERNED_REVIEW_PENDING
from services import chat as CHAT
from services import store_tools
from services.agent_tools import _managed_rail_required


@pytest.fixture
def governed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the flagship format for this module.

    `conftest.py` deliberately runs with no `WORKSHOP_FORMAT`, so
    `requires_managed_rail` returns False and there is no refusal to test.
    """
    from config import settings

    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "governed", raising=False)


def test_the_refusal_envelope_carries_the_non_promising_sentence(governed: None) -> None:
    """The guard runs before any review exists, so it cannot claim one."""
    envelope = json.loads(_managed_rail_required("give_store_credit") or "{}")
    assert envelope["message"] == GOVERNED_ACTION_NOT_PERFORMED
    assert "review_id" not in envelope
    assert "waiting" not in envelope["message"].lower()


def test_every_managed_tool_gets_the_same_honest_default(governed: None) -> None:
    from services.execution_rail import mutation_tools

    assert mutation_tools() == frozenset({"give_store_credit"})
    for tool in sorted(mutation_tools()):
        envelope = json.loads(_managed_rail_required(tool) or "{}")
        assert envelope["message"] == GOVERNED_ACTION_NOT_PERFORMED, tool


def test_a_non_governed_format_produces_no_refusal_at_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """The builders lineage serves the credit in process, so there is nothing to refuse."""
    from config import settings

    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "builders", raising=False)
    assert _managed_rail_required("give_store_credit") is None


def test_the_envelope_keeps_its_machine_fields(governed: None) -> None:
    """`is_boundary_refusal` matches on `error`; the rail name makes it diagnosable."""
    envelope = json.loads(_managed_rail_required("give_store_credit") or "{}")
    assert envelope["error"] == "managed_rail_required"
    assert envelope["tool"] == "give_store_credit"
    assert envelope["required_rail"] == "gateway-mcp"

    from services import operator_review as rv

    assert rv.is_boundary_refusal(envelope) is True


@pytest.mark.parametrize("tool", ["check_stock", "get_orders", "get_tickets", "ask_a_person"])
def test_a_permitted_tool_gets_no_envelope(governed: None, tool: str) -> None:
    assert _managed_rail_required(tool) is None


def test_both_sentences_say_what_did_and_did_not_happen() -> None:
    """The refusal taxonomy in VOICE.md: what happened, what did not, who acts next."""
    for text in (GOVERNED_REVIEW_PENDING, GOVERNED_ACTION_NOT_PERFORMED):
        assert "nothing about your order has" in text.lower()
        assert "pellier specialist" in text.lower()
        assert "—" not in text
        for internal in ("managed_rail", "gateway", "Cedar", "policy", "rail", "tool"):
            assert internal.lower() not in text.lower(), internal
    assert "waiting" in GOVERNED_REVIEW_PENDING.lower()
    assert "waiting" not in GOVERNED_ACTION_NOT_PERFORMED.lower()
    assert "prepared" not in GOVERNED_ACTION_NOT_PERFORMED.lower()


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
    assert params[5] == store_tools.write_request_hash(
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
