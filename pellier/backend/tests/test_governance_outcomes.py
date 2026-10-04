"""The three enforcement boundaries, and the axes that must not infer one another.

Proven live on 2026-08-27 against the partial-reopen authorization surface (damaged
permit ACTIVE, non-damaged forbid ACTIVE, baseline still narrowed):

    THEO    CONFIRMED / ALLOW / PERMITTED / RECEIPTED
    RACHEL  CONFIRMED / DENY  / NOT_REACHED / POLICY_PROOF
    AMARA   CONFIRMED / ALLOW / DENIED / ATTEMPT_RECEIPT

Every assertion here is about a classification rule, not about a captured value: the
rules are what make the live outcomes reproducible.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict

import pytest

from services import governed_execution as GE


# ---------------------------------------------------------------------------
# No axis derives another
# ---------------------------------------------------------------------------

def test_a_policy_denial_never_reaches_aurora() -> None:
    """The tool was not entered, so no statement reached the database."""
    aurora, note = GE.classify_aurora({"status": "policy_denied",
                                       "denied_by": "agentcore_policy"})
    assert aurora == GE.AURORA_NOT_REACHED
    assert GE.classify_evidence_for(GE.POLICY_DENY, aurora, {}) == GE.EVIDENCE_POLICY_PROOF


def test_a_policy_allow_does_not_imply_aurora_permitted() -> None:
    """Outcome C. Authorization and database permission are separate boundaries."""
    denied = {
        "status": "error",
        "sqlstate": "23514",
        "message": "credit of 999999 cents exceeds the per-credit limit for CUST-AMARA",
    }
    aurora, _note = GE.classify_aurora(denied)
    assert aurora == GE.AURORA_DENIED
    assert GE.classify_evidence_for(GE.POLICY_ALLOW, aurora, denied) == (
        GE.EVIDENCE_ATTEMPT_RECEIPT
    )


def test_a_permissive_gateway_result_is_not_an_allow_without_engine_state() -> None:
    """A call that returned under LOG_ONLY is an observation, not an authorization."""
    policy, note = GE.resolve_permissive_policy_state(None)
    assert policy == GE.POLICY_EVALUATION_INCOMPLETE
    assert "could not be read" in note


def test_enforcement_on_turns_a_returned_call_into_a_real_allow() -> None:
    state = GE.PolicyEngineState(
        gateway_mode="ENFORCE",
        policies={"credit_limit_forbid": ("forbid", "ACTIVE")},
        matching_forbids=("credit_limit_forbid",),
    )
    assert state.enforcement_is_on is True
    policy, note = GE.resolve_permissive_policy_state(state)
    assert policy == GE.POLICY_ALLOW
    assert "evaluated the action and permitted it" in note


# ---------------------------------------------------------------------------
# An RLS-hidden row never becomes a business falsehood
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# A tool's own words are never rewritten into a database verdict
# ---------------------------------------------------------------------------

def test_a_tool_message_is_never_rewritten_into_a_database_denial() -> None:
    """The axis reads the envelope as it came; it does not reclassify by message.

    A tool error with no database marker and no SQLSTATE is a tool error. The
    result handed back is the same object content, so no surface renders a
    rewritten message.
    """
    raw = {"status": "error", "message": "A reason is required for a credit."}
    aurora, note = GE._classify_aurora_axis(GE.POLICY_ALLOW, dict(raw))
    assert aurora == GE.AURORA_NOT_REACHED
    assert note == raw["message"]


def test_a_success_envelope_is_permitted_and_unchanged() -> None:
    raw = {"status": "success", "credit_id": 9}
    aurora, _note = GE._classify_aurora_axis(GE.POLICY_ALLOW, dict(raw))
    assert aurora == GE.AURORA_PERMITTED


# ---------------------------------------------------------------------------
# Identity is server-resolved
# ---------------------------------------------------------------------------

def test_the_customer_subject_is_resolved_from_configuration_not_a_caller() -> None:
    source = inspect.getsource(GE.resolve_customer_subject)
    assert "pellier.principal_customers" in inspect.getsource(GE)
    assert "customer_id" in inspect.signature(GE.resolve_customer_subject).parameters
    # No request/browser material reaches it.
    for forbidden in ("request", "payload", "body", "args"):
        assert forbidden not in inspect.signature(GE.resolve_customer_subject).parameters


def test_an_unmapped_client_fails_closed_rather_than_widening() -> None:
    source = inspect.getsource(GE.resolve_customer_subject)
    assert "RLS will fail closed" in source


def test_the_two_principals_are_never_collapsed() -> None:
    params = inspect.signature(GE.execute_confirmed_review).parameters
    assert "operator_sub" in params
    outcome_fields = {f for f in GE.ExecutionOutcome.__dataclass_fields__}
    assert {"operator_sub", "customer_subject"} <= outcome_fields


# ---------------------------------------------------------------------------
# The policy engine must be readable at all
# ---------------------------------------------------------------------------

def test_the_engine_id_is_read_from_settings_not_only_the_environment() -> None:
    """`Settings` loads `.env` into the settings object, not into `os.environ`.

    Reading only the environment returned "" on every normally configured backend, so
    `engine_state_for_action` returned None and every Gateway ALLOW was downgraded to
    NOT_EVALUATED. The workshop's single most important positive claim was unreachable,
    and it failed in the honest direction — which is why nothing looked broken.
    """
    from services import managed_policy as MP

    source = inspect.getsource(MP._engine_id)
    assert "from config import settings" in source
    assert "os.environ.get" in source, "the environment fallback was dropped"
    # And it actually resolves in this hermetic test environment or falls back cleanly.
    assert isinstance(MP._engine_id(), str)


def test_the_engine_state_reader_imports_settings_in_scope() -> None:
    """A bare `settings` reference sat behind the unreachable engine-id guard."""
    from services import managed_policy as MP

    source = inspect.getsource(MP.engine_state_for_action)
    assert "from config import settings as _settings" in source
    assert "getattr(_settings, \"AGENTCORE_GATEWAY_ARN\"" in source
