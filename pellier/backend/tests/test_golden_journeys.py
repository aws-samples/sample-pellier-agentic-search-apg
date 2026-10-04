"""Golden retail journeys: deterministic fixture and teaching-contract gates.

Version 2 keeps the original fixture regressions, then adds the stage contract
participants are meant to learn:

    intent -> identity -> grounding -> proposal -> human decision
      -> authorization -> data enforcement -> durable evidence -> outcome

A journey may stop partway through that order and hand the rest to another
journey. Theo's does: his damaged-bowl thread ends at ``proposal`` with the
review pending, because the shopper turn genuinely ends there. Authorization,
database enforcement, and durable evidence are proved on Jessica's governed
return, where the same request is sent under three identities and identity is
the only variable. Keeping them in Theo's journey implied one shopper turn
crossed all of those boundaries, which no turn in this workshop does.

The file does not claim a local fixture proves AgentCore. Managed verdicts stay
``deferred_live`` until a fresh AWS environment produces them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_FILE = Path(__file__).resolve().parent / "golden" / "journeys.json"

# The one Lab 1 request. Also in personaCurations.ts, WORKSHOP.md, and the
# eval harness golden set.
CANONICAL_ANNA_QUERY = "A housewarming gift under $100 that is currently in stock."


def _load_golden() -> Dict[str, Any]:
    return json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))


GOLDEN = _load_golden()
JOURNEYS = GOLDEN["journeys"]












def test_golden_set_names_the_complete_retail_cast() -> None:
    """The hero remains three people; guest and Jessica add boundary coverage."""
    personas = {journey["persona"] for journey in JOURNEYS}
    assert personas == {"guest", "marco", "anna", "theo", "jessica"}
    assert len({journey["id"] for journey in JOURNEYS}) == len(JOURNEYS)


@pytest.mark.parametrize("journey", JOURNEYS, ids=[j["id"] for j in JOURNEYS])
def test_every_journey_uses_the_same_teaching_order(journey: Dict[str, Any]) -> None:
    """Stages appear in the contract order; a short journey is a prefix of it."""
    expected = GOLDEN["stageContract"]["order"]
    stage_ids = [stage["id"] for stage in journey["stages"]]
    assert stage_ids == expected[: len(stage_ids)]

    allowed = set(GOLDEN["stageContract"]["proofStates"])
    assert all(stage["proof"] in allowed for stage in journey["stages"])
    assert all(stage["teaches"].strip() for stage in journey["stages"])


@pytest.mark.parametrize("journey", JOURNEYS, ids=[j["id"] for j in JOURNEYS])
def test_a_journey_that_stops_early_says_where_it_stops_and_who_continues(
    journey: Dict[str, Any]
) -> None:
    """An unfinished journey must name its last stage and its successor.

    Silently truncating the stage list would read as an oversight. Declaring
    ``endsAt`` and ``handoff`` makes the boundary the teaching point it is.
    """
    expected = GOLDEN["stageContract"]["order"]
    stage_ids = [stage["id"] for stage in journey["stages"]]
    if stage_ids == expected:
        assert "endsAt" not in journey
        return

    assert journey["endsAt"] == stage_ids[-1]
    handoff = journey["handoff"]
    successor = next(
        item for item in JOURNEYS if item["id"] == handoff["continuesIn"]
    )
    remaining = expected[len(stage_ids):]
    assert set(handoff["carries"]).issubset(set(remaining))
    successor_stages = {stage["id"] for stage in successor["stages"]}
    assert set(handoff["carries"]).issubset(successor_stages)


def test_theo_ends_at_a_pending_human_decision() -> None:
    """Lab 3's shopper thread prepares a write; it does not authorize one."""
    journey = next(
        item for item in JOURNEYS if item["id"] == "theo-damaged-return-closed-loop"
    )
    assert journey["kind"] == "governed_proposal"
    assert journey["endsAt"] == "proposal"
    assert journey["human_decision"] == "pending"
    stage_ids = {stage["id"] for stage in journey["stages"]}
    assert not stage_ids & {"authorization", "data_enforcement", "durable_evidence"}
    # A proposal journey must not carry the vocabulary of a completed write.
    assert "localExecutionBoundary" not in journey["closedLoop"]
    assert "idempotencyRequired" not in journey["closedLoop"]


def test_jessica_governed_return_varies_only_identity() -> None:
    """The Lab 4 matrix: one request, four principals, four distinct outcomes."""
    journey = next(
        item for item in JOURNEYS if item["id"] == "jessica-governed-return"
    )
    assert journey["kind"] == "governed_write"
    assert journey["negativeControls"] == ["marco", "anna"]

    matrix = journey["identityMatrix"]
    denied = [case for case in matrix if case["expectedDecision"] == "DENY"]
    allowed = [case for case in matrix if case["expectedDecision"] == "ALLOW"]
    assert {case["principal"] for case in denied} == {"marco", "anna"}
    # A denial leaves neither an execution row nor an effect. Both are asserted
    # because a DENY that still wrote a row is the contradiction worth catching.
    assert all(case["executionRows"] == 0 for case in denied)
    assert all(case["durableEffects"] == 0 for case in denied)

    replay = next(case for case in allowed if case.get("replay"))
    first = next(case for case in allowed if not case.get("replay"))
    assert first["durableEffects"] == 1
    # The replay is authorized and executes again; the idempotency key is what
    # keeps the business effect at exactly one.
    assert replay["executionRows"] == 1
    assert replay["durableEffects"] == 0
    assert journey["closedLoop"]["idempotencyRequired"] is True
    assert journey["closedLoop"]["rowLevelSecurityRequired"] is True
    assert journey["closedLoop"]["correlationKey"] == "idempotency_key"


def test_proposal_keeps_actor_subject_and_confirmation_distinct() -> None:
    """The operator is authorized; the customer is the RLS subject."""
    journey = next(
        item for item in JOURNEYS if item["id"] == "theo-damaged-return-closed-loop"
    )
    actors = journey["actors"]
    contract = journey["closedLoop"]

    assert actors["executor"]["principal"] != actors["customerSubject"]
    assert actors["executor"]["requiredGroup"] == "pellier-operators"
    assert contract["humanConfirmationRequired"] is True
    assert contract["executionParametersSource"] == "persisted_review_only"
    assert contract["serverResolvedCustomerSubject"] is True


def test_every_consequential_journey_binds_the_exact_parameters() -> None:
    """A proposal and an execution both bind the same material parameters."""
    for journey_id in ("theo-damaged-return-closed-loop", "jessica-governed-return"):
        contract = next(
            item for item in JOURNEYS if item["id"] == journey_id
        )["closedLoop"]
        assert contract["materialParameters"] == [
            "customer_id",
            "product_id",
            "reason",
        ], journey_id
        assert contract["actionFingerprint"] == "sha256_canonical_operation_arguments"


def test_the_executing_journey_requires_idempotency_rls_and_receipt() -> None:
    journey = next(
        item for item in JOURNEYS if item["id"] == "jessica-governed-return"
    )
    contract = journey["closedLoop"]

    assert contract["idempotencyRequired"] is True
    assert contract["rowLevelSecurityRequired"] is True
    assert contract["receiptRequired"] is True


def test_local_golden_set_never_fabricates_a_managed_verdict() -> None:
    """Local PostgreSQL may prove workflow state, never Cedar ALLOW/DENY."""
    for journey in JOURNEYS:
        if journey["kind"] != "governed_write":
            continue
        by_id = {stage["id"]: stage for stage in journey["stages"]}
        assert by_id["authorization"]["proof"] == "deferred_live"
        assert by_id["customer_outcome"]["proof"] == "deferred_live"
        assert (
            journey["closedLoop"]["localExecutionBoundary"]
            == "managed_execution_deferred_live"
        )


def test_anna_uses_the_canonical_lab_two_query() -> None:
    """One query string across the guide, the storefront chip, and the harness.

    Lab 1 compares five retrieval strategies on one request. If the journey,
    the clickable chip, and the eval harness each carry their own wording, the
    comparison measures three different questions.
    """
    journey = next(
        item for item in JOURNEYS if item["id"] == "anna-constrained-gift-retrieval"
    )
    assert journey["entryPrompt"] == CANONICAL_ANNA_QUERY

    curations = (
        REPO_ROOT / "pellier" / "frontend" / "src" / "data" / "personaCurations.ts"
    ).read_text(encoding="utf-8")
    assert f"query: '{CANONICAL_ANNA_QUERY}'" in curations


def test_jessica_preserves_fact_context_and_inference() -> None:
    journey = next(
        item
        for item in JOURNEYS
        if item["id"] == "jessica-return-evidence-reconciliation"
    )
    contract = journey["epistemicContract"]

    assert set(contract) == {"fact", "context", "inference", "forbiddenClaim"}
    assert "returns" in contract["fact"].lower()
    assert "TKT-2026-3015" in contract["context"]
    assert journey["safeStop"]["consequentialActionPrepared"] is False
    assert contract["forbiddenClaim"] == "Jessica completed a return"
