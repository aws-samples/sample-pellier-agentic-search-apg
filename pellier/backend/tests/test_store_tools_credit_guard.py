"""``give_store_credit`` writes only what a confirmed review fingerprints.

The guard lives in the shared implementation, so the Operator's execute path
and a staff token at the Gateway are bound the same way. A ``run`` stand-in
records every statement, so the tests can say what was NOT issued.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from services import store_tools
from services.store_tools import write_request_hash

JESSICA = {"customer_id": "CUST-JESSICA", "amount_cents": 10000, "reason": "Two items went back."}
JESSICA_HASH = write_request_hash("give_store_credit", **JESSICA)


class _Run:
    def __init__(self, approved: Optional[List[str]] = None) -> None:
        self.approved = list(approved or [])
        self.calls: List[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        self.calls.append((sql, tuple(params)))
        if "FROM pellier.approvals" in sql:
            return [{"action_hash": value} for value in self.approved]
        if "apply_store_credit" in sql:
            return [{"result": {"status": "success", "credit_id": 1, "idempotent_replay": False}}]
        return []

    def applied(self) -> bool:
        return any("apply_store_credit" in sql for sql, _ in self.calls)


def _credit(run: _Run, **overrides: Any) -> Dict[str, Any]:
    args = {**JESSICA, "idempotency_key": "operator-review:7:abc", "issued_by": "sub-nadia"}
    args.update(overrides)
    return store_tools.give_store_credit(run, **args)


def test_a_confirmed_review_for_these_exact_arguments_admits_the_write() -> None:
    run = _Run(approved=[JESSICA_HASH])
    result = _credit(run)
    assert result["status"] == "success"
    assert run.applied()
    select_sql, select_params = run.calls[0]
    assert "status = 'approved'" in select_sql and select_params == ("CUST-JESSICA",)


def test_no_approval_is_a_distinct_refusal_with_no_write() -> None:
    run = _Run(approved=[])
    result = _credit(run)
    assert result["status"] == store_tools.APPROVAL_REQUIRED
    assert result["denied_by"] == store_tools.APPROVAL_GUARD
    assert not run.applied()


def test_a_changed_amount_is_a_mismatch_with_no_write() -> None:
    run = _Run(approved=[JESSICA_HASH])
    result = _credit(run, amount_cents=10001)
    assert result["status"] == store_tools.APPROVAL_MISMATCH
    assert result["denied_by"] == store_tools.APPROVAL_GUARD
    assert not run.applied()


def test_a_changed_reason_or_customer_is_a_mismatch_too() -> None:
    for change in ({"reason": "Something else."}, {"customer_id": "CUST-THEO"}):
        run = _Run(approved=[JESSICA_HASH])
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
    run = _Run(approved=[JESSICA_HASH])
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
    run = _Run(approved=[write_request_hash("give_store_credit", **over)])
    result = _credit(run, amount_cents=50001)
    assert run.applied()
    assert result["status"] == "success"  # the stand-in applies; Aurora would refuse
