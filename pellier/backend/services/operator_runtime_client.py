"""JWT-authenticated staff Runtime transport; no local fallback after Lab 3."""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

SAFE_FAILURES = frozenset({
    "authentication_required", "authentication_failed", "auth_unavailable", "auth_not_configured",
    "staff_scope_required", "staff_identity_mismatch", "invalid_customer", "invalid_turn",
    "invalid_request", "invalid_operation", "operator_build_not_configured", "operator_runtime_failed",
})

class OperatorRuntimeError(RuntimeError):
    """Safe failure codes, never tokens, response bodies or customer records."""


def investigate_on_runtime(*, customer_id, operator_sub, access_token, turn_id, emit,
                           operation="investigate", endpoint=None, region=None):
    if endpoint is None or region is None:
        from config import settings
        endpoint = endpoint or settings.AGENTCORE_OPERATOR_RUNTIME_ENDPOINT
        region = region or settings.aws_region_resolved
    if not endpoint:
        raise OperatorRuntimeError("operator_runtime_not_configured")
    if not access_token:
        raise OperatorRuntimeError("authentication_required")
    session = hashlib.sha256(f"{operator_sub}:{customer_id}:{turn_id}".encode()).hexdigest()
    url = (f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/"
           f"{urllib.parse.quote(endpoint, safe='')}/invocations?qualifier=DEFAULT")
    request = urllib.request.Request(url, method="POST", data=json.dumps({
        "customer_id": customer_id, "operator_sub": operator_sub, "turn_id": turn_id,
        "operation": operation,
    }).encode(), headers={
        "Authorization": f"Bearer {access_token}", "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session,
    })
    result = None
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            for line in response:
                if not line.startswith(b"data: "):
                    continue
                try:
                    frame = json.loads(line[6:])
                except ValueError as exc:
                    raise OperatorRuntimeError("operator_runtime_invalid_response") from exc
                if not isinstance(frame, dict):
                    raise OperatorRuntimeError("operator_runtime_invalid_response")
                kind, data = frame.get("event"), frame.get("data")
                if not isinstance(data, dict):
                    raise OperatorRuntimeError("operator_runtime_invalid_response")
                if kind == "error":
                    detail = data.get("detail")
                    raise OperatorRuntimeError(detail if isinstance(detail, str) and detail in SAFE_FAILURES
                                               else "operator_runtime_failed")
                if kind == "step":
                    emit(data)
                elif kind == "complete":
                    result = data
    except urllib.error.HTTPError as exc:
        code = "authentication_failed" if exc.code == 401 else (
            "staff_scope_required" if exc.code == 403 else "operator_runtime_unavailable")
        raise OperatorRuntimeError(code) from exc
    except (OSError, ValueError) as exc:
        raise OperatorRuntimeError("operator_runtime_unavailable") from exc
    if (not result or not isinstance(result.get("graph"), dict)
            or result.get("customerId") != customer_id or result.get("turnId") != turn_id
            or result.get("rail") != "gateway-mcp" or result.get("orchestration") != "strands-graph"
            or not result.get("build_fingerprint")
            or result.get("graph", {}).get("execution") != "gateway-mcp"):
        raise OperatorRuntimeError("operator_runtime_invalid_response")
    return result
