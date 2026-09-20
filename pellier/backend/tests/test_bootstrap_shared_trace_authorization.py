"""Bootstrap preserves explicit shared-log authorization across shell boundaries."""

import os
from pathlib import Path
import subprocess

import pytest


REPO = Path(__file__).resolve().parents[3]
FLAG = "AGENTCORE_ALLOW_SHARED_TRACE_LOG_CHANGES"


@pytest.mark.parametrize("requested,expected", [(None, "false"), ("", "false"), ("false", "false"), ("true", "true")])
def test_recovery_file_and_sudo_shell_keep_shared_log_authorization(
    tmp_path, requested, expected,
):
    source = (REPO / "scripts/bootstrap-labs.sh").read_text()
    recovery = source.split('cat > "$PROVISION_ENV" << EOF\n', 1)[1].split("\nEOF", 1)[0]
    sudo = source.split('sudo -u "$CODE_EDITOR_USER" bash -c "', 1)[1]
    flag_export = next(line.strip() for line in sudo.splitlines() if f"export {FLAG}=" in line)
    env = os.environ.copy()
    env.pop(FLAG, None)
    env["AWS_REGION"] = "us-east-1"
    env["PROVISION_ENV"] = str(tmp_path / "provision.env")
    if requested is not None:
        env[FLAG] = requested

    # Exercise the actual recovery heredoc, then read it in a clean child.
    write = subprocess.run(
        ["bash", "-eu", "-c", 'cat > "$PROVISION_ENV" << EOF\n' + recovery + "\nEOF\n"],
        env=env, capture_output=True, text=True, check=True,
    )
    assert write.stdout == ""
    read = subprocess.run(
        ["bash", "-eu", "-c", f'source "$PROVISION_ENV"; printf "%s" "${{{FLAG}}}"'],
        env={"PATH": env["PATH"], "PROVISION_ENV": env["PROVISION_ENV"]},
        capture_output=True, text=True, check=True,
    )
    assert read.stdout == expected

    # Expand the real sudo export in the parent, then remove inherited input
    # before running the child, as sudo does in managed bootstrap.
    sudo_result = subprocess.run(
        ["bash", "-eu", "-c", f'child="{flag_export}"; unset {FLAG}; bash -eu -c "$child; env"'],
        env=env, capture_output=True, text=True, check=True,
    )
    child_env = dict(line.split("=", 1) for line in sudo_result.stdout.splitlines() if "=" in line)
    assert child_env[FLAG] == expected


@pytest.mark.parametrize("requested,expected", [(None, "false"), ("", "false"), ("false", "false"), ("true", "true")])
def test_stage2_manifest_preserves_explicit_shared_log_authorization(tmp_path, requested, expected):
    source = (REPO / "scripts/bootstrap-environment.sh").read_text()
    function = "write_stage2_manifest() {" + source.split("write_stage2_manifest() {", 1)[1].split("\n}\n", 1)[0] + "\n}\n"
    env = {"PATH": os.environ["PATH"], "STAGE2_ENV_MANIFEST": str(tmp_path / "stage2.env")}
    if requested is not None:
        env[FLAG] = requested
    script = "chown() { :; }\n" + function + f'write_stage2_manifest\nunset {FLAG}\nsource "$STAGE2_ENV_MANIFEST"\nprintf "%s" "${{{FLAG}}}"'
    result = subprocess.run(["bash", "-eu", "-c", script], env=env, capture_output=True, text=True, check=True)
    assert result.stdout == expected
    assert (tmp_path / "stage2.env").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("workshop_format", [None, "governed", "builders"])
def test_governed_bootstrap_defers_all_early_transaction_search_calls(tmp_path, workshop_format):
    source = (REPO / "scripts/bootstrap-labs.sh").read_text()
    section = source.split("# STEP 13b: CLOUDWATCH TRANSACTION SEARCH", 1)[1]
    section = section.split("# STEP 14: AUTO-START PELLIER SERVICE", 1)[0]
    section = section[section.index("\n"):]
    calls = tmp_path / "aws-calls"
    env = {"PATH": os.environ["PATH"], "AWS_REGION": "us-east-1", "AWS_CALLS": str(calls)}
    if workshop_format is not None:
        env["WORKSHOP_FORMAT"] = workshop_format
    stubs = '''
log() { :; }
warn() { :; }
aws() {
    printf '%s\\n' "$*" >> "$AWS_CALLS"
    if [ "$1 $2" = "sts get-caller-identity" ]; then printf '123456789012\\n'; fi
}
'''
    subprocess.run(["bash", "-eu", "-c", stubs + section], env=env, capture_output=True, text=True, check=True)
    if workshop_format != "builders":
        assert not calls.exists()
    else:
        observed = calls.read_text()
        assert "logs put-resource-policy" in observed
        assert "xray update-trace-segment-destination" in observed
        assert "xray update-indexing-rule" in observed
