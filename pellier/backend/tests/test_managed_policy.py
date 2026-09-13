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
GATEWAY_PROCESS_RETURN = DEPLOY / "gateway_initiate_return.py"
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
    assert renderer.INITIATE_RETURN_ACTION in statements
    assert 'context.input.reason == "damaged"' in statements
    assert 'resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/test-gw"' in statements
    assert "resource is AgentCore::Gateway" not in statements
    assert "permit (principal, action, resource" not in statements

    # The Lab 4 return-ownership condition is the participant's work. Sensitive
    # Gateway reads now carry their own self-service constraints, but no
    # `initiate_return` baseline statement may bind username to customer_id or
    # the exercise's before-state would be false.
    return_statements = "\n".join(
        policy["statement"]
        for policy in policies
        if renderer.INITIATE_RETURN_ACTION in policy["statement"]
    )
    assert 'principal.getTag("custom:customer_id") == context.input' not in return_statements
    assert "CUST-MARCO" not in return_statements
    for name, action in (
        ("get_customer_preferences_owner_only", renderer.CUSTOMER_PREFERENCES_ACTION),
        ("get_audit_trail_owner_only", renderer.AUDIT_TRAIL_ACTION),
    ):
        policy = next(item for item in policies if item["name"] == name)
        assert policy["statement"].lstrip().startswith("permit (principal is AgentCore::OAuthUser")
        assert action in policy["statement"]
        assert 'principal.hasTag("custom:customer_id")' in policy["statement"]
        assert 'principal.getTag("custom:customer_id") == context.input.customer_id' in policy["statement"]

    source = RENDERER_PATH.read_text()
    assert '"mode": "ENFORCE"' in source
    assert '"policyEngines"' in source


def test_participant_cedar_files_need_only_the_gateway_arn_substituted() -> None:
    """The starter and the solution are CLI sources once the Gateway ARN is filled in.

    The live analyzer rejects `resource is AgentCore::Gateway` for a pinned action, and
    a tracked file cannot carry an account's ARN, so both files name the Gateway with
    the ``${PELLIER_GATEWAY_ARN}`` placeholder the lab guide substitutes before
    ``agentcore add policy --source``. Nothing else is templated.
    """
    expected_action = (
        'AgentCore::Action::"'
        "pellier-concierge-experience-target___initiate_return"
        '"'
    )
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
    assert 'principal.hasTag("custom:customer_id")' in solution
    assert "context.input has customer_id" in solution
    assert 'principal.getTag("custom:customer_id") == context.input.customer_id' in solution
    assert 'getTag("username")' not in solution


def test_advanced_dogwood_example_teaches_sequence_without_false_enforcement() -> None:
    source = ADVANCED_DOGWOOD.read_text()

    assert "when temporal" in source
    assert "formerly within 10m" in source
    assert (
        'AgentCore::Action::"'
        'pellier-curation-recommendation-target___get_customer_preferences"::response'
    ) in source
    assert 'input.customer_id: context.input.customer_id' in source
    assert "eventResource: resource" in source
    assert "x-amzn-bedrock-agentcore-policy-session-id" not in source
    assert "narrow or replace that broad" in source
    assert "would not enforce the sequence" in source


def test_reset_removes_and_redeploys_participant_policy_through_cli() -> None:
    source = RESET_GOVERNED.read_text()

    assert "@aws/agentcore@0.29.0" in source
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


def _load_gateway_initiate_return(name: str):
    spec = importlib.util.spec_from_file_location(name, GATEWAY_PROCESS_RETURN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gateway_initiate_return_only_counts_policy_errors_as_deny() -> None:
    module = _load_gateway_initiate_return("gateway_initiate_return_denial")

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
    module = _load_gateway_initiate_return("gateway_initiate_return_identity")
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
    module = _load_gateway_initiate_return("gateway_initiate_return_mismatch")
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
    """The surface wires the audit; the shared transport performs it.

    Split deliberately. The INSERT moved to `common/dataapi.py` when the four
    surface servers stopped each carrying a copy, so asserting the SQL against
    the surface file would now pass only by accident of duplication returning.
    """
    source = EXPERIENCE_LAMBDA.read_text()
    # The reviewable actions now write their receipt OUTSIDE the business
    # transaction, so an Aurora denial still leaves exactly one attempt receipt.
    assert "_write_tool_audit_independently" in source
    assert "_write_tool_audit_in_transaction" not in source, (
        "the experience surface went back to auditing inside the mutation; a "
        "rolled-back write would take its receipt with it"
    )
    assert 'tool_name in ("initiate_return", "replace_damaged_item")' in source
    # Keyed on the real identity, which this tool's arguments carry.
    assert 'f"gateway-{customer_id}"' in source

    transport = (
        EXPERIENCE_LAMBDA.parent / "common" / "dataapi.py"
    ).read_text()
    assert "INSERT INTO" in transport and "tool_audit" in transport
    assert "::jsonb" in transport
    assert '"gateway"' in transport or "'gateway'" in transport
    # Both writers still exist: the in-transaction one serves restock_inventory,
    # whose boundary is deliberately unchanged.
    assert "def write_tool_audit_independently(" in transport
    assert "transactionId=transaction_id" in transport


# ---------------------------------------------------------------------------
# The live-alignment planner. Audit finding P1-04: the live baseline permits the
# restock action; the fresh baseline leaves it unpermitted so a call is a Cedar DENY.
# The planner exists so that difference can be reviewed before a shared Gateway is
# touched, which means the one property worth testing is that it cannot touch one.
# ---------------------------------------------------------------------------

RESTOCK_PLANNER = DEPLOY / "plan_restock_alignment.py"

# Control-plane writes on the policy engine. A planner that calls any of these is no
# longer a planner.
_POLICY_WRITE_CALLS = (
    "create_policy", "update_policy", "delete_policy",
    "update_gateway", "update_gateway_target", "create_gateway_target",
    "apply_policy_update", "apply_one_target", "apply_target_schemas",
)


def _planner_module():
    spec = importlib.util.spec_from_file_location(
        "pellier_restock_alignment_planner", RESTOCK_PLANNER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_alignment_planner_cannot_write() -> None:
    source = RESTOCK_PLANNER.read_text()
    called = sorted(name for name in _POLICY_WRITE_CALLS if f"{name}(" in source)
    assert not called, f"the alignment planner calls control-plane writes: {called}"
    assert "PLAN ONLY" in source


def test_the_alignment_planner_reports_restock_as_unpermitted_when_fresh() -> None:
    """The fresh side of the comparison, computable with no AWS.

    Asserted through the planner rather than by re-reading the renderer, because the
    planner is what a reviewer will run and its answer is the one that has to be right.
    """
    planner = _planner_module()
    result = planner.offline_plan()

    assert result["applied"] is False
    fresh = result["freshComparison"]
    assert fresh["freshPermitsRestock"] is False
    # A fresh stack publishes no restock tool on the shopper Gateway at all.
    assert fresh["freshPublishesRestock"] is False
    assert fresh["freshRestockActionId"] is None
    # Eleven catalogue reads; the two customer-scoped reads carry owner-only permits.
    assert fresh["freshBaselineActionCount"] == 11
    assert not any(a.endswith("___restock_inventory") for a in fresh["freshBaselineActions"])
