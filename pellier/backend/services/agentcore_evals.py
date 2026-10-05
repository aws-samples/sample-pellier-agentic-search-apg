"""AgentCore batch evaluation sidecar — the prod-cutover graduation path.

This module is the single end-to-end wired example for Amazon Bedrock
AgentCore Evaluations. It is **off by default**: the golden-set regression
in ``tests/test_golden_journeys.py`` is the workshop's day-1 CI gate
(cheap, deterministic, no AWS calls). AgentCore batch evaluation is the
graduation path — opt in by setting ``AGENTCORE_EVALS_ENABLED=true`` and
naming the CloudWatch log groups the managed Runtime writes sessions to.

Why CloudWatch log groups and not a dataset ARN: AgentCore batch
evaluation scores *observed agent sessions*. ``StartBatchEvaluation``
takes a ``dataSourceConfig.cloudWatchLogs`` block naming the service and
log groups to read sessions from; ground truth (assertions, expected tool
trajectory) rides along per session in
``evaluationMetadata.sessionMetadata``. There is no dataset ARN, no job
role, and no evaluator-model parameter on this API.

Verified against botocore's ``bedrock-agentcore`` service model: the
available operations are ``Evaluate``, ``StartBatchEvaluation``,
``GetBatchEvaluation``, ``ListBatchEvaluations``, ``StopBatchEvaluation``,
and ``DeleteBatchEvaluation``. Evaluator definitions live on the
``bedrock-agentcore-control`` plane (``CreateEvaluator`` /
``ListEvaluators``).

Sister artifact: ``tests/test_golden_journeys.py`` (the day-1 gate).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)

# The real operation name, asserted by the unit test against the live
# botocore service model so this module can never drift back onto an
# invented API.
BATCH_EVALUATION_OPERATION = "StartBatchEvaluation"

_SERVICE_NAME = "bedrock-agentcore"


def _csv_setting(raw: Optional[str]) -> List[str]:
    """Split a comma-separated setting into a clean list."""
    if not raw:
        return []
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def log_groups() -> List[str]:
    """CloudWatch log groups holding the agent sessions to evaluate."""
    return _csv_setting(settings.AGENTCORE_EVALS_LOG_GROUPS)


def service_names() -> List[str]:
    """Service names scoping the CloudWatch data source."""
    return _csv_setting(settings.AGENTCORE_EVALS_SERVICE_NAMES) or ["pellier"]


def evaluator_ids() -> List[str]:
    """Evaluator ids created on the control plane (``CreateEvaluator``)."""
    return _csv_setting(settings.AGENTCORE_EVALS_EVALUATOR_IDS)


def is_enabled() -> bool:
    """Return True only when the flag is set and a log group is named.

    The flag alone is not enough: ``StartBatchEvaluation`` requires a
    ``dataSourceConfig`` naming at least one CloudWatch log group, so
    without one the call would fail at the SDK boundary.
    """
    return bool(settings.AGENTCORE_EVALS_ENABLED and log_groups())


def describe_configuration() -> Dict[str, Any]:
    """The evaluation sidecar's configuration envelope.

    Returns the same envelope whether the sidecar runs or not, so a caller
    can tell an off state from a wired one without inspecting credentials.
    """
    return {
        "configured": is_enabled(),
        "flag": "AGENTCORE_EVALS_ENABLED",
        "serviceNames": service_names(),
        "logGroupNames": log_groups(),
        "evaluatorIds": evaluator_ids(),
        "operation": BATCH_EVALUATION_OPERATION,
        "mode": "prod-cutover graduation path",
        "dailyCiGate": "tests/test_golden_journeys.py",
    }


def _client() -> Any:
    import boto3

    return boto3.client(_SERVICE_NAME, region_name=settings.aws_region_resolved)


def _skipped() -> Dict[str, Any]:
    return {
        "status": "skipped",
        "reason": (
            "AGENTCORE_EVALS_ENABLED is false or "
            "AGENTCORE_EVALS_LOG_GROUPS is not set"
        ),
        "configuration": describe_configuration(),
    }


async def submit_batch_evaluation(
    *,
    batch_name: Optional[str] = None,
    session_ids: Optional[List[str]] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Start one AgentCore batch evaluation over recorded agent sessions.

    Args:
        batch_name: Name for this batch. Defaults to
            ``pellier-governed-batch``.
        session_ids: Optional session ids to restrict the CloudWatch data
            source to. When omitted, the evaluation covers every session
            the log groups expose.
        description: Optional human-readable description stored on the
            batch.

    Returns:
        A structured envelope: ``{"status": "submitted"|"skipped"|"error",
        ...}``. ``skipped`` is the steady state — the sidecar is
        deliberately off by default so attendees see the wiring without
        firing real AWS jobs on every PR.
    """
    if not is_enabled():
        return _skipped()

    data_source: Dict[str, Any] = {
        "cloudWatchLogs": {
            "serviceNames": service_names(),
            "logGroupNames": log_groups(),
        }
    }
    if session_ids:
        data_source["cloudWatchLogs"]["filterConfig"] = {
            "sessionIds": list(session_ids)
        }

    payload: Dict[str, Any] = {
        "batchEvaluationName": batch_name or "pellier-governed-batch",
        "dataSourceConfig": data_source,
    }
    if evaluator_ids():
        payload["evaluators"] = [
            {"evaluatorId": evaluator_id} for evaluator_id in evaluator_ids()
        ]
    if description:
        payload["description"] = description

    try:
        import asyncio

        client = _client()
        response = await asyncio.to_thread(
            lambda: client.start_batch_evaluation(**payload)
        )
    except Exception as exc:  # pragma: no cover - SDK/credential error path
        logger.error("AgentCore batch evaluation submission failed: %s", exc)
        return {"status": "error", "reason": str(exc), "request": payload}

    return {
        "status": "submitted",
        "batchEvaluationId": response.get("batchEvaluationId"),
        "batchEvaluationArn": response.get("batchEvaluationArn"),
        "jobStatus": response.get("status"),
        "request": payload,
    }


async def get_batch_evaluation(batch_evaluation_id: str) -> Dict[str, Any]:
    """Read the status and per-evaluator summaries for one batch.

    Args:
        batch_evaluation_id: The id returned by
            :func:`submit_batch_evaluation`.

    Returns:
        ``{"status": "ok", "jobStatus": ..., "results": {...},
        "evaluatorSummaries": [...]}`` on success, or a structured
        ``skipped``/``error`` envelope.
    """
    if not is_enabled():
        return _skipped()
    if not batch_evaluation_id:
        return {"status": "error", "reason": "batch_evaluation_id is required"}

    try:
        import asyncio

        client = _client()
        response = await asyncio.to_thread(
            lambda: client.get_batch_evaluation(
                batchEvaluationId=batch_evaluation_id
            )
        )
    except Exception as exc:  # pragma: no cover - SDK/credential error path
        logger.error("AgentCore batch evaluation read failed: %s", exc)
        return {"status": "error", "reason": str(exc)}

    results = response.get("evaluationResults") or {}
    return {
        "status": "ok",
        "batchEvaluationId": response.get("batchEvaluationId"),
        "jobStatus": response.get("status"),
        "results": results,
        "evaluatorSummaries": results.get("evaluatorSummaries") or [],
        "errorDetails": response.get("errorDetails"),
    }
