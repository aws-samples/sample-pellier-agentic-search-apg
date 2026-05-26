"""AgentCore Evals sidecar — Batch 4 evals spike (graduation path).

This module is the single end-to-end wired example for Bedrock AgentCore
Evals. It is **off by default**: the golden-set regression in
``tests/test_golden_journeys.py`` is the workshop's day-1 CI gate (cheap,
deterministic, no AWS calls). AgentCore Evals is the *prod-cutover*
graduation path — opt in by flipping ``AGENTCORE_EVALS_ENABLED=true``
and supplying a dataset ARN in ``backend/.env``.

The single entry point :func:`submit_evaluation_job` accepts the same
agent runtime ARN the Challenge 5 path already targets, plus the dataset
ARN the workshop facilitator provisions ahead of the prod-cutover demo.
It returns a structured envelope so the Atelier Measure surface can
render either ``configured: false`` (no flag) or ``configured: true``
with the AWS job ARN (flag flipped).

Sister artifact: ``tests/test_golden_journeys.py`` (the day-1 gate).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from config import settings

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    """Return True only when both the env flag is set and a dataset ARN
    is configured. The flag alone is not enough — without a dataset,
    ``create_evaluation_job`` would fail at the SDK boundary."""
    return bool(
        settings.AGENTCORE_EVALS_ENABLED
        and settings.AGENTCORE_EVALS_DATASET_ARN
    )


def describe_configuration() -> Dict[str, Any]:
    """Surface-shape used by the Atelier Measure copy — same envelope
    whether the sidecar runs or not, so the frontend can render a clear
    "off / wired" state without inspecting credentials."""
    return {
        "configured": is_enabled(),
        "flag": "AGENTCORE_EVALS_ENABLED",
        "datasetArn": settings.AGENTCORE_EVALS_DATASET_ARN,
        "jobRoleArn": settings.AGENTCORE_EVALS_JOB_ROLE_ARN,
        "mode": "prod-cutover graduation path",
        "dailyCiGate": "tests/test_golden_journeys.py",
    }


async def submit_evaluation_job(
    *,
    agent_runtime_arn: Optional[str] = None,
    dataset_arn: Optional[str] = None,
    job_role_arn: Optional[str] = None,
    evaluator_model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Kick off a single AgentCore Evals job against ``agent_runtime_arn``.

    Args:
        agent_runtime_arn: The deployed agent under evaluation. Defaults
            to ``settings.AGENTCORE_RUNTIME_ENDPOINT`` so the same ARN
            the Challenge 5 path targets is reused.
        dataset_arn: The Evals dataset ARN to score against. Defaults
            to ``settings.AGENTCORE_EVALS_DATASET_ARN``.
        job_role_arn: IAM role for the eval job. Defaults to
            ``settings.AGENTCORE_EVALS_JOB_ROLE_ARN``.
        evaluator_model_id: Optional override for the evaluator model;
            falls back to the Opus model already used by editorial
            specialists so a single Bedrock model is enough for the demo.

    Returns:
        A structured envelope: ``{"status": "submitted"|"skipped"|"error",
        ...}``. ``skipped`` is the steady state — the spike is deliberately
        off-by-default so attendees see the catalog without firing real
        AWS jobs every PR.
    """
    if not is_enabled():
        return {
            "status": "skipped",
            "reason": (
                "AGENTCORE_EVALS_ENABLED is false or "
                "AGENTCORE_EVALS_DATASET_ARN is not set"
            ),
            "configuration": describe_configuration(),
        }

    runtime_arn = agent_runtime_arn or settings.AGENTCORE_RUNTIME_ENDPOINT
    if not runtime_arn:
        return {
            "status": "error",
            "reason": "no agent runtime ARN configured (set AGENTCORE_RUNTIME_ENDPOINT)",
        }

    try:
        import asyncio

        import boto3
    except ImportError:
        logger.warning("boto3 not installed — skipping AgentCore Evals submission")
        return {
            "status": "error",
            "reason": "boto3 unavailable in this environment",
        }

    client = boto3.client(
        "bedrock-agentcore",
        region_name=getattr(settings, "aws_region_resolved", settings.AWS_REGION),
    )

    payload = {
        "agentRuntimeArn": runtime_arn,
        "datasetArn": dataset_arn or settings.AGENTCORE_EVALS_DATASET_ARN,
        "jobRoleArn": job_role_arn or settings.AGENTCORE_EVALS_JOB_ROLE_ARN,
        "evaluatorModelId": evaluator_model_id or settings.BEDROCK_OPUS_MODEL,
    }

    def _invoke() -> Dict[str, Any]:
        return client.create_evaluation_job(**payload)

    try:
        response = await asyncio.to_thread(_invoke)
    except Exception as exc:  # pragma: no cover - SDK error path
        logger.error("AgentCore Evals submission failed: %s", exc)
        return {"status": "error", "reason": str(exc)}

    return {
        "status": "submitted",
        "jobArn": response.get("evaluationJobArn") or response.get("jobArn"),
        "request": payload,
    }
