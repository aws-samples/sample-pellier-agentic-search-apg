"""Managed Operator execution must prove its package without a local fallback."""
from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import settings
from services import build_fingerprint, operator_graph, operator_runtime


def _response(**overrides):
    payload = {
        "raw": '{"summary":"Fixture evidence only."}',
        "model_id": "fixture-model",
        "build_fingerprint": build_fingerprint.compute_fingerprint(
            Path(__file__).resolve().parents[1]
        ),
        "metadata": {
            "graphId": operator_graph.GRAPH_ID,
            "execution": "agentcore-runtime",
            "status": "complete",
            "executedNodes": [
                {"nodeId": "case-investigator", "status": "completed"},
                {"nodeId": "resolution-planner", "status": "completed"},
            ],
        },
        **overrides,
    }
    return payload


@pytest.fixture
def managed(monkeypatch):
    monkeypatch.setattr(settings, "USE_AGENTCORE_RUNTIME", True)
    monkeypatch.setattr(
        settings, "AGENTCORE_OPERATOR_RUNTIME_ENDPOINT",
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/operator-fixture",
    )
    monkeypatch.delenv("PELLIER_OPERATOR_RUNTIME", raising=False)


def test_managed_operator_uses_iam_and_returns_package_evidence(managed, monkeypatch):
    import boto3

    calls = []
    stream = io.BytesIO(json.dumps(_response()).encode())

    def invoke(**kwargs):
        calls.append(kwargs)
        return {"response": stream, "ResponseMetadata": {"RequestId": "request-fixture"}}

    monkeypatch.setattr(boto3, "client", lambda *a, **kw: SimpleNamespace(invoke_agent_runtime=invoke))
    result = operator_graph.run_operator_graph(
        request="Investigate the fixture.", evidence_text="[FACT] Fixture.", memory_text="",
        contract="Return JSON.",
    )
    assert result.error == ""
    assert result.metadata["fingerprintMatches"] is True
    assert result.metadata["requestId"] == "request-fixture"
    assert result.metadata["execution"] == "agentcore-runtime"
    assert calls[0]["agentRuntimeArn"] == settings.AGENTCORE_OPERATOR_RUNTIME_ENDPOINT
    assert len(calls[0]["runtimeSessionId"]) >= 33
    assert "Authorization" not in calls[0]  # SDK signs with the backend's IAM role.
    assert json.loads(calls[0]["payload"])["request"] == "Investigate the fixture."
    assert stream.closed


@pytest.mark.parametrize("failure", ["stale", "partial", "error", "malformed"])
def test_invalid_managed_result_never_becomes_a_recommendation(managed, monkeypatch, failure):
    import boto3

    payload = _response()
    if failure == "stale":
        payload["build_fingerprint"] = "old-package"
    elif failure == "partial":
        payload["metadata"]["executedNodes"].pop()
    elif failure == "error":
        payload["error"] = "model_unavailable"
    else:
        payload = ["unexpected"]
    stream = io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(
        boto3, "client",
        lambda *a, **kw: SimpleNamespace(invoke_agent_runtime=lambda **kw: {"response": stream}),
    )
    result = operator_runtime.invoke_operator_runtime(request="Fixture")
    assert result.raw == ""
    assert result.metadata["status"] == "failed"
    assert result.error
    assert stream.closed


def test_missing_endpoint_does_not_construct_a_local_graph(managed, monkeypatch):
    import boto3

    monkeypatch.setattr(settings, "AGENTCORE_OPERATOR_RUNTIME_ENDPOINT", None)
    monkeypatch.setattr(boto3, "client", lambda *a, **kw: pytest.fail("No service call expected"))
    result = operator_graph.run_operator_graph(
        request="Fixture", evidence_text="[FACT] Fixture", memory_text="", contract="JSON",
    )
    assert result.error == "operator_runtime_unconfigured"
    assert result.raw == ""


@pytest.mark.parametrize(
    "failure",
    [None, "stale", "partial", "malformed", "metadata", "node", "failed_node", "wrong_graph"],
)
def test_deployment_smoke_requires_the_complete_matching_graph(monkeypatch, failure):
    import importlib.util

    path = Path(__file__).resolve().parents[3] / "scripts/provision_agentcore_end_to_end.py"
    spec = importlib.util.spec_from_file_location("operator_smoke_provisioner", path)
    provisioner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provisioner)
    payload = _response(build_fingerprint="expected-package")
    if failure == "stale":
        payload["build_fingerprint"] = "previous-package"
    elif failure == "partial":
        payload["metadata"]["executedNodes"].pop()
    elif failure == "malformed":
        payload = ["unexpected"]
    elif failure == "metadata":
        payload["metadata"] = "untyped"
    elif failure == "node":
        payload["metadata"]["executedNodes"] = ["untyped"]
    elif failure == "failed_node":
        payload["metadata"]["executedNodes"][1]["status"] = "failed"
    elif failure == "wrong_graph":
        payload["metadata"]["graphId"] = "another-graph"
    stream = io.BytesIO(json.dumps(payload).encode())
    calls = []

    def invoke(**kwargs):
        calls.append(kwargs)
        return {"response": stream}

    monkeypatch.setattr(
        provisioner.boto3, "client",
        lambda *args, **kwargs: SimpleNamespace(invoke_agent_runtime=invoke),
    )
    kwargs = {
        "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/operator-fixture",
        "region": "us-east-1",
        "expected_fingerprint": "expected-package",
    }
    if failure:
        with pytest.raises(RuntimeError, match="Operator Runtime smoke"):
            provisioner._operator_runtime_smoke(**kwargs)
    else:
        result = provisioner._operator_runtime_smoke(**kwargs)
        assert result["runtime_arn"] == kwargs["runtime_arn"]
        assert result["build_fingerprint_match"] is True
        assert result["fixture"] is True
        assert result["executed_nodes"] == ["case-investigator", "resolution-planner"]
    assert stream.closed
    assert len(calls) == 1
    assert len(calls[0]["runtimeSessionId"]) >= 33


def test_operator_entrypoint_accepts_only_bounded_read_envelopes(monkeypatch):
    import importlib.util
    import sys
    import types

    class RuntimeApp:
        def entrypoint(self, handler):
            return handler

    runtime_module = types.ModuleType("bedrock_agentcore.runtime")
    runtime_module.BedrockAgentCoreApp = RuntimeApp
    monkeypatch.setitem(sys.modules, "bedrock_agentcore.runtime", runtime_module)
    monkeypatch.setenv("PELLIER_OPERATOR_RUNTIME", "false")
    path = Path(__file__).resolve().parents[1] / "operator_agentcore_runtime.py"
    spec = importlib.util.spec_from_file_location("operator_entrypoint_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def graph(**payload):
        calls.append(payload)
        return operator_graph.OperatorGraphResult('{"summary":"Fixture"}', "fixture-model")

    monkeypatch.setattr(module, "run_operator_graph", graph)
    payload = {"request": "Fixture", "evidence_text": "[FACT] Fixture", "contract": "Return JSON"}
    assert module.invoke(payload)["raw"] == '{"summary":"Fixture"}'
    assert calls[0]["memory_text"] == ""
    for invalid in (
        {**payload, "execute_tool": "issue_credit"},
        {**payload, "request": "x" * 8001},
        {**payload, "review_id": True},
        {**payload, "checkpoint_state": "APPROVED"},
        {**payload, "shopper_handoff": "untyped"},
    ):
        assert module.invoke(invalid) == {"error": "invalid_operator_request"}
    assert len(calls) == 1
