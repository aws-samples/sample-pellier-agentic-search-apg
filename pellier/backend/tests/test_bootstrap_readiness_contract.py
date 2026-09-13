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
ENVIRONMENT_BOOTSTRAP = REPO / "scripts" / "bootstrap-environment.sh"
MODEL_CHECK = REPO / "scripts" / "check_model_access.py"
HEALTH_GATE = REPO / "scripts" / "health-gate.sh"
BUILDERS_BOOTSTRAP = REPO / "scripts" / "bootstrap-labs.sh"
BUILDERS_DRY_RUN = REPO / "scripts" / "dry-run-builders.sh"
BUILDERS_CLIENT = REPO / "scripts" / "builders_lab.py"
PROVISIONER = REPO / "scripts" / "provision_agentcore_end_to_end.py"
SEED_PREFERENCES = REPO / "scripts" / "seed-sample-preferences.sh"


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
    assert "CLAUDE_CODE_MODEL" not in values
    assert values["AGENT_MODEL_ID"] == "global.anthropic.claude-sonnet-4-6"
    assert values["BEDROCK_MODEL_ACCESS_READY"] == "true"


def test_claude_code_pins_global_sonnet_46_profile() -> None:
    """Workshop Studio does not expose Sonnet 5, so the CLI must pin the
    global Sonnet 4.6 profile instead of the floating ``sonnet`` alias
    (which a current CLI resolves to a denied model on the event account)."""
    source = BUILDERS_BOOTSTRAP.read_text(encoding="utf-8")
    dry_run = BUILDERS_DRY_RUN.read_text(encoding="utf-8")
    pin = "ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-global.anthropic.claude-sonnet-4-6}"
    assert "export CLAUDE_CODE_USE_BEDROCK=1" in source
    assert f"export {pin}" in source
    assert "ANTHROPIC_MODEL=global.anthropic.claude-sonnet-4-6" in dry_run
    assert "ANTHROPIC_MODEL=sonnet" not in dry_run
    assert "CLAUDE_CODE_MODEL" not in source


def test_explorer_shows_only_the_participant_path() -> None:
    """The Code Editor tree must greet participants with pellier/backend,
    README.md, and CLAUDE.md. Everything else stays on disk for the terminal
    commands the lab guide runs, but is hidden from the Explorer and editor
    search so solutions/ (the answers) and the 500-plus-file frontend never
    compete with the two exercise files."""
    source = ENVIRONMENT_BOOTSTRAP.read_text(encoding="utf-8")
    match = re.search(r"<< 'VSCODE_SETTINGS'\n(.*?)\nVSCODE_SETTINGS\n", source, re.S)
    assert match, "VSCODE_SETTINGS heredoc not found"
    excludes = json.loads(match.group(1))["files.exclude"]
    hidden_folders = ("solutions", "skills", "plans", "policies", "data", "pellier/frontend")
    for hidden in hidden_folders:
        assert excludes.get(hidden) is True, f"{hidden} should be hidden from the Explorer"
    for visible in ("pellier", "pellier/backend", "README.md", "CLAUDE.md"):
        assert visible not in excludes, f"{visible} must stay visible in the Explorer"


def test_playwright_mcp_is_pinned_and_optional() -> None:
    source = BUILDERS_BOOTSTRAP.read_text(encoding="utf-8")

    assert 'PLAYWRIGHT_MCP_VERSION="${PLAYWRIGHT_MCP_VERSION:-0.0.79}"' in source
    assert (
        'PLAYWRIGHT_BROWSER_VERSION="${PLAYWRIGHT_BROWSER_VERSION:'
        '-1.63.0-alpha-2026-08-05}"'
    ) in source
    assert "claude mcp add --scope user playwright" in source
    assert "--headless --isolated --output-dir /tmp/pellier-playwright" in source
    assert "Playwright MCP setup failed; core workshop remains ready" in source


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _run_health_gate(
    tmp_path: Path,
    model_ready: bool,
    *,
    claude_ready: bool = True,
    uv_ready: bool = True,
    memory_ready: bool = True,
    schema_ready: bool = True,
) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / "repo"
    fake_bin = tmp_path / "bin"
    repo.mkdir()
    fake_bin.mkdir()
    (repo / ".env").write_text(
        f"BEDROCK_MODEL_ACCESS_READY={'true' if model_ready else 'false'}\n",
        encoding="utf-8",
    )
    _write_executable(
        fake_bin / "curl",
        """#!/bin/bash
case "$*" in
  *api/health*) printf '{"status":"healthy"}' ;;
  *api/agentcore/memory/status*)
    printf '%s' '${MEMORY_RESPONSE}' ;;
  *) printf '<!doctype html><div id="root"></div>' ;;
esac
""".replace(
            "${MEMORY_RESPONSE}",
            (
                '{"live":true,"source":"agentcore-sdk",'
                '"memory_id":"memory-1","resource_status":"ACTIVE"}'
                if memory_ready
                else '{"live":false,"source":"in-process-dict"}'
            ),
        ),
    )
    _write_executable(
        fake_bin / "psql",
        """#!/bin/bash
case "$*" in
  *to_regclass*) printf '${SCHEMA_READY}\n' ;;
  *product_catalog*) printf '40\n' ;;
  *warehouse_inventory*) printf '120\n' ;;
esac
""".replace("${SCHEMA_READY}", "t" if schema_ready else "f"),
    )
    if claude_ready:
        _write_executable(
            fake_bin / "claude",
            "#!/bin/bash\nprintf '2.1.233 (Claude Code)\\n'\n",
        )
    else:
        _write_executable(fake_bin / "claude", "#!/bin/bash\nexit 127\n")
    if uv_ready:
        _write_executable(fake_bin / "uv", "#!/bin/bash\nprintf 'uv 0.8.11\\n'\n")
    else:
        _write_executable(fake_bin / "uv", "#!/bin/bash\nexit 127\n")
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
    return subprocess.run(
        ["bash", str(HEALTH_GATE)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_core_health_gate_includes_required_agentcore_memory(
    tmp_path: Path,
) -> None:
    proc = _run_health_gate(tmp_path, model_ready=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "READY" in proc.stdout
    assert "AgentCore Memory is configured and ACTIVE" in proc.stdout


def test_core_health_gate_requires_model_preflight(tmp_path: Path) -> None:
    proc = _run_health_gate(tmp_path, model_ready=False)
    assert proc.returncode == 1
    assert "model-access preflight did not pass" in proc.stdout


def test_core_health_gate_requires_claude_code(tmp_path: Path) -> None:
    proc = _run_health_gate(tmp_path, model_ready=True, claude_ready=False)
    assert proc.returncode == 1
    assert "Claude Code CLI is missing or unusable" in proc.stdout


def test_core_health_gate_requires_uv(tmp_path: Path) -> None:
    proc = _run_health_gate(tmp_path, model_ready=True, uv_ready=False)
    assert proc.returncode == 1
    assert "uv is missing or unusable" in proc.stdout


def test_core_health_gate_requires_active_agentcore_memory(tmp_path: Path) -> None:
    proc = _run_health_gate(
        tmp_path,
        model_ready=True,
        memory_ready=False,
    )
    assert proc.returncode == 1
    assert "AgentCore Memory is not ACTIVE" in proc.stdout


def test_core_health_gate_rejects_partial_schema_with_healthy_app(tmp_path: Path) -> None:
    proc = _run_health_gate(tmp_path, model_ready=True, schema_ready=False)
    assert proc.returncode == 1
    assert "Required schema migrations are incomplete" in proc.stdout
    assert "NOT READY" in proc.stdout


@pytest.mark.parametrize("frontend_rc,database_rc", [(0, 1), (1, 0), (1, 1)])
def test_failed_parallel_setup_stops_before_memory(
    frontend_rc: int, database_rc: int
) -> None:
    source = BUILDERS_BOOTSTRAP.read_text()
    block = source.split("setup_frontend & PID_FE=$!", 1)[1].split(
        "# STEP 10b:", 1
    )[0]
    process = subprocess.run(
        [
            "bash", "-c",
            "set -euo pipefail\n"
            "log() { :; }\n"
            "fail() { echo \"$1\"; exit 1; }\n"
            f"setup_database() {{ return {database_rc}; }}\n"
            f"(exit {frontend_rc}) & PID_FE=$!\n"
            + block + "\necho REACHED_MEMORY\n",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 1
    assert "REACHED_MEMORY" not in process.stdout
    expected = "Database setup failed" if database_rc else "Frontend dependency"
    assert expected in process.stdout


def test_editor_probe_sends_token_without_following_redirects(tmp_path: Path) -> None:
    source = ENVIRONMENT_BOOTSTRAP.read_text()
    function = re.search(r"^probe_editor_http\(\) \{.*?^\}", source, re.M | re.S)
    assert function is not None
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "curl",
        """#!/bin/bash
token=false
origin=false
while (( $# )); do
  case "$1" in
    --data-urlencode)
      shift
      [[ "$1" == 'tkn=synthetic token&value' ]] || exit 1
      token=true ;;
    -H)
      shift
      [[ "$1" == 'X-Pellier-Origin-Verify: synthetic-origin' ]] && origin=true ;;
    -L|--location) exit 1 ;;
  esac
  shift
done
$token && $origin && printf '302'
""",
    )
    process = subprocess.run(
        ["bash", "-c", function[0] + "\n"
         "probe_editor_http http://127.0.0.1:80/ "
         "-H 'X-Pellier-Origin-Verify: synthetic-origin'"],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "CODE_EDITOR_PASSWORD": "synthetic token&value",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.stdout == "302"
    assert process.stderr == ""


def test_builders_requires_memory_but_defaults_other_managed_services_off() -> None:
    bootstrap = BUILDERS_BOOTSTRAP.read_text(encoding="utf-8")
    dry_run = BUILDERS_DRY_RUN.read_text(encoding="utf-8")

    assert "ENABLE_BUILDERS_MANAGED_PATH:-false" in bootstrap
    assert "Provisioning required AgentCore Memory" in bootstrap
    assert "provision_agentcore_memory.py" in bootstrap
    assert 'upsert_env "USE_AGENTCORE_RUNTIME" "false"' in bootstrap
    assert "skipping optional Runtime, Gateway, and Policy" in bootstrap
    for fragment in (
        "AGENTCORE_RUNTIME_ENDPOINT",
        "AGENTCORE_POLICY_ENGINE_ID",
        "/api/agentcore/",
    ):
        assert fragment not in dry_run


def test_builders_bootstrap_fails_closed_on_verified_starter_state() -> None:
    bootstrap = BUILDERS_BOOTSTRAP.read_text(encoding="utf-8")

    assert (
        'scripts/builders_starter.py" \\\n'
        '        --repo "$REPO_PATH" apply'
    ) in bootstrap
    assert (
        'scripts/builders_starter.py" \\\n'
        '        --repo "$REPO_PATH" verify --expect starter'
    ) in bootstrap
    assert (
        "verified floor_check body + Stock Keeper grant are incomplete"
        in bootstrap
    )
    assert (
        'copy_solution "solutions/closing-marcos-gap/services/'
        'agent_tools_builders_preapply.py"'
        not in bootstrap
    )


def test_builders_dry_run_rehearses_tool_then_agent_completion() -> None:
    dry_run = BUILDERS_DRY_RUN.read_text(encoding="utf-8")

    assert "CLAUDE_CODE_USE_BEDROCK=1" in dry_run
    assert "PELLIER_CLAUDE_READY" in dry_run
    assert "verify --expect starter" in dry_run
    assert "complete-tool" in dry_run
    assert "tool-check" in dry_run
    assert "--expect-tool shipped --expect-agent exercise" in dry_run
    assert "complete-agent" in dry_run
    assert "build-state --expect shipped" in dry_run
    assert "X-Pellier-Session-Token" in dry_run
    assert "WHERE tool='floor_check'" in dry_run
    assert "process_return" not in dry_run
    assert "LEDGER_TOKEN" not in dry_run


def test_builders_client_contract_is_checked_in() -> None:
    client = BUILDERS_CLIENT.read_text(encoding="utf-8")
    bootstrap = BUILDERS_BOOTSTRAP.read_text(encoding="utf-8")

    for fragment in (
        "# /// script",
        "/api/health",
        "/api/agent-trace/build-state",
        "/api/agent-trace/tools/floor-check/run",
        "/api/agent-trace/search-strategies/compare",
        "tool-check",
        "--expect-tool",
        "--expect-agent",
    ):
        assert fragment in client
    assert "uv is missing or unusable" in bootstrap
    assert 'ln -sf "$uv_bin" /usr/local/bin/uv' in bootstrap


def test_runtime_arn_is_recorded_before_smoke() -> None:
    source = PROVISIONER.read_text(encoding="utf-8")
    record = source.index('result["runtime"] = {')
    smoke = source.index("smoke = _authenticated_runtime_smoke(")
    assert record < smoke
    assert 'model_id=required["model_id"]' in source
    assert "render_project(" in source


def test_preference_seed_uses_access_token() -> None:
    source = SEED_PREFERENCES.read_text(encoding="utf-8")
    assert "AuthenticationResult.AccessToken" in source
    assert "AuthenticationResult.IdToken" not in source


def test_builders_storefront_stays_in_process_when_managed_path_provisions() -> None:
    """The optional Runtime flex must never move the storefront rail.

    A managed Runtime dispatches tools to the Gateway's Lambda target, not to
    ``services/agent_tools.py``. Flipping the storefront onto that rail would
    turn both of Lab 2's edits into silent no-ops while the lab still reported
    success, so the builders format records the endpoint and stays in-process.
    """
    bootstrap = BUILDERS_BOOTSTRAP.read_text(encoding="utf-8")

    builders_branch = (
        'if [ "${WORKSHOP_FORMAT:-builders}" = "builders" ]; then\n'
        '            upsert_env "USE_AGENTCORE_RUNTIME" "false"'
    )
    assert builders_branch in bootstrap, (
        "managed provisioning must branch on WORKSHOP_FORMAT and leave the "
        "builders storefront on the in-process rail"
    )
    assert bootstrap.index(builders_branch) < bootstrap.index(
        'upsert_env "USE_AGENTCORE_RUNTIME" "true"'
    ), "the builders branch must guard the managed flip"

    assert 'upsert_env "AGENTCORE_RUNTIME_ENDPOINT" "$RUNTIME_ARN"' in bootstrap
    assert "storefront stays in-process" in bootstrap
