"""``give_store_credit`` writes only what a confirmed review fingerprints, once.

The guard lives in the shared implementation, so the Operator's execute path
and a staff token at the Gateway are bound the same way: the approved row's
fingerprint must match the request, and the request's key must be the one key
that approval admits, ``operator-review:{review id}:{fingerprint[:32]}``. A
``run`` stand-in records every statement, so the tests can say what was NOT
issued.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from services import store_tools
from services.store_tools import execution_idempotency_key, write_request_hash

JESSICA = {"customer_id": "CUST-JESSICA", "amount_cents": 10000, "reason": "Two items went back."}
JESSICA_HASH = write_request_hash("give_store_credit", **JESSICA)
REVIEW_ID = 7
JESSICA_KEY = execution_idempotency_key(REVIEW_ID, JESSICA_HASH)


class _Run:
    """The approved reviews, as ``(review id, fingerprint)``, and every statement."""

    def __init__(self, approved: Optional[List[Tuple[int, str]]] = None) -> None:
        self.approved = list(approved or [])
        self.calls: List[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        self.calls.append((sql, tuple(params)))
        if "FROM pellier.approvals" in sql:
            return [{"id": review_id, "action_hash": value} for review_id, value in self.approved]
        if "apply_store_credit" in sql:
            return [{"result": {"status": "success", "credit_id": 1, "idempotent_replay": False}}]
        return []

    def applied(self) -> bool:
        return any("apply_store_credit" in sql for sql, _ in self.calls)


def _credit(run: _Run, **overrides: Any) -> Dict[str, Any]:
    args = {**JESSICA, "idempotency_key": JESSICA_KEY, "issued_by": "sub-nadia"}
    args.update(overrides)
    return store_tools.give_store_credit(run, **args)


def test_a_confirmed_review_for_these_exact_arguments_admits_the_write() -> None:
    run = _Run(approved=[(REVIEW_ID, JESSICA_HASH)])
    result = _credit(run)
    assert result["status"] == "success"
    assert run.applied()
    select_sql, select_params = run.calls[0]
    assert "status = 'approved'" in select_sql and select_params == ("CUST-JESSICA",)
    credit_params = run.calls[1][1]
    assert credit_params[0] == JESSICA_KEY == f"operator-review:7:{JESSICA_HASH[:32]}"


def test_no_approval_is_a_distinct_refusal_with_no_write() -> None:
    run = _Run(approved=[])
    result = _credit(run)
    assert result["status"] == store_tools.APPROVAL_REQUIRED
    assert result["denied_by"] == store_tools.APPROVAL_GUARD
    assert not run.applied()


def test_a_changed_amount_is_a_mismatch_with_no_write() -> None:
    run = _Run(approved=[(REVIEW_ID, JESSICA_HASH)])
    result = _credit(run, amount_cents=10001)
    assert result["status"] == store_tools.APPROVAL_MISMATCH
    assert result["denied_by"] == store_tools.APPROVAL_GUARD
    assert not run.applied()


def test_a_changed_reason_or_customer_is_a_mismatch_too() -> None:
    for change in ({"reason": "Something else."}, {"customer_id": "CUST-THEO"}):
        run = _Run(approved=[(REVIEW_ID, JESSICA_HASH)])
        result = _credit(run, **change)
        assert result["status"] in (store_tools.APPROVAL_MISMATCH, store_tools.APPROVAL_REQUIRED), change
        assert not run.applied(), change


def test_a_declined_review_admits_nothing() -> None:
    """Only ``approved`` rows reach the guard; the SELECT says so."""
    run = _Run(approved=[])
    _credit(run)
    select_sql, _ = run.calls[0]
    assert "status = 'approved'" in select_sql
    assert "pending" not in select_sql and "rejected" not in select_sql


def test_input_validation_still_runs_before_the_guard() -> None:
    run = _Run(approved=[(REVIEW_ID, JESSICA_HASH)])
    assert _credit(run, idempotency_key="")["status"] == "error"
    assert _credit(run, amount_cents="ten")["status"] == "error"
    assert _credit(run, reason="  ")["status"] == "error"
    assert run.calls == []


def test_the_safety_ceiling_stays_with_the_database_not_the_guard() -> None:
    """A $500.01 request with a matching approval reaches ``apply_store_credit``.

    The $500 ceiling is the function's and the CHECK constraint's job; the guard
    never clamps or caps, so a participant's Cedar rule is what decides $100.01.
    """
    over = {**JESSICA, "amount_cents": 50001}
    over_hash = write_request_hash("give_store_credit", **over)
    run = _Run(approved=[(REVIEW_ID, over_hash)])
    over_key = execution_idempotency_key(REVIEW_ID, over_hash)
    result = _credit(run, amount_cents=50001, idempotency_key=over_key)
    assert run.applied()
    assert result["status"] == "success"  # the stand-in applies; Aurora would refuse


# ---------------------------------------------------------------------------
# One approval admits one key, so one credit
# ---------------------------------------------------------------------------


def test_the_approved_arguments_under_a_fresh_key_are_refused_with_no_write() -> None:
    """A staff caller who copies the approved terms and mints a new key gets nothing.

    Without the key binding, ``apply_store_credit`` would treat a fresh key as
    a new write and credit the same approval again, as many times as a caller
    could mint keys.
    """
    for key in ("credit-2", f"operator-review:8:{JESSICA_HASH[:32]}", JESSICA_KEY + "-again"):
        run = _Run(approved=[(REVIEW_ID, JESSICA_HASH)])
        result = _credit(run, idempotency_key=key)
        assert result["status"] == store_tools.APPROVAL_KEY_MISMATCH, key
        assert result["denied_by"] == store_tools.APPROVAL_GUARD, key
        assert not run.applied(), key


def test_the_refusals_stay_distinct() -> None:
    """No approval, other terms and another key are three different answers."""
    assert _credit(_Run(approved=[]))["status"] == store_tools.APPROVAL_REQUIRED
    assert _credit(_Run(approved=[(REVIEW_ID, JESSICA_HASH)]), amount_cents=9999)["status"] == (
        store_tools.APPROVAL_MISMATCH
    )
    assert _credit(_Run(approved=[(REVIEW_ID, JESSICA_HASH)]), idempotency_key="k")["status"] == (
        store_tools.APPROVAL_KEY_MISMATCH
    )


def test_the_key_is_the_reviews_own_and_is_derived_in_one_place() -> None:
    """The Operator's execute path imports the derivation the guard recomputes."""
    from services import governed_execution

    assert governed_execution.execution_idempotency_key is execution_idempotency_key
    assert execution_idempotency_key(41, "f" * 64) == "operator-review:41:" + "f" * 32
