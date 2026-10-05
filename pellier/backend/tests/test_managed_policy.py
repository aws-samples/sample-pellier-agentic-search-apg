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
GATEWAY_CLIENT = DEPLOY / "gateway_client.py"
STORE_LAMBDA = DEPLOY / "pellier_store_tools.py"
PROVISIONER = REPO_ROOT / "scripts" / "provision_agentcore_end_to_end.py"
DEPLOY_ALL = DEPLOY / "deploy_all.sh"
RESET_GOVERNED = REPO_ROOT / "scripts" / "reset-governed-workshop.sh"
STARTER_CEDAR = REPO_ROOT / "policies" / "workshop_credit_limit.cedar"
SOLUTION_CEDAR = (
    REPO_ROOT
    / "solutions"
    / "the-concierge"
    / "policies"
    / "workshop_credit_limit.cedar"
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
    """The renderer's baseline, and the ENFORCE attachment that makes it consequential.

    The name-by-name contract belongs to ``test_fresh_policy_set.py``. This test asserts
    the two things that are the renderer's own responsibility: every policy it emits is
    enforced and validated, and the engine is attached in ENFORCE rather than LOG_ONLY.
    A LOG_ONLY attachment turns every DENY in the workshop into a note in a log.

    Enumerating names here as well is what allowed the baseline to drift: two copies
    agreed with each other and both disagreed with the live environment.
    """
    policies = renderer.baseline_policies(gateway_arn="arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/test-gw")

    assert policies, "the renderer must emit a baseline"
    assert all(policy["enforcementMode"] == "ACTIVE" for policy in policies)
    assert all(
        policy["validationMode"] == "FAIL_ON_ANY_FINDINGS"
        for policy in policies
    )
    statements = "\n".join(policy["statement"] for policy in policies)
    assert renderer.GIVE_STORE_CREDIT_ACTION in statements
    assert 'resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/test-gw"' in statements
    assert "resource is AgentCore::Gateway" not in statements
    assert "permit (principal, action, resource" not in statements

    # The Lab 4 amount limit is the participant's work. The staff permit that
    # carries `give_store_credit` must not already bound the amount, or the
    # exercise's before-state would be false.
    credit_statements = "\n".join(
        policy["statement"]
        for policy in policies
        if renderer.GIVE_STORE_CREDIT_ACTION in policy["statement"]
    )
    assert "amount_cents" not in credit_statements
    assert "CUST-MARCO" not in credit_statements
    policy = next(item for item in policies if item["name"] == "get_orders_owner_only")
    assert policy["statement"].lstrip().startswith("permit (principal is AgentCore::OAuthUser")
    assert f"{renderer.STORE_TARGET}___get_orders" in policy["statement"]
    assert 'principal.hasTag("custom:customer_id")' in policy["statement"]
    assert 'principal.getTag("custom:customer_id") == context.input.customer_id' in policy["statement"]

    source = RENDERER_PATH.read_text()
    assert '"mode": "ENFORCE"' in source
    assert '"policyEngines"' in source


def test_participant_cedar_files_need_only_the_gateway_arn_substituted() -> None:
    """The starter and the solution are policy statements once the Gateway ARN is filled in.

    The live analyzer rejects `resource is AgentCore::Gateway` for a pinned action, and
    a tracked file cannot carry an account's ARN, so both files name the Gateway with
    the ``${PELLIER_GATEWAY_ARN}`` placeholder the renderer fills in
    (``render_agentcore_project.credit_limit_policy``). Nothing else is templated.
    """
    expected_action = f'AgentCore::Action::"{renderer.GIVE_STORE_CREDIT_ACTION}"'
    assert renderer.GIVE_STORE_CREDIT_ACTION == "pellier-store-tools___give_store_credit"
    starter = STARTER_CEDAR.read_text()
    solution = SOLUTION_CEDAR.read_text()
    for statement in (starter, solution):
        assert expected_action in statement
        assert 'resource == AgentCore::Gateway::"${PELLIER_GATEWAY_ARN}"' in statement
        assert "resource is AgentCore::Gateway" not in statement
        assert "ACTION_TOKEN" not in statement
        code = "\n".join(
            line for line in statement.splitlines() if not line.strip().startswith("//")
        )
        assert code.count("${") == 1, "only the Gateway ARN is templated"
        assert "principal is AgentCore::OAuthUser" in statement
    assert "false" in starter
    assert "unless" in starter
    assert "unless" in solution
    assert "context.input has amount_cents" in solution
    assert "context.input.amount_cents <= 10000" in solution
    starter_code = "\n".join(
        line for line in starter.splitlines() if not line.strip().startswith("//")
    )
    assert "amount_cents" not in starter_code, "the starter must not contain the answer"


def test_reset_restores_the_starter_policy_through_cli() -> None:
    """The reset declares Lab 4's starter again; it never removes the policy."""
    source = RESET_GOVERNED.read_text()

    assert "@aws/agentcore@0.29.0" in source
    assert "remove policy" not in source
    assert "declare_credit_limit" in source
    assert "workshop/starters/workshop_credit_limit.cedar" in source
    assert "_agentcore validate --json" in source
    assert "_agentcore deploy --yes --json" in source
    # A failed CLI call prints [FAIL] and exits, rather than set -e ending silently.
    for command in ("validate --json", "deploy --yes --json"):
        guarded = f"_agentcore {command} >>/tmp/pellier-governed-reset-policy.log || {{\n    fail "
        assert guarded in source, command
    assert "policy_name=workshop_credit_limit" in source
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


def _load_gateway_client(name: str):
    spec = importlib.util.spec_from_file_location(name, GATEWAY_CLIENT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gateway_client_only_counts_policy_errors_as_deny() -> None:
    module = _load_gateway_client("gateway_client_denial")

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
    module = _load_gateway_client("gateway_client_identity")
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
    # `gateway_client` imports boto3 inside the function so the receipt validator
    # can load it without boto3; patch the client factory on boto3 itself.
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: _Cognito())

    identity = module._verified_identity(token)
    assert identity["principal_id"] == "subject-123"
    assert identity["verified_username"] == "marco"
    assert identity["identity_source"] == "cognito"
    assert len(identity["token_fingerprint_sha256"]) == 64


def test_gateway_receipt_identity_rejects_claim_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_gateway_client("gateway_client_mismatch")
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
    # `gateway_client` imports boto3 inside the function so the receipt validator
    # can load it without boto3; patch the client factory on boto3 itself.
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: _Cognito())

    with pytest.raises(RuntimeError, match="username"):
        module._verified_identity(token)


def test_the_gateway_client_records_verified_identity_provenance() -> None:
    helper = GATEWAY_CLIENT.read_text()

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


def test_store_lambda_writes_gateway_tool_audit() -> None:
    """The Lambda wires the audit; the shared transport performs it.

    The credit receipt is written OUTSIDE the business transaction, so an Aurora
    refusal still leaves exactly one attempt receipt. An idempotent replay
    writes none, so a retry keeps one credit and one receipt. Reads write a
    receipt only when the Runtime passed a turn id.
    """
    source = STORE_LAMBDA.read_text()
    assert (
        'if tool_name == "give_store_credit" and not _is_idempotent_replay(result):'
        in source
    )
    assert "write_tool_audit_independently(" in source
    assert "audit_read_call(tool_name, audited_arguments, result, started," in source
    assert "build_fingerprint=build" in source
    # Keyed on the real identity, which this tool's arguments carry.
    assert 'f"gateway-{execution_arguments.get(\'customer_id\') or \'unknown\'}"' in source
    assert "_write_tool_audit_in_transaction" not in source

    transport = (STORE_LAMBDA.parent / "common" / "dataapi.py").read_text()
    assert "INSERT INTO" in transport and "tool_audit" in transport
    assert "::jsonb" in transport
    assert "'gateway'" in transport
    assert "def write_tool_audit_independently(" in transport
