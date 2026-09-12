"""IAM-authenticated Runtime entrypoint for the read-only Operator graph.

Only the Pellier backend invokes this runtime. It authenticates the staff member
and reads scoped evidence before invocation. This package has no business tools;
approval and execution remain separate backend requests.
"""
from __future__ import annotations

import os
import json
from dataclasses import asdict
from typing import Any

os.environ["PELLIER_OPERATOR_RUNTIME"] = "true"

from services.otel_content_redaction import apply_model_content_redaction

apply_model_content_redaction(enabled=True)

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from services.operator_graph import run_operator_graph

app = BedrockAgentCoreApp()
_TEXT_LIMITS = {
    "request": 8000,
    "evidence_text": 100000,
    "memory_text": 16000,
    "contract": 16000,
    "context_block": 32000,
    "checkpoint_state": 64,
    "action_hash": 128,
}


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Accept a bounded evidence envelope, never a request to execute a tool."""
    if not isinstance(payload, dict):
        return {"error": "invalid_operator_request"}
    if set(payload) - set(_TEXT_LIMITS) - {"shopper_handoff", "review_id"}:
        return {"error": "invalid_operator_request"}
    for key, limit in _TEXT_LIMITS.items():
        value = payload.get(key, "")
        if not isinstance(value, str) or len(value) > limit:
            return {"error": "invalid_operator_request"}
    if not all(payload.get(key) for key in ("request", "contract", "evidence_text")):
        return {"error": "invalid_operator_request"}
    handoff = payload.get("shopper_handoff")
    if handoff is not None and (
        not isinstance(handoff, dict)
        or len(json.dumps(handoff)) > 16000
    ):
        return {"error": "invalid_operator_request"}
    review_id = payload.get("review_id")
    if review_id is not None and (type(review_id) is not int or review_id <= 0):
        return {"error": "invalid_operator_request"}
    if payload.get("checkpoint_state", "READ_ONLY_COMPLETE") not in {
        "READ_ONLY_COMPLETE", "WAITING_FOR_HUMAN",
    }:
        return {"error": "invalid_operator_request"}
    result = run_operator_graph(**{"memory_text": "", **payload})
    return {
        **asdict(result),
        "build_fingerprint": os.environ.get("PELLIER_BUILD_FINGERPRINT", ""),
    }


if __name__ == "__main__":
    app.run()
