"""Evidence checks for the one governed Gateway mutation, `give_store_credit`."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY = REPO_ROOT / "scripts" / "deploy"

if str(DEPLOY) not in sys.path:
    sys.path.insert(0, str(DEPLOY))


def _load_server(filename: str, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, DEPLOY / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def _dataapi() -> ModuleType:
    """Return the shared transport module, which owns the only Data API client.

    The seam moved here when the surface servers stopped each constructing a
    client of their own. Patching it in one place is the point: a mutation and
    its audit row must be issued through the same client, in the same
    transaction, or the atomicity these tests assert is not real.
    """
    import common.dataapi as dataapi

    return dataapi


class _DataApi:
    """A Data API stand-in that records every statement the Lambda issues.

    ``transactionId`` presence is the point here: the audit receipt only survives
    a failed business write if it is issued outside any transaction.
    """

    def __init__(
        self,
        result: dict[str, Any],
        *,
        fail_audit: bool = False,
        fail_protected: bool = False,
    ) -> None:
        self.result = result
        self.fail_audit = fail_audit
        self.fail_protected = fail_protected
        self.statements: list[dict[str, Any]] = []
        self.commits: list[dict[str, Any]] = []
        self.rollbacks: list[dict[str, Any]] = []

    def begin_transaction(self, **kwargs: Any) -> dict[str, str]:
        return {"transactionId": "tx-governed-1"}

    def execute_statement(self, **kwargs: Any) -> dict[str, Any]:
        self.statements.append(kwargs)
        sql = kwargs.get("sql", "")
        if "INSERT INTO pellier.tool_audit" in sql:
            if self.fail_audit:
                raise RuntimeError("audit insert failed")
            return {}
        if self.fail_protected and "apply_store_credit" in sql:
            # Stands in for an RLS refusal or a CHECK violation: the protected
            # statement is the one that fails, not the audit.
            raise RuntimeError("new row violates row-level security policy")
        if "SET LOCAL ROLE" in sql or "set_config(" in sql:
            return {}
        return {
            "columnMetadata": [{"name": "result"}],
            "records": [[{"stringValue": __import__("json").dumps(self.result)}]],
        }

    def commit_transaction(self, **kwargs: Any) -> None:
        self.commits.append(kwargs)

    def rollback_transaction(self, **kwargs: Any) -> None:
        self.rollbacks.append(kwargs)


def _credit_event(**overrides: Any) -> dict[str, Any]:
    arguments = {
        "customer_id": "CUST-THEO",
        "amount_cents": 2500,
        "reason": "damaged",
        "idempotency_key": "credit-1",
        "turn_id": "turn-" + ("a" * 32),
    }
    arguments.update(overrides)
    return {"name": "give_store_credit", "arguments": arguments}


def _audit_statements(client: _DataApi) -> list[dict[str, Any]]:
    return [
        call for call in client.statements
        if "INSERT INTO pellier.tool_audit" in call.get("sql", "")
    ]


def test_give_store_credit_casts_every_argument_at_the_call_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Data API integer arrives as bigint, and the function takes an integer.

    PostgreSQL does not narrow bigint to integer while resolving an overload, so
    the unqualified call raised `function pellier.apply_store_credit(text, text,
    text, bigint, text, unknown) does not exist` on the live Gateway (2026-09-10).
    Cedar allowed the call, the Lambda ran, and no credit row was written: the
    kind of failure that looks like a working boundary until someone counts rows.
    """
    module = _load_server("pellier_store_tools.py", "store_credit_casts")
    client = _DataApi({"status": "success", "credit_id": 7})
    monkeypatch.setattr(_dataapi(), "rds_client", client)

    module.lambda_handler(_credit_event(), None)

    credit_sql = next(
        call["sql"] for call in client.statements if "apply_store_credit" in call["sql"]
    )
    for cast in (
        ":p0::text",
        ":p1::text",
        ":p2::text",
        ":p3::integer",
        ":p4::text",
        ":p5::text",
    ):
        assert cast in credit_sql, credit_sql
    # An uncast bind is what broke it; none may come back.
    assert ":p3," not in credit_sql
    assert ":p5)" not in credit_sql


def test_the_credit_amount_travels_as_an_integer_and_the_issuer_is_not_wire_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_server("pellier_store_tools.py", "store_credit_params")
    client = _DataApi({"status": "success", "credit_id": 7})
    monkeypatch.setattr(_dataapi(), "rds_client", client)

    module.lambda_handler(_credit_event(issued_by="staff-spoof"), None)

    credit = next(c for c in client.statements if "apply_store_credit" in c["sql"])
    values = {p["name"]: p["value"] for p in credit["parameters"]}
    assert values["p0"] == {"stringValue": "credit-1"}
    assert values["p2"] == {"stringValue": "CUST-THEO"}
    assert values["p3"] == {"longValue": 2500}
    assert values["p5"] == {"isNull": True}, "an attribution the caller supplied is worse than none"


def test_a_credit_runs_as_one_statement_and_writes_its_receipt_outside_a_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_server("pellier_store_tools.py", "store_credit_receipt")
    client = _DataApi({"status": "success", "credit_id": 7})
    monkeypatch.setattr(_dataapi(), "rds_client", client)

    result = module.lambda_handler(_credit_event(), None)

    assert not result.get("isError")
    receipts = _audit_statements(client)
    assert len(receipts) == 1
    assert not receipts[0].get("transactionId")
    parameters = {p["name"]: p["value"] for p in receipts[0]["parameters"]}
    assert parameters["tool"] == {"stringValue": "give_store_credit"}
    assert parameters["session_id"] == {"stringValue": "gateway-CUST-THEO"}
    assert not client.commits and not client.rollbacks


def test_a_refused_credit_still_leaves_one_attempt_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An error result from the credit function is still an entered tool."""
    module = _load_server("pellier_store_tools.py", "store_credit_refused")
    client = _DataApi({"status": "error", "message": "idempotency key reused"})
    monkeypatch.setattr(_dataapi(), "rds_client", client)

    module.lambda_handler(_credit_event(), None)

    receipts = _audit_statements(client)
    assert len(receipts) == 1
    assert not receipts[0].get("transactionId")


def test_the_audit_receipt_survives_a_failed_business_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The load-bearing audit boundary.

    An action Cedar allowed, that entered the tool, and that Aurora then refused
    must still leave a trace, or "nothing happened" becomes indistinguishable from
    "nothing was attempted".
    """
    module = _load_server("pellier_store_tools.py", "store_credit_survive")
    client = _DataApi({"status": "success", "credit_id": 7}, fail_protected=True)
    monkeypatch.setattr(_dataapi(), "rds_client", client)

    result = module.lambda_handler(_credit_event(), None)

    assert result.get("isError") is True
    receipts = _audit_statements(client)
    assert len(receipts) == 1, (
        f"expected exactly one surviving attempt receipt, got {len(receipts)}"
    )
    assert not receipts[0].get("transactionId")


def test_a_failing_receipt_write_does_not_change_the_credit_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evidence must not break the write: the audit writer swallows its own failure."""
    module = _load_server("pellier_store_tools.py", "store_credit_audit_fails")
    client = _DataApi({"status": "success", "credit_id": 7}, fail_audit=True)
    monkeypatch.setattr(_dataapi(), "rds_client", client)

    result = module.lambda_handler(_credit_event(), None)

    assert not result.get("isError")
    assert '"credit_id": 7' in result["text"]
