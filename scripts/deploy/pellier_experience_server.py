"""
Pellier Experience MCP Server — Lambda-hosted MCP server for the Theo /
return-flow tools that the Experience Guide owns.

Exposes tools:
  - process_return:        Atomic ownership-check → INSERT into ``pellier.returns``
                           → (if damaged) decrement ``pellier.product_catalog.quantity``.
  - escalate_to_stylist:   Honest fallback that hands the conversation off
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
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)

REGION = os.environ.get("REGION", "us-east-1")
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

rds_client = boto3.client("rds-data", region_name=REGION)


def _row_to_dict(record: list, columns: list[str]) -> dict:
    out: dict = {}
    for i, field in enumerate(record):
        if "stringValue" in field:
            out[columns[i]] = field["stringValue"]
        elif "longValue" in field:
            out[columns[i]] = field["longValue"]
        elif "doubleValue" in field:
            out[columns[i]] = field["doubleValue"]
        elif "booleanValue" in field:
            out[columns[i]] = field["booleanValue"]
        elif "isNull" in field:
            out[columns[i]] = None
        else:
            out[columns[i]] = str(field)
    return out


def _execute_in_transaction(transaction_id: str, sql: str, parameters: list = None) -> list[dict]:
    params = {
        "resourceArn": DB_CLUSTER_ARN,
        "secretArn": SECRET_ARN,
        "database": DATABASE,
        "sql": sql,
        "transactionId": transaction_id,
    }
    if parameters:
        params["parameters"] = parameters
    response = rds_client.execute_statement(**params)
    columns = [col["name"] for col in response.get("columnMetadata", [])]
    return [_row_to_dict(record, columns) for record in response.get("records", [])]


def process_return(customer_id: str, product_id: int, reason: str) -> dict:
    """Atomic return: ownership check → INSERT → (if damaged) decrement quantity.

    Mirrors ``BusinessLogic.process_return`` in the source repo. Three
    operations run inside a single RDS Data API transaction so the
    ownership check, the INSERT, and the conditional UPDATE either all
    succeed or all roll back together.

    Cedar gates the reason value upstream; ownership is gated here
    because the principal/resource relationship is a SQL JOIN, not a
    static policy.
    """
    if reason not in ALLOWED_RETURN_REASONS:
        return {
            "status": "policy_blocked",
            "message": (
                f"Reason '{reason}' is not an allowed return reason. "
                f"Allowed: {sorted(ALLOWED_RETURN_REASONS)}."
            ),
        }

    product_id_text = str(product_id)

    begin = rds_client.begin_transaction(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=SECRET_ARN,
        database=DATABASE,
    )
    transaction_id = begin["transactionId"]

    try:
        owns = _execute_in_transaction(
            transaction_id,
            f'SELECT 1 AS hit FROM {SCHEMA}.orders '
            'WHERE customer_id = :cid AND product_id = :pid '
            'LIMIT 1;',
            [
                {"name": "cid", "value": {"stringValue": str(customer_id)}},
                {"name": "pid", "value": {"stringValue": product_id_text}},
            ],
        )
        if not owns:
            rds_client.rollback_transaction(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=SECRET_ARN,
                transactionId=transaction_id,
            )
            return {
                "status": "error",
                "message": (
                    f"Customer {customer_id} did not order product "
                    f"{product_id}; cannot process return."
                ),
            }

        inserted = _execute_in_transaction(
            transaction_id,
            f'INSERT INTO {SCHEMA}.returns (customer_id, product_id, reason) '
            'VALUES (:cid, :pid, :reason) RETURNING id;',
            [
                {"name": "cid", "value": {"stringValue": str(customer_id)}},
                {"name": "pid", "value": {"stringValue": product_id_text}},
                {"name": "reason", "value": {"stringValue": str(reason)}},
            ],
        )
        return_id = inserted[0]["id"] if inserted else None

        new_quantity = None
        product_name = None
        if reason == "damaged":
            updated = _execute_in_transaction(
                transaction_id,
                f'UPDATE {SCHEMA}.product_catalog '
                'SET quantity = GREATEST(quantity - 1, 0), '
                '    updated_at = NOW() '
                'WHERE "productId" = :pid '
                'RETURNING "productId", name, quantity;',
                [{"name": "pid", "value": {"stringValue": product_id_text}}],
            )
            if updated:
                new_quantity = int(updated[0]["quantity"])
                product_name = updated[0]["name"]
        else:
            named = _execute_in_transaction(
                transaction_id,
                f'SELECT "productId", name FROM {SCHEMA}.product_catalog '
                'WHERE "productId" = :pid LIMIT 1;',
                [{"name": "pid", "value": {"stringValue": product_id_text}}],
            )
            if named:
                product_name = named[0].get("name")

        rds_client.commit_transaction(
            resourceArn=DB_CLUSTER_ARN,
            secretArn=SECRET_ARN,
            transactionId=transaction_id,
        )
        return {
            "status": "success",
            "return_id": return_id,
            "product_id": int(product_id),
            "name": product_name,
            "reason": reason,
            "new_quantity": new_quantity,
        }
    except Exception as exc:
        try:
            rds_client.rollback_transaction(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=SECRET_ARN,
                transactionId=transaction_id,
            )
        except Exception:
            logger.warning("rollback failed for transaction %s", transaction_id)
        logger.error("process_return failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def escalate_to_stylist(reason: str = "", customer_id: str = "") -> dict:
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
            "You can keep browsing — we'll pick up where you left off.",
        ],
    }


# --- Lambda MCP handler ---

TOOLS = {
    "process_return": {
        "fn": process_return,
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
            },
            "required": ["customer_id", "product_id", "reason"],
        },
    },
    "escalate_to_stylist": {
        "fn": escalate_to_stylist,
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
                "customer_id": {"type": "string", "description": "Optional customer id so the stylist queue can pre-load order history"},
            },
            "required": [],
        },
    },
}


def lambda_handler(event: dict, context: Any) -> dict:
    """Lambda handler for MCP tool invocation via AgentCore Gateway."""
    tool_name = event.get("name", "")
    arguments = event.get("arguments", {}) or {}

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
        result = TOOLS[tool_name]["fn"](**arguments)
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        logger.error("Tool %s failed: %s", tool_name, e)
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}
