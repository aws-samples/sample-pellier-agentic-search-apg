#!/usr/bin/env python3
"""Call one Gateway tool as a named Cognito user and report what Cedar decided.

One job: mint a real access token for one workshop test user, call one
published tool through the deployed Gateway, classify the outcome, and count
the evidence rows the call left in Aurora. ``provision_agentcore_end_to_end.py``
runs it twice as the live policy proof (a shopper read that must be ALLOWed
with its audit row, and a shopper store credit that must be a Cedar DENY with
no rows); it also answers by hand when a deployment needs checking.

Outcome classification is the one the Lab 3 and Lab 4 probes use
(``gateway_client.is_policy_denial_text``): a 401, a validation failure or a
transport error is ``error``, never a policy decision.

Evidence is keyed by what the call carried. A ``--turn-id`` keys the audit
row the Lambda writes for a correlated read. An ``idempotency_key`` argument
keys the attempt receipt in ``pellier.tool_audit`` and the credit in
``pellier.store_credits``.

Usage::

    python3 scripts/deploy/gateway_policy_probe.py --user theo \\
        --tool get_return_policy --arguments '{"department": "Home"}' \\
        --turn-id turn-readiness-check --expect allow

    python3 scripts/deploy/gateway_policy_probe.py --user theo \\
        --tool give_store_credit --arguments '{"customer_id": "CUST-READINESS-PROBE",
        "amount_cents": 100, "reason": "readiness probe",
        "idempotency_key": "readiness-check"}' --expect deny
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from gateway_client import (
    _exception_summary,
    _is_authorization_denial,
    _jsonable,
    _load_env,
    _require,
    _token_from_cognito,
)

DEFAULT_TARGET = "pellier-store-tools"


async def _call_tool(gateway_url: str, token: str, action: str, arguments: dict[str, Any]) -> Any:
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(30.0, read=300.0),
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(gateway_url, http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(action, arguments)


def classify_call(call: Any, exc: BaseException | None) -> dict[str, Any]:
    """Name the outcome of one Gateway call: ``allow``, ``deny`` or ``error``.

    A raised Cedar denial is ``deny`` and nothing else is: the tool was never
    entered. A result the Lambda marked ``isError`` is ``error`` with the tool
    entered, so a failure inside the tool cannot pose as a policy decision.
    """
    if exc is not None:
        denied = _is_authorization_denial(exc)
        return {
            "outcome": "deny" if denied else "error",
            "cedar_denial": denied,
            "tool_executed": False if denied else None,
            "error_type": exc.__class__.__name__,
            "error": _exception_summary(exc),
        }
    if bool(getattr(call, "isError", False)):
        return {
            "outcome": "error",
            "cedar_denial": False,
            "tool_executed": True,
            "error_type": "ToolError",
            "error": json.dumps(_jsonable(getattr(call, "content", None)), default=str)[:700],
        }
    return {"outcome": "allow", "cedar_denial": False, "tool_executed": True, "result": _jsonable(call)}


def _db_connect() -> Any:
    import psycopg

    return psycopg.connect(
        host=_require("DB_HOST"),
        port=os.environ.get("DB_PORT", "5432"),
        user=_require("DB_USER"),
        password=_require("DB_PASSWORD"),
        dbname=_require("DB_NAME"),
    )


def gather_evidence(tool: str, *, turn_id: str, idempotency_key: str) -> dict[str, Any]:
    """Count the rows this call could have left, keyed by what it carried."""
    evidence: dict[str, Any] = {}
    with _db_connect() as conn:
        with conn.cursor() as cur:
            if turn_id:
                cur.execute(
                    "SELECT audit_id, session_id FROM pellier.tool_audit "
                    "WHERE tool = %s AND caller = 'gateway' AND session_id = %s "
                    "ORDER BY audit_id",
                    (tool, turn_id),
                )
                rows = cur.fetchall()
                evidence["tool_audit_rows"] = len(rows)
                evidence["tool_audit_row"] = (
                    {"audit_id": int(rows[-1][0]), "session_id": str(rows[-1][1])} if rows else None
                )
            if idempotency_key:
                cur.execute(
                    "SELECT count(*) FROM pellier.tool_audit "
                    "WHERE tool = %s AND args->>'idempotency_key' = %s",
                    (tool, idempotency_key),
                )
                evidence["tool_audit_rows"] = int(cur.fetchone()[0])
                cur.execute(
                    "SELECT count(*) FROM pellier.store_credits WHERE idempotency_key = %s",
                    (idempotency_key,),
                )
                evidence["store_credits_rows"] = int(cur.fetchone()[0])
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Call one Gateway tool and report the Cedar outcome.")
    parser.add_argument("--user", required=True, help="Cognito test username, e.g. theo")
    parser.add_argument("--tool", required=True, help="Logical tool name, e.g. get_return_policy")
    parser.add_argument("--arguments", default="{}", help="Tool arguments as JSON")
    parser.add_argument("--turn-id", default="", help="Correlation id for a read's audit row")
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--gateway-url", default="")
    parser.add_argument("--expect", choices=("allow", "deny"), default="")
    args = parser.parse_args()

    import anyio

    _load_env()
    gateway_url = args.gateway_url or _require("AGENTCORE_GATEWAY_URL")
    arguments = json.loads(args.arguments)
    if not isinstance(arguments, dict):
        raise SystemExit("--arguments must be a JSON object")
    if args.turn_id:
        arguments["turn_id"] = args.turn_id
    action = f"{args.target}___{args.tool}"
    token = _token_from_cognito(args.user)

    call, failure = None, None
    try:
        call = anyio.run(_call_tool, gateway_url, token, action, arguments)
    except Exception as exc:  # noqa: BLE001 - every failure shape is classified below
        failure = exc

    payload: dict[str, Any] = {
        "principal": args.user,
        "tool": args.tool,
        "action": action,
        "arguments": arguments,
        "turn_id": args.turn_id,
        "idempotency_key": str(arguments.get("idempotency_key") or ""),
        **classify_call(call, failure),
    }
    payload["evidence"] = gather_evidence(
        args.tool, turn_id=args.turn_id, idempotency_key=payload["idempotency_key"]
    )
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if not args.expect or payload["outcome"] == args.expect else 2


if __name__ == "__main__":
    raise SystemExit(main())
