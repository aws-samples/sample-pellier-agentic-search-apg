"""Relay the actual SDK stream format without losing identity or failure type."""
import io
import urllib.error

import pytest
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from services import operator_runtime_client as client


def invoke(monkeypatch, frames):
    app = BedrockAgentCoreApp()
    content = b"".join(app._convert_to_sse(frame) for frame in frames)
    requests, steps = [], []

    def open_request(request, **_kwargs):
        requests.append(request)
        return io.BytesIO(content)

    monkeypatch.setattr(client.urllib.request, "urlopen", open_request)
    result = client.investigate_on_runtime(customer_id="CUST-JESSICA", operator_sub="staff-sub",
        access_token="test-token", turn_id="turn-transport", emit=steps.append,
        endpoint="arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/operator-test", region="us-east-1")
    return result, steps, requests


def completed():
    return {"event": "complete", "data": {"customerId": "CUST-JESSICA", "turnId": "turn-transport",
            "rail": "gateway-mcp", "orchestration": "strands-graph", "build_fingerprint": "a" * 64,
            "graph": {"execution": "gateway-mcp"}}}


def test_relay_preserves_steps_and_binds_the_invocation(monkeypatch):
    import json
    result, steps, requests = invoke(monkeypatch, [{"event": "step", "data": {"status": "running"}}, completed()])
    assert steps == [{"status": "running"}]
    assert result["rail"] == "gateway-mcp"
    payload = json.loads(requests[0].data)
    assert payload["operator_sub"] == "staff-sub" and payload["customer_id"] == "CUST-JESSICA"
    assert requests[0].headers["Authorization"] == "Bearer test-token"


@pytest.mark.parametrize("detail,expected", [
    ("authentication_failed", "authentication_failed"), ("staff_scope_required", "staff_scope_required"),
    ("internal secret material", "operator_runtime_failed"), ({"arbitrary": "object"}, "operator_runtime_failed"),
])
def test_error_frames_keep_only_known_safe_failure_codes(monkeypatch, detail, expected):
    with pytest.raises(client.OperatorRuntimeError, match=expected):
        invoke(monkeypatch, [{"event": "error", "data": {"detail": detail}}])


@pytest.mark.parametrize("change", [{"customerId": "CUST-THEO"}, {"turnId": "turn-other"},
                                   {"rail": "in-process"}, {"graph": "invalid"}, {"build_fingerprint": ""}])
def test_mismatched_or_incomplete_completion_is_not_success(monkeypatch, change):
    frame = completed()
    frame["data"].update(change)
    with pytest.raises(client.OperatorRuntimeError, match="invalid_response"):
        invoke(monkeypatch, [frame])


@pytest.mark.parametrize("status,code", [(401, "authentication_failed"), (403, "staff_scope_required"),
                                       (503, "operator_runtime_unavailable")])
def test_http_errors_are_not_reported_as_cedar_denials(monkeypatch, status, code):
    def fail(*_args, **_kwargs):
        raise urllib.error.HTTPError("https://runtime.example", status, "private response", {}, None)
    monkeypatch.setattr(client.urllib.request, "urlopen", fail)
    with pytest.raises(client.OperatorRuntimeError, match=code):
        client.investigate_on_runtime(customer_id="CUST-JESSICA", operator_sub="staff-sub",
            access_token="test-token", turn_id="turn-transport", emit=lambda _: None,
            endpoint="runtime-test", region="us-east-1")
