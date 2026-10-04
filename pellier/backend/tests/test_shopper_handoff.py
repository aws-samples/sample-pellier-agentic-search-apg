"""Contracts for the immutable storefront-to-operator handoff."""

from __future__ import annotations

from typing import Any

import pytest

from services import shopper_handoff as HANDOFF


class _Db:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch_one(self, query: str, *params: Any) -> dict[str, Any] | None:
        self.calls.append((query, params))
        return self.row


@pytest.mark.asyncio
async def test_handoff_binds_the_original_turn_to_the_review_fingerprint() -> None:
    db = _Db(
        {
            "review_id": 41,
            "customer_id": "CUST-THEO",
            "action": "give_store_credit",
            "action_hash": "a" * 64,
        }
    )
    history = [
        {"role": "system", "content": "must not persist"},
        {"role": "user", "content": "older"},
        {"role": "assistant", "content": "older answer"},
        {"role": "user", "content": "My bowl arrived chipped."},
    ]

    result = await HANDOFF.build_handoff_context(
        db,
        turn_id="turn-" + ("b" * 32),
        session_id="session-theo",
        customer_id="CUST-THEO",
        shopper_request="Please help me return the chipped bowl.",
        conversation_history=history,
        assistant_response="I prepared the exact request for a person to review.",
        specialist_route="customer_support",
        tool_calls=[
            {"tool": "get_return_policy"},
            {"name": "give_store_credit"},
            {"toolName": "give_store_credit"},
        ],
    )

    assert result["trust"] == HANDOFF.TRUST_LABEL
    assert result["checkpoint"] == HANDOFF.WAITING_FOR_HUMAN
    assert result["source"] == {
        "sessionId": "session-theo",
        "turnId": "turn-" + ("b" * 32),
    }
    assert result["routing"] == {
        "specialist": "customer_support",
        "tools": ["get_return_policy", "give_store_credit"],
    }
    assert result["proposal"] == {
        "reviewId": 41,
        "action": "give_store_credit",
        "actionHash": "a" * 64,
    }
    assert [message["role"] for message in result["transcriptExcerpt"]] == [
        "user",
        "assistant",
        "user",
    ]
    assert result["evidenceRefs"] == [
        {"kind": "governed_turn_receipt", "id": "turn-" + ("b" * 32)},
        {"kind": "approval", "id": 41},
    ]


@pytest.mark.asyncio
async def test_handoff_is_absent_when_no_review_was_prepared() -> None:
    result = await HANDOFF.build_handoff_context(
        _Db(None),
        turn_id="turn-read",
        session_id="session-read",
        customer_id="CUST-MARCO",
        shopper_request="What is in stock?",
        conversation_history=[],
        assistant_response="Three pieces are in stock.",
        specialist_route="inventory",
        tool_calls=["check_stock"],
    )

    assert result == {}


def test_transcript_and_assistant_copy_are_bounded() -> None:
    bounded = HANDOFF._bounded_transcript(
        [
            {"role": "user", "content": str(index) * 800}
            for index in range(8)
        ]
    )

    assert len(bounded) == 6
    assert all(len(message["content"]) == HANDOFF._TRANSCRIPT_CHARS for message in bounded)
    assert all(message["truncated"] == "true" for message in bounded)


def test_attached_evidence_refs_are_identifiers_not_tool_payloads() -> None:
    original = {
        "evidenceRefs": [{"kind": "approval", "id": 41}],
        "proposal": {"reviewId": 41},
    }
    result = HANDOFF.attach_evidence_refs(
        original,
        retrieval_receipt_id=8,
        audit_rows=[{"audit_id": 19, "args": {"secret": "not copied"}}],
    )

    assert result["evidenceRefs"] == [
        {"kind": "approval", "id": 41},
        {"kind": "retrieval_receipt", "id": 8},
        {"kind": "tool_audit", "id": 19},
    ]
    assert original["evidenceRefs"] == [{"kind": "approval", "id": 41}]
    assert "secret" not in str(result)


@pytest.mark.asyncio
async def test_review_resolution_rejects_any_lineage_mismatch() -> None:
    row = {
        "review_id": 41,
        "customer_id": "CUST-THEO",
        "action": "give_store_credit",
        "action_hash": "a" * 64,
        "source_turn_id": "turn-" + ("b" * 32),
        "session_id": "session-theo",
        "handoff_context": {
            "customerId": "CUST-MARCO",
            "source": {"turnId": "turn-" + ("b" * 32)},
            "proposal": {
                "reviewId": 41,
                "action": "give_store_credit",
                "actionHash": "a" * 64,
            },
        },
    }

    with pytest.raises(
        HANDOFF.HandoffIntegrityError, match="shopper_handoff_lineage_mismatch"
    ):
        await HANDOFF.resolve_for_review(
            _Db(row), review_id=41, expected_customer_id="CUST-THEO"
        )


@pytest.mark.asyncio
async def test_latest_handoff_must_match_the_requested_customer() -> None:
    row = {
        "review_id": 41,
        "customer_id": "CUST-THEO",
        "action": "give_store_credit",
        "action_hash": "a" * 64,
        "source_turn_id": "turn-" + ("b" * 32),
        "session_id": "session-theo",
        "handoff_context": {
            "customerId": "CUST-THEO",
            "source": {"turnId": "turn-" + ("b" * 32)},
            "proposal": {
                "reviewId": 41,
                "action": "give_store_credit",
                "actionHash": "a" * 64,
            },
        },
    }

    with pytest.raises(HANDOFF.HandoffIntegrityError):
        await HANDOFF.resolve_latest_for_customer(
            _Db(row), customer_id="CUST-ANNA"
        )
