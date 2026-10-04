"""Reconstructing one governed execution, layer by layer.

The defect this replaces
------------------------

The Observatory's evidence read was rooted at ``pellier.tool_audit`` and joined through
``governed_receipts`` / ``governed_turn_receipts``. Neither carries an operator-rail
execution, so ``GET /api/observatory/tool-audit/recent`` returned zero rows for all
three of the live governed executions — correctly scoped, and unable to show them.

Rooting at the tool is also wrong in principle. For a governed system, execution
evidence begins at the AUTHORIZATION ATTEMPT: a Cedar DENY writes no audit row and
claims no idempotency key, so a reconstruction that requires one cannot render the very
outcome the workshop exists to prove.

The spine is therefore the execution receipt, and an absent downstream layer is
evidence rather than missing data.

Measured live on 2026-08-27:

    review 40  THEO    6 layers present
    review 36  RACHEL  stops after the authorization attempt
    review 41  AMARA   tool entered, claim released, no domain row
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

import pytest

from services import governed_execution as GE


def _receipt(**over: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "receipt_id": 10,
        "review_id": 40,
        "actor_principal": "operator-sub",
        "policy_outcome": "ALLOW",
        "aurora_outcome": "PERMITTED",
        "evidence_outcome": "RECEIPTED",
        "gateway_mode": "ENFORCE",
        "idempotency_key": "operator-review:40:abc",
        "tool": "initiate_return",
        "execution_turn_id": "turn-" + "a" * 32,
    }
    base.update(over)
    return base


def _layers(**over: Any) -> Dict[str, Dict[str, Any]]:
    audit = over.pop("audit", [{"audit_id": 1}])
    writes = over.pop("writes", [{"completed_at": "now"}])
    domain = over.pop("domain", [{"id": 37}])
    episodes = over.pop("episodes", [{"episode_id": 37}])
    got = GE.describe_layers(_receipt(**over), audit, writes, domain, episodes)
    return {layer["key"]: layer for layer in got}


# ---------------------------------------------------------------------------
# The three live shapes
# ---------------------------------------------------------------------------


def test_a_completed_write_presents_every_layer() -> None:
    layers = _layers()
    assert [l["present"] for l in layers.values()] == [True] * 6
    assert "applied exactly once" in layers["write_operations"]["detail"]
    assert "pellier.returns" in layers["domain"]["detail"]


def test_a_policy_denial_stops_at_the_authorization_attempt() -> None:
    """And says why, rather than reporting a gap.

    Rendering "Missing data" for Rachel's absent audit row would describe a hole in the
    evidence. There is no hole: the tool was never entered, and the layer above says so.
    """
    layers = _layers(
        policy_outcome="DENY", aurora_outcome="NOT_REACHED",
        evidence_outcome="POLICY_PROOF", audit=[], writes=[], domain=[],
    )
    assert layers["receipt"]["present"] is True
    assert "DENY" in layers["receipt"]["detail"]
    assert layers["tool_audit"]["present"] is False
    assert layers["tool_audit"]["detail"] == (
        "Tool not entered. AgentCore Policy denied the action before execution."
    )
    assert layers["write_operations"]["present"] is False
    assert "never entered" in layers["write_operations"]["detail"]
    for layer in layers.values():
        assert "missing" not in layer["detail"].lower()
        assert "unknown" not in layer["detail"].lower()


def test_a_database_refusal_keeps_the_tool_execution_visible() -> None:
    """Amara: the tool WAS entered under a policy ALLOW, and the write did not apply."""
    layers = _layers(aurora_outcome="DENIED", evidence_outcome="ATTEMPT_RECEIPT",
                     writes=[{"completed_at": None}], domain=[])
    assert layers["tool_audit"]["present"] is True
    assert layers["write_operations"]["present"] is True
    assert "released" in layers["write_operations"]["detail"]
    assert layers["domain"]["present"] is False
    assert "Row-level security refused" in layers["domain"]["detail"]


def test_a_claim_without_completion_is_not_a_database_effect() -> None:
    """The distinction `tool_audit` cannot draw on its own."""
    layers = _layers(writes=[{"completed_at": None}], domain=[{"id": 1}])
    assert layers["domain"]["present"] is False


def test_a_non_terminal_outcome_reports_no_episode() -> None:
    layers = _layers(episodes=[])
    assert layers["episode"]["present"] is False
    assert "not terminal" in layers["episode"]["detail"]


def test_the_gateway_mode_is_never_asserted_when_unrecorded() -> None:
    layers = _layers(gateway_mode=None)
    assert "unrecorded" in layers["receipt"]["detail"]


# ---------------------------------------------------------------------------
# The linkage, which needed no schema change
# ---------------------------------------------------------------------------


def test_audit_rows_are_joined_on_the_write_key() -> None:
    """Deterministic, and already present.

    The Lambda behind the Gateway records the `idempotency_key` it was called with into
    the audit row's arguments, and that key is `operator-review:{id}:{hash}` — the same
    string the execution receipt carries. Verified live: audit rows 234/235/238 all
    carry `operator-review:40:cde072e08883a305956ee83ba7a19d47`.
    """
    sql = " ".join(GE._AUDIT_FOR_KEY.split())
    assert "args->>'idempotency_key' = %s" in sql
    assert "session_id" not in sql.split("WHERE")[1]


def test_the_linkage_uses_no_timestamp_heuristic() -> None:
    """A proximity match is not evidence. It is a guess that looks like one."""
    source = GE._AUDIT_FOR_KEY + GE._WRITE_OPS_FOR_KEY
    for heuristic in ("created_at >", "created_at <", "interval", "BETWEEN"):
        assert heuristic not in source, heuristic


def test_no_new_identifier_family_was_invented() -> None:
    """review_id, execution_turn_id and idempotency_key all already existed."""
    source = inspect.getsource(GE.reconstruct_execution)
    for invented in ("correlation_id", "trace_id", "story_id", "lineage_id"):
        assert invented not in source, invented


# ---------------------------------------------------------------------------
# Visibility: moved onto the right artifact, not removed
# ---------------------------------------------------------------------------


def test_the_list_is_scoped_to_the_acting_principal() -> None:
    sql = " ".join(GE._REVIEWS_FOR_PRINCIPAL.split())
    assert "r.actor_principal = %s" in sql


def test_the_reconstruction_refuses_another_principals_execution() -> None:
    source = inspect.getsource(GE.reconstruct_execution)
    assert 'actor_principal' in source
    assert "return None" in source


class FakeDb:
    def __init__(self, receipts: Optional[List[Dict[str, Any]]] = None) -> None:
        self.receipts = receipts if receipts is not None else [_receipt()]

    async def fetch_all(self, sql: str, *params: Any):
        if "execution_receipts" in sql:
            return list(self.receipts)
        return []

    async def fetch_one(self, sql: str, *params: Any):
        return {"review_id": 40, "customer_id": "CUST-THEO", "args": {}}


@pytest.mark.asyncio
async def test_a_different_principal_gets_nothing() -> None:
    got = await GE.reconstruct_execution(
        FakeDb(), review_id=40, principal_sub="someone-else"
    )
    assert got is None


@pytest.mark.asyncio
async def test_an_unexecuted_review_gets_nothing() -> None:
    got = await GE.reconstruct_execution(
        FakeDb(receipts=[]), review_id=44, principal_sub="operator-sub"
    )
    assert got is None


@pytest.mark.asyncio
async def test_the_acting_principal_gets_the_story() -> None:
    got = await GE.reconstruct_execution(
        FakeDb(), review_id=40, principal_sub="operator-sub"
    )
    assert got is not None
    assert got["latestReceipt"]["receipt_id"] == 10
    assert [l["key"] for l in got["layers"]] == [
        "review", "receipt", "tool_audit", "write_operations", "domain", "episode",
    ]


def test_the_existing_shopper_scoping_is_untouched() -> None:
    """The old query keeps its joins. Nothing was widened to make rows appear."""
    from services import governed_turn_receipt as gtr

    sql = " ".join(gtr._VISIBLE_AUDIT_SQL.split())
    assert "gr.principal_id = %s" in sql
    assert "gtr.principal_sub = %s" in sql
    assert "governed_receipts" in sql
