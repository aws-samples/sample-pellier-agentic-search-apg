"""``give_store_credit`` hands one exact write to ``pellier.apply_store_credit``.

The approval and order rules live in that database function, so the Operator's
execute path, a staff token at the Gateway and a direct SQL caller are bound
the same way. ``test_operator_credit_postgres.py`` proves the rules on real
PostgreSQL. This file proves the thin shared wrapper: it validates its input
before any statement, passes exactly the approved terms and key, and reports
the function's answer unchanged.
"""
from __future__ import annotations

from typing import Any, Dict, List

from services import store_tools
from services.store_tools import execution_idempotency_key, write_request_hash

JESSICA = {"customer_id": "CUST-JESSICA", "amount_cents": 10000, "reason": "Two items went back."}
JESSICA_HASH = write_request_hash("give_store_credit", **JESSICA)
REVIEW_ID = 7
JESSICA_KEY = execution_idempotency_key(REVIEW_ID, JESSICA_HASH)


class _Run:
    """Answers ``apply_store_credit`` with a fixed result and records every statement."""

    def __init__(self, result: Dict[str, Any] | None = None) -> None:
        self.result = result or {"status": "success", "credit_id": 1, "idempotent_replay": False}
        self.calls: List[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        self.calls.append((sql, tuple(params)))
        return [{"result": dict(self.result)}]


def _credit(run: _Run, **overrides: Any) -> Dict[str, Any]:
    args = {**JESSICA, "idempotency_key": JESSICA_KEY, "issued_by": "sub-nadia"}
    args.update(overrides)
    return store_tools.give_store_credit(run, **args)


def test_one_statement_carries_exactly_the_terms_and_the_reviews_key() -> None:
    run = _Run()
    assert _credit(run)["status"] == "success"
    (sql, params), = run.calls
    assert "pellier.apply_store_credit(" in sql
    # Cast at the call site: the Data API sends integers as bigint.
    assert "%s::integer" in sql
    assert params == (JESSICA_KEY, "CUST-JESSICA", 10000, "Two items went back.", "sub-nadia")
    assert JESSICA_KEY == f"operator-review:7:{JESSICA_HASH[:32]}"


def test_input_validation_runs_before_any_statement() -> None:
    run = _Run()
    assert _credit(run, idempotency_key="")["status"] == "error"
    assert _credit(run, amount_cents="ten")["status"] == "error"
    assert _credit(run, reason="  ")["status"] == "error"
    assert run.calls == []


def test_the_databases_refusals_reach_the_caller_unchanged() -> None:
    """No approval, other terms, another key and an already-credited order stay distinct."""
    for status, guard in (
        (store_tools.APPROVAL_REQUIRED, store_tools.APPROVAL_GUARD),
        (store_tools.APPROVAL_MISMATCH, store_tools.APPROVAL_GUARD),
        (store_tools.APPROVAL_KEY_MISMATCH, store_tools.APPROVAL_GUARD),
        (store_tools.NOT_CREDITABLE, store_tools.ORDER_GUARD),
    ):
        result = _credit(_Run({"status": status, "denied_by": guard, "message": "m"}))
        assert result == {"status": status, "denied_by": guard, "message": "m"}
    assert store_tools.WRITE_GUARDS == {store_tools.APPROVAL_GUARD, store_tools.ORDER_GUARD}


def test_the_wrapper_never_clamps_an_amount() -> None:
    """$100.01 and $500.01 both reach the database; Cedar and the CHECK decide them."""
    for cents in (10001, 50001):
        run = _Run()
        _credit(run, amount_cents=cents)
        assert run.calls[0][1][2] == cents


def test_the_key_is_the_reviews_own_and_is_derived_in_one_place() -> None:
    """The Operator's execute path imports the derivation the database recomputes."""
    from services import governed_execution

    assert governed_execution.execution_idempotency_key is execution_idempotency_key
    assert execution_idempotency_key(41, "f" * 64) == "operator-review:41:" + "f" * 32
