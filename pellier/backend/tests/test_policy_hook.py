"""Tests for the Strands ``BeforeToolCallEvent`` policy hook.

Scope:
  * DENY outcomes set ``event.cancel_tool`` to a human-readable string
    so Strands short-circuits the tool with a synthetic result.
  * ALLOW outcomes leave ``cancel_tool`` untouched.
  * Unmapped tools bypass the policy engine (reads-only: whats_trending,
    side_by_side, floor_check, etc.).
  * Decisions are recorded in the per-session buffer and reachable via
    ``get_decisions``.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _event_for(tool_name: str, **params) -> SimpleNamespace:
    """Build the minimum-shape event the hook consumes: ``tool_use``
    dict with a name + input dict, plus a writable ``cancel_tool``."""
    return SimpleNamespace(
        tool_use={"name": tool_name, "toolUseId": "tid-test", "input": params},
        cancel_tool=False,
    )


@pytest.fixture(autouse=True)
def _reset_decision_buffer():
    """Keep the module-global decision buffer clean between tests."""
    from services import policy_hook
    with policy_hook._decisions_lock:
        policy_hook._decisions.clear()
    yield


def test_allow_for_unmapped_tool_bypasses_policy():
    """Tools not in ``_TOOL_TO_POLICY_ACTION`` (read-only catalog
    queries) run unconditionally — no PolicyService call, no decision
    recorded, no cancel."""
    from services.policy_hook import PolicyEnforcementHook, get_decisions

    hook = PolicyEnforcementHook(session_id="s1")
    event = _event_for("whats_trending", limit=5)

    with patch.object(hook._policy, "evaluate") as evaluate_mock:
        hook._on_before_tool(event)
        evaluate_mock.assert_not_called()

    assert event.cancel_tool is False
    assert get_decisions("s1") == []


def test_allow_result_does_not_cancel_and_records_decision():
    """Policy evaluates as ALLOW → cancel stays False, but the
    decision is still recorded so the Atelier Policy tab can show
    the full audit trail, not just denials."""
    from services.policy_hook import PolicyEnforcementHook, get_decisions

    hook = PolicyEnforcementHook(session_id="s-allow")
    event = _event_for("find_pieces", query="leather sneakers")

    hook._on_before_tool(event)
    assert event.cancel_tool is False

    decisions = get_decisions("s-allow")
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "ALLOW"
    assert decisions[0]["tool_name"] == "find_pieces"


def test_deny_for_restricted_category_cancels_tool():
    """A DENY decision from PolicyService must set ``cancel_tool`` to
    a non-empty string so Strands emits a synthetic tool result. The
    cancel message must mention the violation reason so the agent's
    paraphrase can be specific."""
    from services.policy_hook import PolicyEnforcementHook, get_decisions

    hook = PolicyEnforcementHook(session_id="s-deny")
    event = _event_for("find_pieces", query="a gift with a gun charm")

    hook._on_before_tool(event)

    assert isinstance(event.cancel_tool, str)
    assert "Policy denied" in event.cancel_tool
    assert "restricted" in event.cancel_tool.lower() or "gun" in event.cancel_tool.lower()

    decisions = get_decisions("s-deny")
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "DENY"
    assert decisions[0]["violations"]


def test_deny_for_restock_over_limit():
    """Quantity-gated DENY: restocking > 500 units must cancel."""
    from services.policy_hook import PolicyEnforcementHook

    hook = PolicyEnforcementHook(session_id="s-restock")
    event = _event_for("restock_shelf", product_id=42, quantity=5000)

    hook._on_before_tool(event)

    assert isinstance(event.cancel_tool, str)
    assert "5000" in event.cancel_tool or "500" in event.cancel_tool


def test_evaluate_exception_fails_open():
    """If PolicyService.evaluate raises, the hook must log and fall
    through — never block on a misconfigured policy. Tool runs; no
    decision recorded (because we couldn't produce one)."""
    from services.policy_hook import PolicyEnforcementHook, get_decisions

    hook = PolicyEnforcementHook(session_id="s-error")
    event = _event_for("find_pieces", query="ok")

    with patch.object(hook._policy, "evaluate", side_effect=RuntimeError("boom")):
        hook._on_before_tool(event)

    assert event.cancel_tool is False
    assert get_decisions("s-error") == []


def test_get_decisions_returns_newest_first_and_respects_limit():
    """Decision buffer is newest-first and bounded per call."""
    from services.policy_hook import PolicyEnforcementHook, get_decisions

    hook = PolicyEnforcementHook(session_id="s-many")
    for i in range(5):
        event = _event_for("find_pieces", query=f"ok-{i}")
        hook._on_before_tool(event)

    top2 = get_decisions("s-many", limit=2)
    assert len(top2) == 2
    # Newest entry was the last inserted; its query contained "ok-4".
    assert top2[0]["parameters"]["query"] == "ok-4"
    assert top2[1]["parameters"]["query"] == "ok-3"


# ---------------------------------------------------------------------------
# process_return — Theo's anchor write tool
# ---------------------------------------------------------------------------


def test_process_return_with_canonical_reason_allows_and_records_audit():
    """ALLOW path for process_return + canonical reason — must record
    a decision AND call tool_audit_writer.record_allow (mutating tool)."""
    from services.policy_hook import PolicyEnforcementHook, get_decisions
    from services import tool_audit_writer

    hook = PolicyEnforcementHook(session_id="s-theo")
    event = _event_for(
        "process_return",
        customer_id="c-theo", product_id=21, reason="damaged",
    )

    with patch.object(tool_audit_writer, "record_allow") as record_allow_mock:
        hook._on_before_tool(event)

    assert event.cancel_tool is False
    decisions = get_decisions("s-theo")
    assert decisions[0]["decision"] == "ALLOW"
    assert decisions[0]["tool_name"] == "process_return"
    # Audit writer was called for this mutating-tool ALLOW.
    assert record_allow_mock.call_count == 1
    kwargs = record_allow_mock.call_args.kwargs
    assert kwargs["tool_name"] == "process_return"
    assert kwargs["session_id"] == "s-theo"
    assert kwargs["args"]["reason"] == "damaged"


def test_process_return_with_unknown_reason_denies():
    """DENY path: a non-canonical reason value must cancel the tool
    with a Cedar-shaped explanation. Audit must NOT be called (we
    only audit allowed mutations)."""
    from services.policy_hook import PolicyEnforcementHook, get_decisions
    from services import tool_audit_writer

    hook = PolicyEnforcementHook(session_id="s-theo")
    event = _event_for(
        "process_return",
        customer_id="c-theo", product_id=21, reason="vibes_off",
    )

    with patch.object(tool_audit_writer, "record_allow") as record_allow_mock:
        hook._on_before_tool(event)

    assert isinstance(event.cancel_tool, str)
    assert "Policy denied" in event.cancel_tool
    assert "vibes_off" in event.cancel_tool or "allowed set" in event.cancel_tool
    decisions = get_decisions("s-theo")
    assert decisions[0]["decision"] == "DENY"
    record_allow_mock.assert_not_called()


def test_after_tool_event_writes_audit_update_for_mutating_tool():
    """ALLOW + AfterToolCallEvent → tool_audit_writer.record_after fires
    with the latency captured between the Before and After events."""
    import time
    from services.policy_hook import PolicyEnforcementHook
    from services import tool_audit_writer

    hook = PolicyEnforcementHook(session_id="s-theo")
    before = _event_for(
        "process_return",
        customer_id="c-theo", product_id=21, reason="damaged",
    )

    with patch.object(tool_audit_writer, "record_allow"):
        hook._on_before_tool(before)

    # Simulate the tool finishing 50ms later.
    # The After event shape varies across Strands versions; we mimic
    # the common case where it carries the same tool_use dict + a
    # .result attribute.
    after = SimpleNamespace(
        tool_use={"name": "process_return", "toolUseId": "tid-test"},
        result={"status": "success", "return_id": 42},
    )
    # Tweak the captured start time to make the latency assertion
    # deterministic — the hook stores start in self._allow_starts.
    hook._allow_starts["tid-test"] = time.time() - 0.05  # 50ms ago
    with patch.object(tool_audit_writer, "record_after") as record_after_mock:
        hook._on_after_tool(after)

    assert record_after_mock.call_count == 1
    kwargs = record_after_mock.call_args.kwargs
    assert kwargs["tool_use_id"] == "tid-test"
    assert kwargs["result"]["return_id"] == 42
    assert 30 <= kwargs["latency_ms"] <= 200  # ~50ms with margin


def test_after_tool_event_no_op_when_no_pending_start():
    """If the Before event didn't capture a start (e.g. the tool wasn't
    in _MUTATING_TOOLS), the After event must not call record_after."""
    from services.policy_hook import PolicyEnforcementHook
    from services import tool_audit_writer

    hook = PolicyEnforcementHook(session_id="s-x")
    after = SimpleNamespace(
        tool_use={"name": "find_pieces", "toolUseId": "tid-readonly"},
        result={"products": []},
    )
    with patch.object(tool_audit_writer, "record_after") as record_after_mock:
        hook._on_after_tool(after)
    record_after_mock.assert_not_called()


def test_read_only_allow_does_not_audit():
    """ALLOW on a non-mutating tool (find_pieces) must NOT call
    record_allow — audit is reserved for mutations."""
    from services.policy_hook import PolicyEnforcementHook
    from services import tool_audit_writer

    hook = PolicyEnforcementHook(session_id="s-read")
    event = _event_for("find_pieces", query="leather sneakers")

    with patch.object(tool_audit_writer, "record_allow") as record_allow_mock:
        hook._on_before_tool(event)

    assert event.cancel_tool is False
    record_allow_mock.assert_not_called()
