"""Regression tests for workshop bootstrap readiness and model resolution."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[3]
MODEL_CHECK = REPO / "scripts" / "check_model_access.py"
HEALTH_GATE = REPO / "scripts" / "health-gate.sh"
PROVISIONER = REPO / "scripts" / "provision_agentcore_end_to_end.py"
AGENTCORE_RENDERER = REPO / "scripts" / "deploy" / "render_agentcore_project.py"
BOOTSTRAP = REPO / "scripts" / "bootstrap-labs.sh"
RESET_GOVERNED = REPO / "scripts" / "reset-governed-workshop.sh"
CATALOG_SEED = REPO / "scripts" / "seed_pellier_catalog.py"
WAREHOUSE_MIGRATION = REPO / "scripts" / "migrations" / "006_warehouse_inventory.sql"
SEED_PREFERENCES = REPO / "scripts" / "seed-sample-preferences.sh"
FACILITATOR_DRY_RUN = REPO / "scripts" / "dry-run-builders.sh"
WRITE_TEST_CREDENTIALS = REPO / "scripts" / "write-test-credentials.sh"
ENVIRONMENT_BOOTSTRAP = REPO / "scripts" / "bootstrap-environment.sh"


def _load_model_check():
    spec = importlib.util.spec_from_file_location("pellier_model_check", MODEL_CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for model in module.MODELS:
        model.pop("_resolved_id", None)
    return module


def test_model_preflight_persists_sonnet_46_runtime_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_model_check()
    env_file = tmp_path / ".env"
    env_file.write_text("BEDROCK_OPUS_MODEL=stale\n", encoding="utf-8")

    def fake_check(_client, _rerank_client, model):
        if model.get("role") == "editorial":
            return False
        if model.get("role") == "sonnet":
            model["_resolved_id"] = "global.anthropic.claude-sonnet-4-6"
        if model.get("role") == "fast":
            model["_resolved_id"] = (
                "global.anthropic.claude-haiku-4-5-20251001-v1:0"
            )
        return True

    monkeypatch.setattr(module, "check_model", fake_check)
    monkeypatch.setattr(module.boto3, "client", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        sys, "argv", ["check_model_access.py", "--write-env", str(env_file)]
    )

    module.main()

    values = dict(
        line.split("=", 1)
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    assert values["BEDROCK_OPUS_MODEL"] == "global.anthropic.claude-sonnet-4-6"
    assert values["BEDROCK_ROUTER_MODEL"] == "global.anthropic.claude-sonnet-4-6"
    assert (
        values["BEDROCK_FAST_MODEL"]
        == "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    assert "CLAUDE_CODE_MODEL" not in values
    assert values["AGENT_MODEL_ID"] == "global.anthropic.claude-sonnet-4-6"
    assert values["BEDROCK_MODEL_ACCESS_READY"] == "true"


def test_claude_code_pins_global_sonnet_46_profile() -> None:
    """Workshop Studio does not expose Sonnet 5, so the CLI must pin the
    global Sonnet 4.6 profile instead of the floating ``sonnet`` alias
    (which a current CLI resolves to a denied model on the event account)."""
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert "export CLAUDE_CODE_USE_BEDROCK=1" in source
    assert (
        "export ANTHROPIC_MODEL="
        "${ANTHROPIC_MODEL:-global.anthropic.claude-sonnet-4-6}" in source
    )
    assert "ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-sonnet}" not in source
    assert "CLAUDE_CODE_MODEL" not in source


def test_managed_runtime_handoff_preserves_the_fast_model_profile() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert (
        "export BEDROCK_FAST_MODEL="
        "'${BEDROCK_FAST_MODEL:-global.anthropic.claude-haiku-4-5-20251001-v1:0}'"
        in source
    )


def test_facilitator_dry_run_preflights_the_recommended_claude_lane() -> None:
    """Lab 1 recommends Claude Code, so the release gate must prove it starts.

    The two things that drift per account are the CLI package and Bedrock model
    access under the participant instance role. Both fail silently for a
    facilitator until a room hits them, so the rehearsal probes them directly.
    """
    source = FACILITATOR_DRY_RUN.read_text(encoding="utf-8")
    assert "command -v claude" in source
    assert "CLAUDE_CODE_USE_BEDROCK=1" in source
    assert "PELLIER_CLAUDE_READY" in source


def test_facilitator_dry_run_probes_the_pinned_model_not_the_floating_alias() -> None:
    """``--model sonnet`` would override the pin with the CLI's floating alias.

    A current CLI resolves that alias to a newer Sonnet than Workshop Studio
    accounts expose, so passing it would either fail on a correctly provisioned
    account or pass while testing a model no participant uses. Selection must
    come from ANTHROPIC_MODEL, which bootstrap pins to the same profile.
    """
    source = FACILITATOR_DRY_RUN.read_text(encoding="utf-8")
    assert "--model sonnet" not in source
    assert 'ANTHROPIC_MODEL="$CLAUDE_MODEL_PIN"' in source
    assert (
        'CLAUDE_MODEL_PIN="${ANTHROPIC_MODEL:-global.anthropic.claude-sonnet-4-6}"'
        in source
    )


def test_facilitator_dry_run_covers_both_lab1_build_sites() -> None:
    source = FACILITATOR_DRY_RUN.read_text(encoding="utf-8")
    assert "agents/inventory_agent.py" in source
    assert "agents/inventory_agent_solution.py" in source
    assert "services/agent_tools.py" in source
    assert "agent_tools_check_inventory_solution.py" in source
    assert '"Inventory Agent"[[:space:]]*:[[:space:]]*"shipped"' in source
    assert '"check_inventory"[[:space:]]*:[[:space:]]*"shipped"' in source


def test_governed_bootstrap_restores_all_participant_starters() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    command = "python3 scripts/reset_participant_exercises.py --repo \"$REPO_PATH\""
    assert command in bootstrap
    governed_branch = bootstrap.index(
        'log "Governed format: preserving Inventory Agent and check_inventory scaffolds'
    )
    managed_provision = bootstrap.index(
        'log "Provisioning full AgentCore managed path'
    )
    assert governed_branch < bootstrap.index(command) < managed_provision


def test_governed_reset_restores_participant_starters_before_health_gate() -> None:
    reset = RESET_GOVERNED.read_text(encoding="utf-8")
    command = '"$PYTHON" "$REPO/scripts/reset_participant_exercises.py"'
    health_gate = "_run_health_gate || exit 1"
    assert command in reset
    assert reset.index(command) < reset.index(health_gate)


def test_governed_identity_bootstrap_covers_jessica_as_a_shopper_principal() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    health = HEALTH_GATE.read_text(encoding="utf-8")

    assert "source ~/pellier-token.sh jessica" in bootstrap
    assert "for SHOPPER in marco anna theo jessica" in bootstrap
    assert "for shopper in marco anna theo jessica" in health
    assert "Unknown Cognito username" in bootstrap
    assert 'next((x for x in us if x["username"].lower()==w), us[0])' not in bootstrap


def test_cloudformation_waits_for_stage2_readiness_not_only_the_editor() -> None:
    """A box is not ready until the app, managed rail, and receipt gate pass."""
    source = ENVIRONMENT_BOOTSTRAP.read_text(encoding="utf-8")

    assert 'STAGE2_ENV_MANIFEST="/etc/pellier/bootstrap-stage2.env"' in source
    assert 'chmod 600 "$temp_manifest"' in source
    assert 'chown root:root "$temp_manifest"' in source
    for required in (
        "COGNITO_USER_POOL_ID",
        "COGNITO_CLIENT_ID",
        "COGNITO_TEST_CREDENTIALS_SECRET_ARN",
        "DB_SECRET_ARN",
        "DB_CLUSTER_ARN",
        "AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN",
        "WORKSHOP_SOURCE_REVISION",
    ):
        assert required in source

    stage2 = source.index("Running Stage 2: Labs Bootstrap and governed readiness gate")
    success = source.index('signal_cloudformation \\\n    "SUCCESS"')
    assert stage2 < success
    assert "nohup /tmp/bootstrap-labs.sh" not in source
    assert "pgrep -f bootstrap-labs.sh" not in source
    assert "Authenticated sign-in, managed invocation, and durable evidence receipt passed" in source


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _valid_managed_receipt() -> dict[str, object]:
    canonical_names = [f"tool_{index}" for index in range(15)]
    return {
        "status": "ready",
        "cli": {"package": "@aws/agentcore@0.29.0"},
        "runtime": {"runtime_arn": "arn:aws:bedrock-agentcore:runtime/test"},
        "operator_runtime": {
            "runtime_arn": "arn:aws:bedrock-agentcore:runtime/operator-fixture",
            "authentication": "AWS_IAM",
        },
        "memory": {
            "memory_id": "memory-123",
            "seed": {"status": "ready"},
        },
        "gateway": {
            "gateway_id": "gateway-123",
            "gateway_arn": "arn:aws:bedrock-agentcore:gateway/test",
            "gateway_url": "https://gateway.example.test/mcp",
        },
        "policy": {
            "policy_engine_id": "policy-123",
            "mode": "ENFORCE",
        },
        "observability": {
            "transaction_search": {
                "destination": "CloudWatchLogs",
                "status": "ACTIVE",
                "resource_policy": "TransactionSearchXRayAccess",
                "resource_policy_document": (
                    '{"Version":"2012-10-17","Statement":'
                    '[{"Sid":"TransactionSearchXRayAccess"}]}'
                ),
                "cleanup": {
                    "destination_changed": True,
                    "previous_destination": "XRay",
                    "resource_policy_created": True,
                    "previous_resource_policy_document": None,
                },
            },
            "control_plane_audit": {
                "source": "CloudTrail Event History",
                "event_source": "bedrock-agentcore.amazonaws.com",
                "event_name": "CreateAgentRuntime",
                "event_time": "2026-08-13T12:00:00Z",
                "resource_type": "runtime",
            },
            "runtime_log_group": {
                "name": "/aws/bedrock-agentcore/runtimes/pellier_orchestrator-abc123-DEFAULT",
                "kms_key_arn": (
                    "arn:aws:kms:us-east-1:123456789012:"
                    "key/12345678-1234-1234-1234-1234567890ab"
                ),
                "retention_days": 30,
                "cleanup": {
                    "created_by_workshop": True,
                    "previous_kms_key_arn": None,
                    "previous_retention_days": None,
                },
            },
            "operator_runtime_log_group": {
                "name": "/aws/bedrock-agentcore/runtimes/pellier_operator-fixture-DEFAULT",
                "kms_key_arn": "arn:aws:kms:us-east-1:123456789012:key/fixture",
                "retention_days": 30,
                "cleanup": {"created_by_workshop": True},
            },
            "trace_log_groups": {
                "groups": [
                    {
                        "name": "aws/spans",
                        "kms_key_arn": (
                            "arn:aws:kms:us-east-1:123456789012:"
                            "key/12345678-1234-1234-1234-1234567890ab"
                        ),
                        "retention_days": 30,
                        "cleanup": {
                            "created_by_workshop": True,
                            "previous_kms_key_arn": None,
                            "previous_retention_days": None,
                        },
                    },
                    {
                        "name": "/aws/application-signals/data",
                        "kms_key_arn": (
                            "arn:aws:kms:us-east-1:123456789012:"
                            "key/12345678-1234-1234-1234-1234567890ab"
                        ),
                        "retention_days": 30,
                        "cleanup": {
                            "created_by_workshop": True,
                            "previous_kms_key_arn": None,
                            "previous_retention_days": None,
                        },
                    },
                ],
                "kms_key_arn": (
                    "arn:aws:kms:us-east-1:123456789012:"
                    "key/12345678-1234-1234-1234-1234567890ab"
                ),
                "retention_days": 30,
            },
            "unified_trace": {
                "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                "session_id": "builders-smoke-session-0000000000000001",
                "runtime_arn": "arn:aws:bedrock-agentcore:runtime/test",
                "runtime_log_group": (
                    "/aws/bedrock-agentcore/runtimes/"
                    "pellier_orchestrator-abc123-DEFAULT"
                ),
                "span_count": 3,
                "span_names": [
                    "chat",
                    "execute_tool search_products_hybrid",
                    "invoke_agent pellier_orchestrator",
                ],
                "agent_span": True,
                "model_span": True,
                "tool_span": True,
                "agent_input_observed": True,
                "agent_output_observed": True,
                "tool_input_output_observed": True,
                "tool_input_output_structured": True,
                "tool_input_output_sanitized": True,
                "attribute_contract": {
                    "agent_input": "gen_ai.input.messages",
                    "agent_output": "gen_ai.output.messages",
                    "tool_input": "gen_ai.tool.call.arguments",
                    "tool_output": "gen_ai.tool.call.result",
                },
                "step_latency_observed": True,
                "step_latency_ms": {"agent": 125, "model": 80, "tool": 30},
                "model_ids": ["global.anthropic.claude-sonnet-4-6"],
                "tool_names": ["search_products_hybrid"],
                "provenance": "agentcore-unified-telemetry",
            },
        },
        "verification": {
            "local_tool_schema": {
                "count": 15,
                "canonical_names": canonical_names,
            },
            "gateway_control_plane": {
                "target_count": 4,
                "target_names": [
                    "catalog-target",
                    "experience-target",
                    "inventory-target",
                    "returns-target",
                ],
                "policy_mode": "ENFORCE",
            },
            "targets_attached": True,
            "gateway_tools_discovered": True,
            "gateway_tool_count": 15,
            "gateway_tool_names": canonical_names,
            "gateway_prefixed_tool_names": [
                f"target__{name}" for name in canonical_names
            ],
            "memory_seeded": True,
            "live_policy_allow": True,
            "live_policy_deny": True,
            "live_policy_proof": {
                "allow": {
                    "outcome": "allow",
                    "tool_audit_row_after_call": {"audit_id": 1},
                },
                "deny": {
                    "outcome": "deny",
                    "cedar_denial": True,
                    "tool_audit_row_after_call": None,
                },
            },
            "authenticated_runtime_invoke_smoke": True,
            "transaction_search_ready": True,
            "trace_log_groups_encrypted": True,
            "trace_log_groups_retention_bounded": True,
            "control_plane_audit_verified": True,
            "runtime_log_group_encrypted": True,
            "runtime_log_group_retention_bounded": True,
            "unified_trace_delivered": True,
            "unified_trace_agent_span": True,
            "unified_trace_model_span": True,
            "unified_trace_tool_span": True,
            "unified_trace_agent_input": True,
            "unified_trace_agent_output": True,
            "unified_trace_tool_io_structured": True,
            "unified_trace_tool_io_sanitized": True,
            "unified_trace_step_latency": True,
            "runtime_invoke_smoke": {
                "rail": "gateway-mcp",
                "session_id": "builders-smoke-session-0000000000000001",
                "response_preview": "A live managed response.",
                "build_fingerprint": "fixture-package",
                "build_fingerprint_expected": "fixture-package",
                "build_fingerprint_match": True,
            },
            "operator_runtime_invoke_smoke": {
                "runtime_arn": "arn:aws:bedrock-agentcore:runtime/operator-fixture",
                "session_id": "operator-proof-000000000000000000001",
                "build_fingerprint": "fixture-package",
                "build_fingerprint_match": True,
                "executed_nodes": ["case-investigator", "resolution-planner"],
                "fixture": True,
            },
            "runtime_build_fingerprint_match": True,
            "operator_runtime_build_fingerprint_match": True,
        },
    }


def _run_health_gate(
    tmp_path: Path,
    model_ready: bool,
    *,
    workshop_format: str = "builders",
    managed_ready: bool = False,
    customer_count: int = 5,
    order_count: int = 20,
    audit_count: int = 1,
    retrieval_receipts_exists: bool = True,
    retrieval_citation_snapshot_schema_ready: bool = True,
    governed_turn_receipts_exists: bool = True,
    evidence_ledger_schema_exists: bool = True,
    commerce_schema_exists: bool = True,
    policy_decisions_exists: bool = True,
    workshop_runs_exists: bool = True,
    managed_receipt: dict[str, object] | None = None,
    shopper_in_operator_group: bool = False,
    operator_token_ready: bool = True,
    shopper_claim_ready: bool = True,
    quarantine: str | None = None,
    provision_state: str | None = None,
    provision_phase: str | None = None,
) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / "repo"
    fake_bin = tmp_path / "bin"
    # A real-looking access token for the seeded shopper. The gate decodes its
    # payload the way the application does, so the claim has to be inside it.
    import base64 as _b64

    def _jwt_segment(payload: dict) -> str:
        return _b64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

    shopper_payload = {"sub": "marco-sub", "token_use": "access", "username": "marco"}
    if shopper_claim_ready:
        shopper_payload["custom:customer_id"] = "CUST-MARCO"
    shopper_jwt = ".".join((_jwt_segment({"alg": "none"}), _jwt_segment(shopper_payload), "sig"))
    repo.mkdir()
    fake_bin.mkdir()
    # Both lifecycle markers default to /var/lib/pellier on a box. Point them at
    # the sandbox so a developer's real markers never leak into the verdict.
    quarantine_file = tmp_path / "quarantine"
    provision_state_file = tmp_path / "provision-state"
    if quarantine is not None:
        quarantine_file.write_text(quarantine, encoding="utf-8")
    if provision_state is not None:
        provision_state_file.write_text(provision_state + "\n", encoding="utf-8")
    env_lines = [
        f"BEDROCK_MODEL_ACCESS_READY={'true' if model_ready else 'false'}",
        f"WORKSHOP_FORMAT={workshop_format}",
    ]
    if managed_ready:
        env_lines.extend(
            [
                "AGENTCORE_MEMORY_ID=memory-123",
                "AGENTCORE_RUNTIME_ENDPOINT=arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
                (
                    "USE_AGENTCORE_RUNTIME=false"
                    if workshop_format == "governed"
                    else "USE_AGENTCORE_RUNTIME=true"
                ),
                "AGENTCORE_GATEWAY_URL=https://gateway.example.test/mcp",
                "AGENTCORE_GATEWAY_ARN=arn:aws:bedrock-agentcore:us-east-1:123:gateway/test",
                "AGENTCORE_POLICY_ENGINE_ID=policy-123",
                # A provisioned governed box has a pool, and the operator group check
                # and live sign-in check need one. Without it the gate correctly
                # reports the desk unverified.
                "COGNITO_USER_POOL_ID=us-east-1_example",
                "COGNITO_CLIENT_ID=client-123",
                "COGNITO_CLIENT_SECRET=test-client-secret",
                "COGNITO_DOMAIN=pellier-example.auth.us-east-1.amazoncognito.com",
                "COGNITO_TEST_CREDENTIALS_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123:secret:test-credentials",
                "WORKSHOP_ID=example",
            ]
        )
        (tmp_path / "managed.json").write_text(
            json.dumps(managed_receipt or _valid_managed_receipt()),
            encoding="utf-8",
        )
    (repo / ".env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    _write_executable(
        fake_bin / "curl",
        """#!/bin/bash
case "$*" in
  *api/health*) printf '{"status":"healthy"}' ;;
  *memory/status*) printf '{"live":true,"source":"agentcore-sdk","resource_status":"ACTIVE"}' ;;
  *) printf '<!doctype html><div id="root"></div>' ;;
esac
""",
    )
    _write_executable(
        fake_bin / "psql",
        f"""#!/bin/bash
case "$*" in
  *inventory_consistency_check*) printf '0\n' ;;
  *"principal_customers WHERE principal_sub"*) printf 'CUST-MARCO\n' ;;
  *product_catalog*) printf '1000\n' ;;
  *warehouse_inventory*) printf '180\n' ;;
  *governed_receipts*) printf '1\n' ;;
  *customers*) printf '{customer_count}\n' ;;
  *orders*) printf '{order_count}\n' ;;
  *tool_audit*) printf '{audit_count}\n' ;;
  *"to_regclass('pellier.retrieval_receipts')"*) printf '{"pellier.retrieval_receipts" if retrieval_receipts_exists else ""}\n' ;;
  *"column_name IN ('citation_snapshots', 'citation_snapshot_hash')"*) printf '{"2" if retrieval_citation_snapshot_schema_ready else "0"}\n' ;;
  *"to_regclass('pellier.governed_turn_receipts')"*) printf '{"pellier.governed_turn_receipts" if governed_turn_receipts_exists else ""}\n' ;;
  *"to_regclass('pellier.model_invocation_receipts')"*) printf '{"pellier.model_invocation_receipts" if evidence_ledger_schema_exists else ""}\n' ;;
  *"to_regclass('pellier.evidence_ledger_event_refs')"*) printf '{"pellier.evidence_ledger_event_refs" if evidence_ledger_schema_exists else ""}\n' ;;
  *"to_regclass('pellier.commerce_receipts')"*) printf '{"pellier.commerce_receipts" if commerce_schema_exists else ""}\n' ;;
  *"to_regclass('pellier.commerce_payment_events')"*) printf '{"pellier.commerce_payment_events" if commerce_schema_exists else ""}\n' ;;
  *"to_regclass('pellier.policy_decisions')"*) printf '{"pellier.policy_decisions" if policy_decisions_exists else ""}\n' ;;
  *"to_regclass('pellier.workshop_runs')"*) printf '{"pellier.workshop_runs" if workshop_runs_exists else ""}\n' ;;
  *"column_name = 'requester_kind'"*) printf 'requester_kind\n' ;;
esac
""",
    )
    _write_executable(fake_bin / "node", "#!/bin/bash\nprintf 'v20.20.2\\n'\n")
    # The fake `aws` used to print ENFORCE for every invocation. The operator-group check
    # asks a different question per username, and answering it uniformly would make the
    # shopper-in-group case unrepresentable — which is the case the check exists for.
    _write_executable(
        fake_bin / "aws",
        f"""#!/bin/bash
case "$*" in
  *admin-list-groups-for-user*)
    for arg in "$@"; do
      case "$arg" in
        operator) printf 'pellier-operators\n'; exit 0 ;;
        marco|anna|theo)
          if [ "{'true' if shopper_in_operator_group else 'false'}" = "true" ]; then
            printf 'pellier-operators\n'
          fi
          exit 0 ;;
      esac
    done
    exit 0 ;;
  *describe-user-pool-client*AllowedOAuthFlows*)
    printf 'code\\n'
    exit 0 ;;
  *describe-user-pool-client*AllowedOAuthScopes*)
    printf 'openid email profile\\n'
    exit 0 ;;
  *admin-initiate-auth*USERNAME=marco*)
    printf '%s\\n' '{shopper_jwt}'
    exit 0 ;;
  *admin-initiate-auth*)
    if [ "{'true' if operator_token_ready else 'false'}" = "true" ]; then
      printf 'operator-access-token\\n'
    else
      printf 'None\\n'
    fi
    exit 0 ;;
  *get-user*)
    printf 'operator\\n'
    exit 0 ;;
  *get-secret-value*)
    printf '%s\\n' '{{"users": [{{"username": "marco", "password": "pw"}}, {{"username": "operator", "password": "pw"}}]}}'
    exit 0 ;;
  *) printf 'ENFORCE\n' ;;
esac
""",
    )
    env = os.environ.copy()
    for managed_key in (
        "AGENTCORE_MEMORY_ID",
        "AGENTCORE_RUNTIME_ENDPOINT",
        "USE_AGENTCORE_RUNTIME",
        "AGENTCORE_GATEWAY_URL",
        "AGENTCORE_GATEWAY_ARN",
        "AGENTCORE_POLICY_ENGINE_ID",
        "AGENTCORE_MANAGED_OUTPUT_JSON",
    ):
        env.pop(managed_key, None)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["PELLIER_REPO"] = str(repo)
    env["PELLIER_QUARANTINE_FILE"] = str(quarantine_file)
    env["PELLIER_PROVISION_STATE_FILE"] = str(provision_state_file)
    env.pop("PELLIER_PROVISION_PHASE", None)
    if provision_phase is not None:
        env["PELLIER_PROVISION_PHASE"] = provision_phase
    if managed_ready:
        env["AGENTCORE_MANAGED_OUTPUT_JSON"] = str(tmp_path / "managed.json")
    return subprocess.run(
        ["bash", str(HEALTH_GATE)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_core_health_gate_allows_missing_optional_agentcore_pillars(
    tmp_path: Path,
) -> None:
    proc = _run_health_gate(tmp_path, model_ready=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "READY" in proc.stdout
    assert "AGENTCORE_MEMORY_ID empty" in proc.stdout
    assert "AGENTCORE_RUNTIME_ENDPOINT empty" in proc.stdout
    assert "AGENTCORE_GATEWAY_URL empty" in proc.stdout


def test_core_health_gate_requires_model_preflight(tmp_path: Path) -> None:
    proc = _run_health_gate(tmp_path, model_ready=False)
    assert proc.returncode == 1
    assert "model-access preflight did not pass" in proc.stdout


def test_governed_health_gate_rejects_missing_agentcore_pillars(
    tmp_path: Path,
) -> None:
    proc = _run_health_gate(
        tmp_path,
        model_ready=True,
        workshop_format="governed",
    )
    assert proc.returncode == 1
    assert "AGENTCORE_MEMORY_ID empty" in proc.stdout
    assert "AGENTCORE_RUNTIME_ENDPOINT empty" in proc.stdout
    assert "AGENTCORE_GATEWAY_URL empty" in proc.stdout
    assert "AGENTCORE_POLICY_ENGINE_ID empty" in proc.stdout
    assert "NOT READY" in proc.stdout


def test_governed_health_gate_requires_complete_managed_receipt(
    tmp_path: Path,
) -> None:
    proc = _run_health_gate(
        tmp_path,
        model_ready=True,
        workshop_format="governed",
        managed_ready=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "gateway-mcp Runtime smoke" in proc.stdout
    assert "Labs 1-2 start in-process" in proc.stdout
    assert "READY" in proc.stdout


def test_governed_health_gate_rejects_incomplete_managed_receipt(
    tmp_path: Path,
) -> None:
    proc = _run_health_gate(
        tmp_path,
        model_ready=True,
        workshop_format="governed",
        managed_ready=True,
        managed_receipt={"status": "ready"},
    )
    assert proc.returncode == 1
    assert "cli.package" in proc.stdout
    assert "Managed provisioning receipt is incomplete or degraded" in proc.stdout
    assert "NOT READY" in proc.stdout


@pytest.mark.parametrize(
    ("missing_data", "message"),
    [
        ({"customer_count": 0}, "Customer records empty or missing"),
        ({"order_count": 19}, "Orders incomplete or missing"),
        (
            {"audit_count": 0},
            "JSONB tool execution ledger has no completed agent or Gateway actions",
        ),
        (
            {"retrieval_receipts_exists": False},
            "Retrieval receipt schema missing",
        ),
        (
            {"retrieval_citation_snapshot_schema_ready": False},
            "Retrieval citation snapshot schema missing",
        ),
        (
            {"governed_turn_receipts_exists": False},
            "Governed turn receipt schema missing",
        ),
        (
            {"evidence_ledger_schema_exists": False},
            "Evidence Ledger schema missing",
        ),
        (
            {"commerce_schema_exists": False},
            "Proof-carrying commerce schema missing",
        ),
        (
            {"policy_decisions_exists": False},
            "Policy decision schema missing. Apply scripts/migrations/048_policy_decisions.sql",
        ),
        (
            {"workshop_runs_exists": False},
            "Workshop run schema missing. Apply scripts/migrations/049_workshop_runs.sql",
        ),
    ],
)
def test_governed_health_gate_rejects_missing_operational_data(
    tmp_path: Path,
    missing_data: dict[str, int | bool],
    message: str,
) -> None:
    proc = _run_health_gate(
        tmp_path,
        model_ready=True,
        workshop_format="governed",
        managed_ready=True,
        **missing_data,
    )
    assert proc.returncode == 1
    assert message in proc.stdout
    assert "NOT READY" in proc.stdout


def test_runtime_arn_is_recorded_before_smoke() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")
    renderer = AGENTCORE_RENDERER.read_text(encoding="utf-8")
    record = source.index('result["runtime"] = {')
    smoke = source.index("runtime_smoke = _authenticated_runtime_smoke(")
    assert record < smoke
    assert '{"name": "BEDROCK_ROUTER_MODEL", "value": model_id}' in renderer
    assert 'os.environ.get("AGENT_MODEL_ID", "global.' not in source


def _load_provisioner():
    spec = importlib.util.spec_from_file_location("pellier_provisioner", PROVISIONER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("rail", "should_pass"),
    [
        ("gateway-mcp", True),
        ("in-process", False),
        ("", False),
    ],
)
def test_runtime_smoke_requires_gateway_mcp_rail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rail: str,
    should_pass: bool,
) -> None:
    module = _load_provisioner()

    class Secrets:
        def get_secret_value(self, *, SecretId):
            if "client" in SecretId:
                return {"SecretString": json.dumps({"client_secret": "secret"})}
            return {
                "SecretString": json.dumps(
                    {"users": [{"username": "Marco", "password": "Password1"}]}
                )
            }

    class Cognito:
        def admin_initiate_auth(self, **_kwargs):
            return {"AuthenticationResult": {"AccessToken": "jwt-token"}}

        def get_user(self, **_kwargs):
            return {"Username": "marco"}

    def fake_client(service, **_kwargs):
        return Secrets() if service == "secretsmanager" else Cognito()

    monkeypatch.setattr(module.boto3, "client", fake_client)

    access_token, username = module._cognito_access_token(
        region="us-east-1",
        user_pool_id="us-east-1_pool",
        client_id="client-id",
        credentials_secret_arn="test-users",
        client_secret_arn="client-secret",
    )
    assert access_token == "jwt-token"
    assert username == "marco"

    runtime_payload = {
        "response": "runtime response",
        "rail": rail,
    }
    monkeypatch.setattr(
        module,
        "_agentcore",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["agentcore", "invoke"],
            returncode=0,
            stdout=json.dumps(
                {
                    "success": True,
                    "response": json.dumps(runtime_payload),
                }
            ),
            stderr="",
        ),
    )

    invoke = lambda: module._authenticated_runtime_smoke(
        root=tmp_path,
        access_token=access_token,
        username=username,
        env={},
    )
    if should_pass:
        assert invoke()["rail"] == "gateway-mcp"
    else:
        with pytest.raises(RuntimeError, match="Gateway MCP"):
            invoke()


def test_agentcore_command_errors_redact_bearer_tokens(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_provisioner()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="denied",
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        module._run(
            ["agentcore", "invoke", "--bearer-token", "secret-token"],
            cwd=tmp_path,
        )

    assert "secret-token" not in str(exc_info.value)
    assert "--bearer-token <redacted>" in str(exc_info.value)


def test_policy_attachment_is_a_provisioning_hard_gate() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")
    renderer = AGENTCORE_RENDERER.read_text(encoding="utf-8")

    assert '"policyEngineConfiguration"' in renderer
    assert '"mode": "ENFORCE"' in renderer
    assert "policy_state = _require_state_resource(" in source
    assert '"policyEngines", POLICY_ENGINE_NAME' in source
    assert 'result["status"] = "ready"' in source
    assert source.index(
        "policy_state = _require_state_resource("
    ) < source.index('result["status"] = "ready"')
    assert "_live_policy_proof(" in source
    assert '"live_policy_allow"' in source
    assert '"live_policy_deny"' in source
    assert "Gateway Policy mode is" in source
    assert "_discover_live_gateway_tools(" in source
    assert '"gateway_tools_discovered"' in source
    assert '"gateway_tool_count"' in source
    assert "len(tools) != len(expected)" in source
    assert "Gateway target mismatch" in source


def test_bootstrap_normalizes_cognito_aliases_before_managed_provisioning() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")
    pool_alias = (
        'export COGNITO_POOL="${COGNITO_POOL:-'
        '${COGNITO_POOL_ID:-${COGNITO_USER_POOL_ID:-}}}"'
    )
    client_alias = (
        'export COGNITO_CLIENT="${COGNITO_CLIENT:-'
        '${COGNITO_CLIENT_ID:-}}"'
    )
    provision = "python3 '$REPO_PATH/scripts/provision_agentcore_end_to_end.py'"

    assert source.index(pool_alias) < source.index(provision)
    assert source.index(client_alias) < source.index(provision)
    assert "export COGNITO_POOL='${COGNITO_POOL:-}'" in source
    assert "export COGNITO_CLIENT='${COGNITO_CLIENT:-}'" in source
    assert "export AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN=" in source
    assert "export AGENTCORE_RUNTIME_LOG_RETENTION_DAYS=" in source


def test_deploy_wrapper_requires_runtime_log_protection_inputs() -> None:
    source = (REPO / "scripts" / "deploy" / "deploy_all.sh").read_text(
        encoding="utf-8"
    )

    assert "AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN" in source
    assert "AGENTCORE_RUNTIME_LOG_RETENTION_DAYS" in source


def test_governed_reset_restores_catalog_before_exact_warehouse_matrix() -> None:
    reset = RESET_GOVERNED.read_text(encoding="utf-8")
    seeder = CATALOG_SEED.read_text(encoding="utf-8")
    warehouse = WAREHOUSE_MIGRATION.read_text(encoding="utf-8")

    catalog_reset = '"$REPO/scripts/seed_pellier_catalog.py"'
    warehouse_reset = "006_warehouse_inventory.sql"
    assert reset.index(catalog_reset) < reset.index(warehouse_reset)
    assert "quantity = EXCLUDED.quantity" in seeder
    assert "DELETE FROM pellier.warehouse_inventory;" in warehouse
    assert "IF nrows <> 180 OR invalid_products <> 0 THEN" in warehouse


def test_facilitator_dry_run_requires_managed_rail_and_current_policy_receipts() -> None:
    source = FACILITATOR_DRY_RUN.read_text(encoding="utf-8")
    assert '-H "Authorization: Bearer ${POLICY_TOKEN}"' in source
    assert 'runtime_rail" == "gateway-mcp"' in source
    assert "gateway_initiate_return.py" in source
    assert "--expect allow --record-receipt" in source
    assert "--expect deny --record-receipt" in source
    assert "POLICY_ALLOW_SESSION" in source
    assert "POLICY_DENY_SESSION" in source
    assert "absence_verified" in source
    assert "Skipping local initiate_return; governed mutations require gateway-mcp" in source
    assert "JOIN pellier.tool_audit ta ON ta.audit_id = gr.audit_id" in source
    assert "gr.identity_source='cognito'" in source


def test_preference_seed_uses_access_token() -> None:
    source = SEED_PREFERENCES.read_text(encoding="utf-8")
    assert "AuthenticationResult.AccessToken" in source
    assert "AuthenticationResult.IdToken" not in source


def test_hash_locked_test_requirements_include_async_pytest_plugin() -> None:
    lock = (REPO / "pellier" / "backend" / "requirements.lock").read_text(
        encoding="utf-8"
    )
    assert "pytest-asyncio==1.4.0" in lock


# ---------------------------------------------------------------------------
# Governed database roles and RLS provisioning (spec sections 10, 11)
# ---------------------------------------------------------------------------
#
# Three separate steps have to survive edits to two long shell scripts, and a
# missing one fails quietly rather than loudly:
#
#   * bootstrap must apply migration 016, or the runtime roles and policies
#     never exist and the governed rail silently runs ungoverned;
#   * bootstrap must seed the principal mappings, or Row-Level Security denies
#     every signed-in shopper their own orders;
#   * reset must re-apply 016, because a participant experimenting with
#     `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` would otherwise leave the
#     box in a state where the exercise cannot be repeated.

RLS_MIGRATION = REPO / "scripts" / "migrations" / "016_runtime_roles_rls.sql"
PRINCIPAL_SEED = REPO / "scripts" / "seed_principal_mappings.py"


def test_rls_migration_and_seeder_exist() -> None:
    assert RLS_MIGRATION.is_file(), "migration 016 is missing"
    assert PRINCIPAL_SEED.is_file(), "principal mapping seeder is missing"


def test_bootstrap_applies_the_rls_migration() -> None:
    assert "016_runtime_roles_rls.sql" in BOOTSTRAP.read_text(), (
        "bootstrap must apply migration 016, or pellier_agent, pellier_query, "
        "and the RLS policies never exist on a fresh box"
    )


def test_query_statistics_extension_is_created_during_bootstrap_and_reset() -> None:
    name = "054_query_statistics.sql"
    sql = (REPO / "scripts/migrations" / name).read_text()
    assert "CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;" in sql
    assert name in BOOTSTRAP.read_text()
    assert name in RESET_GOVERNED.read_text()


def test_bootstrap_seeds_the_principal_mappings() -> None:
    body = BOOTSTRAP.read_text()
    assert "seed_principal_mappings.py" in body, (
        "bootstrap must seed pellier.principal_customers; an empty mapping "
        "denies every signed-in shopper their own orders"
    )


def test_reset_reapplies_the_rls_migration() -> None:
    assert "016_runtime_roles_rls.sql" in RESET_GOVERNED.read_text(), (
        "reset must re-apply migration 016 so a disabled policy or altered "
        "grant returns to the shipped state"
    )


def test_reset_verifies_the_principal_mappings() -> None:
    body = RESET_GOVERNED.read_text()
    invocation = next(
        (line for line in body.splitlines() if "seed_principal_mappings.py" in line),
        "",
    )
    assert invocation and "--check" in invocation, (
        "reset must verify pellier.principal_customers; it is authorization "
        "config rather than evidence, so it is not truncated, but an empty "
        "mapping must not pass silently"
    )
    # Both identity steps fail closed: a warning let the reset report READY while
    # every shopper was denied their own rows or every owner-scoped read was denied.
    assert "_quarantine principal-mappings" in body
    assert "_quarantine claim-trigger" in body
    assert 'warn "RLS principal mappings incomplete' not in body
    assert 'warn "Customer claim trigger' not in body


def test_health_gate_proves_the_customer_claim_on_a_shopper_token() -> None:
    gate = HEALTH_GATE.read_text(encoding="utf-8")
    assert "custom:customer_id" in gate
    assert "principal_customers WHERE principal_sub" in gate
    assert "carries no custom:customer_id" in gate


def test_the_health_gate_refuses_a_shopper_token_without_the_customer_claim(tmp_path) -> None:
    """A detached claim trigger denies every owner-scoped read while sign-in still works."""
    proc = _run_health_gate(
        tmp_path, model_ready=True, workshop_format="governed", managed_ready=True,
        shopper_claim_ready=False,
    )
    assert proc.returncode != 0, proc.stdout
    assert "carries no custom:customer_id" in proc.stdout


def test_the_health_gate_passes_a_shopper_token_whose_claim_matches_the_mapping(tmp_path) -> None:
    proc = _run_health_gate(
        tmp_path, model_ready=True, workshop_format="governed", managed_ready=True,
    )
    assert "custom:customer_id=CUST-MARCO, matching the mapping" in proc.stdout, proc.stdout


def test_reset_does_not_truncate_the_authorization_mapping() -> None:
    """The mapping is configuration, not turn evidence.

    Truncating it would make every reset break every signed-in shopper until
    someone re-ran the seeder.
    """
    body = RESET_GOVERNED.read_text()
    truncate_block = body.split("TRUNCATE TABLE", 1)
    assert len(truncate_block) == 2, "reset no longer truncates evidence tables"
    statement = truncate_block[1].split(";", 1)[0]
    assert "principal_customers" not in statement


# Tables the reset script's migrations create that are deliberately NOT
# truncated, each with the reason it is configuration rather than turn
# evidence. Anything not listed here and not truncated fails the test below.
_RESET_EXEMPT_TABLES = {
    # Authorization mapping. Truncating it denies every signed-in shopper
    # their own orders; reset verifies it instead (see the test above).
    "principal_customers",
    # Deterministic warehouse rows, reseeded by 006 rather than emptied.
    "warehouse_inventory",
    # Warehouse dimension (code, city, ship window). Reference data 006
    # re-inserts; `warehouse_inventory` has an FK onto it.
    "warehouses",
    # Idempotency-key registry recreated by 011 with its own constraints.
    "write_keys",
    # Source-controlled persona metadata and deterministic guided requests.
    # These are reseeded/presentation reference rows, not a participant turn.
    "persona_profiles",
    "workshop_scenarios",
}


def test_reset_truncates_every_evidence_table_its_migrations_create() -> None:
    """A surviving evidence row makes the next participant's first proof lie.

    Several proofs read "this table was empty, you acted, now there is one
    row". `pellier.governed_query_receipts` was created by migration 017 and
    re-applied by reset for a full workshop cycle without being truncated,
    so a second run started with the previous participant's receipts and the
    count-based proof read as already-done.

    Rather than pin today's list, this derives it: every table created by a
    migration reset applies must be truncated or exempted with a reason.
    """
    body = RESET_GOVERNED.read_text()
    migrations_dir = REPO / "scripts" / "migrations"

    applied = [
        name
        for name in sorted(p.name for p in migrations_dir.glob("*.sql"))
        if name in body
    ]
    assert applied, "reset applies no migrations — the list moved"

    created: dict[str, str] = {}
    for name in applied:
        sql = (migrations_dir / name).read_text()
        for match in re.finditer(
            r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?pellier\.([a-z_]+)", sql
        ):
            created.setdefault(match.group(1), name)

    truncated = body.split("TRUNCATE TABLE", 1)[1].split(";", 1)[0]
    missing = {
        table: migration
        for table, migration in created.items()
        if table not in truncated and table not in _RESET_EXEMPT_TABLES
    }

    assert not missing, (
        "reset creates these tables but neither truncates nor exempts them, "
        "so rows survive into the next run: "
        + ", ".join(f"pellier.{t} (from {m})" for t, m in sorted(missing.items()))
    )


def test_runtime_roles_never_request_bypassrls() -> None:
    """A runtime role with BYPASSRLS would void every policy silently.

    Scoped to role-defining statements: the migration legitimately mentions
    BYPASSRLS in comments, in a `pg_roles` verification query, and in the
    exception message that query raises.
    """
    sql = RLS_MIGRATION.read_text()

    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lowered = stripped.lower()
        if not ("create role" in lowered or "alter role" in lowered):
            continue
        if "bypassrls" not in lowered:
            continue
        assert "nobypassrls" in lowered, (
            f"role statement grants BYPASSRLS, voiding every policy: {stripped}"
        )

    # And the migration must actively verify it rather than only asserting it,
    # because ALTER ROLE ... NOBYPASSRLS needs a true superuser on Aurora.
    assert "rolbypassrls" in sql.lower(), (
        "the migration should verify pg_roles.rolbypassrls, since it cannot "
        "set the attribute on Aurora"
    )


# ---------------------------------------------------------------------------
# Participant workspace: Code Editor conventions
#
# Derived from delivery experience across sibling workshops, not from this
# repo's own behaviour, so the assertions cannot cement a local bug.
# ---------------------------------------------------------------------------

BOOTSTRAP_ENV = REPO / "scripts" / "bootstrap-environment.sh"


def _settings_blocks() -> list[dict]:
    """Return every Code Editor settings heredoc as parsed JSON."""
    source = BOOTSTRAP_ENV.read_text(encoding="utf-8")
    blocks = []
    for tag in ("VSCODE_SETTINGS", "WORKSPACE_SETTINGS"):
        match = re.search(rf"<< '{tag}'\n(.*?)\n{tag}\n", source, re.S)
        assert match, f"{tag} heredoc not found"
        blocks.append(json.loads(match.group(1)))
    return blocks


def test_both_settings_files_are_valid_json() -> None:
    """A malformed settings file is ignored silently; the editor just looks wrong."""
    assert len(_settings_blocks()) == 2


def test_the_editor_opens_without_a_dialog() -> None:
    """Any first-run prompt costs every participant the same minute."""
    user_settings, _workspace = _settings_blocks()
    assert user_settings["workbench.startupEditor"] == "none"
    assert user_settings["workbench.tips.enabled"] is False
    assert user_settings["update.showReleaseNotes"] is False
    # VS Code's setting id carries the `workbench.` prefix. Asserting the
    # abbreviated form some notes use would fail against correct settings.
    assert (
        user_settings["workbench.welcomePage.walkthroughs.openOnInstall"] is False
    )
    trust = [k for k in user_settings if k.startswith("security.workspace.trust")]
    assert len(trust) >= 4, f"workspace-trust prompts not fully disabled: {trust}"


def test_the_ui_scales_for_a_projector() -> None:
    """Editor font alone leaves the sidebar, tabs, and palette unreadable.

    `window.zoomLevel` is the setting that scales the whole interface, which is
    what a participant reading from the back of a room actually needs.
    """
    for settings in _settings_blocks():
        assert settings.get("window.zoomLevel", 0) >= 1
        assert settings["terminal.integrated.fontSize"] >= 18
        assert settings["workbench.colorTheme"] == "Default Dark Modern"


def test_the_automatic_terminal_task_can_actually_fire() -> None:
    """A folderOpen task only runs from the .vscode of the folder that opened.

    It also needs automatic tasks allowed, or the editor prompts instead of
    running it - which is the same as not having the task.
    """
    _user, workspace = _settings_blocks()
    assert workspace["task.allowAutomaticTasks"] == "on"
    source = BOOTSTRAP_ENV.read_text(encoding="utf-8")
    assert "folderOpen" in source
    # The task must be written into the repo folder's .vscode, not the parent.
    assert "REPO_VSCODE" in source


def test_source_control_is_hidden_from_the_editor() -> None:
    """An injected lab seam otherwise reads as a mistake worth reverting."""
    user_settings, _workspace = _settings_blocks()
    assert user_settings["git.enabled"] is False
    assert user_settings["git.decorations.enabled"] is False
    assert user_settings["scm.diffDecorations"] == "none"


def test_explorer_hides_repo_meta_but_keeps_the_lab_folders() -> None:
    """Lab 4 opens policies/, the documented fallback lane opens solutions/,
    and the runtime skills live in skills/ - hiding any of them strands a
    participant step. Repo meta stays on disk for Claude Code and the
    terminal but out of the Explorer and editor search."""
    user_settings, _workspace = _settings_blocks()
    excludes = user_settings["files.exclude"]
    for hidden in (".claude", ".gitignore", "LICENSE", "NOTICE", "VOICE.md", "data"):
        assert excludes.get(hidden) is True, f"{hidden} should be hidden from the Explorer"
    for visible in ("policies", "skills", "solutions", "pellier", "pellier/frontend"):
        assert visible not in excludes, f"{visible} must stay visible in the Explorer"


def test_the_workspace_is_detached_from_git_on_every_path() -> None:
    """Hiding the panel does not stop `git checkout -- .` in a terminal.

    The fallback clone always deleted .git. The CloudFormation path did not, so
    an event box shipped a live detached checkout and a participant could revert
    the exercise mid-lab, or stash it, with nothing on screen to explain where
    their work went. Both paths must converge.
    """
    source = (REPO / "scripts" / "bootstrap-labs.sh").read_text(encoding="utf-8")
    removals = re.findall(r'rm -rf "\$REPO_PATH/\.git"', source)
    assert removals, "bootstrap no longer removes .git"

    # The removal must not be reachable only from inside the clone branch.
    guard = 'if [ -d "$REPO_PATH/.git" ]; then'
    assert guard in source, "unconditional .git removal guard is missing"
    assert source.index(guard) > source.index('log "✅ Repository exists"'), (
        ".git removal must sit after the clone branch, so it covers the event path"
    )


def test_provenance_survives_removing_git() -> None:
    """After .git is gone, a file must still answer which content this box runs."""
    source = (REPO / "scripts" / "bootstrap-labs.sh").read_text(encoding="utf-8")
    assert source.count(".workshop-ref.json") >= 2, (
        "provenance is written on only one of the two paths"
    )
    assert "cloudformation-userdata" in source
    assert "bootstrap-fallback" in source


def test_participant_psql_is_proven_during_bootstrap() -> None:
    """Every SQL step in the guide is typed as a bare `psql`.

    If that path is broken, Lab 1 is where a participant finds out. The check
    must run as the participant with no PGPASSWORD, so a pass means `.pgpass`
    was found and readable; running it as root with the script's own password
    would prove something no participant does.
    """
    source = (REPO / "scripts" / "bootstrap-labs.sh").read_text(encoding="utf-8")
    probe = re.search(
        r"sudo -u \"\$CODE_EDITOR_USER\" env -i(.*?)psql -X -Atc 'SELECT 1'",
        source,
        re.S,
    )
    assert probe, "no participant psql probe in bootstrap"
    env_block = probe.group(1)
    assert "PGPASSWORD" not in env_block, (
        "the probe passes PGPASSWORD, so it cannot prove .pgpass works"
    )
    assert "PGSSLMODE=require" in env_block
    assert 'HOME="$PGPASS_DIR"' in env_block, "probe must resolve the user's .pgpass"


def test_a_bare_psql_negotiates_tls() -> None:
    """Aurora accepts TLS but does not require it unless rds.force_ssl is on."""
    source = (REPO / "scripts" / "bootstrap-labs.sh").read_text(encoding="utf-8")
    assert "export PGSSLMODE=require" in source


def test_the_pgpass_file_is_not_world_readable() -> None:
    source = (REPO / "scripts" / "bootstrap-labs.sh").read_text(encoding="utf-8")
    assert 'chmod 600 "$PGPASS_DIR/.pgpass"' in source
    # And the shell profile belongs in the user's own .bashrc, never in
    # /etc/profile.d, which every account on the box can read.
    assert "/etc/profile.d" not in source


def test_the_health_gate_refuses_a_shopper_in_the_operator_group(tmp_path) -> None:
    """The specific regression the operator-group check exists to catch.

    `require_operator` used to accept any valid token, so `marco` could confirm, decline
    and execute any review. Adding a shopper to `pellier-operators` restores exactly that
    behaviour through a legitimate-looking configuration change, and no other check would
    notice: the group exists, the operator is in it, the API and Cedar both enforce
    membership, and the shopper simply has it.
    """
    proc = _run_health_gate(
        tmp_path,
        model_ready=True,
        workshop_format="governed",
        managed_ready=True,
        shopper_in_operator_group=True,
    )
    assert proc.returncode == 1, proc.stdout
    assert "shopper(s) in pellier-operators" in proc.stdout
    assert "marco" in proc.stdout


def test_the_health_gate_passes_when_only_the_operator_is_in_the_group(tmp_path) -> None:
    proc = _run_health_gate(
        tmp_path, model_ready=True, workshop_format="governed", managed_ready=True
    )
    assert proc.returncode == 0, proc.stdout
    assert "Operator group pellier-operators authorizes operator" in proc.stdout
    assert "No shopper is in pellier-operators" in proc.stdout
    assert "Hosted UI client is configured for OAuth authorization-code sign-in" in proc.stdout
    assert "Seeded Operator can complete Cognito sign-in" in proc.stdout


def test_the_health_gate_refuses_an_operator_that_cannot_sign_in(tmp_path) -> None:
    proc = _run_health_gate(
        tmp_path,
        model_ready=True,
        workshop_format="governed",
        managed_ready=True,
        operator_token_ready=False,
    )
    assert proc.returncode == 1, proc.stdout
    assert "Seeded Operator cannot obtain a Cognito access token" in proc.stdout


# ---------------------------------------------------------------------------
# Quarantine marker and provisioning state machine
#
# A reset that could not clean AgentCore Memory or restore Cedar enforcement has
# left the box with someone else's residue or with denials that silently do not
# happen. Both used to exit 1 into a log nobody reads while the next `health`
# read green. The marker makes that state durable until a full reset clears it.
#
# The provisioning state file answers "how far did bootstrap actually get" for
# CloudFormation and for every later gate run: PROVISIONING -> APP_READY ->
# MANAGED_READY -> E2E_PROVED, or FAILED.
# ---------------------------------------------------------------------------

QUARANTINE_DEFAULT = '"${PELLIER_QUARANTINE_FILE:-/var/lib/pellier/quarantine}"'
PROVISION_STATE_DEFAULT = '"${PELLIER_PROVISION_STATE_FILE:-/var/lib/pellier/provision-state}"'


def _run_reset(
    tmp_path: Path,
    *,
    memory_exit: int = 0,
    policy_exit: int = 0,
    quarantine_seed: str | None = None,
    backend_listening: bool = False,
    recovery_installed: str = "f",
    recovery_records: str = "0",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the real reset against a sandbox repo with every external binary faked.

    The reset's own contract tests read its text. This one runs it, because the
    quarantine marker is a FILE the health gate reads, and "the script contains the
    string `_quarantine memory`" does not prove a marker is ever written, nor that a
    leg the box legitimately lacks avoids writing one.

    Args:
        tmp_path: The pytest sandbox.
        memory_exit: Exit status the faked interpreter returns for the Memory leg.
        policy_exit: Exit status the faked interpreter returns for the Policy leg.
        quarantine_seed: Marker content to place before the run, to prove a clean
            run clears it.
        backend_listening: Whether the faked curl answers /api/health. True also
            sets PELLIER_RESET_ALLOW_LIVE, since a listening backend with no systemd
            unit is exactly what the reset refuses to race.

    Returns:
        The completed process and the path the quarantine marker would occupy.
    """
    repo = tmp_path / "repo"
    fake_bin = tmp_path / "bin"
    (repo / "scripts" / "migrations").mkdir(parents=True)
    (repo / "pellier" / "backend" / ".venv" / "bin").mkdir(parents=True)
    (repo / ".agentcore-project" / "pellier" / "agentcore").mkdir(parents=True)
    fake_bin.mkdir()

    quarantine_file = tmp_path / "quarantine"
    if quarantine_seed is not None:
        quarantine_file.write_text(quarantine_seed, encoding="utf-8")
    (repo / ".env").write_text(
        "DB_NAME=pellier\nDB_USER=pellier\nDB_HOST=localhost\nDB_PORT=5432\n",
        encoding="utf-8",
    )
    (repo / ".agentcore-project" / "pellier" / "agentcore" / "agentcore.json").write_text(
        "{}\n", encoding="utf-8"
    )
    for migration in (REPO / "scripts" / "migrations").glob("*.sql"):
        (repo / "scripts" / "migrations" / migration.name).touch()
    _write_executable(repo / "scripts" / "health-gate.sh", "#!/bin/bash\nexit 0\n")
    _write_executable(
        repo / "pellier" / "backend" / ".venv" / "bin" / "python",
        f"""#!/bin/bash
case "$1" in
  *reset_memory_runtime.py) exit {memory_exit} ;;
  *policy_mode.py) exit {policy_exit} ;;
esac
exit 0
""",
    )
    # Baseline verification reads real counts: every runtime table empty, and exactly
    # one row each for the migration 010 forensic incident.
    _write_executable(
        fake_bin / "psql",
        f"""#!/bin/bash
case "$*" in
  *"to_regclass('pellier.replacements')"*) printf '%s\\n' '{recovery_installed}' ;;
  *"FROM pellier.replacements;"*) printf '%s\\n' '{recovery_records}' ;;
  *CUST-JESSICA*) printf '0\\n' ;;
  *"FROM pellier.returns;"*) printf '1\\n' ;;
  *"FROM pellier.tool_audit;"*) printf '1\\n' ;;
  *"FROM pellier.governed_receipts;"*) printf '1\\n' ;;
  *"count(*)"*) printf '0\\n' ;;
esac
exit 0
""",
    )
    _write_executable(
        fake_bin / "curl",
        "#!/bin/bash\n"
        + ("printf '{\"status\":\"healthy\"}'\n" if backend_listening else "exit 1\n"),
    )
    # No systemd on this host, which is the developer-clone branch of the contract.
    _write_executable(fake_bin / "systemctl", "#!/bin/bash\nexit 1\n")
    _write_executable(
        fake_bin / "jq",
        """#!/bin/bash
case "$*" in
  *policyEngines*) exit 1 ;;
  *agentCoreGateways*) printf 'ENFORCE\\n' ;;
esac
exit 0
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["PELLIER_REPO"] = str(repo)
    env["PELLIER_QUARANTINE_FILE"] = str(quarantine_file)
    for inherited in ("PELLIER_RESET_SKIP_MEMORY", "PELLIER_RESET_SKIP_AGENTCORE"):
        env.pop(inherited, None)
    if backend_listening:
        env["PELLIER_RESET_ALLOW_LIVE"] = "1"
    else:
        env.pop("PELLIER_RESET_ALLOW_LIVE", None)
    proc = subprocess.run(
        ["bash", str(RESET_GOVERNED)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc, quarantine_file


@pytest.mark.parametrize(("installed", "records"), [("t", "1"), ("t", ""), ("", "0")])
def test_reset_refuses_owned_or_unknown_recovery_records_before_reseeding(
    tmp_path: Path, installed: str, records: str,
) -> None:
    proc, _ = _run_reset(tmp_path, recovery_installed=installed, recovery_records=records)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "replacement recovery" in proc.stdout.lower() or "replacement recovery records" in proc.stdout.lower()
    assert "Catalog quantities restored" not in proc.stdout
    assert "Cleared:" not in proc.stdout


@pytest.mark.parametrize(
    ("leg", "reason"),
    [
        ("memory", "Could not clean AgentCore Memory runtime"),
        ("policy", "Could not restore live Cedar enforcement mode"),
    ],
)
def test_a_failed_restore_leg_actually_writes_the_marker_the_gate_reads(
    tmp_path: Path, leg: str, reason: str
) -> None:
    """The gate's READ is behavioral; without this the WRITE was only asserted as text."""
    proc, quarantine_file = _run_reset(
        tmp_path,
        memory_exit=1 if leg == "memory" else 0,
        policy_exit=1 if leg == "policy" else 0,
        backend_listening=leg == "policy",
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert quarantine_file.exists(), proc.stdout + proc.stderr
    marker = json.loads(quarantine_file.read_text(encoding="utf-8"))
    assert marker["step"] == leg
    assert marker["reason"] == reason
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", marker["at"]), marker


def test_a_box_with_no_policy_engine_is_reported_not_quarantined(tmp_path: Path) -> None:
    """Exit 2 from policy_mode.py means "no engine provisioned", not "restore failed".

    Quarantining on it strands the box permanently: only a full successful reset
    clears the marker, and on a box with no engine that reset can never happen, so
    `health` fails forever. The seeded marker proves the recovery direction too.
    """
    proc, quarantine_file = _run_reset(
        tmp_path,
        policy_exit=2,
        quarantine_seed='{"reason": "stale", "step": "policy", "at": "2026-09-01T00:00:00Z"}',
        backend_listening=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not quarantine_file.exists(), proc.stdout
    assert "NOT_EVALUATED" in proc.stdout
    assert "Could not restore live Cedar enforcement mode" not in proc.stdout


def test_a_box_with_no_memory_resource_is_reported_not_quarantined(tmp_path: Path) -> None:
    """The Memory leg carries the same distinction on its own reserved exit code."""
    proc, quarantine_file = _run_reset(
        tmp_path, memory_exit=3, backend_listening=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not quarantine_file.exists(), proc.stdout
    assert "Could not clean AgentCore Memory runtime" not in proc.stdout


def test_the_reset_writes_a_quarantine_marker_when_memory_or_policy_cannot_be_restored() -> None:
    reset = RESET_GOVERNED.read_text(encoding="utf-8")
    assert f"QUARANTINE_FILE={QUARANTINE_DEFAULT}" in reset
    assert "_quarantine() {" in reset
    assert "sudo -n tee" in reset
    for key in ('"reason"', '"step"', '"at"'):
        assert key in reset, f"quarantine JSON lacks {key}"
    memory = reset[reset.index("reset_memory_runtime.py"):reset.index("# STEP 7")]
    policy_end = reset.rindex("_restart_services_and_wait || exit 1")
    policy = reset[reset.index("policy_mode.py"):policy_end]
    assert "_quarantine memory" in memory
    assert "_quarantine policy" in policy
    # A full success clears it, and only after both legs have actually run.
    assert "_clear_quarantine() {" in reset
    assert "_clear_quarantine\n" in reset
    assert reset.rindex("_clear_quarantine\n") > reset.index("_quarantine policy")


def test_the_health_gate_refuses_a_quarantined_box(tmp_path: Path) -> None:
    marker = json.dumps(
        {
            "reason": "Could not clean AgentCore Memory runtime",
            "step": "memory",
            "at": "2026-09-04T10:00:00Z",
        }
    )
    proc = _run_health_gate(
        tmp_path,
        model_ready=True,
        workshop_format="governed",
        managed_ready=True,
        quarantine=marker,
    )
    assert proc.returncode == 1, proc.stdout
    assert "Box is quarantined:" in proc.stdout
    assert '"step": "memory"' in proc.stdout
    assert "NOT READY" in proc.stdout
    assert f"QUARANTINE_FILE={QUARANTINE_DEFAULT}" in HEALTH_GATE.read_text(encoding="utf-8")


def test_bootstrap_creates_the_lifecycle_state_directory_for_the_participant() -> None:
    """The participant runs reset and must be able to write and clear the marker.

    No sudoers line for `tee`/`rm` on one path: the directory is group-writable by
    the participant's group instead, which is narrower than a passwordless rm.
    """
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'mkdir -p "$PELLIER_STATE_DIR"' in bootstrap
    assert 'PELLIER_STATE_DIR="/var/lib/pellier"' in bootstrap
    assert 'chown "root:$CODE_EDITOR_USER" "$PELLIER_STATE_DIR"' in bootstrap
    assert 'chmod 0775 "$PELLIER_STATE_DIR"' in bootstrap
    assert "/var/lib/pellier/quarantine" not in bootstrap.split("PELLIER_STATE_DIR=")[0]
    # Assert the GRANT, not the shell around it. The old slice ended at `visudo`,
    # so its `" rm " not in ...` could never see the `rm -f "$SUDOERS_FILE"` that
    # sits after it, and the assertion could not fail for the thing it named.
    granted = next(
        line for line in bootstrap.splitlines() if "NOPASSWD:" in line
    ).partition("NOPASSWD:")[2]
    assert "quarantine" not in granted
    assert "tee" not in granted
    assert re.search(r"\brm\b", granted) is None, granted
    assert "${SYSTEMCTL_BIN}" in granted, granted


def test_bootstrap_advances_the_provision_state_in_lifecycle_order() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    assert f"PROVISION_STATE_FILE={PROVISION_STATE_DEFAULT}" in bootstrap
    assert "set_provision_state() {" in bootstrap
    assert 'chmod 0644 "$PROVISION_STATE_FILE"' in bootstrap
    positions = [
        bootstrap.index(f"set_provision_state {state}")
        for state in ("PROVISIONING", "APP_READY", "MANAGED_READY", "E2E_PROVED")
    ]
    assert positions == sorted(positions), "provision states are not written in order"
    # FAILED comes from the one function every fatal path already calls.
    fail_fn = bootstrap[bootstrap.index("fail() {"):]
    fail_fn = fail_fn[: fail_fn.index("\n")]
    assert "set_provision_state FAILED" in fail_fn
    # APP_READY means the service answered, not that systemd spawned it.
    app_ready = bootstrap.index("set_provision_state APP_READY")
    assert "api/health" in bootstrap[app_ready - 1500:app_ready]
    # MANAGED_READY sits with the managed proof, E2E_PROVED with the health gate.
    managed_ready = bootstrap.index("set_provision_state MANAGED_READY")
    assert bootstrap.index("AGENTCORE_OK=true") < managed_ready
    e2e_proved = bootstrap.index("set_provision_state E2E_PROVED")
    assert bootstrap.index("HEALTH_GATE_OK=true") < e2e_proved
    e2e = bootstrap[bootstrap.index("set_provision_state E2E_PROVED") - 400:]
    assert '"${WORKSHOP_FORMAT}" = "governed"' in e2e[:400]


def test_the_gate_verdict_starts_false_so_an_absent_gate_cannot_prove_anything() -> None:
    """E2E_PROVED and a CloudFormation SUCCESS both hang off this one flag.

    Initialised to true, a health-gate.sh that is missing or not executable skipped
    the `if` entirely and the flag stayed true: governed bootstrap reported a proved
    environment with no gate evidence at all. Only a gate that ran and passed may
    set it.
    """
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    assignments = re.findall(r"^\s*HEALTH_GATE_OK=(\w+)", bootstrap, re.M)
    assert assignments, "the health gate verdict flag is gone"
    assert assignments[0] == "false", f"the flag is initialised {assignments[0]}"
    # Exactly one place may raise it, and it sits inside the gate invocation.
    assert assignments.count("true") == 1
    gate_call = bootstrap.index("bash '$REPO_PATH/scripts/health-gate.sh'")
    assert gate_call < bootstrap.index("HEALTH_GATE_OK=true")
    # A missing or non-executable gate must say so rather than pass in silence.
    guard = bootstrap.index('if [ -x "$REPO_PATH/scripts/health-gate.sh" ]')
    assert "health gate" in bootstrap[guard:gate_call + 2000].lower()
    assert 'warn "No health gate' in bootstrap


def test_bootstrap_marks_its_own_gate_runs_as_the_proving_phase() -> None:
    """The gate demands E2E_PROVED, which bootstrap cannot have written yet.

    Bootstrap runs the gate twice before that state exists: once inside the
    governed reset, once at STEP 19. Both are marked as the proving run.
    """
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    reset_call = bootstrap.index("bash '$REPO_PATH/scripts/reset-governed-workshop.sh'")
    gate_call = bootstrap.index("bash '$REPO_PATH/scripts/health-gate.sh'")
    for position in (reset_call, gate_call):
        assert "export PELLIER_PROVISION_PHASE=bootstrap" in bootstrap[position - 400:position]


def test_stage_one_signals_success_only_from_the_proved_state() -> None:
    source = ENVIRONMENT_BOOTSTRAP.read_text(encoding="utf-8")
    assert f"PROVISION_STATE_FILE={PROVISION_STATE_DEFAULT}" in source
    read_state = source.index('cat "$PROVISION_STATE_FILE"')
    success = source.index('signal_cloudformation \\\n    "SUCCESS"')
    assert read_state < success
    decision = source[read_state:success]
    assert "E2E_PROVED" in decision
    assert "APP_READY" in decision and "MANAGED_READY" in decision
    assert 'signal_cloudformation "FAILURE"' in decision
    assert "${provision_state:-absent}" in decision


@pytest.mark.parametrize(
    ("state", "phase", "ready"),
    [
        ("E2E_PROVED", None, True),
        ("FAILED", None, False),
        ("MANAGED_READY", None, False),
        ("MANAGED_READY", "bootstrap", True),
        ("FAILED", "bootstrap", False),
    ],
)
def test_the_health_gate_requires_the_proved_state_outside_bootstrap(
    tmp_path: Path, state: str, phase: str | None, ready: bool
) -> None:
    proc = _run_health_gate(
        tmp_path,
        model_ready=True,
        workshop_format="governed",
        managed_ready=True,
        provision_state=state,
        provision_phase=phase,
    )
    assert f"Provision state: {state}" in proc.stdout
    if ready:
        assert proc.returncode == 0, proc.stdout
    else:
        assert proc.returncode == 1, proc.stdout
        assert "NOT READY" in proc.stdout


def test_the_health_gate_reports_an_absent_state_file_as_informational(tmp_path: Path) -> None:
    proc = _run_health_gate(
        tmp_path, model_ready=True, workshop_format="governed", managed_ready=True
    )
    assert proc.returncode == 0, proc.stdout
    assert "Provision state: absent" in proc.stdout


def test_governed_bootstrap_makes_the_participant_credentials_file_required() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")

    assert 'CREDENTIALS_FILE="$HOME_FOLDER/test-credentials.txt"' in bootstrap
    assert 'OUT_FILE="$CREDENTIALS_FILE"' in bootstrap
    assert '>> "$CREDENTIALS_FILE"' in bootstrap
    assert "pellier-oauth-callback.service" not in bootstrap
    assert "OAuth callback registration is a CloudFormation readiness dependency" in bootstrap


def test_credential_file_routes_participants_through_pellier_not_a_raw_hosted_ui_login() -> None:
    credentials_writer = WRITE_TEST_CREDENTIALS.read_text(encoding="utf-8")

    assert "open PellierURL from the Workshop Studio outputs" in credentials_writer
    assert "do not open a raw Hosted UI /login link" in credentials_writer
    assert 'echo "Sign-in URL: $HOSTED_UI"' not in credentials_writer
