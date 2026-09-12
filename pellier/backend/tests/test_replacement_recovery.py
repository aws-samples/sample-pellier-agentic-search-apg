"""Hermetic recovery boundary checks. Live Aurora concurrency is a separate gate."""
from __future__ import annotations

import importlib.util
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from services import operator_review as review
from services import replacement_recovery as recovery
from services.governed_execution import classify_aurora, classify_evidence_for

DEPLOY = Path(__file__).resolve().parents[3] / "scripts" / "deploy"
if str(DEPLOY) not in sys.path:
    sys.path.insert(0, str(DEPLOY))


def load(filename):
    spec = importlib.util.spec_from_file_location(f"recovery_test_{filename}", DEPLOY / f"{filename}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MATERIAL = dict(customer_id="CUST-THEO", order_id=7, product_id=37,
                quantity=1, reason="damaged", disposition="inspection_required")


@pytest.mark.asyncio
async def test_preparation_binds_exact_order_and_only_prepares_a_review(monkeypatch):
    db = Mock(fetch_one=AsyncMock(side_effect=[
        {"available": True},
        {"id": 7, "product_id": "37", "quantity": 2, "returned": 1, "name": "Wabi-Sabi Bowl"},
    ]))
    proposal = AsyncMock(return_value=91)
    monkeypatch.setattr(review, "propose_review", proposal)
    result = await recovery.prepare(db, customer_id="CUST-THEO", order_id=7,
                                    quantity=1, issue="  Reported chipped rim  ", operator_sub="staff")
    assert result == 91
    args = proposal.call_args.kwargs
    assert args["args"] == MATERIAL
    assert args["issue"] == "Reported chipped rim"
    assert args["requester_kind"] == "operator"
    assert "credit" not in args["recommendation"]
    assert db.fetch_one.call_args.args[1:] == (7, "CUST-THEO")


@pytest.mark.asyncio
@pytest.mark.parametrize("rows,quantity,code", [
    ([{"available": False}], 1, "replacement_not_installed"),
    ([{"available": True}, None], 1, "replacement_order_not_found"),
    ([{"available": True}, {"quantity": 1, "returned": 1}], 1, "replacement_quantity_exceeds_order"),
    ([{"available": True}, {"quantity": 2, "returned": 0}], 0, "replacement_quantity_exceeds_order"),
])
async def test_invalid_preparation_never_proposes(monkeypatch, rows, quantity, code):
    proposal = AsyncMock()
    monkeypatch.setattr(review, "propose_review", proposal)
    with pytest.raises(review.ReviewError, match=code):
        await recovery.prepare(Mock(fetch_one=AsyncMock(side_effect=rows)), customer_id="CUST-THEO",
                               order_id=7, quantity=quantity, issue="Damage", operator_sub="staff")
    proposal.assert_not_called()


@pytest.mark.asyncio
async def test_blank_report_is_rejected_before_database_access():
    db = Mock()
    with pytest.raises(review.ReviewError, match="replacement_issue_required"):
        await recovery.prepare(db, customer_id="CUST-THEO", order_id=7,
                               quantity=1, issue=" \n ", operator_sub="staff")
    assert not db.mock_calls


@pytest.mark.asyncio
async def test_exact_evidence_query_keeps_customer_and_operation_scope():
    db = Mock(fetch_one=AsyncMock(return_value={"available": True}), fetch_all=AsyncMock(return_value=[]))
    result = await recovery.read_replacements(db, "CUST-THEO", "2e8e1191-caa8-4f88-a9cc-186c9572276c")
    assert result == {"available": True, "replacements": []}
    assert db.fetch_all.call_args.args[1:] == (
        "CUST-THEO", "2e8e1191-caa8-4f88-a9cc-186c9572276c", "2e8e1191-caa8-4f88-a9cc-186c9572276c",
    )
    assert "task_token" not in db.fetch_all.call_args.args[0]


@pytest.fixture
def target(monkeypatch):
    module = load("pellier_experience_server")
    sequence = []
    monkeypatch.setattr(module, "_begin_transaction", lambda: "tx1")
    monkeypatch.setattr(module, "_bind_runtime_principal", lambda *a, **kw: sequence.append(("bind", a, kw)))
    monkeypatch.setattr(module, "_execute_in_transaction", lambda *a: (
        sequence.append(("sql", a)) or [{"result": {"status": "success", "return_id": 9}}]
    ))
    monkeypatch.setattr(module, "_commit_transaction", lambda tx: sequence.append(("commit", tx)))
    monkeypatch.setattr(module, "_rollback_transaction", lambda tx: sequence.append(("rollback", tx)))
    monkeypatch.setattr(module, "_write_tool_audit_independently", lambda **kw: sequence.append(("audit", kw)))
    return module, sequence


def test_target_binds_scope_and_approval_hash_before_committing(target):
    module, sequence = target
    result = module.replace_damaged_item(**MATERIAL, review_id=91, idempotency_key="review-key", customer_subject="theo-sub")
    assert result["status"] == "success"
    assert [event[0] for event in sequence] == ["bind", "sql", "commit", "audit"]
    assert sequence[0][2] == {"customer_subject": "theo-sub"}
    values = {p["name"]: next(iter(p["value"].values())) for p in sequence[1][1][2]}
    assert values["hash"] == review.action_fingerprint("replace_damaged_item", MATERIAL)
    assert values["review_id"] == 91


def test_lost_commit_response_remains_unknown_without_claiming_rollback(target, monkeypatch):
    module, sequence = target
    def lost(_tx):
        raise TimeoutError("response lost after commit")
    monkeypatch.setattr(module, "_commit_transaction", lost)
    result = module.replace_damaged_item(**MATERIAL, review_id=91, idempotency_key="same-review-key")
    assert result["status"] == "outcome_unknown"
    assert "rollback" not in [event[0] for event in sequence]
    assert sequence[-1][0] == "audit"
    assert classify_aurora(result)[0] == "OUTCOME_UNKNOWN"
    assert classify_evidence_for("ALLOW", "OUTCOME_UNKNOWN", result) == "ATTEMPT_RECEIPT"


@pytest.mark.parametrize("marker,expected", [
    ("replacement_approval_invalid", "database_approval_guard"),
    ("replacement_order_out_of_scope", "database_row_level_security"),
])
def test_database_refusal_rolls_back_and_preserves_attempt(target, monkeypatch, marker, expected):
    module, sequence = target
    def refuse(*_args):
        raise RuntimeError(marker)
    monkeypatch.setattr(module, "_execute_in_transaction", refuse)
    result = module.replace_damaged_item(**MATERIAL, review_id=91, idempotency_key="review-key")
    assert result["denied_by"] == expected
    assert [event[0] for event in sequence] == ["bind", "rollback", "audit"]


@pytest.mark.parametrize("change", [{"quantity": True}, {"quantity": 101}, {"reason": "other"}, {"disposition": "discard"}])
def test_target_revalidates_terms_even_if_gateway_schema_was_sanitized(target, change):
    module, sequence = target
    result = module.replace_damaged_item(**{**MATERIAL, **change}, review_id=91, idempotency_key="review-key")
    assert result["status"] == "error"
    assert sequence == []


@contextmanager
def transaction():
    yield "test-transaction"


def test_provider_commits_before_simulated_response_loss(monkeypatch):
    worker = load("replacement_worker")
    events = []
    @contextmanager
    def commit():
        events.append("begin")
        yield "tx"
        events.append("committed")
    monkeypatch.setattr(worker, "_transaction", commit)
    monkeypatch.setattr(worker, "_sql", lambda *a, **kw: events.append("provider-acceptance"))
    monkeypatch.setattr(worker, "record_state", lambda *a, **kw: events.append("outcome-unknown"))
    monkeypatch.setenv("SIMULATE_LOST_RESPONSE", "true")
    with pytest.raises(worker.SimulatedLostResponse):
        worker.dispatch("replacement")
    assert events == ["begin", "provider-acceptance", "committed", "outcome-unknown"]


@pytest.mark.parametrize("previous,next_state", [("shipped", "outcome_unknown"), ("shipped", "accepted"), ("accepted", "outcome_unknown")])
def test_delayed_attempt_cannot_regress_known_provider_state(monkeypatch, previous, next_state):
    worker = load("replacement_worker")
    sql = Mock(return_value=[{"status": previous}])
    monkeypatch.setattr(worker, "_transaction", transaction)
    monkeypatch.setattr(worker, "_sql", sql)
    assert worker.record_state("replacement", next_state, key="late")["state"] == previous
    assert sql.call_count == 1
    assert "FOR UPDATE" in sql.call_args.args[1]


def test_shipment_before_wait_registration_completes_new_callback(monkeypatch):
    worker = load("replacement_worker")
    queries = []
    def sql(tx, query, **kw):
        queries.append(query)
        return [{"status": "shipped"}] if "SELECT status FROM" in query else []
    sent = Mock(return_value={"state": "shipped"})
    monkeypatch.setattr(worker, "_transaction", transaction)
    monkeypatch.setattr(worker, "_sql", sql)
    monkeypatch.setattr(worker, "record_shipment", sent)
    assert worker.register_callback("replacement", "private-token")["state"] == "shipped"
    assert "FOR UPDATE" in queries[0]
    sent.assert_called_once_with("replacement")


def test_outbox_retry_uses_identical_execution_name_and_input(monkeypatch):
    worker = load("replacement_worker")
    row = {"event_id": "event-7", "replacement_id": "replacement-7", "lease_token": "lease-7"}
    monkeypatch.setattr(worker, "_transaction", transaction)
    monkeypatch.setattr(worker, "_sql", lambda tx, query, **kw: [row] if "WITH candidate" in query else [])
    states = Mock()
    class AlreadyExists(Exception):
        pass
    states.exceptions.ExecutionAlreadyExists = AlreadyExists
    states.start_execution.side_effect = [TimeoutError("lost StartExecution response"), AlreadyExists()]
    payload = json.dumps({"replacementId": "replacement-7", "eventId": "event-7"}, sort_keys=True, separators=(",", ":"))
    states.describe_execution.return_value = {"input": payload}
    monkeypatch.setattr(worker, "_states", lambda: states)
    monkeypatch.setenv("REPLACEMENT_STATE_MACHINE_ARN", "arn:aws:states:us-east-1:000000000000:stateMachine:recovery")
    with pytest.raises(TimeoutError):
        worker.relay()
    worker.relay()
    assert states.start_execution.call_args_list[0] == states.start_execution.call_args_list[1]
    assert states.start_execution.call_args.kwargs["input"] == payload
    assert states.describe_execution.call_args.kwargs["executionArn"].endswith(":execution:recovery:replacement-event-7")
