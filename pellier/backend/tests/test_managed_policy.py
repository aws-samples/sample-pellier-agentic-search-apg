"""Tests for Pellier's AgentCore CLI-managed Cedar policy contract."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "pellier" / "backend"
DEPLOY = REPO_ROOT / "scripts" / "deploy"
RENDERER_PATH = DEPLOY / "render_agentcore_project.py"
GATEWAY_PROCESS_RETURN = DEPLOY / "gateway_process_return.py"
EXPERIENCE_LAMBDA = DEPLOY / "pellier_experience_server.py"
PROVISIONER = REPO_ROOT / "scripts" / "provision_agentcore_end_to_end.py"
DEPLOY_ALL = DEPLOY / "deploy_all.sh"
RESET_GOVERNED = REPO_ROOT / "scripts" / "reset-governed-workshop.sh"
GOVERNED_RECEIPTS_MIGRATION = (
    REPO_ROOT / "scripts" / "migrations" / "010_governed_receipts.sql"
)
STARTER_CEDAR = REPO_ROOT / "policies" / "workshop_identity_match_forbid.cedar"
ADVANCED_DOGWOOD = (
    REPO_ROOT / "policies" / "advanced_verified_customer_context.dogwood"
)
SOLUTION_CEDAR = (
    REPO_ROOT
    / "solutions"
    / "the-concierge"
    / "policies"
    / "identity_match_forbid.cedar"
)

if str(DEPLOY) not in sys.path:
    sys.path.insert(0, str(DEPLOY))

import render_agentcore_project as renderer  # noqa: E402


def test_local_policy_hook_and_fake_engine_are_removed() -> None:
    assert not (BACKEND / "services" / "policy_hook.py").exists()
    assert not (BACKEND / "services" / "agentcore_policy.py").exists()


def test_raw_agentcore_policy_provisioners_are_removed() -> None:
    assert not (DEPLOY / "deploy_policy.py").exists()
    assert not (DEPLOY / "workshop_policy_rule.py").exists()
    assert not (DEPLOY / "deploy_gateway.py").exists()


def test_no_dangling_local_policy_imports() -> None:
    offenders = []
    for path in BACKEND.rglob("*.py"):
        if path.name.startswith("test_"):
            continue
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for symbol in (
                "PolicyEnforcementHook",
                "attach_policy_hook",
                "get_policy_service",
                "create_policy_from_natural_language",
            ):
                if symbol in stripped:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {stripped}")
    assert not offenders, "\n".join(offenders)


def test_renderer_owns_baseline_cedar_and_enforce_attachment() -> None:
    gateway_arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/pellier-test"
    policies = renderer.baseline_policies(gateway_arn=gateway_arn)
    names = {policy["name"] for policy in policies}

    assert names == {
        "baseline_permit_gateway_tools",
        "process_return_damaged_only",
        "process_return_allow_damaged",
    }
    assert all(policy["enforcementMode"] == "ACTIVE" for policy in policies)
    statements = "\n".join(policy["statement"] for policy in policies)
    assert renderer.PROCESS_RETURN_ACTION in statements
    assert 'context.input.reason != "damaged"' in statements
    assert f'resource == AgentCore::Gateway::"{gateway_arn}"' in statements

    source = RENDERER_PATH.read_text()
    assert '"mode": "ENFORCE"' in source
    assert '"policyEngines"' in source


def test_participant_cedar_files_are_direct_cli_sources() -> None:
    expected_action = (
        'AgentCore::Action::"'
        "pellier-concierge-experience-target___process_return"
        '"'
    )
    starter = STARTER_CEDAR.read_text()
    solution = SOLUTION_CEDAR.read_text()

    for statement in (starter, solution):
        assert expected_action in statement
        assert "resource is AgentCore::Gateway" in statement
        assert "ACTION_TOKEN" not in statement
        assert "GATEWAY_ARN" not in statement

    assert "false" in starter
    assert "unless" in starter
    assert "unless" in solution
    assert 'principal.hasTag("username")' in solution
    assert "context.input has customer_id" in solution
    assert 'principal.getTag("username") == context.input.customer_id' in solution
    assert 'principal.getTag("username") != context.input.customer_id' not in solution


def test_advanced_dogwood_example_teaches_sequence_without_false_enforcement() -> None:
    source = ADVANCED_DOGWOOD.read_text()

    assert "when temporal" in source
    assert "formerly within 10m" in source
    assert (
        'AgentCore::Action::"'
        'pellier-curation-recommendation-target___preference_snapshot"::response'
    ) in source
    assert 'input.customer_id: context.input.customer_id' in source
    assert "eventResource: resource" in source
    assert "x-amzn-bedrock-agentcore-policy-session-id" not in source
    assert "narrow or replace that broad" in source
    assert "would not enforce the sequence" in source


def test_reset_removes_and_redeploys_participant_policy_through_cli() -> None:
    source = RESET_GOVERNED.read_text()

    assert "@aws/agentcore@1.0.0-preview.26" in source
    assert "remove policy" in source
    assert "--engine \"$POLICY_ENGINE_NAME\"" in source
    assert "_agentcore validate --json" in source
    assert "_agentcore deploy --yes --json" in source
    assert "workshop_identity_match_forbid" in source
    assert "policyEngineConfiguration.mode" in source
    assert "ENFORCE" in source
    assert "workshop_policy_rule.py" not in source
    assert "bedrock-agentcore-control" not in source


def test_deploy_paths_do_not_mutate_agentcore_control_plane_directly() -> None:
    provisioner = PROVISIONER.read_text()
    deploy_all = DEPLOY_ALL.read_text()
    renderer_source = RENDERER_PATH.read_text()
    combined = "\n".join((provisioner, deploy_all, renderer_source))

    assert "render_project(" in provisioner
    assert '"validate"' in provisioner
    assert '"deploy"' in provisioner
    for operation in (
        "create_gateway(",
        "create_gateway_target(",
        "create_memory(",
        "create_policy_engine(",
        "create_policy(",
        "update_gateway(",
    ):
        assert operation not in combined
    assert "deploy_policy.py" not in combined
    assert "deploy_gateway.py" not in combined


def _load_gateway_process_return(name: str):
    spec = importlib.util.spec_from_file_location(name, GATEWAY_PROCESS_RETURN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gateway_process_return_only_counts_policy_errors_as_deny() -> None:
    module = _load_gateway_process_return("gateway_process_return_denial")

    assert module._is_authorization_denial(
        RuntimeError("AuthorizeActionException: explicit deny")
    )
    assert module._is_authorization_denial(
        RuntimeError("Tool call not allowed due to policy enforcement [Policy")
    )
    assert not module._is_authorization_denial(
        RuntimeError("Connection refused while calling Gateway")
    )
    assert not module._is_authorization_denial(
        RuntimeError("HTTP 401 Unauthorized: invalid bearer token")
    )
    assert not module._is_authorization_denial(
        RuntimeError("AccessDeniedException: Lambda execution role denied")
    )


def test_gateway_receipt_identity_is_bound_to_exact_cognito_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_gateway_process_return("gateway_process_return_identity")
    claims = {
        "sub": "subject-123",
        "username": "marco",
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_POOL",
        "client_id": "client-123",
        "token_use": "access",
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )
    token = f"header.{encoded}.signature"

    class _Cognito:
        def get_user(self, *, AccessToken: str) -> dict:
            assert AccessToken == token
            return {
                "Username": "marco",
                "UserAttributes": [{"Name": "sub", "Value": "subject-123"}],
            }

    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("COGNITO_POOL_ID", "us-east-1_POOL")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client-123")
    monkeypatch.setattr(module.boto3, "client", lambda *args, **kwargs: _Cognito())

    identity = module._verified_identity(token)
    assert identity["principal_id"] == "subject-123"
    assert identity["verified_username"] == "marco"
    assert identity["identity_source"] == "cognito"
    assert len(identity["token_fingerprint_sha256"]) == 64


def test_gateway_receipt_identity_rejects_claim_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_gateway_process_return("gateway_process_return_mismatch")
    claims = {
        "sub": "subject-123",
        "username": "not-marco",
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_POOL",
        "client_id": "client-123",
        "token_use": "access",
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )
    token = f"header.{encoded}.signature"

    class _Cognito:
        def get_user(self, *, AccessToken: str) -> dict:
            return {
                "Username": "marco",
                "UserAttributes": [{"Name": "sub", "Value": "subject-123"}],
            }

    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("COGNITO_POOL_ID", "us-east-1_POOL")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client-123")
    monkeypatch.setattr(module.boto3, "client", lambda *args, **kwargs: _Cognito())

    with pytest.raises(RuntimeError, match="username"):
        module._verified_identity(token)


def test_governed_receipts_record_verified_identity_provenance() -> None:
    helper = GATEWAY_PROCESS_RETURN.read_text()
    migration = GOVERNED_RECEIPTS_MIGRATION.read_text()

    assert "--principal-id" not in helper
    assert "--principal-label" not in helper
    assert "get_user(AccessToken=token)" in helper
    for field in (
        "token_fingerprint_sha256",
        "verified_subject",
        "verified_username",
        "issuer",
        "client_id",
        "identity_source",
    ):
        assert field in helper
        assert field in migration


def test_gateway_absence_proof_uses_the_exact_invocation_key() -> None:
    helper = GATEWAY_PROCESS_RETURN.read_text()

    assert "def _idempotency_key(" in helper
    assert helper.count("args->>'idempotency_key' = %s") == 2
    assert '"idempotency_key": _idempotency_key(args)' in helper


def test_experience_lambda_writes_gateway_tool_audit() -> None:
    source = EXPERIENCE_LAMBDA.read_text()
    assert "_write_tool_audit" in source
    assert "INSERT INTO" in source and "tool_audit" in source
    assert "::jsonb" in source
    assert 'tool_name == "process_return"' in source
    assert '"gateway"' in source or "'gateway'" in source
