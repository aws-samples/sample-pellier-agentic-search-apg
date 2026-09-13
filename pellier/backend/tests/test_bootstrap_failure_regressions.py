"""Execute the bootstrap boundaries that previously hid or fabricated failures."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

import pytest


REPO = Path(__file__).resolve().parents[3]
ENVIRONMENT = REPO / "scripts/bootstrap-environment.sh"
LABS = REPO / "scripts/bootstrap-labs.sh"


def run_bash(script: str, **environment: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", "set -euo pipefail\n" + script],
        env={**os.environ, **environment},
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    "stage2_url,wait_handle,returncode,expected",
    [
        ("", "", 0, "calling UserData"),
        ("", "synthetic-handle", 1, "SIGNAL_FAILURE"),
        ("https://example.invalid/stage2.sh", "synthetic-handle", 0, "CONTINUE_STAGE2"),
    ],
)
def test_stage_one_respects_the_owner_of_the_final_signal(
    stage2_url: str, wait_handle: str, returncode: int, expected: str
) -> None:
    source = ENVIRONMENT.read_text()
    start = source.index('if [ -z "${STAGE2_SCRIPT_URL}" ]; then')
    end = source.index('log "Running Stage 2:', start)
    result = run_bash(
        'log() { echo "$1"; }\n'
        'error() { echo "$1"; exit 1; }\n'
        'signal_cloudformation() { echo "SIGNAL_$1"; }\n'
        + source[start:end]
        + '\necho CONTINUE_STAGE2\n',
        STAGE2_SCRIPT_URL=stage2_url,
        CFN_WAIT_HANDLE=wait_handle,
    )
    assert result.returncode == returncode, result.stderr
    assert expected in result.stdout
    assert "SIGNAL_SUCCESS" not in result.stdout
    if not stage2_url and not wait_handle:
        assert "SIGNAL_FAILURE" not in result.stdout
        assert "CONTINUE_STAGE2" not in result.stdout


@pytest.mark.parametrize("frontend_rc,database_rc", [(0, 1), (1, 0), (1, 1), (0, 0)])
def test_parallel_setup_cannot_advance_after_a_failed_dependency(
    frontend_rc: int, database_rc: int, tmp_path: Path
) -> None:
    source = LABS.read_text()
    start = source.index("setup_frontend & PID_FE=$!")
    end = source.index("# Memory is created once", start)
    fail_function = next(line for line in source.splitlines() if line.startswith("fail()"))
    result = run_bash(
        "RED='' NC=''\n"
        'log() { :; }\n'
        'set_provision_state() { printf "%s" "$1" > "$PROBE_STATE"; }\n'
        + fail_function + "\n"
        + f"setup_frontend() {{ return {frontend_rc}; }}\n"
        + f"setup_database() {{ return {database_rc}; }}\n"
        + source[start:end]
        + '\nset_provision_state APP_READY\necho ADVANCED\n',
        PROBE_STATE=str(tmp_path / "state"),
    )
    if frontend_rc or database_rc:
        assert result.returncode == 1
        assert (tmp_path / "state").read_text() == "FAILED"
        assert "ADVANCED" not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "state").read_text() == "APP_READY"


@pytest.mark.parametrize("status,ready", [("200", True), ("302", True), ("403", False), ("000", False)])
def test_editor_readiness_requires_an_authenticated_response(
    status: str, ready: bool, tmp_path: Path
) -> None:
    source = ENVIRONMENT.read_text()
    probe = re.search(r"^probe_editor_http\(\) \{.*?^\}", source, re.M | re.S)
    assert probe
    start = source.index("MAX_RETRIES=30")
    end = source.index("# STEP 8:", start)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl = fake_bin / "curl"
    curl.write_text(
        "#!/bin/bash\n"
        "token=false\n"
        "while (( $# )); do\n"
        '  if [[ "$1" == --data-urlencode ]]; then\n'
        "    shift\n"
        "    [[ \"$1\" == 'tkn=synthetic token&value' ]] && token=true\n"
        "  fi\n"
        "  shift\n"
        "done\n"
        '$token || exit 1\nprintf "%s" "$MOCK_HTTP"\n'
    )
    curl.chmod(0o755)
    result = run_bash(
        'log() { :; }\nerror() { echo "$1"; exit 1; }\nsleep() { :; }\n'
        + probe[0] + "\n" + source[start:end] + "\necho EDITOR_READY\n",
        PATH=f"{fake_bin}:{os.environ['PATH']}",
        CODE_EDITOR_PASSWORD="synthetic token&value",
        MOCK_HTTP=status,
    )
    assert result.returncode == (0 if ready else 1), result.stderr
    assert ("EDITOR_READY" in result.stdout) is ready
    assert "synthetic token&value" not in result.stdout + result.stderr


def test_generating_the_service_does_not_execute_its_comments(tmp_path: Path) -> None:
    source = LABS.read_text()
    block = re.search(
        r"cat > /etc/systemd/system/pellier.service << EOF\n.*?\nEOF\n",
        source,
        re.S,
    )
    assert block
    unit = tmp_path / "pellier.service"
    result = run_bash(
        'npm() { echo called > "$PROBE_CALLED"; }\n'
        + block[0].replace("/etc/systemd/system/pellier.service", str(unit), 1),
        PROBE_CALLED=str(tmp_path / "unexpected-command"),
        REPO_PATH="/synthetic/workshop",
        CODE_EDITOR_USER="participant",
        UVICORN_RELOAD_ARGS="--reload",
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "unexpected-command").exists()
    assert "ExecStartPre=" in unit.read_text()


def test_environment_summary_does_not_print_the_editor_password() -> None:
    summary = ENVIRONMENT.read_text().split("# SUMMARY\n", 1)[1]
    result = run_bash(
        "log() { :; }\n" + summary,
        PY_VER="3.14",
        CODE_EDITOR_PASSWORD="synthetic-private-editor-password",
    )
    assert result.returncode == 0, result.stderr
    assert "synthetic-private-editor-password" not in result.stdout + result.stderr
