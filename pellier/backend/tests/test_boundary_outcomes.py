from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.governance_boundaries import assess, summarize
from services import governed_execution as execution


def observation(auth="VERIFIED", policy="ALLOW", output="RETURNED", counts=(1, 1, 1, 1, 0), **extra):
    return {"authentication": auth, "authorization": policy, "output": output,
            "database": {"queried": True, **dict(zip(
                ("executionRows", "writeRows", "committedRows", "domainRows", "ledgerRows"), counts))}, **extra}


@pytest.mark.parametrize("value,outcome,executed,changed", [
    (observation("REJECTED", "NOT_EVALUATED", "UNKNOWN", (0, 0, 0, 0, 0)), "authentication_failed", False, False),
    (observation(policy="DENY", output="UNKNOWN", counts=(0, 0, 0, 0, 0)), "cedar_denied", False, False),
    (observation(counts=(1, 0, 0, 0, 0), businessRejected=True), "transaction_rejected", True, False),
    (observation(), "committed", True, True),
    (observation(output="SUPPRESSED"), "output_suppressed", True, True),
])
def test_independent_outcomes(value, outcome, executed, changed):
    result = assess(value)
    assert (result["outcome"], result["toolExecuted"], result["dataChanged"]) == (outcome, executed, changed)


@pytest.mark.parametrize("value", [
    {}, observation(auth="UNKNOWN"), observation(policy="UNKNOWN"),
    observation(output="UNKNOWN"), observation(counts=(0, 0, 0, 0, 0)),
    observation(counts=(1, 0, 0, 0, 0)),  # generic error is not a business rejection
    observation(output="SUPPRESSED", counts=(0, 0, 0, 0, 0)),
    observation(counts=(1, 0, 0, 0, 1), businessRejected=True),
])
def test_incomplete_evidence_never_proves_an_outcome(value):
    assert assess(value)["outcome"] == "inconclusive"


def test_failed_database_read_and_unmatched_commit_stay_unknown():
    value = observation()
    value["database"]["queried"] = False
    assert assess(value)["toolExecuted"] is None
    assert assess(value)["dataChanged"] is None
    result = assess(observation(counts=(1, 1, 1, 0, 0)))
    assert result["dataChanged"] is None
    assert result["contradiction"]


@pytest.mark.parametrize("value", [observation(policy="DENY"), observation("REJECTED", "NOT_EVALUATED")])
def test_rejection_with_execution_is_a_visible_contradiction(value):
    assert assess(value)["contradiction"]


def test_suppression_with_leaked_canary_remains_a_contradiction():
    result = assess(observation(output="SUPPRESSED", canaryReturned=True))
    assert result["outcome"] == "inconclusive"
    assert "reached the caller" in result["contradiction"]


def record(value, case="allow", run="one", index=1):
    return {"proofRunId": run, "caseName": case, "observationId": index,
            "operationKey": "key", "invocationId": f"{run}-{case}", "tool": "issue_credit",
            "verifiedUsername": "operator", "createdAt": "2026-09-17T12:00:00Z", "observation": value}


def test_run_completion_needs_final_controls_and_never_combines_runs():
    values = [observation("REJECTED", "NOT_EVALUATED", counts=(0, 0, 0, 0, 0)),
              observation(policy="DENY", counts=(0, 0, 0, 0, 0)),
              observation(counts=(1, 0, 0, 0, 0), businessRejected=True),
              observation(), observation(output="SUPPRESSED")]
    rows = [record(v, case=str(i), index=i) for i, v in enumerate(values)]
    assert not summarize(rows)["runs"][0]["complete"]
    checks = record({"runChecks": {"identityProofPassed": True, "configurationUnchanged": True,
                                    "outputControlsPassed": True}}, "run-checks")
    assert summarize(rows + [checks])["runs"][0]["complete"]
    checks["observation"]["runChecks"]["configurationUnchanged"] = False
    assert not summarize(rows + [checks])["runs"][0]["complete"]
    rows[-1]["proofRunId"] = "another-run"
    assert not any(run["complete"] for run in summarize(rows)["runs"])


def load_driver():
    path = Path(__file__).resolve().parents[3] / "scripts/prove_governance_outcomes.py"
    spec = importlib.util.spec_from_file_location("boundary_proof_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_suppression_requires_explicit_response_phase_and_policy_identity():
    driver = load_driver()
    assert driver.suppression_reported("Output suppressed by policy credit-check-123", "credit-check-123")
    for message in ("403 Forbidden", "401 Unauthorized", "Tool call not allowed due to policy credit-check-123",
                    "Output suppressed by another-policy", "Connection timeout"):
        assert not driver.suppression_reported(message, "credit-check-123")


def test_runtime_never_labels_output_suppression_a_cedar_denial_or_rollback():
    message = "Output suppressed by policy enforcement credit-check-123"
    assert not execution.is_policy_denial(message)
    assert execution.is_output_suppression(message)
    state, note = execution.classify_aurora({"status": "output_suppressed"})
    assert state == execution.AURORA_OUTCOME_UNKNOWN
    assert "does not roll back" in note


@pytest.mark.asyncio
async def test_response_phase_policy_events_do_not_overwrite_request_admission(monkeypatch):
    monkeypatch.setattr(execution, "_execute_through_gateway", AsyncMock(return_value=(
        execution.POLICY_ALLOW, {"status": "output_suppressed"}, "output control")))
    observer = AsyncMock()
    monkeypatch.setattr(execution, "_observe_policy_decisions", observer)
    state = execution.PolicyEngineState(gateway_mode="ENFORCE", policies={})
    policy, result, notes = await execution._run_gateway_rail(
        None, tool="issue_credit", args={}, idempotency_key="same-key", access_token="test",
        operator_sub="operator", execution_turn_id="turn", engine_state=state)
    assert policy != execution.POLICY_DENY
    assert result["status"] == "output_suppressed"
    assert "output" in notes
    observer.assert_not_called()


def test_suppression_proof_needs_benign_control_no_leak_and_same_key_replay():
    driver = load_driver()
    benign = record(observation(), "benign-output")
    first = record(observation(output="SUPPRESSED", canaryReturned=False), "suppressed-output")
    replay = record(observation(output="SUPPRESSED", counts=(2, 1, 1, 1, 0), canaryReturned=False), "suppressed-replay")
    replay["observation"]["database"]["idempotentReplay"] = True
    rows = [benign, first, replay]
    assert driver.output_controls_passed(rows)
    first["observation"]["canaryReturned"] = True
    assert not driver.output_controls_passed(rows)
    first["observation"]["canaryReturned"] = False
    replay["operationKey"] = "new-key"
    assert not driver.output_controls_passed(rows)
    replay["operationKey"] = "key"
    benign["observation"]["output"] = "SUPPRESSED"
    assert not driver.output_controls_passed(rows)
    assert not driver.output_controls_passed([])


def test_output_policy_and_permission_are_narrowly_scoped():
    driver = load_driver()
    import output_guardrail
    arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/test"
    policy = output_guardrail.policy(arn)
    assert policy["statement"].startswith("suppressOutput")
    assert output_guardrail.ACTION in policy["statement"]
    assert "context.input" not in policy["statement"]
    assert "context.output.content[0].text" in policy["statement"]
    assert 'SensitiveInformation(["EMAIL"]' in policy["statement"]
    control, iam = Mock(), Mock()
    control.get_gateway.return_value = {"roleArn": "arn:aws:iam::123456789012:role/path/gateway"}
    output_guardrail.ensure_permission(control, iam, gateway_id="test", region="us-east-1")
    import json
    call = iam.put_role_policy.call_args.kwargs
    assert call["RoleName"] == "gateway"
    assert json.loads(call["PolicyDocument"])["Statement"][0]["Action"] == "bedrock:InvokeGuardrailChecks"


def test_preflight_refuses_log_only_or_modified_output_policy():
    driver = load_driver()
    control = Mock()
    arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/test"
    control.get_gateway.return_value = {"gatewayArn": arn, "authorizerType": "CUSTOM_JWT", "policyEngineConfiguration": {"mode": "LOG_ONLY", "arn": "arn:engine/e"}}
    with pytest.raises(RuntimeError, match="enforce"):
        driver.policy_configuration(control, "test", "e")
    control.get_gateway.return_value["policyEngineConfiguration"]["mode"] = "ENFORCE"
    control.list_policies.return_value = {"policies": [{"name": driver.POLICY_NAME, "policyId": "p"}]}
    control.get_policy.return_value = {"policyId": "p", "enforcementMode": "ACTIVE", "definition": {"cedar": {"statement": "permit(principal, action, resource);"}}}
    with pytest.raises(RuntimeError, match="differs"):
        driver.policy_configuration(control, "test", "e")


def test_boundary_endpoint_requires_operator_and_failed_read_is_not_an_empty_run(monkeypatch):
    from routes import governance, observatory
    from services.auth import require_operator
    app = FastAPI()
    app.include_router(governance.router)
    client = TestClient(app)
    assert client.get("/api/observatory/governance/outcomes").status_code in (401, 403)
    app.dependency_overrides[require_operator] = lambda: {"sub": "operator"}
    async def failed_db():
        raise RuntimeError("unavailable")
    monkeypatch.setattr(observatory, "_live_db", failed_db)
    response = client.get("/api/observatory/governance/outcomes")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "boundary_evidence_unavailable"}
