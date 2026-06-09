"""Tests pinning the MANAGED AgentCore Policy contract (the 4th pillar).

Pellier replaced its local Strands ``BeforeToolCallEvent`` Cedar hook with
**managed AgentCore Policy** enforced at the Gateway. These tests pin that
migration STATICALLY (no AWS calls) so a regression back to the local
fake-Cedar gate — or a drift in the provisioning contract — trips here:

  1. The local hook + hand-rolled fake-Cedar engine are GONE (one gate only).
  2. ``scripts/deploy/deploy_policy.py`` provisions a managed Cedar engine with
     the correct GA boto3 contract (create_policy_engine / create_policy
     definition={"cedar":...} / update_gateway policyEngineConfiguration ENFORCE)
     and the correct Cedar action spelling for process_return.
  3. The experience Lambda reconstructs the ``pellier.tool_audit`` evidence row
     on the Gateway rail (so the Act II SQL proof survives).
  4. The deploy path (provisioner + deploy_all.sh) wires the policy step.
  5. The gateway execution role gets the four policy-EVALUATION permissions.

Runnable from repo root per ``pytest.ini``.
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "pellier" / "backend"
DEPLOY = REPO_ROOT / "scripts" / "deploy"

DEPLOY_POLICY = DEPLOY / "deploy_policy.py"
EXPERIENCE_LAMBDA = DEPLOY / "pellier_experience_server.py"
DEPLOY_GATEWAY = DEPLOY / "deploy_gateway.py"
PROVISIONER = REPO_ROOT / "scripts" / "provision_agentcore_end_to_end.py"
DEPLOY_ALL = DEPLOY / "deploy_all.sh"

# Cedar action spelling is keyed on the Gateway TARGET name (what the Gateway
# registers tools under), NOT the Lambda function name. The live GA engine
# rejected the function-name form on a fresh account; the verified dat403
# contract is <gateway-target-name>___<tool-name> (triple _). deploy_policy.py
# tries that first, then <target>__<tool>, then defers to the engine's own
# "did you mean" hint — so the action prefix below must be the TARGET name.
EXPERIENCE_TARGET = "pellier-concierge-experience-target"
EXPECTED_ACTION = f"{EXPERIENCE_TARGET}___process_return"


# ---------------------------------------------------------------------------
# 1. The local gate is gone (single managed gate, no hybrid confusion)
# ---------------------------------------------------------------------------


def test_local_policy_hook_removed() -> None:
    assert not (BACKEND / "services" / "policy_hook.py").exists(), (
        "services/policy_hook.py (local BeforeToolCall Cedar gate) must be removed — "
        "managed AgentCore Policy at the Gateway is now the single gate."
    )


def test_fake_cedar_engine_removed() -> None:
    assert not (BACKEND / "services" / "agentcore_policy.py").exists(), (
        "services/agentcore_policy.py (hand-rolled fake-Cedar PolicyService) must be "
        "removed — Cedar is now real + managed."
    )


def test_no_dangling_local_policy_refs() -> None:
    """No backend module still imports the removed local-policy symbols."""
    offenders = []
    for py in (BACKEND).rglob("*.py"):
        if py.name.startswith("test_"):
            continue
        text = py.read_text()
        for sym in ("PolicyEnforcementHook", "attach_policy_hook",
                    "get_policy_service", "create_policy_from_natural_language"):
            # an import/use, not a comment line
            for line in text.splitlines():
                stripped = line.strip()
                if sym in stripped and not stripped.startswith("#"):
                    offenders.append(f"{py.relative_to(REPO_ROOT)}: {stripped}")
    assert not offenders, "Dangling references to removed local-policy code:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# 2. deploy_policy.py — the managed provisioning contract
# ---------------------------------------------------------------------------


def test_deploy_policy_exists_and_uses_ga_contract() -> None:
    assert DEPLOY_POLICY.is_file(), "scripts/deploy/deploy_policy.py must exist"
    src = DEPLOY_POLICY.read_text()
    # GA bedrock-agentcore-control verbs (NOT the preview-era shape).
    assert "bedrock-agentcore-control" in src
    assert "create_policy_engine" in src
    assert "create_policy" in src
    assert 'definition={"cedar"' in src or "'cedar'" in src, "policies must be direct Cedar"
    assert "policyEngineConfiguration" in src and "ENFORCE" in src, "must attach engine in ENFORCE mode"
    # MUST NOT use the dead preview-era natural-language definition shape.
    assert "naturalLanguage" not in src, "must not use the preview-era definition={naturalLanguage} shape"


def test_deploy_policy_gates_process_return_to_damaged() -> None:
    src = DEPLOY_POLICY.read_text()
    # The action prefix is the Gateway TARGET name (the dat403-verified contract),
    # not the Lambda function name. The literal action string is now assembled at
    # runtime from candidate_actions, so assert the target-name default is present.
    assert EXPERIENCE_TARGET in src, (
        f"Cedar action prefix must be the Gateway target name {EXPERIENCE_TARGET}"
    )
    assert "___process_return" in src, "primary candidate must be target___tool (triple _)"
    # Must NOT regress to the Lambda-function-name action that the live engine rejected.
    assert "pellier-experience-server-function___process_return" not in src, (
        "must not use the Lambda function name as the Cedar action prefix — "
        "the GA engine rejects it; key on the Gateway target name"
    )
    assert "forbid(" in src and 'reason != "damaged"' in src, (
        "must FORBID process_return unless reason == 'damaged'"
    )


def test_deploy_policy_self_corrects_action_identifier() -> None:
    """The action identifier the GA engine accepts has drifted across API
    revisions, so deploy_policy.py must self-correct: try candidates, then parse
    the engine's 'did you mean' hint and retry with the exact token."""
    src = DEPLOY_POLICY.read_text()
    assert "_extract_suggested_action" in src, (
        "must parse the engine's 'did you mean' hint to recover the accepted action"
    )
    assert "candidate_actions" in src, "must try multiple candidate action formats"


def test_deploy_policy_compiles_and_exposes_helpers() -> None:
    """Import the module and confirm the porting kept the dat403 helper shape."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("deploy_policy", DEPLOY_POLICY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for fn in ("create_or_reuse_engine", "create_or_reuse_policy",
               "create_pellier_policies", "attach_engine_to_gateway",
               "create_action_policy_with_fallback", "_extract_suggested_action"):
        assert hasattr(mod, fn), f"deploy_policy.py must define {fn}"


# ---------------------------------------------------------------------------
# 3. Experience Lambda reconstructs the tool_audit evidence row
# ---------------------------------------------------------------------------


def test_experience_lambda_writes_tool_audit() -> None:
    src = EXPERIENCE_LAMBDA.read_text()
    assert "_write_tool_audit" in src, "experience Lambda must write tool_audit on the Gateway rail"
    assert "INSERT INTO" in src and "tool_audit" in src
    # JSONB columns must be cast so args->>'reason' / result->>'return_id' work.
    assert "::jsonb" in src
    # Only the audited write tool gets a row.
    assert 'tool_name == "process_return"' in src


# ---------------------------------------------------------------------------
# 4. Deploy path wires the policy step
# ---------------------------------------------------------------------------


def test_provisioner_invokes_deploy_policy() -> None:
    src = PROVISIONER.read_text()
    assert "deploy_policy.py" in src, "provisioner must call deploy_policy.py after the gateway"
    assert "POLICY_ENGINE_ID" in src, "provisioner must capture the policy engine id"


def test_deploy_all_invokes_deploy_policy() -> None:
    src = DEPLOY_ALL.read_text()
    assert "deploy_policy.py" in src and "ENFORCE" in src


# ---------------------------------------------------------------------------
# 5. Gateway role gets the policy-evaluation permissions
# ---------------------------------------------------------------------------


def test_gateway_role_has_policy_eval_perms() -> None:
    src = DEPLOY_GATEWAY.read_text()
    for action in ("bedrock-agentcore:AuthorizeAction",
                   "bedrock-agentcore:GetPolicyEngine",
                   "bedrock-agentcore:CheckAuthorizePermissions",
                   "bedrock-agentcore:PartiallyAuthorizeActions"):
        assert action in src, f"gateway role must grant {action} for invoke-time Cedar eval"
