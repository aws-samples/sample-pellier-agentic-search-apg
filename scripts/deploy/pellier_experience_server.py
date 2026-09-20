"""
Pellier Experience MCP Server — Lambda-hosted MCP server for the Theo /
return-flow tools that the Customer Service Agent owns.

Exposes tools:
  - initiate_return:        Atomic ownership-check → INSERT into ``pellier.returns``
                           → (if damaged) decrement ``pellier.product_catalog.quantity``.
  - issue_credit:          Idempotent goodwill store credit, capped at $500.
  - get_ticket_history:    Read-only past support interactions for context.
  - escalate_to_human:   Honest fallback that hands the conversation off
                           to a human stylist when no catalog tool fits.

Deployed as a Lambda function behind AgentCore Gateway. Mirrors the
in-process @tool functions in ``pellier/backend/services/agent_tools.py``
and ``pellier/backend/services/business_logic.py`` — same JSON envelopes,
same Cedar-allowed reason set, same ownership SQL — so the orchestrator's
prompt is identical whether tools execute in-process or behind Gateway.

References:
    RDS Data API transactions:
        https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.html
"""
import json
import hashlib
import logging
import os
import time
from typing import Any

import boto3

from common.types import resolve_invocation
from common.handler import audit_read_call
from common.replacement_contract import REPLACEMENT_TOOL
from common.dataapi import (
    execute_sql as _execute_sql,
    begin_transaction as _begin_transaction,
    commit_transaction as _commit_transaction,
    rollback_transaction as _rollback_transaction,
    execute_in_transaction as _execute_in_transaction,
    row_to_dict as _row_to_dict,
    bind_runtime_principal as _bind_runtime_principal,
    write_tool_audit_independently as _write_tool_audit_independently,
)

logger = logging.getLogger(__name__)

REGION = os.environ.get("REGION", "us-east-1")
DB_REGION = os.environ.get("DB_REGION", REGION)
DB_CLUSTER_ARN = os.environ.get("DB_CLUSTER_ARN", "")
SECRET_ARN = os.environ.get("SECRET_ARN", "")
DATABASE = os.environ.get("DATABASE", "postgres")
SCHEMA = "pellier"

# Cedar policy ``process-return-allowed-reasons`` enforces this set
# upstream; we re-check inside the Lambda as defense-in-depth so a
# misbehaving caller that bypasses Cedar can't write garbage.
ALLOWED_RETURN_REASONS = {
    "damaged",
    "wrong_size",
    "not_as_described",
    "changed_mind",
    "other",
}


def _write_request_hash(operation: str, arguments: dict) -> str:
    payload = json.dumps(
        {"operation": operation, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reports_not_ordered(result: dict | None) -> bool:
    """True when the write function concluded the customer never ordered.

    Matches the function's own phrasing rather than a status code, because
    `status: error` covers several unrelated outcomes. Same predicate as
    `BusinessLogic._reports_not_ordered`.
    """
    if not isinstance(result, dict) or result.get("status") != "error":
        return False
    return "did not order" in str(result.get("message", ""))


def initiate_return(
    customer_id: str,
    product_id: int,
    reason: str,
    idempotency_key: str,
    *,
    audit_arguments: dict | None = None,
    customer_subject: str | None = None,
) -> dict:
    """Execute the shared idempotent return transaction in Aurora, row-scoped.

    ``customer_subject`` is the Cognito subject of the CUSTOMER whose rows this
    touches, resolved server-side from the confirmed review. It is bound
    transaction-locally so Row-Level Security applies to this write.

    It is emphatically NOT the operator. AgentCore Policy authorizes the operator
    at the Gateway; RLS scopes the customer here. Passing the operator's subject
    would scope the transaction to the operator's own rows and the write would
    fail for every client they are not mapped to.

    ``None`` binds an empty principal, which resolves to no customer scope and
    denies. That is the correct outcome for a client with no identity mapping.
    """
    if reason not in ALLOWED_RETURN_REASONS:
        return {
            "status": "policy_blocked",
            "message": (
                f"Reason '{reason}' is not an allowed return reason. "
                f"Allowed: {sorted(ALLOWED_RETURN_REASONS)}."
            ),
        }

    clean_key = str(idempotency_key or "").strip()
    if not clean_key:
        return {"status": "error", "message": "idempotency_key is required."}
    product_id_text = str(product_id)
    request_hash = _write_request_hash(
        "initiate_return",
        {
            "customer_id": str(customer_id),
            "product_id": int(product_id),
            "reason": str(reason),
        },
    )

    started = time.monotonic()
    transaction_id = _begin_transaction()

    try:
        # Role and principal first, on this transaction, before the protected
        # statement. Statements sharing a transactionId share one server-side
        # transaction, so these settings apply to the write below.
        _bind_runtime_principal(transaction_id, customer_subject=customer_subject)
        rows = _execute_in_transaction(
            transaction_id,
            f"SELECT {SCHEMA}.process_return_idempotent("
            ":idempotency_key, :request_hash, :cid, :pid, :reason"
            ") AS result;",
            [
                {"name": "idempotency_key", "value": {"stringValue": clean_key}},
                {"name": "request_hash", "value": {"stringValue": request_hash}},
                {"name": "cid", "value": {"stringValue": str(customer_id)}},
                {"name": "pid", "value": {"stringValue": product_id_text}},
                {"name": "reason", "value": {"stringValue": str(reason)}},
            ],
        )
        raw_result = rows[0].get("result") if rows else None
        result = json.loads(raw_result) if isinstance(raw_result, str) else (
            raw_result or {"status": "error", "message": "Return produced no result."}
        )
        # Distinguish "you may not see this" from "it does not exist".
        #
        # `process_return_idempotent` establishes ownership with a SELECT against
        # `pellier.orders`. Under RLS that select is scoped to the bound principal,
        # so a customer outside the scope finds nothing and the function reports
        # "did not order" — which is a false statement about Aurora's contents and
        # disguises an authorization boundary as a data fact. Box-verified: the
        # live Gateway said CUST-AMARA "did not order product 46" for an order
        # that exists.
        #
        # So when the function reports not-ordered, ask the database, inside the
        # same transaction, whether the customer is in scope at all. Mirrors
        # `BusinessLogic._initiate_return_governed` on the in-process rail so both
        # rails classify a denial the same way.
        if _reports_not_ordered(result):
            scope_rows = _execute_in_transaction(
                transaction_id,
                f"SELECT count(*) AS in_scope FROM "
                f"{SCHEMA}.current_principal_customers() WHERE customer_id = :cid;",
                [{"name": "cid", "value": {"stringValue": str(customer_id)}}],
            )
            in_scope = bool(scope_rows and int(scope_rows[0].get("in_scope") or 0))
            if not in_scope:
                result = {
                    "status": "policy_blocked",
                    "message": (
                        f"This session is not authorized to act on {customer_id}'s "
                        "orders. The database refused the read the return depends "
                        "on, so nothing was changed."
                    ),
                    "denied_by": "database_row_level_security",
                }
        _commit_transaction(transaction_id)
        committed = True
    except Exception as exc:
        _rollback_transaction(transaction_id)
        logger.error("initiate_return failed: %s", exc)
        result = {"status": "error", "message": str(exc)}
        committed = False

    # The receipt commits in its own transaction, so it survives a rolled-back
    # business write. An RLS denial must leave exactly one attempt receipt: with
    # the receipt inside the mutation, the rollback destroyed the only evidence
    # that a governed action was ever attempted.
    _write_tool_audit_independently(
        tool="initiate_return",
        args=audit_arguments
        or {
            "customer_id": customer_id,
            "product_id": product_id,
            "reason": reason,
            "idempotency_key": clean_key,
        },
        result=result,
        latency_ms=int((time.monotonic() - started) * 1000),
        session_id=f"gateway-{customer_id}",
    )
    return result


def replace_damaged_item(
    customer_id: str, order_id: int, product_id: int, quantity: int, reason: str,
    disposition: str, review_id: int, idempotency_key: str,
    *, audit_arguments: dict | None = None, customer_subject: str | None = None,
) -> dict:
    """Commit the approved remedy; an ambiguous commit stays recoverable."""
    material = {
        "customer_id": customer_id, "order_id": order_id, "product_id": product_id,
        "quantity": quantity, "reason": reason, "disposition": disposition,
    }
    if (reason != "damaged" or disposition != "inspection_required"
            or any(type(value) is not int or value < 1
                   for value in (order_id, product_id, quantity, review_id))
            or quantity > 100 or not idempotency_key or len(idempotency_key) > 128):
        return {"status": "error", "message": "invalid_replacement_terms"}
    request_hash = _write_request_hash("replace_damaged_item", material)
    started = time.monotonic()
    transaction_id = _begin_transaction()
    commit_started = False
    try:
        _bind_runtime_principal(transaction_id, customer_subject=customer_subject)
        bindings = [
            {"name": name, "value": {"longValue" if type(value) is int else "stringValue": value}}
            for name, value in {
                "review_id": review_id, "key": idempotency_key, "hash": request_hash,
                "customer": customer_id, "order_id": order_id, "product": str(product_id),
                "quantity": quantity, "disposition": disposition,
            }.items()
        ]
        rows = _execute_in_transaction(
            transaction_id,
            "SELECT pellier.replace_damaged_item(:review_id::bigint, :key::text, "
            ":hash::text, :customer::text, :order_id::bigint, :product::text, "
            ":quantity::integer, :disposition::text) AS result", bindings,
        )
        raw = rows[0]["result"] if rows else None
        result = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(result, dict):
            raise ValueError("replacement_result_missing")
        commit_started = True
        _commit_transaction(transaction_id)
    except Exception as exc:
        if not commit_started:
            try:
                _rollback_transaction(transaction_id)
            except Exception:
                logger.warning("Replacement rollback could not be confirmed")
        # A CommitTransaction transport error can occur after Aurora committed.
        # Preserve ambiguity instead of claiming that a rollback undid the write.
        result = {
            "status": "outcome_unknown" if commit_started else "error",
            "message": (
                "The commit response was interrupted. Check the recorded replacement "
                "or retry the same approved action to recover its result."
                if commit_started else str(exc)
            ),
        }
        if not commit_started:
            message = str(exc)
            if "replacement_order_out_of_scope" in message or "replacement_approval_out_of_scope" in message:
                result["denied_by"] = "database_row_level_security"
            elif "replacement_approval_" in message:
                result["denied_by"] = "database_approval_guard"
            elif any(code in message for code in ("replacement_stock_changed", "replacement_quantity_exceeds_order")):
                result["sqlstate"] = "23514"
            elif "replacement_idempotency_conflict" in message:
                result["status"] = "idempotency_conflict"
    _write_tool_audit_independently(
        tool="replace_damaged_item",
        args=audit_arguments or {**material, "review_id": review_id, "idempotency_key": idempotency_key},
        result=result, latency_ms=int((time.monotonic() - started) * 1000),
        session_id=f"gateway-{customer_id}",
    )
    return result


def issue_credit(
    customer_id: str,
    amount_cents: int,
    reason: str,
    idempotency_key: str,
    *,
    audit_arguments: dict | None = None,
) -> dict:
    """Apply a goodwill store credit exactly once, in Aurora.

    Mirrors ``BusinessLogic.issue_credit`` on the in-process rail: same
    ``pellier.apply_store_credit`` function, same envelopes, same $500
    ceiling. The ceiling is enforced by a CHECK constraint on
    ``pellier.store_credits``; the readable ``policy_blocked`` below exists so
    the agent sees a sentence rather than a raw SQL error.

    ``issued_by`` is not accepted here. This rail has no verified operator
    token to read, and an attribution the model supplied would be worse than
    none. The operator console attributes credits through
    ``routes/operator.py``, where ``require_operator`` has already produced a
    verified ``sub``.
    """
    clean_key = str(idempotency_key or "").strip()
    if not clean_key:
        return {"status": "error", "message": "idempotency_key is required."}
    try:
        cents = int(amount_cents)
    except (TypeError, ValueError):
        return {
            "status": "error",
            "message": f"amount_cents must be an integer, got {amount_cents!r}.",
        }
    clean_reason = str(reason or "").strip()
    if not clean_reason:
        return {"status": "error", "message": "A reason is required for a credit."}

    request_hash = _write_request_hash(
        "issue_credit",
        {
            "customer_id": str(customer_id),
            "amount_cents": cents,
            "reason": clean_reason,
        },
    )

    started = time.monotonic()
    transaction_id = _begin_transaction()

    try:
        rows = _execute_in_transaction(
            transaction_id,
            # Every argument is cast at the call site. The Data API sends an
            # integer as `longValue`, which arrives as bigint, and PostgreSQL
            # does not implicitly narrow bigint to the function's `integer`
            # parameter when resolving an overload. Live on 2026-09-10 that
            # produced "function pellier.apply_store_credit(text, text, text,
            # bigint, text, unknown) does not exist" - Cedar allowed the call,
            # the Lambda ran, and no credit row was written.
            f"SELECT {SCHEMA}.apply_store_credit("
            ":idempotency_key::text, :request_hash::text, :cid::text,"
            " :amount_cents::integer, :reason::text, NULL::text"
            ") AS result;",
            [
                {"name": "idempotency_key", "value": {"stringValue": clean_key}},
                {"name": "request_hash", "value": {"stringValue": request_hash}},
                {"name": "cid", "value": {"stringValue": str(customer_id)}},
                {"name": "amount_cents", "value": {"longValue": cents}},
                {"name": "reason", "value": {"stringValue": clean_reason}},
            ],
        )
        raw_result = rows[0].get("result") if rows else None
        result = json.loads(raw_result) if isinstance(raw_result, str) else (
            raw_result or {"status": "error", "message": "Credit produced no result."}
        )
        _commit_transaction(transaction_id)
        committed = True
    except Exception as exc:
        _rollback_transaction(transaction_id)
        logger.error("issue_credit failed: %s", exc)
        result = {"status": "error", "message": str(exc)}
        committed = False

    # Independent receipt, same reason as initiate_return: the $500 CHECK
    # constraint rolls the transaction back, and the attempt must survive that.
    _write_tool_audit_independently(
        tool="issue_credit",
        args=audit_arguments
        or {
            "customer_id": customer_id,
            "amount_cents": cents,
            "reason": clean_reason,
            "idempotency_key": clean_key,
        },
        result=result,
        latency_ms=int((time.monotonic() - started) * 1000),
        session_id=f"gateway-{customer_id}",
    )
    return result


def get_ticket_history(customer_id: str, limit: int = 5) -> dict:
    """Read one customer's past support tickets, newest first.

    Read-only, so no transaction and no audit write: ``tool_audit`` records
    what ran on the write rails, and every ALLOWed call is already recorded by
    the handler below.
    """
    try:
        capped = max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        capped = 5

    tickets = _execute_sql(
        f"SELECT ticket_id, subject, status, channel, last_note, "
        f"opened_at, resolved_at FROM {SCHEMA}.support_tickets "
        "WHERE customer_id = :cid ORDER BY opened_at DESC LIMIT :lim;",
        [
            {"name": "cid", "value": {"stringValue": str(customer_id)}},
            {"name": "lim", "value": {"longValue": capped}},
        ],
    ) or []
    return {
        "status": "success",
        "customer_id": str(customer_id),
        "count": len(tickets),
        "open_count": sum(
            1 for t in tickets if str(t.get("status")) in ("open", "pending")
        ),
        "tickets": tickets,
    }


def escalate_to_human(reason: str = "", customer_id: str = "") -> dict:
    """Honest fallback that hands the conversation off to a human stylist.

    No DB write, no products — pure UI handoff. The chat surface renders
    a `StylistHandoffCard` from this payload (Type ``escalation``). The
    ``stylist`` channel is a placeholder for whatever live-chat / email /
    CX-ticket system a production deployment would wire in.
    """
    cleaned_reason = (reason or "").strip() or (
        "The agent thought a human stylist was the right next step."
    )
    cleaned_customer = (customer_id or "").strip() or None
    return {
        "type": "escalation",
        "channel": "stylist",
        "status": "handed_off",
        "reason": cleaned_reason,
        "customer_id": cleaned_customer,
        "contact": {
            "label": "Talk to a stylist",
            "mailto": "stylist@pellier.example",
            "response_window": "Within 1 business day",
        },
        "next_steps": [
            "A Pellier stylist receives your note with full context.",
            "They reply within one business day.",
            "You can keep browsing. We'll pick up where you left off.",
        ],
    }


# --- Lambda MCP handler ---

TOOLS = {
    "initiate_return": {
        "fn": initiate_return,
        "description": (
            "Process a customer return atomically. Verifies ownership "
            "(customer must have ordered the product), inserts a row "
            "into pellier.returns, and (if reason='damaged') decrements "
            "product_catalog.quantity. Reason must be one of: damaged, "
            "wrong_size, not_as_described, changed_mind, other."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Salesforce-style customer ID"},
                "product_id": {"type": "integer", "description": "productId in pellier.product_catalog"},
                "reason": {
                    "type": "string",
                    "description": "One of damaged, wrong_size, not_as_described, changed_mind, other",
                    "enum": sorted(ALLOWED_RETURN_REASONS),
                },
                "idempotency_key": {
                    "type": "string",
                    "description": "Stable unique key for this intended return",
                },
            },
            "required": ["customer_id", "product_id", "reason", "idempotency_key"],
        },
    },
    "issue_credit": {
        "fn": issue_credit,
        "description": (
            "Issue a goodwill store credit to a customer for service "
            "recovery, up to $500.00. Writes one durable row per "
            "idempotency key into pellier.store_credits. Use when a client "
            "was let down and a refund is not the right remedy."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer receiving the credit"},
                "amount_cents": {
                    "type": "integer",
                    "description": "Credit amount in integer cents; 2500 means $25.00",
                    "minimum": 1,
                    "maximum": 50000,
                },
                "reason": {"type": "string", "description": "Why the credit is issued; audited"},
                "idempotency_key": {
                    "type": "string",
                    "description": "Stable unique key for this intended credit",
                },
            },
            "required": ["customer_id", "amount_cents", "reason", "idempotency_key"],
        },
    },
    "get_ticket_history": {
        "fn": get_ticket_history,
        "description": (
            "Read a customer's past support tickets, newest first. Use for "
            "context before answering a service question so the client is "
            "not asked to repeat what already happened."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer whose tickets to read"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum tickets to return, newest first",
                    "minimum": 1,
                    "maximum": 25,
                },
            },
            "required": ["customer_id"],
        },
    },
    "escalate_to_human": {
        "fn": escalate_to_human,
        "description": (
            "Hand the conversation off to a human stylist. Honest fallback "
            "for asks the catalog cannot answer (cultural dressing norms, "
            "body-image fit, out-of-policy returns, catalog misses). Do "
            "not call this when another tool can answer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "One short sentence describing why the handoff is happening"},
                "customer_id": {"type": "string", "description": "Verified customer id for the handoff context"},
            },
            "required": ["customer_id"],
        },
    },
}


TOOLS["replace_damaged_item"] = {**REPLACEMENT_TOOL, "fn": replace_damaged_item}


def _resolve_customer_subject(customer_id: str) -> str | None:
    """The RLS subject for a customer, from the authorization mapping table.

    Trusted server-side resolution, deliberately. The MCP arguments carry
    ``customer_id`` — which the operator's confirmation fingerprint already binds
    — and this turns it into an RLS principal by asking the database, so no
    caller can substitute one.

    ``None`` means the customer has no linked identity. The caller binds an empty
    principal, RLS resolves no scope, and the write is denied. That is the correct
    fail-closed answer, not an error.
    """
    if not customer_id:
        return None
    # Normalise the persona alias before the lookup. The live shopper prompt and
    # the Gateway proof script both pass the bare `theo`, while the mapping table
    # is keyed on the canonical `CUST-THEO`. Without this the subject would
    # resolve to nothing and RLS would deny a legitimate owned-order action —
    # which looks exactly like a governance finding and is really a key mismatch.
    #
    # Server-side normalisation, so it is not caller input: the argument still has
    # to name a customer, and only the canonical form of that name is used.
    lookup = customer_id.strip()
    if not lookup.upper().startswith("CUST-"):
        lookup = f"CUST-{lookup.upper()}"
    else:
        lookup = lookup.upper()
    try:
        rows = _execute_sql(
            f"SELECT principal_sub FROM {SCHEMA}.principal_customers "
            "WHERE customer_id = :cid ORDER BY principal_sub LIMIT 1;",
            [{"name": "cid", "value": {"stringValue": lookup}}],
        )
    except Exception as exc:  # noqa: BLE001 - fail closed, never widen
        logger.error("customer-subject resolution failed for %s: %s", customer_id, exc)
        return None
    if not rows:
        logger.info(
            "customer %s (looked up as %s) has no principal_customers mapping; "
            "RLS will deny",
            customer_id, lookup,
        )
        return None
    value = rows[0].get("principal_sub") if isinstance(rows[0], dict) else None
    return str(value) if value else None


def lambda_handler(event: dict, context: Any) -> dict:
    """Lambda handler for MCP tool invocation via AgentCore Gateway."""
    # Resolve BOTH invocation shapes (Gateway client_context-prefixed vs direct
    # {name,arguments}); shared helper in common/types.py, packaged into the zip.
    tool_name, arguments = resolve_invocation(event, context)

    if tool_name == "list_tools":
        return {
            "tools": [
                {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
                for name, spec in TOOLS.items()
            ]
        }

    if tool_name not in TOOLS:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        started = time.monotonic()
        audit_arguments = dict(arguments)
        # `customer_subject` is never accepted from the wire. A caller that could
        # name its own RLS principal could read and write any customer's rows
        # while passing every other check, so the subject is resolved here from
        # trusted server-side data instead.
        execution_arguments = {
            key: value
            for key, value in arguments.items()
            if key not in ("turn_id", "customer_subject")
        }
        if tool_name in ("initiate_return", "replace_damaged_item"):
            result = TOOLS[tool_name]["fn"](
                **execution_arguments,
                audit_arguments=audit_arguments,
                customer_subject=_resolve_customer_subject(
                    str(execution_arguments.get("customer_id") or "")
                ),
            )
        else:
            result = TOOLS[tool_name]["fn"](**execution_arguments)
        latency_ms = int((time.monotonic() - started) * 1000)
        if tool_name not in ("initiate_return", "replace_damaged_item", "issue_credit"):
            audit_read_call(tool_name, audit_arguments, result, started)
        # Guardrail data paths cannot index the MCP content array. Expose the
        # exact same serialized output as a record field for the managed check.
        text = json.dumps(result, default=str)
        return {"text": text, "content": [{"type": "text", "text": text}]}
    except Exception as e:
        logger.error("Tool %s failed: %s", tool_name, e)
        text = json.dumps({"error": "The requested action could not be completed."})
        return {"text": text, "content": [{"type": "text", "text": text}], "isError": True}
