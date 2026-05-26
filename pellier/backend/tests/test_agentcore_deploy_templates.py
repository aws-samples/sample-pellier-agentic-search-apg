"""Tests for the AgentCore CLI deploy templates (Batch 3 — CLI migration).

The new ``@aws/agentcore`` CLI (https://github.com/aws/agentcore-cli)
has no flag overrides for region / role ARN / JWT config / env vars —
every dynamic value must be present in ``agentcore.json`` /
``aws-targets.json`` before ``agentcore deploy`` runs. The deploy
script (``scripts/deploy/deploy_all.sh``) renders those files from
``*.template`` siblings via ``envsubst``.

A typo or rename in either side (a placeholder in the template that
``deploy_all.sh`` never exports, or vice versa) would silently leave
``${UNSET_VAR}`` in the rendered JSON — the agentcore CLI would then
either reject the file or, worse, deploy a runtime that points at the
literal string ``${MCP_GATEWAY_URL}``. These tests pin the contract:

  1. Both templates are valid JSON once ``envsubst`` is run with the
     full set of env vars that ``deploy_all.sh`` exports.
  2. After substitution there are no leftover ``${...}`` placeholders.
  3. Every placeholder named in the template is exported by the deploy
     script (so the script never falls back to an empty string).

Skipped when ``envsubst`` is not on PATH (e.g. minimal CI images that
strip gettext).

Runnable from the repo root per ``pytest.ini``:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_agentcore_deploy_templates.py -v
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "pellier" / "backend"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "deploy_all.sh"

AGENTCORE_TEMPLATE = BACKEND_DIR / "agentcore.json.template"
AWS_TARGETS_TEMPLATE = BACKEND_DIR / "aws-targets.json.template"

PLACEHOLDER_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
UNRESOLVED_RE = re.compile(r"\$\{[A-Z_][A-Z0-9_]*\}")

# Smoke values for every variable the templates reference. Intentionally
# distinguishable so the JSON-shape assertions can confirm the right value
# landed in the right slot.
SMOKE_ENV = {
    "AGENTCORE_ROLE_ARN": "arn:aws:iam::123456789012:role/test-agentcore-role",
    "OAUTH_ISSUER_URL": "https://cognito-idp.us-west-2.amazonaws.com/us-west-2_TESTPOOL",
    "COGNITO_CLIENT": "test-client-id",
    "MCP_GATEWAY_URL": "https://gateway.test.example.com/mcp",
    "AGENT_MODEL_ID": "global.anthropic.claude-opus-4-6-v1",
    "AWS_ACCOUNT": "123456789012",
    "AWS_REGION": "us-west-2",
}


def _envsubst_or_skip() -> str:
    """Locate ``envsubst`` on PATH or skip — same gate the deploy script
    relies on at runtime."""
    binary = shutil.which("envsubst")
    if not binary:
        pytest.skip("envsubst not installed (gettext); deploy templates can't be rendered")
    return binary


def _render(template_path: Path, env: dict) -> str:
    binary = _envsubst_or_skip()
    # Pass a clean env so the test never accidentally inherits a host
    # variable that happens to share a name with a placeholder.
    proc = subprocess.run(
        [binary],
        input=template_path.read_text(),
        capture_output=True,
        text=True,
        env={**env, "PATH": os.environ.get("PATH", "")},
        check=True,
    )
    return proc.stdout


def _placeholders_in(template_path: Path) -> set[str]:
    return set(PLACEHOLDER_RE.findall(template_path.read_text()))


# ---------------------------------------------------------------------------
# Both templates exist
# ---------------------------------------------------------------------------


def test_agentcore_json_template_exists() -> None:
    assert AGENTCORE_TEMPLATE.is_file(), (
        f"agentcore.json.template missing at {AGENTCORE_TEMPLATE}"
    )


def test_aws_targets_template_exists() -> None:
    assert AWS_TARGETS_TEMPLATE.is_file(), (
        f"aws-targets.json.template missing at {AWS_TARGETS_TEMPLATE}"
    )


# ---------------------------------------------------------------------------
# Render with the full env → valid JSON, no leftover placeholders
# ---------------------------------------------------------------------------


def test_agentcore_json_template_renders_clean() -> None:
    rendered = _render(AGENTCORE_TEMPLATE, SMOKE_ENV)
    leftover = UNRESOLVED_RE.findall(rendered)
    assert not leftover, (
        f"agentcore.json still has unresolved placeholders after envsubst: {leftover}\n"
        f"Either the template references a variable deploy_all.sh does not "
        f"export, or the smoke env in this test is stale."
    )
    parsed = json.loads(rendered)
    runtimes = parsed.get("runtimes", [])
    assert len(runtimes) == 1
    runtime = runtimes[0]
    assert runtime["name"] == "pellier_orchestrator"
    assert runtime["executionRoleArn"] == SMOKE_ENV["AGENTCORE_ROLE_ARN"]
    auth = runtime["authorizerConfiguration"]["customJwtAuthorizer"]
    assert SMOKE_ENV["OAUTH_ISSUER_URL"] in auth["discoveryUrl"]
    assert SMOKE_ENV["COGNITO_CLIENT"] in auth["allowedClients"]
    env_vars = {ev["name"]: ev["value"] for ev in runtime["envVars"]}
    assert env_vars["MCP_GATEWAY_URL"] == SMOKE_ENV["MCP_GATEWAY_URL"]
    assert env_vars["AGENT_MODEL_ID"] == SMOKE_ENV["AGENT_MODEL_ID"]


def test_aws_targets_template_renders_clean() -> None:
    rendered = _render(AWS_TARGETS_TEMPLATE, SMOKE_ENV)
    leftover = UNRESOLVED_RE.findall(rendered)
    assert not leftover, (
        f"aws-targets.json still has unresolved placeholders after envsubst: {leftover}"
    )
    parsed = json.loads(rendered)
    assert parsed["account"] == SMOKE_ENV["AWS_ACCOUNT"]
    assert parsed["region"] == SMOKE_ENV["AWS_REGION"]


# ---------------------------------------------------------------------------
# Every placeholder is exported by deploy_all.sh
# ---------------------------------------------------------------------------


def test_every_template_placeholder_is_exported_by_deploy_script() -> None:
    """If a template references ``${X}`` but ``deploy_all.sh`` never exports
    or sources ``X``, ``envsubst`` silently substitutes an empty string.
    Catch that drift here so a rename on either side trips the test."""
    assert DEPLOY_SCRIPT.is_file(), f"deploy_all.sh missing at {DEPLOY_SCRIPT}"
    script = DEPLOY_SCRIPT.read_text()

    template_vars = _placeholders_in(AGENTCORE_TEMPLATE) | _placeholders_in(
        AWS_TARGETS_TEMPLATE
    )

    # ``deploy_all.sh`` either exports the variable directly (``export FOO=...``)
    # or relies on its caller having sourced CFN outputs into the env. Caller-
    # exported vars (PGHOSTARN, AGENTCORE_ROLE_ARN, etc.) are documented in the
    # script's prerequisites comment block, so we accept either pattern.
    missing = []
    for var in sorted(template_vars):
        # ``\b`` doesn't apply inside ``${...}`` so we anchor explicitly.
        # Bash supports several ways to reference a variable; accept any of
        # them — including the ``${VAR:?msg}`` "fail fast if unset" guard.
        if (
            f"export {var}=" in script
            or f"${{{var}}}" in script
            or f"${{{var}:" in script
            or f"${var}" in script
            or f"{var}=" in script
        ):
            continue
        missing.append(var)

    assert not missing, (
        f"Template placeholders not referenced anywhere in deploy_all.sh: {missing}. "
        f"Either the script needs to export them (via CFN outputs / aws CLI), or "
        f"the template should drop the placeholder."
    )
