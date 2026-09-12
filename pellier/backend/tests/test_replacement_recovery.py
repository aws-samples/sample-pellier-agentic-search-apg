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


@pytest.mark.asyncio
async def test_read_model_preserves_provider_acceptance_beside_required_follow_up():
    row = {
        "replacement_id": "replacement-7", "review_id": 91, "order_id": 7, "product_id": 37,
        "product_name": "Wabi-Sabi Bowl", "quantity": 1, "disposition": "inspection_required",
        "status": "accepted", "workflow_resolution": "operator_review_required",
        "provider_operation_id": "simulator:replacement-7", "workflow_execution_arn": "execution-7",
        "idempotency_key": "review-key", "request_hash": "a" * 64, "outbox_id": None,
        "created_at": None, "updated_at": None, "events": [],
    }
    db = Mock(fetch_one=AsyncMock(return_value={"available": True}),
              fetch_all=AsyncMock(return_value=[row]))
    result = (await recovery.read_replacements(db, "CUST-THEO"))["replacements"][0]
    assert result["state"] == "accepted"
    assert result["workflowResolution"] == "operator_review_required"
    assert result["providerOperationId"] == row["provider_operation_id"]


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


@pytest.fixture
def recovery_state(monkeypatch):
    worker = load("replacement_worker")
    row = {"status": "accepted", "workflow_resolution": None}
    events = []
    def sql(_tx, query, **values):
        if "SELECT status," in query:
            return [dict(row)]
        if "UPDATE pellier.replacements SET status" in query:
            row["status"] = values["state"]
            if values["state"] == "shipped":
                row["workflow_resolution"] = "shipment_recorded"
        elif "UPDATE pellier.replacements" in query:
            row["workflow_resolution"] = "operator_review_required"
        elif "INSERT INTO pellier.replacement_events" in query:
            events.append(values)
        return []
    monkeypatch.setattr(worker, "_transaction", transaction)
    monkeypatch.setattr(worker, "_sql", sql)
    return worker, row, events


def test_timeout_requests_follow_up_without_erasing_acceptance(recovery_state):
    worker, row, events = recovery_state
    for _ in range(2):
        result = worker.request_operator_review("replacement", reason="workflow_timed_out")
    assert result["state"] == row["status"] == "accepted"
    assert result["workflowResolution"] == "operator_review_required"
    assert len(events) == 1
    assert json.loads(events[0]["details"]) == {"reason": "workflow_timed_out"}


@pytest.mark.parametrize("shipment_first", [False, True])
def test_shipment_and_timeout_in_either_serialized_order_leave_follow_up_closed(recovery_state, shipment_first):
    worker, row, _events = recovery_state
    shipment = lambda: worker.record_state("replacement", "shipped", key="provider-shipment")
    timeout = lambda: worker.request_operator_review("replacement", reason="workflow_timed_out")
    first, second = (shipment, timeout) if shipment_first else (timeout, shipment)
    first()
    result = second()
    assert result["state"] == row["status"] == "shipped"
    assert result["workflowResolution"] == row["workflow_resolution"] == "shipment_recorded"


def test_late_acceptance_does_not_silently_clear_operator_follow_up(recovery_state):
    worker, _row, _events = recovery_state
    worker.request_operator_review("replacement")
    result = worker.record_state("replacement", "accepted", key="late-acceptance")
    assert result["state"] == "accepted"
    assert result["workflowResolution"] == "operator_review_required"


def test_raw_workflow_error_is_never_accepted_as_evidence(monkeypatch):
    worker = load("replacement_worker")
    sql = Mock()
    monkeypatch.setattr(worker, "_sql", sql)
    with pytest.raises(ValueError, match="invalid_follow_up_reason"):
        worker.request_operator_review("replacement", reason="raw Cause with a private token")
    sql.assert_not_called()


@pytest.mark.parametrize("status,reason", [
    ("FAILED", "workflow_failed"), ("TIMED_OUT", "workflow_timed_out"),
    ("ABORTED", "workflow_aborted"), ("SUCCEEDED", "workflow_ended_without_shipment"),
    ("RUNNING", None), ("PENDING_REDRIVE", None),
])
def test_scheduled_observer_covers_terminal_executions_without_claiming_shipment(monkeypatch, status, reason):
    worker = load("replacement_worker")
    in_transaction = False
    @contextmanager
    def tracked_transaction():
        nonlocal in_transaction
        in_transaction = True
        yield "tx"
        in_transaction = False
    def describe(**kwargs):
        assert not in_transaction, "Do not hold a database transaction across an AWS request"
        assert kwargs == {"executionArn": "execution-7"}
        return {"status": status}
    monkeypatch.setattr(worker, "_transaction", tracked_transaction)
    monkeypatch.setattr(worker, "_sql", Mock(return_value=[
        {"replacement_id": "replacement-7", "workflow_execution_arn": "execution-7"},
    ]))
    states = Mock()
    states.describe_execution.side_effect = describe
    monkeypatch.setattr(worker, "_states", lambda: states)
    follow_up = Mock(return_value={"workflowResolution": "operator_review_required"})
    record = Mock()
    monkeypatch.setattr(worker, "request_operator_review", follow_up)
    monkeypatch.setattr(worker, "record_state", record)
    assert worker.inspect_workflows() == {"checked": 1, "followUps": int(reason is not None)}
    if reason:
        follow_up.assert_called_once_with("replacement-7", reason=reason)
    else:
        follow_up.assert_not_called()
    record.assert_not_called()


def test_workflow_fallback_persists_follow_up_and_schedule_observes_uncaught_failure():
    template = json.loads((DEPLOY / "replacement-workflow.template.json").read_text())
    states = template["Resources"]["Workflow"]["Properties"]["Definition"]["States"]
    assert states["AwaitShipment"]["Catch"][0]["Next"] == "NeedsReview"
    assert states["NeedsReview"]["Type"] == "Task"
    assert states["NeedsReview"]["Parameters"]["action"] == "request_operator_review"
    targets = template["Resources"]["PollOutbox"]["Properties"]["Targets"]
    assert {"relay", "inspect_workflows"} == {json.loads(target["Input"])["action"] for target in targets}


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


def test_failed_delivery_does_not_strand_other_claimed_outbox_events(monkeypatch):
    worker = load("replacement_worker")
    rows = [{"event_id": value, "replacement_id": value, "lease_token": value}
            for value in ("interrupted", "deliverable")]
    published = []
    def sql(_tx, query, **values):
        if "WITH candidate" in query:
            return rows
        if "UPDATE pellier.replacement_outbox" in query:
            published.append(values["event"])
            return [{"replacement_id": values["event"]}]
        return []
    states = Mock()
    states.exceptions.ExecutionAlreadyExists = type("AlreadyExists", (Exception,), {})
    states.start_execution.side_effect = [TimeoutError("interrupted"), {"executionArn": "execution-good"}]
    monkeypatch.setattr(worker, "_transaction", transaction)
    monkeypatch.setattr(worker, "_sql", sql)
    monkeypatch.setattr(worker, "_states", lambda: states)
    monkeypatch.setenv("REPLACEMENT_STATE_MACHINE_ARN", "state-machine")
    with pytest.raises(TimeoutError, match="interrupted"):
        worker.relay()
    assert published == ["deliverable"]
    assert states.start_execution.call_count == 2


def test_unreadable_execution_does_not_hide_another_clients_follow_up(monkeypatch):
    worker = load("replacement_worker")
    monkeypatch.setattr(worker, "_transaction", transaction)
    monkeypatch.setattr(worker, "_sql", Mock(return_value=[
        {"replacement_id": "first", "workflow_execution_arn": "execution-unavailable"},
        {"replacement_id": "second", "workflow_execution_arn": "execution-failed"},
    ]))
    states = Mock()
    states.describe_execution.side_effect = [TimeoutError("unreadable"), {"status": "FAILED"}]
    follow_up = Mock(return_value={"workflowResolution": "operator_review_required"})
    monkeypatch.setattr(worker, "_states", lambda: states)
    monkeypatch.setattr(worker, "request_operator_review", follow_up)
    with pytest.raises(TimeoutError, match="unreadable"):
        worker.inspect_workflows()
    follow_up.assert_called_once_with("second", reason="workflow_failed")
