"""Tests for the AgentCore batch-evaluation sidecar.

The critical test here is
``test_operation_exists_in_installed_service_model``: it asserts the
operation this module calls is really present in the installed botocore
service model. The previous version of this suite stubbed a fake client
that *defined* the method it was asserting on, so an invented API name
passed. Introspecting the service model makes that failure mode
impossible.

Three states matter and all are deterministic:

  * Off by default — flag unset → ``skipped`` envelope, no boto3 call.
  * Flag on but no log group — still ``skipped``; the real API requires a
    ``dataSourceConfig``.
  * Wired — flag + log groups set → exactly one ``start_batch_evaluation``
    call with a payload that validates against the real input shape.

Sister test: ``test_golden_journeys.py`` (the day-1 CI gate).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

import services.agentcore_evals as agentcore_evals
from config import settings


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AGENTCORE_EVALS_ENABLED", True, raising=False)
    monkeypatch.setattr(
        settings,
        "AGENTCORE_EVALS_LOG_GROUPS",
        "/aws/bedrock-agentcore/runtimes/pellier",
        raising=False,
    )
    monkeypatch.setattr(
        settings, "AGENTCORE_EVALS_SERVICE_NAMES", "pellier", raising=False
    )
    monkeypatch.setattr(
        settings, "AGENTCORE_EVALS_EVALUATOR_IDS", None, raising=False
    )


def _service_model() -> Any:
    import boto3

    return (
        boto3.session.Session()
        .client("bedrock-agentcore", region_name="us-east-1")
        .meta.service_model
    )


def test_operation_exists_in_installed_service_model() -> None:
    """The operation we call must exist in the installed botocore model.

    This is the regression guard for the launch blocker: a previous
    version called ``create_evaluation_job``, which no AgentCore service
    model has ever exposed.
    """
    operations = set(_service_model().operation_names)

    assert agentcore_evals.BATCH_EVALUATION_OPERATION in operations
    assert "GetBatchEvaluation" in operations
    assert "create_evaluation_job" not in operations
    assert "CreateEvaluationJob" not in operations


def test_submitted_payload_validates_against_real_input_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every key we send must be a real member of the input shape, and
    every required member must be present."""
    shape = _service_model().operation_model(
        agentcore_evals.BATCH_EVALUATION_OPERATION
    ).input_shape

    _enable(monkeypatch)
    captured: List[Dict[str, Any]] = []

    class _Client:
        def start_batch_evaluation(self, **kwargs: Any) -> Dict[str, Any]:
            captured.append(kwargs)
            return {
                "batchEvaluationId": "be-123",
                "batchEvaluationArn": (
                    "arn:aws:bedrock-agentcore:us-east-1:123456789012:"
                    "batch-evaluation/be-123"
                ),
                "status": "IN_PROGRESS",
            }

    monkeypatch.setattr(agentcore_evals, "_client", lambda: _Client())

    result = _run(agentcore_evals.submit_batch_evaluation())

    assert result["status"] == "submitted"
    assert result["batchEvaluationId"] == "be-123"
    assert result["jobStatus"] == "IN_PROGRESS"
    assert len(captured) == 1

    payload = captured[0]
    members = set(shape.members)
    assert set(payload) <= members, f"unknown params: {set(payload) - members}"
    required = set(getattr(shape, "required_members", []) or [])
    assert required <= set(payload), f"missing required: {required - set(payload)}"

    cw = payload["dataSourceConfig"]["cloudWatchLogs"]
    assert cw["logGroupNames"] == ["/aws/bedrock-agentcore/runtimes/pellier"]
    assert cw["serviceNames"] == ["pellier"]
    # The obsolete parameter model must never come back.
    assert "datasetArn" not in payload
    assert "jobRoleArn" not in payload
    assert "agentRuntimeArn" not in payload


def test_session_ids_become_a_filter_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restricting to specific sessions uses the real filterConfig block."""
    _enable(monkeypatch)
    captured: List[Dict[str, Any]] = []

    class _Client:
        def start_batch_evaluation(self, **kwargs: Any) -> Dict[str, Any]:
            captured.append(kwargs)
            return {"batchEvaluationId": "be-9", "status": "IN_PROGRESS"}

    monkeypatch.setattr(agentcore_evals, "_client", lambda: _Client())

    _run(agentcore_evals.submit_batch_evaluation(session_ids=["s-1", "s-2"]))

    filters = captured[0]["dataSourceConfig"]["cloudWatchLogs"]["filterConfig"]
    assert filters["sessionIds"] == ["s-1", "s-2"]


def test_evaluator_ids_are_sent_as_structures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evaluators are a list of {evaluatorId}, not bare strings."""
    _enable(monkeypatch)
    monkeypatch.setattr(
        settings, "AGENTCORE_EVALS_EVALUATOR_IDS", "ev-a, ev-b", raising=False
    )
    captured: List[Dict[str, Any]] = []

    class _Client:
        def start_batch_evaluation(self, **kwargs: Any) -> Dict[str, Any]:
            captured.append(kwargs)
            return {"batchEvaluationId": "be-1", "status": "IN_PROGRESS"}

    monkeypatch.setattr(agentcore_evals, "_client", lambda: _Client())

    _run(agentcore_evals.submit_batch_evaluation())

    assert captured[0]["evaluators"] == [
        {"evaluatorId": "ev-a"},
        {"evaluatorId": "ev-b"},
    ]


def test_skipped_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default state: flag false → skipped envelope, no AWS call."""
    monkeypatch.setattr(settings, "AGENTCORE_EVALS_ENABLED", False, raising=False)
    monkeypatch.setattr(
        settings,
        "AGENTCORE_EVALS_LOG_GROUPS",
        "/aws/bedrock-agentcore/runtimes/pellier",
        raising=False,
    )

    result = _run(agentcore_evals.submit_batch_evaluation())

    assert result["status"] == "skipped"
    assert "AGENTCORE_EVALS_ENABLED" in result["reason"]
    assert result["configuration"]["configured"] is False


def test_skipped_when_flag_on_but_log_groups_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag on with no log group → still skipped; the API needs a source."""
    monkeypatch.setattr(settings, "AGENTCORE_EVALS_ENABLED", True, raising=False)
    monkeypatch.setattr(
        settings, "AGENTCORE_EVALS_LOG_GROUPS", None, raising=False
    )

    result = _run(agentcore_evals.submit_batch_evaluation())

    assert result["status"] == "skipped"
    assert agentcore_evals.is_enabled() is False


def test_describe_configuration_envelope_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configuration envelope's keys are a contract — pin them."""
    _enable(monkeypatch)

    cfg = agentcore_evals.describe_configuration()

    assert cfg["configured"] is True
    assert cfg["flag"] == "AGENTCORE_EVALS_ENABLED"
    assert cfg["operation"] == "StartBatchEvaluation"
    assert cfg["logGroupNames"] == ["/aws/bedrock-agentcore/runtimes/pellier"]
    assert cfg["dailyCiGate"] == "tests/test_golden_journeys.py"


def test_submit_error_is_structured_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An SDK failure returns an envelope so the surface still renders."""
    _enable(monkeypatch)

    class _Client:
        def start_batch_evaluation(self, **kwargs: Any) -> Dict[str, Any]:
            raise RuntimeError("AccessDeniedException")

    monkeypatch.setattr(agentcore_evals, "_client", lambda: _Client())

    result = _run(agentcore_evals.submit_batch_evaluation())

    assert result["status"] == "error"
    assert "AccessDenied" in result["reason"]


def test_get_batch_evaluation_surfaces_evaluator_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reading a batch returns per-evaluator summaries for the surface."""
    _enable(monkeypatch)

    class _Client:
        def get_batch_evaluation(self, **kwargs: Any) -> Dict[str, Any]:
            assert kwargs == {"batchEvaluationId": "be-123"}
            return {
                "batchEvaluationId": "be-123",
                "status": "COMPLETED",
                "evaluationResults": {
                    "totalNumberOfSessions": 12,
                    "numberOfSessionsCompleted": 12,
                    "evaluatorSummaries": [
                        {
                            "evaluatorId": "ev-a",
                            "statistics": {"averageScore": 0.91},
                            "totalEvaluated": 12,
                            "totalFailed": 0,
                        }
                    ],
                },
            }

    monkeypatch.setattr(agentcore_evals, "_client", lambda: _Client())

    result = _run(agentcore_evals.get_batch_evaluation("be-123"))

    assert result["status"] == "ok"
    assert result["jobStatus"] == "COMPLETED"
    assert result["results"]["totalNumberOfSessions"] == 12
    assert result["evaluatorSummaries"][0]["statistics"]["averageScore"] == 0.91


def test_get_batch_evaluation_requires_an_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty id is a structured error, not a boto3 call."""
    _enable(monkeypatch)

    result = _run(agentcore_evals.get_batch_evaluation(""))

    assert result["status"] == "error"
    assert "required" in result["reason"]


# ---------------------------------------------------------------------------
# Provenance states (audit finding C2)
# ---------------------------------------------------------------------------
