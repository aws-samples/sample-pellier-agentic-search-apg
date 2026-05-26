"""Tests for the AgentCore Evals sidecar (Batch 4 evals spike).

Two states matter and both must be deterministic:

  * Off by default — flag unset → ``submit_evaluation_job`` returns a
    structured ``skipped`` envelope without touching boto3. This is the
    steady state the workshop ships in.
  * Wired — flag + dataset ARN set → ``submit_evaluation_job`` calls
    ``bedrock-agentcore.create_evaluation_job`` exactly once with the
    configured payload. We stub ``boto3.client`` so the test never hits
    AWS.

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


def test_skipped_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default state: flag false → skipped envelope, no AWS call."""
    monkeypatch.setattr(settings, "AGENTCORE_EVALS_ENABLED", False, raising=False)
    monkeypatch.setattr(
        settings, "AGENTCORE_EVALS_DATASET_ARN", None, raising=False
    )

    result = _run(agentcore_evals.submit_evaluation_job())

    assert result["status"] == "skipped"
    assert "AGENTCORE_EVALS_ENABLED" in result["reason"]
    assert result["configuration"]["configured"] is False


def test_skipped_when_flag_on_but_dataset_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag on but dataset ARN unset → still skipped — `is_enabled` requires both."""
    monkeypatch.setattr(settings, "AGENTCORE_EVALS_ENABLED", True, raising=False)
    monkeypatch.setattr(
        settings, "AGENTCORE_EVALS_DATASET_ARN", None, raising=False
    )

    result = _run(agentcore_evals.submit_evaluation_job())

    assert result["status"] == "skipped"
    assert agentcore_evals.is_enabled() is False


def test_describe_configuration_envelope_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Atelier Measure surface relies on the envelope keys — pin them."""
    monkeypatch.setattr(settings, "AGENTCORE_EVALS_ENABLED", True, raising=False)
    monkeypatch.setattr(
        settings,
        "AGENTCORE_EVALS_DATASET_ARN",
        "arn:aws:bedrock:us-west-2:123456789012:agent-evaluation-dataset/demo",
        raising=False,
    )
    monkeypatch.setattr(
        settings,
        "AGENTCORE_EVALS_JOB_ROLE_ARN",
        "arn:aws:iam::123456789012:role/PellierEvalsRole",
        raising=False,
    )

    cfg = agentcore_evals.describe_configuration()

    assert cfg["configured"] is True
    assert cfg["flag"] == "AGENTCORE_EVALS_ENABLED"
    assert cfg["datasetArn"].endswith(":agent-evaluation-dataset/demo")
    assert cfg["dailyCiGate"] == "tests/test_golden_journeys.py"


def test_error_when_runtime_arn_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag on + dataset set but no runtime ARN → structured error, not raise."""
    monkeypatch.setattr(settings, "AGENTCORE_EVALS_ENABLED", True, raising=False)
    monkeypatch.setattr(
        settings,
        "AGENTCORE_EVALS_DATASET_ARN",
        "arn:aws:bedrock:us-west-2:123456789012:agent-evaluation-dataset/demo",
        raising=False,
    )
    monkeypatch.setattr(
        settings, "AGENTCORE_RUNTIME_ENDPOINT", None, raising=False
    )

    result = _run(agentcore_evals.submit_evaluation_job())

    assert result["status"] == "error"
    assert "agent runtime ARN" in result["reason"]


class _FakeClient:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def create_evaluation_job(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "evaluationJobArn": (
                "arn:aws:bedrock:us-west-2:123456789012:evaluation-job/demo-1"
            )
        }


def test_submit_calls_create_evaluation_job_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag + dataset + runtime all set → one boto3 call with the
    configured payload. The test never reaches real AWS — boto3.client
    is replaced with a fake."""
    monkeypatch.setattr(settings, "AGENTCORE_EVALS_ENABLED", True, raising=False)
    monkeypatch.setattr(
        settings,
        "AGENTCORE_EVALS_DATASET_ARN",
        "arn:aws:bedrock:us-west-2:123456789012:agent-evaluation-dataset/demo",
        raising=False,
    )
    monkeypatch.setattr(
        settings,
        "AGENTCORE_EVALS_JOB_ROLE_ARN",
        "arn:aws:iam::123456789012:role/PellierEvalsRole",
        raising=False,
    )
    monkeypatch.setattr(
        settings,
        "AGENTCORE_RUNTIME_ENDPOINT",
        "arn:aws:bedrock:us-west-2:123456789012:agent-runtime/pellier",
        raising=False,
    )

    fake = _FakeClient()

    import boto3

    monkeypatch.setattr(boto3, "client", lambda *args, **kw: fake)

    result = _run(agentcore_evals.submit_evaluation_job())

    assert result["status"] == "submitted"
    assert result["jobArn"].endswith("/demo-1")
    assert len(fake.calls) == 1
    payload = fake.calls[0]
    assert payload["agentRuntimeArn"].endswith("/pellier")
    assert payload["datasetArn"].endswith("/demo")
    assert payload["jobRoleArn"].endswith("/PellierEvalsRole")
    # Evaluator defaults to the Opus profile already used by editorial agents.
    assert "claude-opus" in payload["evaluatorModelId"]
