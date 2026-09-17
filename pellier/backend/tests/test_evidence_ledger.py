"""Typed Evidence Ledger projection tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from services.evidence_ledger import (
    EvidenceLedgerProjectionError,
    _sufficiency,
    project_session_ledger,
    project_turn_ledger,
)


class _LedgerDB:
    def __init__(self, *, denied: bool = False) -> None:
        self.denied = denied
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch_all(self, query: str, *params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        if "evidence_ledger_event_refs" in query:
            assert params[-1] == "principal-1"
            turn_id = "turn-" + ("a" * 32)
            session_id = "session-1"
            rows = [
                {
                    "turn_id": turn_id,
                    "session_id": session_id,
                    "event_kind": "route",
                    "phase": "routing",
                    "status": "succeeded",
                    "provenance": "aurora-receipt",
                    "source_kind": "governed_turn_receipt",
                    "source_id": turn_id,
                    "occurred_at": datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
                    "duration_ms": None,
                    "summary": {"rail": "gateway-mcp"},
                },
                {
                    "turn_id": turn_id,
                    "session_id": session_id,
                    "event_kind": "policy",
                    "phase": "governance",
                    "status": "denied" if self.denied else "succeeded",
                    "provenance": "aurora-receipt",
                    "source_kind": "governed_turn_receipt_policy",
                    "source_id": f"{turn_id}:1",
                    "occurred_at": datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
                    "duration_ms": None,
                    "summary": {"decision": "DENY" if self.denied else "ALLOW"},
                },
            ]
            if not self.denied:
                rows.append(
                    {
                        "turn_id": turn_id,
                        "session_id": session_id,
                        "event_kind": "tool",
                        "phase": "execution",
                        "status": "succeeded",
                        "provenance": "aurora-receipt",
                        "source_kind": "tool_audit",
                        "source_id": "17",
                        "occurred_at": datetime(
                            2026, 9, 2, 12, 0, 1, tzinfo=timezone.utc
                        ),
                        "duration_ms": 18,
                        "summary": {
                            "tool": "initiate_return",
                            "caller": "gateway",
                        },
                    }
                )
            rows.append(
                {
                    "turn_id": turn_id,
                    "session_id": session_id,
                    "event_kind": "response",
                    "phase": "terminal",
                    "status": "denied" if self.denied else "succeeded",
                    "provenance": "aurora-receipt",
                    "source_kind": "governed_turn_receipt",
                    "source_id": turn_id,
                    "occurred_at": datetime(
                        2026, 9, 2, 12, 0, 2, tzinfo=timezone.utc
                    ),
                    "duration_ms": 45,
                    "summary": {
                        "terminal_status": (
                            "denied-before-execution"
                            if self.denied
                            else "complete"
                        ),
                        "citation_count": 0,
                        "tool_count": 0 if self.denied else 1,
                    },
                }
            )
            return rows
        if "governed_query_receipts" in query:
            return []
        if "retrieval_receipts" in query:
            return []
        raise AssertionError(f"unexpected query: {query}")


def test_turn_projection_is_principal_scoped_and_explicitly_typed() -> None:
    db = _LedgerDB()
    turn_id = "turn-" + ("a" * 32)

    ledger = asyncio.run(
        project_turn_ledger(
            db,
            turn_id=turn_id,
            principal_sub="principal-1",
        )
    )

    assert ledger is not None
    assert ledger["authority"] == "canonical-receipt-projection"
    assert ledger["principalScoped"] is True
    assert [event["eventKind"] for event in ledger["events"]] == [
        "route",
        "policy",
        "tool",
        "response",
    ]
    assert all(event["evidenceRef"]["kind"] for event in ledger["events"])
    assert db.calls[0][1] == (turn_id, "principal-1")


def test_deny_replay_does_not_invent_tool_execution() -> None:
    ledger = asyncio.run(
        project_turn_ledger(
            _LedgerDB(denied=True),
            turn_id="turn-" + ("a" * 32),
            principal_sub="principal-1",
        )
    )

    assert ledger is not None
    assert "tool" not in {event["eventKind"] for event in ledger["events"]}
    tool_check = next(
        check
        for check in ledger["evidenceSufficiency"]
        if check["id"] == "tool-execution"
    )
    assert tool_check["status"] == "not_reached"


def test_operator_lifecycle_is_a_post_turn_typed_ledger_event() -> None:
    class _OperatorLifecycleDB(_LedgerDB):
        async def fetch_all(
            self, query: str, *params: Any
        ) -> list[dict[str, Any]]:
            rows = await super().fetch_all(query, *params)
            if "evidence_ledger_event_refs" not in query:
                return rows
            turn_id = "turn-" + ("a" * 32)
            rows.extend(
                [
                    {
                        "turn_id": turn_id,
                        "session_id": "session-1",
                        "event_kind": "operator_review",
                        "phase": "follow_up",
                        "status": "planned",
                        "provenance": "aurora-receipt",
                        "source_kind": "operator_review",
                        "source_id": "41",
                        "occurred_at": datetime(
                            2026, 9, 2, 12, 1, tzinfo=timezone.utc
                        ),
                        "duration_ms": None,
                        "summary": {
                            "lifecycle": "review_opened",
                            "review_id": 41,
                            "action": "initiate_return",
                        },
                    },
                    {
                        "turn_id": turn_id,
                        "session_id": "session-1",
                        "event_kind": "operator_review",
                        "phase": "follow_up",
                        "status": "succeeded",
                        "provenance": "aurora-receipt",
                        "source_kind": "operator_review_decision",
                        "source_id": "41:decision",
                        "occurred_at": datetime(
                            2026, 9, 2, 12, 2, tzinfo=timezone.utc
                        ),
                        "duration_ms": None,
                        "summary": {
                            "lifecycle": "confirmed",
                            "review_id": 41,
                            "action": "initiate_return",
                        },
                    },
                    {
                        "turn_id": turn_id,
                        "session_id": "session-1",
                        "event_kind": "operator_review",
                        "phase": "follow_up",
                        "status": "denied",
                        "provenance": "aurora-receipt",
                        "source_kind": "operator_execution_receipt",
                        "source_id": "73",
                        "occurred_at": datetime(
                            2026, 9, 2, 12, 3, tzinfo=timezone.utc
                        ),
                        "duration_ms": None,
                        "summary": {
                            "lifecycle": "execution_recorded",
                            "review_id": 41,
                            "action": "initiate_return",
                            "rail": "gateway-mcp",
                            "policy_outcome": "DENY",
                            "aurora_outcome": "NOT_REACHED",
                            "evidence_outcome": "POLICY_PROOF",
                        },
                    },
                ]
            )
            return rows

    ledger = asyncio.run(
        project_turn_ledger(
            _OperatorLifecycleDB(),
            turn_id="turn-" + ("a" * 32),
            principal_sub="principal-1",
        )
    )

    assert ledger is not None
    lifecycle = [
        event
        for event in ledger["events"]
        if event["eventKind"] == "operator_review"
    ]
    # The terminal shopper receipt remains terminal for that rail. Later human
    # review and execution facts follow it instead of being presented as
    # contemporaneous shopper-tool activity.
    assert ledger["events"][
        next(
            index
            for index, event in enumerate(ledger["events"])
            if event["eventKind"] == "response"
        )
    ]["sequence"] < lifecycle[0]["sequence"]
    assert [event["title"] for event in lifecycle] == [
        "Operator review opened",
        "Operator confirmed the prepared action",
        "Operator execution receipt",
    ]
    assert lifecycle[0]["summary"] == (
        "initiate_return was prepared for Operator review. "
        "The shopper rail did not execute the mutation."
    )
    assert lifecycle[2]["summary"] == (
        "Operator execution for initiate_return: policy DENY; Aurora "
        "NOT_REACHED; evidence POLICY_PROOF."
    )
    assert "actor_principal" not in lifecycle[2]["details"]


def test_session_projection_filters_on_session_and_principal() -> None:
    db = _LedgerDB()
    ledger = asyncio.run(
        project_session_ledger(
            db,
            session_id="session-1",
            principal_sub="principal-1",
        )
    )

    assert ledger is not None
    assert ledger["sessionId"] == "session-1"
    assert ledger["turnIds"] == ["turn-" + ("a" * 32)]
    assert db.calls[0][1] == ("session-1", "principal-1")


def test_strict_projection_distinguishes_unavailable_from_not_found() -> None:
    class _UnavailableDB:
        async def fetch_all(self, query: str, *params: Any) -> list[dict[str, Any]]:
            raise RuntimeError("database unavailable")

    assert (
        asyncio.run(
            project_turn_ledger(
                _UnavailableDB(),
                turn_id="turn-" + ("b" * 32),
                principal_sub="principal-1",
            )
        )
        is None
    )
    with pytest.raises(EvidenceLedgerProjectionError):
        asyncio.run(
            project_turn_ledger(
                _UnavailableDB(),
                turn_id="turn-" + ("b" * 32),
                principal_sub="principal-1",
                raise_on_error=True,
            )
        )


# ---------------------------------------------------------------------------
# Contradiction: two canonical receipts that cannot both be true
# ---------------------------------------------------------------------------
def _event(
    kind: str, status: str, tool: str | None = None,
    *, turn_id: str = "turn-1", audit_id: int | None = 77,
) -> dict[str, Any]:
    return {
        "eventKind": kind,
        "status": status,
        "turnId": turn_id,
        "evidenceRef": {"kind": "tool_audit" if kind == "tool" else "governed_turn_receipt_policy", "id": "77"},
        "details": {"tool": tool, "audit_id": audit_id} if tool else {},
    }


def _check(checks: list[dict[str, Any]], check_id: str) -> dict[str, Any]:
    return next(check for check in checks if check["id"] == check_id)


@pytest.mark.parametrize("execution_status", ["succeeded", "unavailable"])
def test_deny_linked_to_the_exact_execution_row_reads_contradicted(execution_status: str) -> None:
    """A DENY linked to the exact executed audit row cannot hold.

    tool_audit records only calls that ran. Reporting this pair as two
    satisfied checks is exactly how a receipt asserts a non-execution that did
    execute, so the ledger names the disagreement instead.
    """
    checks = _sufficiency(
        [
            _event("response", "succeeded"),
            _event("policy", "denied", "issue_credit"),
            _event("tool", execution_status, "issue_credit"),
        ]
    )

    assert _check(checks, "tool-execution")["status"] == "contradicted"
    assert _check(checks, "policy-decision")["status"] == "contradicted"
    assert "issue_credit" in _check(checks, "tool-execution")["detail"]


def test_deny_and_execution_of_different_tools_is_not_a_contradiction() -> None:
    """One tool refused while another runs is ordinary governed behaviour.

    The guard against a false positive: a contradiction is a claim refuted by
    its own evidence, not merely a DENY sharing a turn with an execution.
    """
    checks = _sufficiency(
        [
            _event("response", "succeeded"),
            _event("policy", "denied", "issue_credit"),
            _event("tool", "succeeded", "check_inventory"),
        ]
    )

    assert _check(checks, "tool-execution")["status"] == "satisfied"
    assert _check(checks, "policy-decision")["status"] == "satisfied"


@pytest.mark.parametrize(
    ("tool_turn", "audit_id"),
    [("turn-1", None), ("turn-1", 78), ("turn-2", 77)],
)
def test_repeated_tool_names_do_not_establish_a_contradiction(
    tool_turn: str, audit_id: int | None,
) -> None:
    checks = _sufficiency([
        _event("response", "succeeded"),
        _event("policy", "denied", "issue_credit", audit_id=audit_id),
        _event("tool", "succeeded", "issue_credit", turn_id=tool_turn),
    ])
    assert _check(checks, "tool-execution")["status"] == "satisfied"
    assert _check(checks, "policy-decision")["status"] == "satisfied"
    if audit_id is None:
        assert _check(checks, "policy-execution-correlation")["status"] == "unavailable"
    else:
        assert not any(check["id"] == "policy-execution-correlation" for check in checks)


def test_null_tool_result_still_has_execution_evidence() -> None:
    checks = _sufficiency([_event("tool", "unavailable", "check_inventory")])
    assert _check(checks, "tool-execution")["status"] == "satisfied"
