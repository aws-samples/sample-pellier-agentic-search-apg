"""AgentCore entrypoint for the staff Investigator → Advisor Strands graph.

The signed caller supplies staff authority. The request selects a case, then
immutable tool closures carry both through Gateway. This Runtime holds no
database credentials and exposes no approval or credit execution operation.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from services.runtime_env import bridge_cli_injected_names
from services.otel_content_redaction import (
    apply_model_content_redaction,
    redact_adot_mcp_tool_content,
    withhold_botocore_message_content,
)

os.environ.update(bridge_cli_injected_names(os.environ))
apply_model_content_redaction(enabled=True)
redact_adot_mcp_tool_content()
withhold_botocore_message_content()

from services.operator_gateway import operator_tools
from services.operator_graph import run_investigation
from services.runtime_identity import RuntimeIdentityError, verified_operator_identity

logger = logging.getLogger(__name__)
app = BedrockAgentCoreApp()


def _no_database(*_args, **_kwargs):
    raise RuntimeError("operator_runtime_has_no_database_access")


@app.entrypoint
async def invoke(payload, context=None):
    """Stream actual graph steps and one terminal result, with source provenance."""
    try:
        if not isinstance(payload, dict):
            raise RuntimeIdentityError("invalid_request")
        headers = getattr(context, "request_headers", None) or {}
        auth = headers.get("Authorization") or headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            raise RuntimeIdentityError("authentication_required")
        token = auth[7:].strip()
        identity = verified_operator_identity(token, payload)
        turn_id = payload.get("turn_id")
        if not isinstance(turn_id, str) or not re.fullmatch(r"turn-[A-Za-z0-9_-]{6,}", turn_id):
            raise RuntimeIdentityError("invalid_turn")
        operation = payload.get("operation", "investigate")
        if operation not in {"inspect", "investigate"}:
            raise RuntimeIdentityError("invalid_operation")
        fingerprint = os.environ.get("PELLIER_BUILD_FINGERPRINT", "")
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise RuntimeIdentityError("operator_build_not_configured")
    except RuntimeIdentityError as exc:
        yield {"event": "error", "data": {"detail": str(exc)}}
        return

    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def post(event, data):
        loop.call_soon_threadsafe(queue.put_nowait, {"event": event, "data": data})

    def work():
        try:
            with operator_tools(token=token, identity=identity, turn_id=turn_id,
                                build_fingerprint=fingerprint) as call:
                customer = call("get_case", {})
                if operation == "inspect":
                    result = {"status": "ready", "turnId": turn_id, "customerId": identity.customer_id,
                              "case_access": {key: customer[key] for key in (
                                  "database_role", "visible_orders", "visible_tickets")},
                              "graph": {"pattern": "strands-graph", "execution": "gateway-mcp"}}
                else:
                    result = run_investigation(
                        run=_no_database, run_customer=_no_database, customer_id=identity.customer_id,
                        customer_name=customer["name"], operator_sub=identity.subject, turn_id=turn_id,
                        emit=lambda step: post("step", step), call_tool=call,
                    ).as_payload()
                post("complete", {**result, "build_fingerprint": fingerprint,
                                  "rail": "gateway-mcp", "orchestration": "strands-graph"})
        except Exception as exc:
            logger.warning("staff Runtime failed kind=%s", type(exc).__name__)
            post("error", {"detail": "operator_runtime_failed", "turnId": turn_id})
        finally:
            post(None, {})

    task = asyncio.create_task(asyncio.to_thread(work))
    try:
        while True:
            event = await queue.get()
            if event["event"] is None:
                break
            yield event
        await task
    finally:
        # Cancelling a relay cannot interrupt the thread. Its only write is a
        # pending, deduplicated proposal; it can never approve or pay one.
        if not task.done():
            task.cancel()


if __name__ == "__main__":
    app.run()
