"""PROMPT 4 Phase A — governed execution of a confirmed review.

The whole point of this stage is that four controls stay independent:

    Human      did a person decide?
    Cedar      may this principal attempt this action?
    RLS        may this session touch these rows?
    CHECK      is this mutation valid regardless of who asked?

Most of the assertions below are therefore negative. A policy verdict must never
appear on a rail where no policy engine was consulted; an ALLOW must never be
inferred from a call that merely returned under LOG_ONLY; and the operator's own
identity must never become the Row-Level Security subject.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

REPO = BACKEND.parents[1]
DEPLOY = REPO / "scripts" / "deploy"

from services import governed_execution as ge  # noqa: E402
from services.store_tools import write_request_hash  # noqa: E402

CREDIT_ARGS = {"customer_id": "CUST-THEO", "amount_cents": 2500, "reason": "courtesy"}
CREDIT_HASH = write_request_hash("give_store_credit", **CREDIT_ARGS)
THEO_SUBJECT = "sub-theo-cognito"
OPERATOR_SUBJECT = "sub-operator-cognito"


# The gateway attachment every governed write now requires. Tests about denial
# classification and telemetry pass this so the mode precondition is satisfied.
ENFORCED = ge.PolicyEngineState(gateway_mode="ENFORCE")


def approved_review(**overrides: Any) -> Dict[str, Any]:
    row = {
        "review_id": 12,
        "customer_id": "CUST-THEO",
        "action": "give_store_credit",
        "args": dict(CREDIT_ARGS),
        "status": "approved",
        "action_hash": CREDIT_HASH,
        "source_turn_id": "turn-" + ("a" * 32),
        "order_id": None,
        "execution_turn_id": None,
        "decided_by": "operator-1",
    }
    row.update(overrides)
    return row


class FakeCredit:
    """Captures what reached ``pellier.apply_store_credit`` and what it answers."""

    calls: List[Dict[str, Any]] = []
    envelope: Dict[str, Any] = {"status": "success", "credit_id": 9}
    raises: Optional[BaseException] = None


class FakeDb:
    """Records statements so the tests can assert what did NOT run."""

    def __init__(
        self,
        *,
        customer_subject: Optional[str] = THEO_SUBJECT,
        existing_execution_turn: Optional[str] = None,
    ) -> None:
        self.customer_subject = customer_subject
        self.existing_execution_turn = existing_execution_turn
        self.statements: List[str] = []
        self.claimed_turns: List[str] = []

    async def fetch_one(self, query: str, *params: Any) -> Optional[Dict[str, Any]]:
        self.statements.append(query)
        if "FROM pellier.principal_customers" in query:
            return (
                {"principal_sub": self.customer_subject}
                if self.customer_subject
                else None
            )
        if query.strip().startswith("UPDATE pellier.approvals"):
            if self.existing_execution_turn:
                return None  # the WHERE ... IS NULL guard refuses a second claim
            self.existing_execution_turn = params[0]
            self.claimed_turns.append(params[0])
            return {"execution_turn_id": params[0]}
        if "SELECT execution_turn_id" in query:
            return {"execution_turn_id": self.existing_execution_turn}
        return None

    async def fetch_all(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        self.statements.append(query)
        if "FROM pellier.approvals" in query:
            # The confirmed review the credit under test binds to: its id is
            # what derives the one key the write is admitted under.
            return [{"id": 12, "action_hash": CREDIT_HASH}]
        if "apply_store_credit" not in query:
            return []
        key, request_hash, customer_id, amount_cents, reason, issued_by = params
        FakeCredit.calls.append(
            {
                "idempotency_key": key,
                "request_hash": request_hash,
                "customer_id": customer_id,
                "amount_cents": amount_cents,
                "reason": reason,
                "issued_by": issued_by,
                "params": params,
            }
        )
        if FakeCredit.raises is not None:
            raise FakeCredit.raises
        return [{"result": dict(FakeCredit.envelope)}]


@pytest.fixture(autouse=True)
def _reset_logic(monkeypatch: pytest.MonkeyPatch):
    FakeCredit.calls = []
    FakeCredit.envelope = {"status": "success", "credit_id": 9}
    FakeCredit.raises = None
    # Default to the in-process rail unless a test opts into the Gateway. The
    # governed format refuses that rail, so the baseline here is the builders one.
    from config import settings

    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "builders", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_URL", "", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_POLICY_ENGINE_ID", "", raising=False)
    monkeypatch.delenv("AGENTCORE_POLICY_ENGINE_ID", raising=False)

    async def receipt_written(*_args: Any, **_kwargs: Any) -> int:
        return 1

    monkeypatch.setattr(ge, "record_receipt", receipt_written)
    yield
    FakeCredit.calls = []


def _governed(monkeypatch: pytest.MonkeyPatch, *, gateway_url: str = "https://gw.example",
              engine_id: str = "engine-1") -> None:
    from config import settings

    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "governed", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_URL", gateway_url, raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_POLICY_ENGINE_ID", engine_id, raising=False)


def _gateway_returns(monkeypatch: pytest.MonkeyPatch, policy: str,
                     envelope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []

    async def fake_gateway(**kwargs: Any):
        calls.append(kwargs)
        if policy == ge.POLICY_DENY:
            return (ge.POLICY_DENY, {"status": "policy_denied",
                                     "denied_by": "agentcore_policy"}, "Cedar denied it.")
        return (ge.POLICY_ALLOW, dict(envelope or {"status": "success", "credit_id": 9}),
                "AgentCore Policy permitted the action.")

    monkeypatch.setattr(ge, "_execute_through_gateway", fake_gateway)
    return calls


# ---------------------------------------------------------------------------
# Gateway vocabulary: source is authoritative
# ---------------------------------------------------------------------------

def test_the_runtime_target_map_matches_the_provisioning_schemas() -> None:
    """One vocabulary, asserted rather than duplicated on trust.

    Cedar action ids embed the target name, so a runtime map that drifts from the
    provisioning schemas would point policies at a target that no longer
    publishes the tool. The backend cannot import the deploy module at runtime,
    so the copy is pinned here instead.
    """
    if str(DEPLOY) not in sys.path:
        sys.path.insert(0, str(DEPLOY))
    from gateway_tool_schemas import TOOL_SCHEMAS

    from services.agentcore_gateway import GATEWAY_TARGET_FOR_TOOL

    expected = {
        tool["name"]: config["target_name"]
        for config in TOOL_SCHEMAS.values()
        for tool in config["tools"]
    }
    assert GATEWAY_TARGET_FOR_TOOL == expected


def test_every_published_tool_has_a_target() -> None:
    from services.agentcore_gateway import GATEWAY_TARGET_FOR_TOOL, GATEWAY_TOOL_TIERS

    missing = sorted(set(GATEWAY_TOOL_TIERS) - set(GATEWAY_TARGET_FOR_TOOL))
    assert not missing, f"published tools with no Gateway target: {missing}"
    assert set(GATEWAY_TARGET_FOR_TOOL.values()) == {"pellier-store-tools"}


def test_the_gateway_vocabulary_is_exactly_the_nine_published_tools() -> None:
    """One target, nine tools: the vocabulary participants and Cedar both see."""
    if str(DEPLOY) not in sys.path:
        sys.path.insert(0, str(DEPLOY))
    from gateway_tool_schemas import TOOL_SCHEMAS

    from services.agentcore_gateway import GATEWAY_TARGET_FOR_TOOL, mutation_tool_names

    published = {
        tool["name"]
        for config in TOOL_SCHEMAS.values()
        for tool in config["tools"]
    }
    assert published == {
        "search_products", "browse_department", "compare_products", "check_stock",
        "get_orders", "get_return_policy", "get_tickets", "give_store_credit",
        "ask_a_person",
    }
    assert set(GATEWAY_TARGET_FOR_TOOL.values()) == {"pellier-store-tools"}
    assert mutation_tool_names() == ["give_store_credit"]


def test_the_cedar_action_id_is_target_qualified() -> None:
    assert (
        ge.gateway_action_id("give_store_credit")
        == "pellier-store-tools___give_store_credit"
    )
    with pytest.raises(ge.ExecutionError):
        ge.gateway_action_id("not_a_tool")


# ---------------------------------------------------------------------------
# Confirmation integrity
# ---------------------------------------------------------------------------

def test_a_pending_review_cannot_be_executed() -> None:
    with pytest.raises(ge.ExecutionError) as exc:
        ge.verify_confirmation(approved_review(status="pending"))
    assert exc.value.code == "review_not_confirmed"


def test_a_declined_review_cannot_be_executed() -> None:
    with pytest.raises(ge.ExecutionError) as exc:
        ge.verify_confirmation(approved_review(status="rejected"))
    assert exc.value.code == "review_declined"


def test_parameters_edited_after_confirmation_are_refused() -> None:
    """The fingerprint is what makes "the operator approved this" checkable."""
    tampered = approved_review()
    tampered["args"] = {**CREDIT_ARGS, "reason": "changed_mind"}
    with pytest.raises(ge.ExecutionError) as exc:
        ge.verify_confirmation(tampered)
    assert exc.value.code == "confirmation_invalid"


def test_verification_returns_the_persisted_parameters() -> None:
    """Execution parameters come from the row, never from a caller."""
    assert ge.verify_confirmation(approved_review()) == CREDIT_ARGS


@pytest.mark.asyncio
async def test_a_tampered_review_never_reaches_the_database() -> None:
    tampered = approved_review()
    tampered["args"] = {**CREDIT_ARGS, "amount_cents": 999999}
    db = FakeDb()
    with pytest.raises(ge.ExecutionError):
        await ge.execute_confirmed_review(
            db, tampered, operator_sub=OPERATOR_SUBJECT
        )
    assert FakeCredit.calls == [], "a write ran despite an invalid confirmation"
    assert db.statements == [], "the database was touched before verification"


# ---------------------------------------------------------------------------
# The two principals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_customer_subject_is_resolved_server_side() -> None:
    """A caller that could name its own RLS principal could read any client."""
    db = FakeDb(customer_subject=THEO_SUBJECT)
    outcome = await ge.execute_confirmed_review(
        db, approved_review(), operator_sub=OPERATOR_SUBJECT
    )
    assert any("FROM pellier.principal_customers" in s for s in db.statements), (
        "the subject was not resolved from the authorization mapping table"
    )
    assert outcome.customer_subject == THEO_SUBJECT
    assert outcome.operator_sub == OPERATOR_SUBJECT


@pytest.mark.asyncio
async def test_a_credit_attributes_the_operator_as_the_actor() -> None:
    """Attribution is the operator; the customer's subject is a different fact."""
    await ge.execute_confirmed_review(
        FakeDb(customer_subject=THEO_SUBJECT), approved_review(),
        operator_sub=OPERATOR_SUBJECT,
    )
    assert len(FakeCredit.calls) == 1
    call = FakeCredit.calls[0]
    assert call["issued_by"] == OPERATOR_SUBJECT
    assert call["customer_id"] == "CUST-THEO"
    assert call["amount_cents"] == 2500
    assert call["reason"] == "courtesy"
    assert THEO_SUBJECT not in call["params"], "the customer subject reached the write"


@pytest.mark.asyncio
async def test_the_write_carries_the_confirmed_request_hash() -> None:
    """The database compares the hash the human confirmed, not one the caller built."""
    await ge.execute_confirmed_review(
        FakeDb(), approved_review(), operator_sub=OPERATOR_SUBJECT
    )
    assert FakeCredit.calls[0]["request_hash"] == CREDIT_HASH


@pytest.mark.asyncio
async def test_only_the_credit_action_is_executable() -> None:
    """A confirmed row naming any other action is refused before a write."""
    other = approved_review(action="check_stock")
    with pytest.raises(ge.ExecutionError) as exc:
        await ge.execute_confirmed_review(
            FakeDb(), other, operator_sub=OPERATOR_SUBJECT
        )
    assert exc.value.code == "action_not_executable"
    assert FakeCredit.calls == []


# ---------------------------------------------------------------------------
# execution_turn_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_execution_turn_is_a_second_turn_not_the_shopper_turn() -> None:
    """Two logical turns, one lineage. Reusing one id would collapse it."""
    review = approved_review()
    outcome = await ge.execute_confirmed_review(
        FakeDb(), review, operator_sub=OPERATOR_SUBJECT
    )
    assert outcome.execution_turn_id != review["source_turn_id"]
    assert outcome.execution_turn_id.startswith("turn-")
    assert len(outcome.execution_turn_id) == 37


@pytest.mark.asyncio
async def test_a_retry_reuses_the_same_execution_turn() -> None:
    """One confirmed action is one attempt, however many times HTTP repeats."""
    db = FakeDb()
    first = await ge.execute_confirmed_review(
        db, approved_review(), operator_sub=OPERATOR_SUBJECT
    )
    second = await ge.execute_confirmed_review(
        db, approved_review(), operator_sub=OPERATOR_SUBJECT
    )
    assert first.execution_turn_id == second.execution_turn_id
    assert len(db.claimed_turns) == 1, "a second execution turn was minted"


@pytest.mark.asyncio
async def test_concurrent_executions_share_one_turn_and_one_write_key() -> None:
    """Two submissions of one confirmed action reach the write with one key.

    The turn is assigned once by the database's own guard, and the write key is
    derived from the review and its fingerprint rather than minted per request,
    so the second submission collapses onto the first inside
    ``pellier.write_operations`` instead of becoming a second business effect.
    """
    db = FakeDb()
    first, second = await asyncio.gather(
        ge.execute_confirmed_review(db, approved_review(), operator_sub=OPERATOR_SUBJECT),
        ge.execute_confirmed_review(db, approved_review(), operator_sub=OPERATOR_SUBJECT),
    )
    assert first.execution_turn_id == second.execution_turn_id
    assert first.idempotency_key == second.idempotency_key
    assert len(db.claimed_turns) == 1, "a second execution turn was minted"
    keys = {call["idempotency_key"] for call in FakeCredit.calls}
    assert keys == {first.idempotency_key}, keys


def test_the_database_refuses_an_execution_turn_on_an_unconfirmed_review() -> None:
    """Assign-once and confirmation-first are storage guarantees, not habits."""
    sql = (REPO / "scripts" / "migrations" / "021_governed_execution.sql").read_text()
    assert "approvals_execution_requires_confirmation_check" in sql
    assert "execution_turn_id IS NULL OR status = 'approved'" in sql
    assert "approvals_execution_turn_unique_idx" in sql
    assert "^turn-[0-9a-f]{32}$" in sql


def test_the_approval_status_was_not_widened_with_execution_outcomes() -> None:
    """The human axis stays the human axis.

    Adding `executed`, `policy_denied`, or `rls_denied` here would fold three
    independent controls into one column, which is the conflation this entire arc
    exists to dismantle.
    """
    for name in ("020_operator_review.sql", "021_governed_execution.sql"):
        sql = (REPO / "scripts" / "migrations" / name).read_text()
        for forbidden in ("'executed'", "'policy_denied'", "'rls_denied'", "'failed'"):
            assert forbidden not in sql, f"{name} widened approvals.status with {forbidden}"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_the_write_key_is_derived_from_the_confirmed_action() -> None:
    key = ge.execution_idempotency_key(12, CREDIT_HASH)
    assert key == ge.execution_idempotency_key(12, CREDIT_HASH)
    assert key.startswith("operator-review:12:")
    assert len(key) <= 128


def test_a_different_confirmed_action_gets_a_different_key() -> None:
    other = write_request_hash(
        "give_store_credit", customer_id="CUST-THEO", amount_cents=500, reason="courtesy"
    )
    assert ge.execution_idempotency_key(12, CREDIT_HASH) != ge.execution_idempotency_key(
        12, other
    )
    assert ge.execution_idempotency_key(12, CREDIT_HASH) != ge.execution_idempotency_key(
        13, CREDIT_HASH
    )


@pytest.mark.asyncio
async def test_two_executions_of_one_review_claim_the_same_write_key() -> None:
    db = FakeDb()
    await ge.execute_confirmed_review(
        db, approved_review(), operator_sub=OPERATOR_SUBJECT
    )
    await ge.execute_confirmed_review(
        db, approved_review(), operator_sub=OPERATOR_SUBJECT
    )
    keys = {call["idempotency_key"] for call in FakeCredit.calls}
    assert len(keys) == 1, f"a retry used a different write key: {keys}"


# ---------------------------------------------------------------------------
# Policy axis honesty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_in_process_rail_never_claims_a_policy_verdict() -> None:
    """No engine was asked, so no verdict may be reported."""
    outcome = await ge.execute_confirmed_review(
        FakeDb(), approved_review(), operator_sub=OPERATOR_SUBJECT
    )
    assert outcome.rail == ge.RAIL_IN_PROCESS
    assert outcome.policy == ge.POLICY_NOT_EVALUATED
    assert "not consulted" in outcome.notes["policy"]


def test_an_unreadable_engine_yields_no_verdict_rather_than_a_guess() -> None:
    policy, note = ge.resolve_permissive_policy_state(None)
    assert policy == ge.POLICY_EVALUATION_INCOMPLETE
    assert "no verdict is claimed" in note


def test_only_real_policy_denials_are_classified_as_denials() -> None:
    """A broken Gateway must never look like a governance proof."""
    assert ge.is_policy_denial("AuthorizeActionException: denied") is True
    assert ge.is_policy_denial("Tool call not allowed due to policy enforcement") is True
    assert ge.is_policy_denial("Policy evaluation denied due to forbid-1") is True
    for benign in (
        "AccessDeniedException: not authorized to invoke",
        "Unauthorized",
        "403 Forbidden",
        "ConnectTimeout",
        "Unknown tool",
    ):
        assert ge.is_policy_denial(benign) is False, benign


# ---------------------------------------------------------------------------
# Aurora and evidence axes
# ---------------------------------------------------------------------------

def test_only_an_rls_marker_counts_as_an_aurora_denial() -> None:
    denied, note = ge.classify_aurora(
        {"status": "policy_blocked", "denied_by": "database_row_level_security"}
    )
    assert denied == ge.AURORA_DENIED
    assert "Row-Level Security" in note

    # A business-rule refusal from the tool is not a database authorization fact.
    other, _ = ge.classify_aurora(
        {"status": "policy_blocked", "message": "reason not allowed"}
    )
    assert other == ge.AURORA_NOT_REACHED


def test_a_replay_is_permitted_but_says_so() -> None:
    state, note = ge.classify_aurora(
        {"status": "success", "idempotent_replay": True}
    )
    assert state == ge.AURORA_PERMITTED
    assert "replayed" in note


def test_an_idempotency_conflict_is_a_database_refusal_not_a_permitted_write() -> None:
    state, note = ge.classify_aurora(
        {
            "status": "idempotency_conflict",
            "message": "Idempotency key was already used with different arguments.",
        }
    )
    assert state == ge.AURORA_DENIED
    assert "different" in note
    assert (
        ge.classify_evidence_for(ge.POLICY_ALLOW, state, {})
        == ge.EVIDENCE_ATTEMPT_RECEIPT
    )


def test_a_database_raised_integrity_violation_is_an_aurora_denial() -> None:
    """SQLSTATE class 23 executed INSIDE Aurora; "not reached" would be false.

    The Gateway Lambda stringifies the RDS Data API error, which carries the
    SQLSTATE in prose. The axis once reported NOT_REACHED / NO_EXECUTION for a
    statement the database had executed and refused.
    """
    state, note = ge.classify_aurora(
        {
            "status": "error",
            "message": (
                "An error occurred (DatabaseErrorException) when calling the "
                "ExecuteStatement operation: ERROR: credit of 999999 cents exceeds "
                "the per-credit limit for customer CUST-THEO; SQLState: 23514"
            ),
        }
    )
    assert state == ge.AURORA_DENIED
    assert "23514" in note
    assert "exceeds the per-credit limit" in note, "the guard's own words must survive"
    assert (
        ge.classify_evidence_for(ge.POLICY_ALLOW, state, {"status": "error"})
        == ge.EVIDENCE_ATTEMPT_RECEIPT
    )


def test_an_explicit_sqlstate_field_needs_no_message_parsing() -> None:
    state, _ = ge.classify_aurora(
        {"status": "error", "sqlstate": "23514", "message": "guard refused"}
    )
    assert state == ge.AURORA_DENIED


def test_a_non_integrity_sqlstate_is_not_a_database_denial() -> None:
    """A syntax error or a cancelled query is a failure, not a governance proof."""
    for message in (
        "ERROR: syntax error at or near SELECT; SQLState: 42601",
        "ERROR: canceling statement due to user request; SQLState: 57014",
    ):
        state, _ = ge.classify_aurora({"status": "error", "message": message})
        assert state == ge.AURORA_NOT_REACHED, message


@pytest.mark.asyncio
async def test_an_in_process_integrity_violation_becomes_an_attempt_receipt() -> None:
    """The psycopg CheckViolation must not escape as a 500 that records nothing."""
    import psycopg

    FakeCredit.raises = psycopg.errors.CheckViolation(
        "credit of 999999 cents exceeds the per-credit limit for customer CUST-THEO"
    )
    outcome = await ge.execute_confirmed_review(
        FakeDb(), approved_review(), operator_sub=OPERATOR_SUBJECT
    )
    assert outcome.aurora == ge.AURORA_DENIED
    assert outcome.evidence == ge.EVIDENCE_ATTEMPT_RECEIPT
    assert outcome.result.get("sqlstate") == "23514"
    # And the policy axis is still honest about this rail.
    assert outcome.policy == ge.POLICY_NOT_EVALUATED


@pytest.mark.asyncio
async def test_a_non_integrity_database_error_still_raises_in_process() -> None:
    """A connection failure is an infrastructure problem, not an Aurora verdict."""
    import psycopg

    FakeCredit.raises = psycopg.OperationalError("server closed the connection")
    with pytest.raises(psycopg.OperationalError):
        await ge.execute_confirmed_review(
            FakeDb(), approved_review(), operator_sub=OPERATOR_SUBJECT
        )


@pytest.mark.asyncio
async def test_a_database_denial_envelope_reports_denied_and_an_attempt_receipt() -> None:
    FakeCredit.envelope = {
        "status": "policy_blocked",
        "message": "not authorized to act on CUST-THEO's credits",
        "denied_by": "database_row_level_security",
    }
    outcome = await ge.execute_confirmed_review(
        FakeDb(), approved_review(), operator_sub=OPERATOR_SUBJECT
    )
    assert outcome.aurora == ge.AURORA_DENIED
    assert outcome.evidence == ge.EVIDENCE_ATTEMPT_RECEIPT
    # And the human axis is untouched by a database outcome.
    assert outcome.as_payload()["assurance"]["human"] == "CONFIRMED"


# ---------------------------------------------------------------------------
# Runtime role and RLS binding, on the Gateway rail
# ---------------------------------------------------------------------------

def test_the_data_api_helper_binds_a_non_owner_role_and_the_principal() -> None:
    source = (DEPLOY / "common" / "dataapi.py").read_text()
    assert "def bind_runtime_principal(" in source
    assert "SET LOCAL ROLE" in source
    assert "set_config('pellier.principal_sub'" in source
    assert ", true)" in source, "the principal must be transaction-local"
    assert "_RUNTIME_ROLES" in source, "the role must be whitelisted, not interpolated"


def test_the_runtime_roles_are_non_owner_and_do_not_bypass_rls() -> None:
    sql = (REPO / "scripts" / "migrations" / "016_runtime_roles_rls.sql").read_text()
    assert "CREATE ROLE pellier_agent NOLOGIN NOINHERIT NOBYPASSRLS" in sql
    assert "CREATE ROLE pellier_query NOLOGIN NOINHERIT NOBYPASSRLS" in sql
    assert "ALTER TABLE pellier.orders  ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE pellier.returns ENABLE ROW LEVEL SECURITY" in sql


# ---------------------------------------------------------------------------
# Bypass closure
# ---------------------------------------------------------------------------

def test_legacy_action_handlers_are_not_kept_as_importable_backdoors() -> None:
    source = (BACKEND / "routes" / "operator.py").read_text()
    assert "async def resolve_return(" not in source
    assert "async def give_store_credit(" not in source
    assert "async def _require_confirmed_review(" not in source


def test_the_execute_route_accepts_no_action_parameters() -> None:
    """The browser supplies review identity only.

    Asserted on the model's declared fields. An earlier version scanned the class
    source and tripped on its own docstring, which names the parameters precisely
    in order to say they are not accepted.
    """
    from routes.operator import ReviewExecuteRequest

    fields = set(ReviewExecuteRequest.model_fields)
    assert fields == {"expectedActionHash"}, (
        f"the execute request accepts {sorted(fields)}; anything beyond a "
        "stale-view fingerprint would let a browser execute a different mutation "
        "than the one confirmed"
    )


def test_policy_mode_is_never_client_input() -> None:
    """Enforcement is control-plane state, not a request parameter."""
    source = (BACKEND / "routes" / "operator.py").read_text()
    for forbidden in ("LOG_ONLY", "ENFORCE", "policy_mode", "policyMode"):
        assert forbidden not in source, (
            f"{forbidden} appears in the operator routes; policy mode must come "
            "from the engine, never from a caller"
        )


# ---------------------------------------------------------------------------
# Migration-only compatibility alias (Phase B1)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The Gateway Lambda: one target, one audited mutation
# ---------------------------------------------------------------------------


def _load_store_tools_lambda():
    if str(DEPLOY) not in sys.path:
        sys.path.insert(0, str(DEPLOY))
    import pellier_store_tools

    return pellier_store_tools


def test_the_credit_call_writes_one_audit_row_under_the_canonical_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mutation audit goes through the independent writer, by tool name."""
    lam = _load_store_tools_lambda()
    audits: List[Dict[str, Any]] = []
    monkeypatch.setattr(lam, "write_tool_audit_independently", lambda **kw: audits.append(kw))
    monkeypatch.setitem(
        lam.TOOLS, "give_store_credit", lambda _args, _turn: {"status": "success", "credit_id": 1}
    )

    response = lam.lambda_handler(
        {"name": "give_store_credit", "arguments": dict(CREDIT_ARGS, idempotency_key="k-1")},
        None,
    )

    assert response["text"], "the MCP envelope must carry the result text"
    assert [a["tool"] for a in audits] == ["give_store_credit"]
    assert audits[0]["session_id"] == "gateway-CUST-THEO"


def test_an_unpublished_name_is_unknown_and_writes_no_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lam = _load_store_tools_lambda()
    audits: List[Dict[str, Any]] = []
    monkeypatch.setattr(lam, "write_tool_audit_independently", lambda **kw: audits.append(kw))

    response = lam.lambda_handler({"name": "not_a_tool", "arguments": {}}, None)

    assert response == {"error": "Unknown tool: not_a_tool"}
    assert audits == []


# ---------------------------------------------------------------------------
# Migration 047: evidence immutability
# ---------------------------------------------------------------------------

MIGRATIONS = REPO / "scripts" / "migrations"


def _sql_without_comments(path: Path) -> str:
    return "\n".join(line.split("--", 1)[0] for line in path.read_text().splitlines())


def test_migration_047_installs_append_only_and_fill_once_triggers() -> None:
    """Receipts are append-only; tool_audit and write_operations fill exactly once."""
    sql = _sql_without_comments(MIGRATIONS / "047_evidence_immutability.sql")
    assert "FUNCTION pellier.reject_evidence_mutation()" in sql
    assert "FUNCTION pellier.tool_audit_fill_once()" in sql
    assert "FUNCTION pellier.write_operations_fill_once()" in sql
    for trigger, table in (
        ("governed_receipts_append_only", "pellier.governed_receipts"),
        ("execution_receipts_append_only", "pellier.execution_receipts"),
        ("tool_audit_fill_once", "pellier.tool_audit"),
        ("write_operations_fill_once", "pellier.write_operations"),
    ):
        assert f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table}" in sql, trigger
    assert "ERRCODE = 'insufficient_privilege'" in sql


def test_migration_047_narrows_the_agent_update_grant_on_write_operations() -> None:
    """016 granted table-wide UPDATE; only the claim -> completed columns survive."""
    sql = _sql_without_comments(MIGRATIONS / "047_evidence_immutability.sql")
    assert "REVOKE UPDATE ON pellier.write_operations FROM pellier_agent" in sql
    assert "GRANT UPDATE (result, completed_at) ON pellier.write_operations TO pellier_agent" in sql


def test_migration_047_keeps_the_claim_release_path_of_023() -> None:
    """023 leaves a failed claim unfilled; deleting an UNFILLED claim must stay legal."""
    sql = _sql_without_comments(MIGRATIONS / "047_evidence_immutability.sql")
    body = sql[sql.index("write_operations_fill_once() RETURNS trigger"):]
    delete_branch = body[body.index("IF TG_OP = 'DELETE'"):body.index("RETURN OLD")]
    assert "OLD.completed_at IS NOT NULL" in delete_branch


def test_migration_047_leaves_no_probe_residue() -> None:
    """The self-probe cannot delete what it inserts, so it must roll itself back."""
    text = (MIGRATIONS / "047_evidence_immutability.sql").read_text()
    assert "SQLSTATE 'P0047'" in text
    assert "ERRCODE = 'P0047'" in text


# The scans above read the file. A trigger function whose body was reduced to
# RETURN NEW would satisfy every one of them, so one test has to put a statement
# to a server and watch it be refused. It runs against any database with the
# migration list applied.
#
#   PELLIER_MIGRATION_DSN=postgresql://... .venv/bin/python -m pytest \
#       tests/test_governed_execution.py -k immutability_is_enforced -v

_MIGRATION_DSN = os.environ.get("PELLIER_MIGRATION_DSN", "")


@pytest.mark.skipif(
    not _MIGRATION_DSN,
    reason="set PELLIER_MIGRATION_DSN to a database with the migrations applied",
)
def test_migration_047_immutability_is_enforced_by_the_server() -> None:
    """UPDATE and DELETE really are refused, and the one legal completion is not.

    Everything happens inside a transaction that is rolled back, because after
    047 nothing can remove what this test inserts.
    """
    import psycopg

    probe = "migration-047-live-probe"
    with psycopg.connect(_MIGRATION_DSN) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO pellier.governed_receipts"
                    " (session_id, principal_id, principal_label, tool, caller, decision)"
                    " VALUES (%s, 'probe', 'probe', 'probe', 'gateway', 'ALLOW')"
                    " RETURNING receipt_id",
                    (probe,),
                )
                receipt_id = cur.fetchone()[0]
            for statement, params in (
                ("UPDATE pellier.governed_receipts SET decision = 'DENY'"
                 " WHERE receipt_id = %s", (receipt_id,)),
                ("DELETE FROM pellier.governed_receipts WHERE receipt_id = %s",
                 (receipt_id,)),
            ):
                with conn.transaction(force_rollback=True):
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        with conn.cursor() as cur:
                            cur.execute(statement, params)

            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO pellier.tool_audit (session_id, tool, caller, args)"
                    " VALUES (%s, 'probe', 'probe', '{}'::jsonb) RETURNING audit_id",
                    (probe,),
                )
                audit_id = cur.fetchone()[0]
                # The one completion the writer is allowed.
                cur.execute(
                    "UPDATE pellier.tool_audit SET result = '{}'::jsonb, latency_ms = 1"
                    " WHERE audit_id = %s",
                    (audit_id,),
                )
            with conn.transaction(force_rollback=True):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE pellier.tool_audit SET latency_ms = 2"
                            " WHERE audit_id = %s",
                            (audit_id,),
                        )
        finally:
            conn.rollback()


# 047 makes three earlier probes illegal on any re-apply. Each was fixed in
# place rather than exempted: the reset and a second bootstrap both re-run the
# whole migration list, and a switch that suspends the triggers is the one thing
# append-only evidence must not ship with.


@pytest.mark.parametrize(
    "migration, code",
    [
        ("019_operator_desk.sql", "P0019"),
        ("023_idempotency_claims_release_on_failure.sql", "P0023"),
        ("025_execution_receipts.sql", "P0025"),
    ],
)
def test_the_earlier_probes_roll_back_instead_of_deleting_evidence(
    migration: str, code: str
) -> None:
    """A probe that deletes its own completed rows cannot run twice after 047."""
    text = (MIGRATIONS / migration).read_text()
    assert f"ERRCODE = '{code}'" in text, "the probe must end by raising its private code"
    assert f"SQLSTATE '{code}'" in text, "and catch it, so the subtransaction rolls back"
    sql = _sql_without_comments(MIGRATIONS / migration)
    for table in ("pellier.write_operations", "pellier.execution_receipts",
                  "pellier.approvals"):
        assert f"DELETE FROM {table}" not in sql, (
            f"{migration} still deletes {table}; 047 refuses that on a re-apply"
        )


def test_migration_025_proves_the_cascade_from_the_catalog() -> None:
    """The cascade cannot be exercised any more, so the declaration is asserted."""
    sql = _sql_without_comments(MIGRATIONS / "025_execution_receipts.sql")
    assert "confdeltype = 'c'" in sql
    assert "confrelid = 'pellier.approvals'::regclass" in sql


# ---------------------------------------------------------------------------
# Task 2.4: the engine read is an inference; decisions come from observations
# ---------------------------------------------------------------------------


class _FakeControlPlane:
    def __init__(self, gateway_mode: str = "LOG_ONLY") -> None:
        self.gateway_mode = gateway_mode

    def get_gateway(self, **_kw: Any) -> Dict[str, Any]:
        return {"policyEngineConfiguration": {"mode": self.gateway_mode}}

    def list_policies(self, **_kw: Any) -> Dict[str, Any]:
        return {"policies": [{"policyId": "pol-1"}, {"policyId": "pol-2"}]}

    def get_policy(self, *, policyEngineId: str, policyId: str) -> Dict[str, Any]:  # noqa: N803
        if policyId == "pol-1":
            return {
                "name": "credit_limit_forbid",
                "enforcementMode": "ACTIVE",
                "definition": {"cedar": {"statement": (
                    'forbid(principal, action == AgentCore::Action::'
                    '"pellier-store-tools___give_store_credit", resource)'
                    ' unless { context.amount_cents <= 5000 };'
                )}},
            }
        return {
            "name": "baseline_permit",
            "enforcementMode": "ACTIVE",
            "definition": {"cedar": {"statement": "permit(principal, action, resource);"}},
        }


@pytest.mark.asyncio
async def test_engine_state_for_action_is_labeled_inferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import managed_policy as mp

    _governed(monkeypatch)
    from config import settings

    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_ARN", "arn:aws:x:y:z:gateway/gw-1",
                        raising=False)
    import boto3

    monkeypatch.setattr(boto3, "client", lambda *_a, **_k: _FakeControlPlane("LOG_ONLY"))

    state = await mp.engine_state_for_action(
        "pellier-store-tools___give_store_credit"
    )
    assert state["inferred"] is True
    assert state["matching"] == ["credit_limit_forbid"]
    assert state["gateway_mode"] == "LOG_ONLY"
    assert state["policies"]["credit_limit_forbid"] == ("forbid", "ACTIVE")
    assert state["policy_ids"]["credit_limit_forbid"] == "pol-1"
    assert state["policy_engine_id"] == "engine-1"
    assert "WOULD_DENY" not in str(state)


def test_the_mode_precondition_applies_only_to_the_governed_managed_rail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import settings

    gateway = ge.RailSelection(rail=ge.RAIL_GATEWAY)
    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "governed", raising=False)
    assert ge.require_enforced_engine(gateway, ENFORCED) is gateway
    assert ge.require_enforced_engine(gateway, None).rail == ge.RAIL_REFUSED
    refused = ge.RailSelection(rail=ge.RAIL_REFUSED, missing=("access_token",))
    assert ge.require_enforced_engine(refused, None) is refused
    assert ge.require_enforced_engine(ge.RailSelection(rail=ge.RAIL_IN_PROCESS), None).rail == ge.RAIL_IN_PROCESS
    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "builders", raising=False)
    assert ge.require_enforced_engine(gateway, None) is gateway


# ---------------------------------------------------------------------------
# Task 2.5: fail closed for governed writes
# ---------------------------------------------------------------------------


def test_select_rail_refuses_in_governed_format_without_a_gateway_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _governed(monkeypatch, gateway_url="")
    selection = ge.select_rail("jwt")
    assert selection.rail == ge.RAIL_REFUSED
    assert selection.missing == ("AGENTCORE_GATEWAY_URL",)
    assert "AGENTCORE_GATEWAY_URL" in selection.refusal_reason


def test_select_rail_names_every_missing_item(monkeypatch: pytest.MonkeyPatch) -> None:
    _governed(monkeypatch, gateway_url="", engine_id="")
    selection = ge.select_rail(None)
    assert selection.rail == ge.RAIL_REFUSED
    assert selection.missing == (
        "AGENTCORE_GATEWAY_URL", "access_token", "AGENTCORE_POLICY_ENGINE_ID",
    )


def test_select_rail_refuses_when_only_the_access_token_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Gateway with no caller JWT authorizes nobody. Refuse, do not execute."""
    _governed(monkeypatch)
    selection = ge.select_rail(None)
    assert selection.rail == ge.RAIL_REFUSED
    assert selection.missing == ("access_token",)
    assert "access_token" in selection.refusal_reason


def test_select_rail_refuses_when_only_the_policy_engine_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure this whole task exists to close.

    A Gateway URL and a token with no policy engine is the most dangerous of the
    three gaps: the write runs against Aurora and returns, and the only trace is
    one EVALUATION_INCOMPLETE row that reads as "we could not see the verdict"
    rather than "there was no verdict to see".
    """
    _governed(monkeypatch, engine_id="")
    selection = ge.select_rail("jwt")
    assert selection.rail == ge.RAIL_REFUSED
    assert selection.missing == ("AGENTCORE_POLICY_ENGINE_ID",)
    assert "AGENTCORE_POLICY_ENGINE_ID" in selection.refusal_reason


def test_select_rail_takes_the_gateway_when_everything_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _governed(monkeypatch)
    selection = ge.select_rail("jwt")
    assert selection == ge.RailSelection(rail=ge.RAIL_GATEWAY)
    assert selection.refusal_reason == ""


def test_select_rail_keeps_the_in_process_rail_for_the_builders_format() -> None:
    assert ge.select_rail(None).rail == ge.RAIL_IN_PROCESS
    assert ge.select_rail("jwt").rail == ge.RAIL_IN_PROCESS


@pytest.mark.asyncio
async def test_a_refusal_without_a_token_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    _governed(monkeypatch)
    with pytest.raises(ge.GovernedRailUnavailable) as caught:
        await ge.execute_confirmed_review(
            FakeDb(), approved_review(), operator_sub=OPERATOR_SUBJECT, access_token=None,
        )
    assert caught.value.missing == ("access_token",)


@pytest.mark.asyncio
async def test_the_builders_format_keeps_the_in_process_rail_and_the_receipt_says_so() -> None:
    outcome = await ge.execute_confirmed_review(
        FakeDb(), approved_review(), operator_sub=OPERATOR_SUBJECT
    )
    assert outcome.rail == ge.RAIL_IN_PROCESS
    assert outcome.policy == ge.POLICY_NOT_EVALUATED
    assert "builders" in outcome.notes["rail"]
    assert "in-process" in outcome.notes["rail"]
    assert len(FakeCredit.calls) == 1


def test_the_execute_route_maps_a_refusal_to_409(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes import operator as operator_module
    from services import operator_review as rv

    _governed(monkeypatch, gateway_url="")

    async def review_loaded(_db: Any, _review_id: int) -> Dict[str, Any]:
        return approved_review()

    monkeypatch.setattr(rv, "get_review", review_loaded)

    app = FastAPI()
    app.include_router(operator_module.router)
    app.dependency_overrides[operator_module.get_db_service] = lambda: FakeDb()
    app.dependency_overrides[operator_module.require_operator] = lambda: {
        "sub": OPERATOR_SUBJECT, "username": "operator", "groups": ("pellier-operators",),
        "access_token": "jwt",
    }
    response = TestClient(app).post("/api/operator/reviews/12/execute", json={})

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == {
        "error": "governed_rail_unavailable", "missing": ["AGENTCORE_GATEWAY_URL"],
    }
    assert FakeCredit.calls == []


# ---------------------------------------------------------------------------
# A metric reading is minute-granular, and the receipt says so
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Retry of the unchanged request on the in-process rail
# ---------------------------------------------------------------------------

class _IdempotentDb(FakeDb):
    """``apply_store_credit`` as Aurora behaves: one credit per key, then replay.

    Also records the ``tool_audit`` rows the in-process writer inserts and the
    approvals the guard reads, so both counts can be asserted.
    """

    def __init__(self) -> None:
        super().__init__()
        self.credits: Dict[str, Dict[str, Any]] = {}
        self.audit_rows: List[Dict[str, Any]] = []
        self.approved: List[str] = [CREDIT_HASH]

    async def fetch_one(self, query: str, *params: Any) -> Optional[Dict[str, Any]]:
        if "INSERT INTO pellier.tool_audit" in query:
            self.statements.append(query)
            import json as _json
            self.audit_rows.append({"session_id": params[0], "tool": params[1], "caller": params[2],
                                    "args": _json.loads(params[3]), "result": _json.loads(params[4])})
            return {"audit_id": len(self.audit_rows)}
        return await super().fetch_one(query, *params)

    async def fetch_all(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        if "FROM pellier.approvals" in query:
            self.statements.append(query)
            return [{"id": 12, "action_hash": value} for value in self.approved]
        if "apply_store_credit" not in query:
            return await super().fetch_all(query, *params)
        self.statements.append(query)
        key = params[0]
        if key in self.credits:
            return [{"result": {**self.credits[key], "idempotent_replay": True}}]
        self.credits[key] = {
            "status": "success", "credit_id": len(self.credits) + 1, "idempotent_replay": False,
        }
        return [{"result": dict(self.credits[key])}]


@pytest.mark.asyncio
async def test_a_retry_on_the_in_process_rail_applies_the_credit_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-process rail keeps one credit per key and one audit row.

    The Lab 4 retry contract, on this rail as on the Gateway's: the first
    execution writes one ``store_credits`` row and one ``tool_audit`` row; the
    unchanged retry replays the credit and writes no second audit row, because
    Aurora applied nothing.
    """
    db = _IdempotentDb()
    first = await ge.execute_confirmed_review(db, approved_review(), operator_sub=OPERATOR_SUBJECT)
    audits_after_first = [s for s in db.statements if "INSERT INTO pellier.tool_audit" in s]
    second = await ge.execute_confirmed_review(db, approved_review(), operator_sub=OPERATOR_SUBJECT)

    assert first.idempotency_key == second.idempotency_key
    assert len(db.credits) == 1, "the retry issued a second credit"
    assert first.result["idempotent_replay"] is False
    assert second.result["idempotent_replay"] is True
    assert second.aurora == ge.AURORA_PERMITTED and "replayed" in second.notes["aurora"]
    audits = [s for s in db.statements if "INSERT INTO pellier.tool_audit" in s]
    assert len(audits_after_first) == 1, "the executed credit must leave exactly one audit row"
    assert len(audits) == 1, "the idempotent replay must not write a second audit row"
    assert db.audit_rows[0]["args"]["idempotency_key"] == first.idempotency_key
    assert db.audit_rows[0]["caller"] == OPERATOR_SUBJECT
    assert "tool_audit row" in first.notes["audit"] and "replay" in second.notes["audit"]


@pytest.mark.asyncio
async def test_a_credit_nobody_approved_is_refused_in_process_and_still_audited() -> None:
    """The approval guard binds this rail too: no write, one attempt row."""
    db = _IdempotentDb()
    db.approved = []
    outcome = await ge.execute_confirmed_review(db, approved_review(), operator_sub=OPERATOR_SUBJECT)
    assert outcome.result["status"] == "approval_required"
    assert outcome.aurora == ge.AURORA_NOT_REACHED
    # The tool was entered and refused, and this rail left the attempt row, as
    # the Lambda does on the Gateway rail: the same artifact on both axes.
    assert outcome.evidence == ge.EVIDENCE_ATTEMPT_RECEIPT
    assert "no confirmed review" in outcome.notes["aurora"].lower() or "confirmed review" in outcome.notes["aurora"]
    assert len(db.credits) == 0
    assert len([s for s in db.statements if "INSERT INTO pellier.tool_audit" in s]) == 1


def test_an_approval_guard_refusal_is_not_an_aurora_verdict() -> None:
    refusal = {"status": "approval_mismatch", "denied_by": "approval_guard"}
    aurora, note = ge.classify_aurora(refusal)
    assert aurora == ge.AURORA_NOT_REACHED
    assert "fingerprints" in note
    assert ge.classify_evidence_for(ge.POLICY_NOT_EVALUATED, aurora, {}) == ge.EVIDENCE_NO_EXECUTION


@pytest.mark.parametrize("policy", [ge.POLICY_NOT_EVALUATED, ge.POLICY_ALLOW])
def test_a_guard_refusal_is_an_attempt_receipt_on_either_rail(policy: str) -> None:
    """In process (NOT_EVALUATED) and at the Gateway (ALLOW) the refusal is one axis.

    Both rails enter the tool and leave one attempt row for the refusal, so the
    evidence axis names that row whichever rail refused.
    """
    for status in ("approval_required", "approval_mismatch", "approval_key_mismatch"):
        refusal = {"status": status, "denied_by": "approval_guard"}
        aurora, _note = ge.classify_aurora(refusal)
        assert ge.classify_evidence_for(policy, aurora, refusal) == ge.EVIDENCE_ATTEMPT_RECEIPT


@pytest.mark.asyncio
async def test_the_in_process_rail_refuses_the_approved_credit_under_a_fresh_key() -> None:
    """The in-process rail's entry point binds the key too, not only execute's derivation.

    ``execute_confirmed_review`` always derives the review's own key, so the
    fresh key is passed to the rail directly: the shared tool refuses it, and
    nothing reaches ``apply_store_credit``.
    """
    db = _IdempotentDb()
    first = await ge.execute_confirmed_review(db, approved_review(), operator_sub=OPERATOR_SUBJECT)
    fresh = await ge._execute_in_process(
        db, tool="give_store_credit", args=CREDIT_ARGS,
        idempotency_key="operator-review:99:minted", operator_sub=OPERATOR_SUBJECT,
    )
    retry = await ge.execute_confirmed_review(db, approved_review(), operator_sub=OPERATOR_SUBJECT)

    assert first.result["idempotent_replay"] is False
    assert fresh["status"] == "approval_key_mismatch" and fresh["denied_by"] == "approval_guard"
    assert retry.result["idempotent_replay"] is True
    assert list(db.credits) == [first.idempotency_key], "one approval, one credit"


# ---------------------------------------------------------------------------
# The Gateway rail: the engine's declared mode decides what a returned call means
# ---------------------------------------------------------------------------


def test_a_returned_call_is_an_allow_only_under_enforce() -> None:
    policy, _note = ge.resolve_permissive_policy_state(ENFORCED)
    assert policy == ge.POLICY_ALLOW
    policy, note = ge.resolve_permissive_policy_state(ge.PolicyEngineState(gateway_mode="LOG_ONLY"))
    assert policy == ge.POLICY_EVALUATION_INCOMPLETE and "not a decision" in note
    policy, _note = ge.resolve_permissive_policy_state(None)
    assert policy == ge.POLICY_EVALUATION_INCOMPLETE


def test_the_engine_state_round_trips_the_control_plane_read() -> None:
    state = ge.PolicyEngineState.from_engine_read({
        "gateway_mode": "ENFORCE", "policies": {"p": ("forbid", "ACTIVE")},
        "matching": ["p"], "policy_ids": {"p": "id-1"}, "policy_engine_id": "engine-1",
    })
    assert state is not None and state.enforcement_is_on
    assert state.matching_forbids == ("p",) and state.policy_ids == {"p": "id-1"}
    assert ge.PolicyEngineState.from_engine_read(None) is None


@pytest.mark.asyncio
async def test_a_gateway_denial_is_a_deny_with_policy_proof_and_nothing_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _governed(monkeypatch)
    _gateway_returns(monkeypatch, ge.POLICY_DENY)
    outcome = await ge.execute_confirmed_review(
        FakeDb(), approved_review(), operator_sub=OPERATOR_SUBJECT, access_token="jwt",
        engine_state=ENFORCED,
    )
    assert outcome.rail == ge.RAIL_GATEWAY
    assert outcome.policy == ge.POLICY_DENY
    assert outcome.aurora == ge.AURORA_NOT_REACHED
    assert outcome.evidence == ge.EVIDENCE_POLICY_PROOF
    assert FakeCredit.calls == [], "a denied action never enters the tool"
    assert outcome.record["creditRows"] == 0 and outcome.record["auditRows"] == 0


@pytest.mark.asyncio
async def test_a_returned_gateway_call_under_enforce_is_an_allow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _governed(monkeypatch)
    calls = _gateway_returns(monkeypatch, ge.POLICY_ALLOW)
    outcome = await ge.execute_confirmed_review(
        FakeDb(), approved_review(), operator_sub=OPERATOR_SUBJECT, access_token="jwt",
        engine_state=ENFORCED,
    )
    assert outcome.policy == ge.POLICY_ALLOW
    assert outcome.aurora == ge.AURORA_PERMITTED
    assert outcome.evidence == ge.EVIDENCE_RECEIPTED
    assert calls[0]["idempotency_key"] == outcome.idempotency_key
    assert calls[0]["args"] == CREDIT_ARGS, "the Gateway is called with the confirmed arguments and nothing else"


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", [ge.PolicyEngineState(gateway_mode="LOG_ONLY"), None])
async def test_a_non_enforcing_or_unreadable_engine_refuses_before_the_call(
    monkeypatch: pytest.MonkeyPatch, engine,
) -> None:
    _governed(monkeypatch)
    calls = _gateway_returns(monkeypatch, ge.POLICY_ALLOW)
    with pytest.raises(ge.GovernedRailUnavailable) as caught:
        await ge.execute_confirmed_review(
            FakeDb(), approved_review(), operator_sub=OPERATOR_SUBJECT, access_token="jwt",
            engine_state=engine,
        )
    assert "policy_engine_mode=ENFORCE" in caught.value.missing[0]
    assert calls == [] and FakeCredit.calls == []


@pytest.mark.asyncio
async def test_a_refused_execution_records_a_refused_receipt_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _governed(monkeypatch, gateway_url="")
    recorded: List[Dict[str, Any]] = []

    async def record(_db: Any, outcome: Any, **_kwargs: Any) -> int:
        recorded.append(outcome.as_payload())
        return 7

    monkeypatch.setattr(ge, "record_receipt", record)
    with pytest.raises(ge.GovernedRailUnavailable) as caught:
        await ge.execute_confirmed_review(FakeDb(), approved_review(), operator_sub=OPERATOR_SUBJECT, access_token="jwt")
    assert caught.value.receipt_id == 7
    assert recorded[0]["rail"] == ge.RAIL_REFUSED
    assert recorded[0]["assurance"] == {
        "human": "CONFIRMED", "policy": ge.POLICY_EVALUATION_INCOMPLETE,
        "aurora": ge.AURORA_NOT_REACHED, "evidence": ge.EVIDENCE_NO_EXECUTION,
    }
    assert FakeCredit.calls == []


def test_the_evidence_axis_names_the_artifact_that_exists() -> None:
    assert ge.classify_evidence_for(ge.POLICY_DENY, ge.AURORA_NOT_REACHED, {}) == ge.EVIDENCE_POLICY_PROOF
    assert ge.classify_evidence_for(ge.POLICY_ALLOW, ge.AURORA_DENIED, {}) == ge.EVIDENCE_ATTEMPT_RECEIPT
    assert ge.classify_evidence_for(ge.POLICY_ALLOW, ge.AURORA_PERMITTED, {"status": "success"}) == ge.EVIDENCE_RECEIPTED
    assert ge.classify_evidence_for(ge.POLICY_NOT_EVALUATED, ge.AURORA_NOT_REACHED, {}) == ge.EVIDENCE_NO_EXECUTION
    assert ge.classify_evidence_for(ge.POLICY_ALLOW, ge.AURORA_OUTCOME_UNKNOWN, {}) == ge.EVIDENCE_ATTEMPT_RECEIPT


@pytest.mark.asyncio
async def test_the_record_is_read_from_the_two_tables_that_hold_the_evidence() -> None:
    class _Db:
        async def fetch_all(self, query: str, *params: Any) -> List[Dict[str, Any]]:
            if "FROM pellier.store_credits" in query:
                return [{"credit_id": 12, "customer_id": "CUST-JESSICA", "amount_cents": 10000,
                         "reason": "r", "issued_by": "sub", "created_at": None}]
            if "FROM pellier.tool_audit" in query:
                assert "give_store_credit" in query and "idempotency_key" in query
                return [{"audit_id": 4051, "caller": "nadia", "created_at": None}]
            return []

    record = await ge.evidence_for_key(_Db(), "operator-review:41:abc")
    assert record == {
        "idempotencyKey": "operator-review:41:abc", "creditRows": 1, "creditIds": [12],
        "amountCents": 10000, "auditRows": 1, "auditIds": [4051], "readable": True,
    }


@pytest.mark.asyncio
async def test_an_unreadable_evidence_table_never_reads_as_absence() -> None:
    class _Db:
        async def fetch_all(self, query: str, *params: Any) -> List[Dict[str, Any]]:
            raise RuntimeError("down")

    record = await ge.evidence_for_key(_Db(), "operator-review:41:abc")
    assert record["readable"] is False and record["creditRows"] == 0
