"""Backend bridge to the separate, IAM-authenticated Operator Runtime."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from services.operator_graph import GRAPH_ID, GRAPH_PATTERN, OperatorGraphResult

logger = logging.getLogger(__name__)
DEPLOYMENT_TARGET = "Amazon Bedrock AgentCore Runtime (Operator)"


def invoke_operator_runtime(**payload: Any) -> OperatorGraphResult:
    """Fail closed on an unavailable or stale managed package; never run locally."""
    import boto3
    from botocore.config import Config
    from config import settings
    from pathlib import Path
    from services.build_fingerprint import compute_fingerprint

    endpoint = settings.AGENTCORE_OPERATOR_RUNTIME_ENDPOINT or ""
    session_id = f"pellier-operator-{uuid.uuid4()}"
    metadata = {
        "graphId": GRAPH_ID,
        "pattern": GRAPH_PATTERN,
        "execution": "agentcore-runtime",
        "deploymentTarget": DEPLOYMENT_TARGET,
        "runtimeArn": endpoint,
        "runtimeSessionId": session_id,
        "status": "failed",
        "executedNodes": [],
    }
    if not endpoint:
        return OperatorGraphResult("", "", metadata, "operator_runtime_unconfigured")
    try:
        client = boto3.client(
            "bedrock-agentcore",
            region_name=settings.AWS_REGION,
            config=Config(
                connect_timeout=10, read_timeout=210,
                retries={"total_max_attempts": 1},
            ),
        )
        response = client.invoke_agent_runtime(
            agentRuntimeArn=endpoint,
            runtimeSessionId=session_id,
            qualifier="DEFAULT",
            contentType="application/json",
            accept="application/json",
            payload=json.dumps(payload, default=str).encode(),
        )
        stream = response["response"]
        try:
            decoded = json.loads(stream.read(1024 * 1024))
        finally:
            stream.close()
        expected = compute_fingerprint(Path(__file__).resolve().parents[1])
        if not isinstance(decoded, dict) or decoded.get("build_fingerprint") != expected:
            raise ValueError("operator_runtime_build_mismatch")
        observed = decoded.get("metadata") or {}
        nodes = observed.get("executedNodes") or []
        if (
            decoded.get("error")
            or observed.get("graphId") != GRAPH_ID
            or observed.get("execution") != "agentcore-runtime"
            or observed.get("status") != "complete"
            or [node.get("nodeId") for node in nodes] != [
                "case-investigator", "resolution-planner",
            ]
            or any(node.get("status") != "completed" for node in nodes)
            or not isinstance(decoded.get("raw"), str)
            or not decoded["raw"].strip()
        ):
            raise ValueError("operator_runtime_invalid_result")
        return OperatorGraphResult(
            raw=decoded["raw"],
            model_id=str(decoded.get("model_id") or ""),
            metadata={
                **observed,
                **{key: value for key, value in metadata.items() if key not in ("status", "executedNodes")},
                "buildFingerprint": expected,
                "fingerprintMatches": True,
                "requestId": response.get("ResponseMetadata", {}).get("RequestId", ""),
            },
        )
    except Exception as exc:
        # Do not log the evidence envelope, model output, or service error body.
        logger.warning("Operator Runtime failed: %s", type(exc).__name__)
        return OperatorGraphResult("", "", metadata, "operator_runtime_unavailable")
