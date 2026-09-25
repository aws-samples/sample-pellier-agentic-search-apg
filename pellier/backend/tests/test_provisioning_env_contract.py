"""Every variable the fresh provisioner requires must actually reach it.

The fresh-account failure this closes
-------------------------------------

Measured on a real fresh provision, 2026-08-28. The managed AgentCore path died on one
line:

    RuntimeError: Missing required environment variable: AGENT_MODEL_ID

and took Runtime, Memory, Gateway and Policy with it. Nine readiness checks then failed,
all with that single cause, and the box came up as a storefront with no governed rail:
Labs 3 and 4 would have been impossible.

The mechanism is worth stating precisely, because it is not obvious from either side.
`bootstrap-labs.sh` invokes the provisioner through
`sudo -u <participant> bash -c "..."`, and **sudo strips the parent environment**. Only
the variables that block explicitly re-exports survive. `check_model_access.py` resolves
the model ids at bootstrap time and writes them into `pellier/backend/.env`, because they
are not static: an account without Opus access gets a documented fallback. Nothing carried
that value from the file into the provisioner's process.

So both halves are asserted here: the provisioner reads the `.env` as a fallback, and the
bootstrap block re-exports what it needs. Either alone fixes today's variable; together
they close the class, which is what matters, since the next required variable will be
added by someone who has never read this file.
"""

from __future__ import annotations

import re
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Set

REPO = Path(__file__).resolve().parents[3]
PROVISIONER = REPO / "scripts" / "provision_agentcore_end_to_end.py"
BOOTSTRAP = REPO / "scripts" / "bootstrap-labs.sh"
MODEL_CHECK = REPO / "scripts" / "check_model_access.py"

# Variables the CloudFormation asset sets for the whole boot, which bootstrap re-exports
# or defaults itself. Listed so the assertion below is about the provisioner's contract
# rather than about CloudFormation's.
SHELL_PROVIDED = {"AWS_REGION", "AWS_DEFAULT_REGION", "REPO_PATH"}


def _required_env_names() -> Set[str]:
    """Every `_require_env("NAME")` the provisioner will raise on."""
    return set(re.findall(r'_require_env\(\s*"([A-Z0-9_]+)"', PROVISIONER.read_text()))


def _sudo_block() -> str:
    """The `sudo -u ... bash -c "..."` block that launches the provisioner.

    Bounded by the invocation itself, so an export somewhere else in bootstrap does not
    count: sudo only carries what this block re-exports.
    """
    body = BOOTSTRAP.read_text()
    start = body.index('sudo -u "$CODE_EDITOR_USER" bash -c "\n')
    end = body.index("provision_agentcore_end_to_end.py", start)
    return body[start:end]


def _env_written_by_bootstrap() -> Set[str]:
    """Variables bootstrap or the model preflight writes into the backend `.env`."""
    names = set(re.findall(r"^([A-Z0-9_]+)='", BOOTSTRAP.read_text(), re.MULTILINE))
    names |= set(re.findall(r'_upsert_env\([^,]+,\s*"([A-Z0-9_]+)"', MODEL_CHECK.read_text()))
    return names


def test_the_scan_finds_the_contract() -> None:
    """A guard that discovers nothing passes forever."""
    required = _required_env_names()
    assert len(required) >= 5, f"only {len(required)} required variables found"
    assert "AWS_REGION" in required
    block = _sudo_block()
    assert "export " in block and len(block) > 200


def test_every_required_variable_reaches_the_provisioner() -> None:
    """Each one is exported by the launching block, or written to the .env it reads."""
    required = _required_env_names()
    exported = set(re.findall(r"export ([A-Z0-9_]+)=", _sudo_block()))
    from_env_file = _env_written_by_bootstrap()

    unreachable = sorted(
        name for name in required
        if name not in exported and name not in from_env_file and name not in SHELL_PROVIDED
    )
    assert not unreachable, (
        "these variables are required by provision_agentcore_end_to_end.py but nothing "
        "delivers them. sudo strips the parent environment, so an export elsewhere in "
        "bootstrap does not count:\n  " + "\n  ".join(unreachable)
    )


def test_the_provisioner_reads_the_env_file_as_a_fallback() -> None:
    """The safety net, and it must run before the first requirement."""
    source = PROVISIONER.read_text()
    assert "def _load_env_fallback(" in source
    assert "_load_env_fallback(repo)" in source
    assert source.index("_load_env_fallback(repo)") < source.index('_require_env("AWS_REGION")')


def test_the_env_fallback_never_overrides_a_real_variable() -> None:
    """An explicit export is the caller's decision; a stale file must not win over it."""
    source = PROVISIONER.read_text()
    body = source[source.index("def _load_env_fallback("): source.index("def _require_env(")]
    assert 'not os.environ.get(key, "").strip()' in body, (
        "the fallback assigns unconditionally, so a stale .env would override an "
        "explicitly exported value"
    )


def _load_saved_inputs(repo: Path, environment: dict[str, str]) -> None:
    """Execute the actual loader without importing deployment side effects."""
    tree = ast.parse(PROVISIONER.read_text())
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "_load_env_fallback")
    namespace = {"Path": Path, "os": SimpleNamespace(environ=environment), "re": re}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(PROVISIONER), "exec"), namespace)
    namespace["_load_env_fallback"](repo)


def test_clean_participant_shell_loads_bootstrap_provisioning_inputs(tmp_path) -> None:
    (tmp_path / ".env").write_text("AGENT_MODEL_ID='resolved-model'\nDB_CLUSTER_ARN='cluster'\n")
    (tmp_path / ".provision.env").write_text(
        "export AWS_REGION='us-east-1'\n"
        "export COGNITO_POOL='fresh-pool'\n"
        "export COGNITO_CLIENT='fresh-client'\n"
        "export AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN='log-key'\n"
    )
    environment = {}
    _load_saved_inputs(tmp_path, environment)
    assert environment == {
        "AGENT_MODEL_ID": "resolved-model", "DB_CLUSTER_ARN": "cluster",
        "AWS_REGION": "us-east-1", "COGNITO_POOL": "fresh-pool",
        "COGNITO_CLIENT": "fresh-client", "AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN": "log-key",
    }


def test_saved_provisioning_inputs_preserve_caller_and_runtime_precedence(tmp_path) -> None:
    (tmp_path / ".env").write_text("AGENT_MODEL_ID='runtime-model'\n")
    (tmp_path / ".provision.env").write_text(
        "export COGNITO_POOL='saved-pool'\n"
        "export AGENT_MODEL_ID='stale-model'\n"
        "export PELLIER_DEPLOYMENT_SUFFIX='stale-suffix'\n"
        "export AWS_REGION='us-east-1'\n"
    )
    environment = {"COGNITO_POOL": "caller-pool", "PELLIER_DEPLOYMENT_SUFFIX": "", "AWS_REGION": ""}
    _load_saved_inputs(tmp_path, environment)
    assert environment == {
        "COGNITO_POOL": "caller-pool", "PELLIER_DEPLOYMENT_SUFFIX": "",
        "AWS_REGION": "us-east-1", "AGENT_MODEL_ID": "runtime-model",
    }


def test_saved_assignments_are_literal_data_and_invalid_names_are_ignored(tmp_path) -> None:
    literal = '${OTHER} $(touch should-not-exist) `echo nope` \\ path'
    (tmp_path / ".provision.env").write_text(
        f"export VALUE='{literal}'\nexport INVALID NAME=ignored\nexport EMPTY=''\n"
    )
    environment = {}
    _load_saved_inputs(tmp_path, environment)
    assert environment == {"VALUE": literal}
    assert not (tmp_path / "should-not-exist").exists()


def test_the_model_id_is_resolved_not_hardcoded() -> None:
    """`AGENT_MODEL_ID` is written at bootstrap time, so it cannot be pinned in source.

    An account without Opus access takes a documented fallback, which is exactly why the
    value has to travel from `check_model_access.py` rather than being a literal.
    """
    assert "AGENT_MODEL_ID" in _required_env_names()
    assert 'AGENT_MODEL_ID"' in MODEL_CHECK.read_text()
    assert "export AGENT_MODEL_ID=" in _sudo_block()


def test_the_rls_seed_runs_as_the_user_that_owns_the_dependencies() -> None:
    """Root's python3 has no boto3, and an empty mapping denies every shopper.

    Dependencies are installed with `pip install --user` for the participant. Running the
    seed as root raised ModuleNotFoundError on a fresh box, left
    `pellier.principal_customers` empty, and Row-Level Security then denied every
    signed-in shopper their own orders. That presents as a broken storefront rather than
    as governance.
    """
    body = BOOTSTRAP.read_text()
    # The INVOCATION, not the `[ -f ... ]` existence guard a few lines above it. Anchoring
    # on the bare filename found the guard and read the wrong window.
    marker = 'python3.14 "$REPO_PATH/scripts/seed_principal_mappings.py"'
    assert marker in body, "bootstrap no longer invokes the RLS principal seed"
    call = body.index(marker)
    window = body[max(0, call - 700): call]
    assert 'sudo -u "$CODE_EDITOR_USER"' in window, (
        "the RLS principal seed runs as root, whose python3 has no --user dependencies"
    )
