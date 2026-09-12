"""Durable outbox relay and explicitly simulated warehouse for Theo's case.

Invoked by EventBridge/Step Functions or an IAM-authorized workshop operator.
There is no Function URL. Task tokens stay in a worker-only table, never in
the conversation, read model, events, or logs.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import boto3

from common import dataapi


class SimulatedLostResponse(Exception):
    pass


def _params(**values: Any) -> list[dict]:
    return [{
        "name": key,
        "value": {"longValue" if type(value) is int else "stringValue": value},
    } for key, value in values.items()]


@contextmanager
def _transaction():
    transaction = dataapi.begin_transaction()
    committing = False
    try:
        dataapi.execute_in_transaction(transaction, "SET LOCAL ROLE pellier_fulfillment")
        yield transaction
        committing = True
        dataapi.commit_transaction(transaction)
    except Exception:
        if not committing:
            try:
                dataapi.rollback_transaction(transaction)
            except Exception:
                pass
        raise


def _sql(transaction: str, query: str, **values: Any) -> list[dict]:
    return dataapi.execute_in_transaction(transaction, query, _params(**values))


def _states():
    return boto3.client("stepfunctions", region_name=os.environ.get("REGION", "us-east-1"))


def _event(transaction: str, replacement: str, key: str, state: str, **details: Any) -> None:
    _sql(transaction, """
        INSERT INTO pellier.replacement_events (replacement_id, event_key, event_type, details)
        VALUES (:replacement::uuid, :key::text, :state::text, :details::jsonb)
        ON CONFLICT (replacement_id, event_key) DO NOTHING
    """, replacement=replacement, key=key, state=state, details=json.dumps(details, sort_keys=True))


def record_state(replacement: str, state: str, *, key: str) -> dict:
    if state not in {"outcome_unknown", "accepted", "shipped"}:
        raise ValueError("invalid_replacement_transition")
    with _transaction() as tx:
        current = _sql(tx, """
            SELECT status, workflow_resolution FROM pellier.replacements
             WHERE replacement_id = :replacement::uuid FOR UPDATE
        """, replacement=replacement)
        if not current:
            raise ValueError("replacement_not_found")
        previous = current[0]["status"]
        resolution = current[0].get("workflow_resolution")
        # Delayed retries cannot undo a confirmed acceptance or shipment.
        if previous == "shipped" or (previous == "accepted" and state == "outcome_unknown"):
            return {"replacementId": replacement, "state": previous, "workflowResolution": resolution}
        _sql(tx, """
            UPDATE pellier.replacements SET status = :state::text, updated_at = now(),
                provider_operation_id = CASE WHEN :state::text IN ('accepted', 'shipped')
                    THEN 'simulator:' || replacement_id::text ELSE provider_operation_id END,
                workflow_resolution = CASE WHEN :state::text = 'shipped'
                    THEN 'shipment_recorded' ELSE workflow_resolution END
             WHERE replacement_id = :replacement::uuid
        """, replacement=replacement, state=state)
        _event(tx, replacement, key, state, provider="workshop-simulator")
    return {
        "replacementId": replacement, "state": state,
        "workflowResolution": "shipment_recorded" if state == "shipped" else resolution,
    }


def request_operator_review(replacement: str, *, reason: str = "fulfillment_unresolved") -> dict:
    # Keep raw Step Functions Cause payloads and callback tokens out of evidence.
    if reason not in {
        "fulfillment_unresolved", "workflow_failed", "workflow_timed_out",
        "workflow_aborted", "workflow_ended_without_shipment",
    }:
        raise ValueError("invalid_follow_up_reason")
    with _transaction() as tx:
        current = _sql(tx, """
            SELECT status, workflow_resolution FROM pellier.replacements
             WHERE replacement_id = :replacement::uuid FOR UPDATE
        """, replacement=replacement)
        if not current:
            raise ValueError("replacement_not_found")
        row = current[0]
        resolution = row.get("workflow_resolution")
        # Shares the shipment row lock: either shipment closes this follow-up,
        # or the late timeout observes shipment and leaves it closed.
        if row["status"] != "shipped" and resolution != "operator_review_required":
            _sql(tx, """
                UPDATE pellier.replacements
                   SET workflow_resolution = 'operator_review_required', updated_at = now()
                 WHERE replacement_id = :replacement::uuid
            """, replacement=replacement)
            _event(tx, replacement, "operator-follow-up", "operator_review_required", reason=reason)
            resolution = "operator_review_required"
    return {"replacementId": replacement, "state": row["status"], "workflowResolution": resolution}


def inspect_workflows() -> dict:
    # A whole-execution timeout, abort, or uncatchable error cannot run its own
    # Catch handler. The existing scheduled worker observes terminal executions.
    # Rotate bounded batches so one long-running callback cannot starve later rows.
    with _transaction() as tx:
        rows = _sql(tx, """
            WITH candidate AS (
                SELECT replacement_id FROM pellier.replacements
                 WHERE workflow_execution_arn IS NOT NULL
                   AND workflow_resolution IS NULL AND status <> 'shipped'
                 ORDER BY workflow_checked_at NULLS FIRST, created_at
                 LIMIT 10 FOR UPDATE SKIP LOCKED
            )
            UPDATE pellier.replacements r SET workflow_checked_at = now()
              FROM candidate c WHERE r.replacement_id = c.replacement_id
            RETURNING r.replacement_id::text, r.workflow_execution_arn
        """)
    reasons = {
        "FAILED": "workflow_failed", "TIMED_OUT": "workflow_timed_out",
        "ABORTED": "workflow_aborted", "SUCCEEDED": "workflow_ended_without_shipment",
    }
    follow_ups = 0
    failures = []
    for row in rows:
        try:
            execution = _states().describe_execution(executionArn=row["workflow_execution_arn"])
            reason = reasons.get(execution["status"])
            if reason:
                outcome = request_operator_review(row["replacement_id"], reason=reason)
                follow_ups += outcome["workflowResolution"] == "operator_review_required"
        except Exception as error:
            failures.append(error)
    # One unreadable execution cannot repeatedly strand the rest of its batch.
    # Still fail the invocation so operational monitoring sees the incomplete work.
    if failures:
        raise failures[0]
    return {"checked": len(rows), "followUps": follow_ups}


def relay() -> dict:
    machine = os.environ["REPLACEMENT_STATE_MACHINE_ARN"]
    with _transaction() as tx:
        rows = _sql(tx, """
            WITH candidate AS (
                SELECT event_id FROM pellier.replacement_outbox
                 WHERE published_at IS NULL AND (lease_until IS NULL OR lease_until < now())
                 ORDER BY created_at LIMIT 10 FOR UPDATE SKIP LOCKED
            )
            UPDATE pellier.replacement_outbox o
               SET lease_until = now() + interval '2 minutes', lease_token = gen_random_uuid(),
                   attempts = attempts + 1
              FROM candidate c WHERE o.event_id = c.event_id
            RETURNING o.event_id::text, o.replacement_id::text, o.lease_token::text
        """)
    published = 0
    failures = []
    for row in rows:
        try:
            published += _publish_outbox(row, machine)
        except Exception as error:
            failures.append(error)
    if failures:
        raise failures[0]
    return {"published": published}


def _publish_outbox(row: dict, machine: str) -> int:
    # Stable name AND byte-identical input make an uncertain StartExecution
    # retry refer to the same Standard execution.
    name = f"replacement-{row['event_id']}"
    payload = json.dumps({
        "replacementId": row["replacement_id"], "eventId": row["event_id"],
    }, sort_keys=True, separators=(",", ":"))
    states = _states()
    try:
        execution = states.start_execution(stateMachineArn=machine, name=name, input=payload)["executionArn"]
    except states.exceptions.ExecutionAlreadyExists:
        execution = machine.replace(":stateMachine:", ":execution:") + ":" + name
        existing = states.describe_execution(executionArn=execution)
        if existing["input"] != payload:
            raise ValueError("replacement_execution_input_conflict")
    with _transaction() as tx:
        saved = _sql(tx, """
            UPDATE pellier.replacement_outbox
               SET published_at = now(), execution_arn = :execution::text, lease_until = NULL
             WHERE event_id = :event::uuid AND lease_token = :lease::uuid
               AND published_at IS NULL RETURNING replacement_id::text
        """, event=row["event_id"], lease=row["lease_token"], execution=execution)
        if saved:
            _sql(tx, """
                UPDATE pellier.replacements SET workflow_execution_arn = :execution::text,
                    status = CASE WHEN status = 'reserved' THEN 'awaiting_fulfillment' ELSE status END,
                    updated_at = now() WHERE replacement_id = :replacement::uuid
            """, replacement=row["replacement_id"], execution=execution)
            _event(tx, row["replacement_id"], "workflow-started", "awaiting_fulfillment", executionArn=execution)
    return int(bool(saved))


def dispatch(replacement: str) -> dict:
    # This table is the warehouse simulator's own durable outcome, distinct from
    # Pellier's knowledge of it. A retry cannot create another provider operation.
    with _transaction() as tx:
        _sql(tx, """
            INSERT INTO pellier.replacement_simulator_operations (operation_id, status)
            VALUES (:replacement::uuid, 'accepted') ON CONFLICT (operation_id) DO NOTHING
        """, replacement=replacement)
    if os.environ.get("SIMULATE_LOST_RESPONSE", "false").lower() == "true":
        record_state(replacement, "outcome_unknown", key="dispatch-response-lost")
        raise SimulatedLostResponse("The simulator accepted the request; its response was deliberately lost.")
    return reconcile(replacement)


def reconcile(replacement: str) -> dict:
    with _transaction() as tx:
        rows = _sql(tx, """
            SELECT status FROM pellier.replacement_simulator_operations
             WHERE operation_id = :replacement::uuid
        """, replacement=replacement)
    state = rows[0]["status"] if rows else "outcome_unknown"
    return record_state(replacement, state, key=f"reconciled-{state}")


def register_callback(replacement: str, task_token: str) -> dict:
    if not task_token:
        raise ValueError("missing_task_token")
    with _transaction() as tx:
        # Serialize registration with shipment publication. Without the shared
        # row lock, each transaction can miss the other's uncommitted record.
        _sql(tx, "SELECT replacement_id FROM pellier.replacements WHERE replacement_id = :replacement::uuid FOR UPDATE",
             replacement=replacement)
        _sql(tx, """
            INSERT INTO pellier.replacement_callbacks (replacement_id, task_token)
            VALUES (:replacement::uuid, :token::text)
            ON CONFLICT (replacement_id) DO UPDATE SET task_token = EXCLUDED.task_token, updated_at = now()
        """, replacement=replacement, token=task_token)
        shipped = _sql(tx, """
            SELECT status FROM pellier.replacement_simulator_operations
             WHERE operation_id = :replacement::uuid AND status = 'shipped'
        """, replacement=replacement)
    # A shipment callback can race registration. Re-read durable provider state
    # after saving the token, so neither ordering strands a waiting workflow.
    if shipped:
        return record_shipment(replacement)
    return {"replacementId": replacement, "waiting": True}


def record_shipment(replacement: str) -> dict:
    with _transaction() as tx:
        _sql(tx, "SELECT replacement_id FROM pellier.replacements WHERE replacement_id = :replacement::uuid FOR UPDATE",
             replacement=replacement)
        rows = _sql(tx, """
            UPDATE pellier.replacement_simulator_operations SET status = 'shipped'
             WHERE operation_id = :replacement::uuid RETURNING operation_id
        """, replacement=replacement)
        if not rows:
            raise ValueError("fulfillment_has_not_accepted_this_replacement")
        callback = _sql(tx, """
            SELECT task_token FROM pellier.replacement_callbacks
             WHERE replacement_id = :replacement::uuid
        """, replacement=replacement)
    outcome = record_state(replacement, "shipped", key="simulator-shipped")
    if callback:
        states = _states()
        try:
            states.send_task_success(taskToken=callback[0]["task_token"], output=json.dumps(outcome))
        except (states.exceptions.TaskDoesNotExist, states.exceptions.TaskTimedOut):
            # The provider result remains authoritative after workflow expiry.
            with _transaction() as tx:
                _event(tx, replacement, "callback-expired", "callback_expired")
    return outcome


def lambda_handler(event: dict, context: Any) -> dict:
    action = event.get("action")
    if action == "relay":
        return relay()
    if action == "inspect_workflows":
        return inspect_workflows()
    replacement = str(UUID(str(event["replacementId"])))
    if action == "dispatch":
        return dispatch(replacement)
    if action == "reconcile":
        return reconcile(replacement)
    if action == "wait_for_shipment":
        return register_callback(replacement, str(event.get("taskToken") or ""))
    if action == "record_shipment":
        return record_shipment(replacement)
    if action == "request_operator_review":
        return request_operator_review(replacement)
    raise ValueError("unknown_replacement_worker_action")
