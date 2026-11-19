"""A configuration flag never proves that Pellier runs on AgentCore.

lab3-start.sh writes USE_AGENTCORE_RUNTIME=true before it restarts the service and makes the
one signed-in turn that must report the rail gateway-mcp. A restart or a turn that failed
leaves the flag set. The participant deploy that follows used to read the flag alone and print
"Pellier is already using AgentCore.", which Task 3B reads as permission to continue. These
tests drive the real script with a fake curl and a fake systemctl, and the move with a fake
runner. No AWS and no systemd are touched.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"
FAKE_CURL = """#!/usr/bin/env bash
case "$*" in
  *"/api/health"*) [ "$FAKE_HEALTHY" = "yes" ] && echo '{"status": "healthy"}' || exit 22 ;;
  *"/api/chat/stream"*)
    echo "chat" >> "$FAKE_LOG"
    reply='{"type": "complete", "response": {"rail": "%s", "turn_id": "turn-1"}}'
    printf "data: $reply\\n" "$FAKE_RAIL"
    ;;
esac
"""


@pytest.fixture
def box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A copy of the script beside stub helpers, with a fake curl, sudo and systemctl."""
    scripts = tmp_path / "repo" / "scripts"
    (scripts / "lib").mkdir(parents=True)
    for name in ("lab3-start.sh", "lib/dotenv.sh", "lib/progress.sh"):
        shutil.copy(SCRIPTS / name, scripts / name)
    (scripts / "validate_agentcore_receipt.py").write_text("raise SystemExit(0)\n")
    (tmp_path / "repo" / ".env").write_text(
        "AGENTCORE_GATEWAY_URL=https://gateway\nAGENTCORE_RUNTIME_ENDPOINT=arn:runtime\n"
        "AGENTCORE_OPERATOR_RUNTIME_ENDPOINT=arn:staff\n")
    run_env = tmp_path / "run.env"
    run_env.write_text("USE_AGENTCORE_RUNTIME=true\n")
    (tmp_path / "managed.json").write_text("{}")
    bin_dir, log = tmp_path / "bin", tmp_path / "calls.log"
    bin_dir.mkdir()
    for name, body in {
        "curl": FAKE_CURL,
        "sudo": '#!/usr/bin/env bash\nshift\nexec "$@"\n',
        "systemctl": '#!/usr/bin/env bash\necho "systemctl $*" >> "$FAKE_LOG"\n',
    }.items():
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(bin_dir.joinpath(name).stat().st_mode | stat.S_IXUSR)
    for key, value in {
        "PATH": f"{bin_dir}:{os.environ['PATH']}", "PELLIER_REPO": str(tmp_path / "repo"),
        "PELLIER_RUN_ENV": str(run_env), "PELLIER_PYTHON": sys.executable,
        "PELLIER_TOKEN": "token", "FAKE_LOG": str(log), "FAKE_HEALTHY": "yes",
        "FAKE_RAIL": "gateway-mcp", "AGENTCORE_MANAGED_OUTPUT_JSON": str(tmp_path / "managed.json"),
        "AGENTCORE_PARTICIPANT_OUTPUT_JSON": str(tmp_path / "absent.json"),
        "TMPDIR": str(tmp_path),
    }.items():
        monkeypatch.setenv(key, value)
    return {"script": scripts / "lab3-start.sh", "run_env": run_env, "log": log,
            "cwd": tmp_path / "repo"}


def _run(box: dict[str, Any], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(box["script"]), *args], cwd=box["cwd"],
                          capture_output=True, text=True, timeout=60)


def _calls(box: dict[str, Any]) -> list[str]:
    return box["log"].read_text().splitlines() if box["log"].exists() else []


def test_verify_only_proves_the_running_app_without_changing_anything(box) -> None:
    before = box["run_env"].read_text()
    done = _run(box, "--verify-only", "theo")
    assert done.returncode == 0 and done.stdout == "" and done.stderr == ""
    assert _calls(box) == ["chat"], "one signed-in turn, and no restart"
    assert box["run_env"].read_text() == before


def test_a_flag_that_the_running_app_does_not_honour_fails_the_verification(
        box, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_RAIL", "in-process")
    before = box["run_env"].read_text()
    done = _run(box, "--verify-only", "theo")
    assert done.returncode == 1
    assert "Pellier did not answer on AgentCore" in done.stdout
    assert "reported rail 'in-process' not gateway-mcp" in done.stdout
    assert "running the switch again" in done.stdout
    assert "Already written" not in done.stdout + done.stderr
    assert box["run_env"].read_text() == before
    assert not [call for call in _calls(box) if call.startswith("systemctl")]


def test_an_app_that_is_down_fails_the_verification_without_a_turn(box, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_HEALTHY", "no")
    done = _run(box, "--verify-only", "theo")
    assert done.returncode == 1 and "is not healthy" in done.stdout
    assert _calls(box) == []


def test_a_receipt_that_is_missing_fails_the_verification(box, monkeypatch) -> None:
    monkeypatch.setenv("AGENTCORE_MANAGED_OUTPUT_JSON", str(box["cwd"] / "nope.json"))
    done = _run(box, "--verify-only", "theo")
    assert done.returncode == 1 and "receipt not found" in done.stdout
    assert _calls(box) == []


def test_the_full_switch_is_unchanged(box) -> None:
    box["run_env"].write_text("USE_AGENTCORE_RUNTIME=false\n")
    done = _run(box, "theo")
    assert done.returncode == 0
    assert "USE_AGENTCORE_RUNTIME=true" in box["run_env"].read_text()
    assert _calls(box) == ["systemctl restart pellier", "chat"]
    assert "Pellier Lab 3 start: managed rail" in done.stdout
    assert "Turn turn-1 executed on rail gateway-mcp" in done.stdout
    assert "Lab 3 may proceed." in done.stdout


def test_a_failed_full_switch_still_says_the_flag_survives(box, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_RAIL", "in-process")
    done = _run(box, "theo")
    assert done.returncode == 1
    assert "Already written to" in done.stdout and "survives this failure" in done.stdout
