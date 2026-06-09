"""Tests for the AgentCore Runtime deploy contract (@aws/agentcore 0.18, CDK).

The 0.18 CLI replaced the old flat-config deploy (a bare ``agentcore.json`` +
``aws-targets.json`` rendered via ``envsubst``, then ``agentcore deploy``) with
a STATEFUL, CDK-based project model:

    agentcore create   -> scaffold <root>/<proj>/agentcore/
    agentcore add agent -> register a runtime (BYO points at our entrypoint)
    agentcore deploy    -> CDK synth + deploy from the PROJECT ROOT

``add agent`` sets name/entrypoint/protocol/CUSTOM_JWT via flags, but has NO
flags for ``executionRoleArn`` or ``envVars`` — those are JSON-patched into
``agentcore/agentcore.json`` afterward. ``aws-targets.json`` is now an ARRAY.

These tests pin that contract STATICALLY (no AWS calls, no Node, no CLI) so a
drift between ``deploy_all.sh`` and ``provision_agentcore_end_to_end.py`` — or a
regression back to the dead flat-template path — trips here. They assert:

  1. The obsolete flat templates are gone (no resurrection of the old path).
  2. Both deploy paths pin the SAME CLI version (no @latest in production).
  3. Both paths use the create -> add agent --type byo -> deploy verbs and the
     in-repo orchestrator entrypoint (agentcore_runtime.py), not the adapter.
  4. The JSON-patch step sets executionRoleArn + envVars + runtimeVersion.

Runnable from the repo root per ``pytest.ini``:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_agentcore_deploy_templates.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "pellier" / "backend"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "deploy_all.sh"
PROVISIONER = REPO_ROOT / "scripts" / "provision_agentcore_end_to_end.py"
ENTRYPOINT = BACKEND_DIR / "agentcore_runtime.py"
PYPROJECT = BACKEND_DIR / "pyproject.toml"

PINNED_CLI = "@aws/agentcore@0.18.0"
RUNTIME_NAME = "pellier_orchestrator"


# ---------------------------------------------------------------------------
# The obsolete flat-config path is gone (must not be resurrected)
# ---------------------------------------------------------------------------


def test_flat_templates_removed() -> None:
    """The old envsubst templates are incompatible with 0.18 — they must not
    exist (their presence would imply the dead deploy path is back)."""
    for stale in ("agentcore.json.template", "aws-targets.json.template"):
        assert not (BACKEND_DIR / stale).exists(), (
            f"{stale} should have been removed in the 0.18 CLI migration — "
            "the stateful create/add/deploy path replaces it."
        )


def test_no_latest_pin_in_deploy_paths() -> None:
    """@latest re-resolves per run and drifted contracts mid-development. Both
    deploy paths must pin an explicit version."""
    for path in (DEPLOY_SCRIPT, PROVISIONER):
        text = path.read_text()
        assert "@aws/agentcore@latest" not in text, (
            f"{path.name} still references @aws/agentcore@latest — pin a version."
        )
        assert PINNED_CLI in text, (
            f"{path.name} does not pin {PINNED_CLI}."
        )


# ---------------------------------------------------------------------------
# Both paths use the new verbs + the in-repo BYO entrypoint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [DEPLOY_SCRIPT, PROVISIONER], ids=lambda p: p.name)
def test_uses_create_add_deploy_sequence(path: Path) -> None:
    text = path.read_text()
    for verb in ("create", "add", "deploy"):
        assert verb in text, f"{path.name} is missing the '{verb}' CLI verb"
    assert "--type" in text and "byo" in text, (
        f"{path.name} must register a BYO agent (--type byo)"
    )
    assert "agentcore_runtime.py" in text, (
        f"{path.name} must deploy the in-repo orchestrator entrypoint "
        "agentcore_runtime.py (not the Gateway adapter)"
    )
    assert RUNTIME_NAME in text, f"{path.name} must name the runtime {RUNTIME_NAME}"
    assert "CUSTOM_JWT" in text, f"{path.name} must set the CUSTOM_JWT authorizer"


# ---------------------------------------------------------------------------
# The JSON-patch step sets what add agent's flags can't
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [DEPLOY_SCRIPT, PROVISIONER], ids=lambda p: p.name)
def test_patches_role_envvars_runtimeversion(path: Path) -> None:
    text = path.read_text()
    for field in ("executionRoleArn", "envVars", "runtimeVersion"):
        assert field in text, (
            f"{path.name} must patch '{field}' into agentcore.json "
            "(add agent has no flag for it)"
        )
    for env_key in ("MCP_GATEWAY_URL", "AGENT_MODEL_ID"):
        assert env_key in text, f"{path.name} must set the {env_key} env var"


# ---------------------------------------------------------------------------
# The BYO code-location ships its deps as pyproject.toml (0.18 uses uv)
# ---------------------------------------------------------------------------


def test_pyproject_carries_runtime_imports() -> None:
    assert PYPROJECT.is_file(), (
        f"pyproject.toml missing at {PYPROJECT} — 0.18 CodeZip builds use uv + "
        "pyproject.toml, not requirements.txt."
    )
    deps = PYPROJECT.read_text()
    # The orchestrator entrypoint transitively imports these; if any is absent
    # the CodeZip would ImportError at microVM load.
    for pkg in ("strands-agents", "bedrock-agentcore", "pydantic-settings", "boto3"):
        assert pkg in deps, f"pyproject.toml is missing the '{pkg}' dependency"


def test_entrypoint_is_byo_app() -> None:
    """The deployed entrypoint must expose the BedrockAgentCoreApp @entrypoint."""
    text = ENTRYPOINT.read_text()
    assert "BedrockAgentCoreApp" in text
    assert "@app.entrypoint" in text
