"""Staff graph tools through a separate Lambda and restricted PostgreSQL login.

Cedar requires the signed returns scope and matches operator_sub to the token's
subject. Customer binding is fixed by Runtime before it constructs the graph.
Every call uses one transaction; proposal creation and its audit receipt commit
together. No model, arbitrary SQL, approval, or credit execution is exposed.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict
from pathlib import Path

from common import dataapi
from common.fingerprint import OPERATOR_SOURCE_PATHS, deployed_fingerprint
from common.types import resolve_invocation
from gateway_tool_schemas import OPERATOR_SCHEMA
from services import operator_graph as graph
from services import store_tools

logger = logging.getLogger(__name__)
TOOLS = frozenset(tool["name"] for tool in OPERATOR_SCHEMA["tools"])
TOOLS_FINGERPRINT = deployed_fingerprint(Path(__file__).resolve().parent, source_paths=OPERATOR_SOURCE_PATHS)


def _execute(tool, args, run):
    customer = args["customer_id"]
    rows = run("SELECT id, name, cognito_username FROM pellier.customers WHERE id = %s", (customer,))
    if not rows:
        raise ValueError("unknown_case")
    run("SELECT set_config('pellier.principal_username', %s, true)", (rows[0]["cognito_username"],))
    case = graph._Case(run, run, customer, rows[0]["name"], args["operator_sub"],
                       args["turn_id"], lambda _event: None)
    if tool == "operator_get_case":
        # Unfiltered reads make the deployment probe test RLS itself, rather
        # than accidentally passing because a WHERE clause hides other cases.
        return {"status": "success", "name": rows[0]["name"],
                "database_role": "pellier_operator_tools",
                "visible_orders": [row["customer_id"] for row in run(
                    "SELECT DISTINCT customer_id FROM pellier.orders")],
                "visible_tickets": [row["customer_id"] for row in run(
                    "SELECT DISTINCT customer_id FROM pellier.support_tickets")]}
    if tool == "operator_get_orders":
        return store_tools.get_orders(run, customer_id=customer, limit=args.get("limit", 10))
    if tool == "operator_get_tickets":
        return store_tools.get_tickets(run, customer_id=customer, limit=args.get("limit", 5))
    if tool == "operator_get_store_credits":
        return graph.read_store_credits(run, customer_id=customer, limit=args.get("limit", 5))
    if tool == "operator_get_return_policy":
        return graph.read_return_policies(case)
    if tool == "operator_propose_store_credit":
        orders = args.get("order_ids")
        reason = args.get("reason")
        if (not isinstance(orders, list) or len(orders) > 100
                or any(type(value) is not int for value in orders)
                or not isinstance(reason, str) or len(reason) > 2000):
            raise ValueError("invalid_proposal")
        result = graph.propose_credit(case, order_ids=orders, reason=reason)
        return {**result, "proposal": asdict(case.proposal) if case.proposal else None}
    if tool == "operator_finish_investigation":
        review = args.get("review_id")
        if type(review) is not int or review < 0:
            raise ValueError("invalid_review")
        if review and not run(
            "SELECT id FROM pellier.approvals WHERE id = %s AND customer_id = %s "
            "AND tool = 'give_store_credit' AND status IN ('pending', 'approved')",
            (review, customer),
        ):
            raise ValueError("review_case_mismatch")
        answered = store_tools.answer_credit_requests(
            run, customer_id=customer, investigation_turn_id=args["turn_id"], review_id=review or None)
        return {"status": "success", "answered_ids": answered}
    raise ValueError("operator_tool_not_granted")


def lambda_handler(event, context):
    tool, args = resolve_invocation(event, context)
    if tool not in TOOLS:
        return {"isError": True, "content": [{"type": "text", "text": "operator_tool_not_granted"}]}
    # Direct IAM invocation is an administrative permission. It is not a
    # substitute for this Gateway's signed-user authorization in the app.
    custom = getattr(getattr(context, "client_context", None), "custom", {}) or {}
    request_id = custom.get("bedrockAgentCoreAwsRequestId")
    transaction = None
    started = time.monotonic()
    try:
        for name, pattern in (("customer_id", r"CUST-[A-Z0-9-]{1,40}"),
                              ("turn_id", r"turn-[A-Za-z0-9_-]{6,}"),
                              ("build_fingerprint", r"[0-9a-f]{64}")):
            if not isinstance(args.get(name), str) or not re.fullmatch(pattern, args[name]):
                raise ValueError("invalid_operator_context")
        actor = args.get("operator_sub")
        if not isinstance(actor, str) or not actor.strip() or len(actor) > 128:
            raise ValueError("invalid_operator_context")
        logger.info("tool_entered tool=%s gateway_request_id=%s lambda_request_id=%s",
                    tool, request_id or "unknown", getattr(context, "aws_request_id", "unknown"))
        transaction = dataapi.begin_transaction()

        def run(sql, params=()):
            return dataapi.execute_in_transaction(transaction, *dataapi._named(sql, params))

        role = run("SELECT session_user AS login, current_user AS role, rolsuper, rolbypassrls "
                   "FROM pg_roles WHERE rolname = current_user")
        if role != [{"login": "pellier_operator_tools", "role": "pellier_operator_tools",
                     "rolsuper": False, "rolbypassrls": False}]:
            raise ValueError("operator_database_role_mismatch")
        result = {**_execute(tool, args, run), "customer_id": args["customer_id"]}
        audited = {key: value for key, value in args.items()
                   if key not in {"gateway_request_id", "tools_fingerprint", "build_fingerprint"}}
        audited.update(gateway_request_id=request_id, tools_fingerprint=TOOLS_FINGERPRINT or None)
        dataapi.write_tool_audit(tool=tool, args=audited, result=result,
                                latency_ms=(time.monotonic() - started) * 1000,
                                session_id=f"operator-{args['customer_id']}",
                                build_fingerprint=args["build_fingerprint"], transaction_id=transaction)
        dataapi.commit_transaction(transaction)
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as exc:
        if transaction:
            dataapi.rollback_transaction(transaction)
        # An ambiguous commit is not retried here. The pending review's unique
        # key lets a later investigation resolve it without creating another.
        logger.warning("operator tool failed tool=%s kind=%s", tool, type(exc).__name__)
        return {"isError": True, "content": [{"type": "text", "text": "operator_tool_failed"}]}
