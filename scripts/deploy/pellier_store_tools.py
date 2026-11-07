"""Pellier's nine store tools behind one AgentCore Gateway target.

One Lambda, one target (``pellier-store-tools``), so every Cedar action id is
``pellier-store-tools___<tool>``. The tools themselves are not implemented
here: each one is a function in ``services/store_tools.py`` that takes a
``run(sql, params) -> rows`` callable, and this module hands it the RDS Data
API runner from ``common/dataapi.py``. The in-process ``@tool`` wrappers in
``pellier/backend/services/agent_tools.py`` hand the same functions the psycopg
pool, so a tool answers identically on either rail.

``deploy_lambda.py`` stages ``services/store_tools.py`` and the two pure
retrieval modules it imports next to this file, so the import below resolves
inside the zip exactly as it does in the backend.

Evidence contract:

* A successful credit and its ``pellier.tool_audit`` row commit together.
  A refused or failed attempt is recorded independently after rollback.
  An idempotent replay writes none: the original receipt stays with its credit.
* A read writes an audit row only when the Runtime passed a ``turn_id``, so an
  uncorrelated probe cannot pose as a shopper turn.
* Every audit row records the Runtime build and the Lambda's own source digest.
  Gateway request ids come from service context, never caller arguments.
* A Cedar DENY does not invoke this function. Missing rows alone cannot prove
  non-entry because independent attempt auditing can also fail.

``get_orders`` and ``get_tickets`` read as ``pellier_agent`` with the customer
named (``common.dataapi.run_as_customer``), so row-level security holds here as
it does in process.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from common.dataapi import (
    EMBED_MODEL_ID,
    RERANK_MODEL_ID,
    query_embedding,
    rerank_documents,
    run_as_credit_writer,
    run_as_customer,
    run_store_sql,
    write_tool_audit,
    write_tool_audit_independently,
)
from common.handler import audit_read_call, tool_catalog
from common.fingerprint import deployed_fingerprint
from common.types import resolve_invocation
from gateway_tool_schemas import TOOL_SCHEMAS
from services import store_tools

logger = logging.getLogger(__name__)

TARGET = "pellier-store-tools"
RAIL = "gateway-mcp"
TOOLS_FINGERPRINT = deployed_fingerprint(Path(__file__).resolve().parent)

# A route-minted turn id. Anything else is not a shopper turn and gets no receipt.
_TURN_ID = re.compile(r"^turn-[A-Za-z0-9_-]{6,}$")
# A build fingerprint: the SHA-256 the Runtime package carries.
_BUILD = re.compile(r"^[0-9a-f]{64}$")
# Correlation the Runtime attaches beside the tool's own arguments. The audit
# row keeps them; the tool never sees them.
_CORRELATION_ARGUMENTS = ("turn_id", "build_fingerprint", "memory_record_ids_json",
                          "gateway_request_id", "tools_fingerprint")

ToolFn = Callable[[Dict[str, Any], Optional[str]], Dict[str, Any]]


def _turn_id(arguments: Dict[str, Any]) -> Optional[str]:
    value = arguments.get("turn_id")
    return value if isinstance(value, str) and _TURN_ID.fullmatch(value) else None


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def _requirements(args: Dict[str, Any], query: str) -> Optional[Dict[str, Any]]:
    """Read Runtime's bound extraction, or explicit limits on a direct tool call.

    Runtime hides and overwrites requirements_json before every catalog call.
    Direct Gateway callers may supply their own search criteria; this metadata
    is retrieval context and never an identity or authorization credential.
    """
    if "requirements_json" in args:
        reading = json.loads(args["requirements_json"])
        if not isinstance(reading, dict) or reading.get("extraction_status") == "extraction_failed":
            raise ValueError("Invalid shopper requirements")
        return reading
    in_stock_only = args.get("in_stock_only")
    exclusions = args.get("exclusions")
    if in_stock_only is None and exclusions is None:
        return None
    if isinstance(exclusions, str):
        exclusions = [exclusions]
    return {
        "in_stock_only": _bool(in_stock_only),
        "exclusions": [str(value) for value in exclusions] if isinstance(exclusions, list) else [],
        "soft_signal": query,
    }


def _search_products(args: Dict[str, Any], turn_id: Optional[str]) -> Dict[str, Any]:
    receipt = None
    if turn_id:
        receipt = {
            "turn_id": turn_id,
            "rail": RAIL,
            "embedding_model": EMBED_MODEL_ID,
            "rerank_model": RERANK_MODEL_ID,
        }
    query = str(args.get("query") or "")
    requirements = _requirements(args, query)
    return store_tools.search_products(
        run_store_sql,
        query=query,
        embed=query_embedding,
        rerank=rerank_documents,
        extracted=requirements,
        max_price=_float(args.get("max_price")),
        max_price_is_shoppers=bool((requirements or {}).get("max_price_is_shoppers")),
        min_rating=_float(args.get("min_rating")) or 0.0,
        category=args.get("category") or None,
        limit=_int(args.get("limit"), 5),
        receipt=receipt,
    )


def _browse_department(args: Dict[str, Any], turn_id: Optional[str]) -> Dict[str, Any]:
    # A browse uses the same Runtime-bound reading as the preceding search.
    requirements = _requirements(args, "")
    return store_tools.browse_department(
        run_store_sql,
        department=str(args.get("department") or ""),
        limit=_int(args.get("limit"), 5),
        extracted=requirements,
        department_named_by_shopper=bool((requirements or {}).get("department_named_by_shopper")),
        max_price=_float(args.get("max_price")),
    )


def _compare_products(args: Dict[str, Any], turn_id: Optional[str]) -> Dict[str, Any]:
    return store_tools.compare_products(
        run_store_sql,
        product_id_1=args.get("product_id_1"),
        product_id_2=args.get("product_id_2"),
    )


def _check_stock(args: Dict[str, Any], turn_id: Optional[str]) -> Dict[str, Any]:
    return store_tools.check_stock(run_store_sql, product_query=str(args.get("product_query") or ""))


def _get_orders(args: Dict[str, Any], turn_id: Optional[str]) -> Dict[str, Any]:
    customer_id = str(args.get("customer_id") or "")
    return run_as_customer(customer_id, lambda run: store_tools.get_orders(
        run, customer_id=customer_id, limit=_int(args.get("limit"), 10),
    ))


def _get_return_policy(args: Dict[str, Any], turn_id: Optional[str]) -> Dict[str, Any]:
    return store_tools.get_return_policy(
        run_store_sql, department=str(args.get("department") or "default")
    )


def _get_tickets(args: Dict[str, Any], turn_id: Optional[str]) -> Dict[str, Any]:
    customer_id = str(args.get("customer_id") or "")
    return run_as_customer(customer_id, lambda run: store_tools.get_tickets(
        run, customer_id=customer_id, limit=_int(args.get("limit"), 5),
    ))


def _give_store_credit(
    args: Dict[str, Any], turn_id: Optional[str], *, record_success: Any = None,
) -> Dict[str, Any]:
    # ``issued_by`` is not accepted from the wire. This rail has no verified
    # operator token to read, and an attribution the caller supplied would be
    # worse than none. The Operator desk attributes credits in its own review
    # record, where ``require_operator`` has already produced a verified sub.
    options = {"record_success": record_success} if record_success is not None else {}
    return run_as_credit_writer(lambda run: store_tools.give_store_credit(
        run,
        customer_id=str(args.get("customer_id") or ""),
        amount_cents=args.get("amount_cents"),
        reason=str(args.get("reason") or ""),
        idempotency_key=str(args.get("idempotency_key") or ""),
    ), **options)


def _ask_a_person(args: Dict[str, Any], turn_id: Optional[str]) -> Dict[str, Any]:
    # The Runtime binds ``customer_id`` to the signed-in shopper before the call
    # reaches the Gateway, but no verified subject reaches this function, so a
    # credit request opened here is recorded as unverified for staff to check.
    # A request carries no amount: any amount on the wire is ignored, never read.
    return store_tools.ask_a_person(
        run_store_sql,
        reason=str(args.get("reason") or ""),
        customer_id=args.get("customer_id") or None,
        credit_request=args.get("credit_request") is True,
        source_turn_id=turn_id,
        requested_by_sub=None,
        requester_kind="unverified",
    )


TOOLS: Dict[str, ToolFn] = {
    "search_products": _search_products,
    "browse_department": _browse_department,
    "compare_products": _compare_products,
    "check_stock": _check_stock,
    "get_orders": _get_orders,
    "get_return_policy": _get_return_policy,
    "get_tickets": _get_tickets,
    "give_store_credit": _give_store_credit,
    "ask_a_person": _ask_a_person,
}

_CATALOG = {tool["name"]: tool for tool in TOOL_SCHEMAS["store"]["tools"]}
assert set(TOOLS) == set(_CATALOG) == set(store_tools.TOOL_NAMES), "catalog and dispatch drifted"


def _envelope(result: Any, *, is_error: bool = False) -> Dict[str, Any]:
    """The MCP content envelope, with the same text as a record field.

    Guardrail data paths cannot index the MCP content array, so the managed
    output check on the credit tool reads ``context.output.text``.
    """
    text = json.dumps(result, default=str)
    envelope: Dict[str, Any] = {"text": text, "content": [{"type": "text", "text": text}]}
    if is_error:
        envelope["isError"] = True
    return envelope


def lambda_handler(event: dict, context: Any) -> dict:
    """Dispatch one MCP tool invocation from the Gateway, or a direct probe."""
    tool_name, arguments = resolve_invocation(event, context)

    if tool_name == "list_tools":
        return tool_catalog(_CATALOG)
    if tool_name not in TOOLS:
        return {"error": f"Unknown tool: {tool_name}"}

    started = time.monotonic()
    turn_id = _turn_id(arguments)
    build = arguments.get("build_fingerprint")
    build = build if isinstance(build, str) and _BUILD.fullmatch(build) else None
    execution_arguments = {
        key: value for key, value in arguments.items() if key not in _CORRELATION_ARGUMENTS
    }
    audited_arguments = {key: value for key, value in arguments.items()
                         if key not in {"build_fingerprint", "gateway_request_id", "tools_fingerprint"}}
    audited_arguments["tools_fingerprint"] = TOOLS_FINGERPRINT or None
    # Gateway supplies this service request id in Lambda client context. Never
    # accept an event argument as provenance. It joins the committed receipt
    # to AgentCore's aws.request.id without guessing from overlapping times.
    custom = getattr(getattr(context, "client_context", None), "custom", {}) or {}
    request_id = custom.get("bedrockAgentCoreAwsRequestId")
    if isinstance(request_id, str) and request_id:
        audited_arguments["gateway_request_id"] = request_id
    logger.info("tool_entered tool=%s gateway_request_id=%s lambda_request_id=%s",
                tool_name, request_id or "unknown", getattr(context, "aws_request_id", "unknown"))
    failed = False
    try:
        if tool_name == "give_store_credit":
            def record_success(transaction_id: str, result: Dict[str, Any]) -> None:
                write_tool_audit(
                    tool=tool_name, args=audited_arguments, result=result,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    session_id=f"gateway-{execution_arguments.get('customer_id') or 'unknown'}",
                    build_fingerprint=build, transaction_id=transaction_id,
                )
            result = _give_store_credit(execution_arguments, turn_id, record_success=record_success)
        else:
            result = TOOLS[tool_name](execution_arguments, turn_id)
    except Exception as exc:  # noqa: BLE001 - every failure becomes one envelope
        logger.error("Tool %s failed: %s", tool_name, exc)
        result = {"error": "The requested action could not be completed."}
        failed = True

    if tool_name == "give_store_credit" and result.get("status") != "success":
        # The attempt is evidence even when Aurora refused it: the receipt
        # commits on its own, so a rolled-back write still leaves its row. A
        # replay is not an attempt: ``give_store_credit`` handed back the
        # first result without touching ``store_credits``, so the retry of an
        # unchanged request keeps one credit and one audit row.
        write_tool_audit_independently(
            tool=tool_name,
            args=audited_arguments,
            result=result,
            latency_ms=int((time.monotonic() - started) * 1000),
            session_id=f"gateway-{execution_arguments.get('customer_id') or 'unknown'}",
            build_fingerprint=build,
        )
    elif tool_name != "give_store_credit":
        audit_read_call(tool_name, audited_arguments, result, started, build_fingerprint=build)
    return _envelope(result, is_error=failed)
