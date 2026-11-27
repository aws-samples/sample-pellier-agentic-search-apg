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
    for arg in "$@"; do
      case "$arg" in
        "Authorization: Bearer "*) echo "${arg#Authorization: Bearer }" >> "$FAKE_LOG.bearers" ;;
        *'"session_id":"'*) printf '%s\\n' "$arg" | sed -E 's/.*"session_id":"([^"]*)".*/\\1/' >> "$FAKE_LOG.sessions" ;;
      esac
    done
    if [ -n "${FAKE_REPLIES:-}" ]; then
      n="$(grep -c '^chat$' "$FAKE_LOG")"
      entry="$(printf '%s' "$FAKE_REPLIES" | cut -d, -f"$n")"
      case "$entry" in
        error:*) printf 'data: {"type": "error", "code": "%s", "retryable": true}\\n' "${entry#error:}" ;;
        complete:*) printf 'data: {"type": "complete", "response": {"rail": "%s", "turn_id": "turn-%s"}}\\n' "${entry#complete:}" "$n" ;;
      esac
      exit 0
    fi
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
        "sleep": '#!/usr/bin/env bash\necho "sleep $*" >> "$FAKE_LOG.sleeps"\n',
    }.items():
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(bin_dir.joinpath(name).stat().st_mode | stat.S_IXUSR)
    for key, value in {
        "PATH": f"{bin_dir}:{os.environ['PATH']}", "PELLIER_REPO": str(tmp_path / "repo"),
        "PELLIER_RUN_ENV": str(run_env), "PELLIER_PYTHON": sys.executable,
        "PELLIER_TOKEN": "token", "FAKE_LOG": str(log), "FAKE_HEALTHY": "yes",
        "FAKE_RAIL": "gateway-mcp", "AGENTCORE_MANAGED_OUTPUT_JSON": str(tmp_path / "managed.json"),
        "AGENTCORE_PARTICIPANT_OUTPUT_JSON": str(tmp_path / "absent.json"),
        "TMPDIR": str(tmp_path), "PELLIER_TOKEN_HELPER": str(tmp_path / "no-token-helper.sh"),
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
    # The proof fails on a clean line; it never trips set -u on the switch-only rail_target.
    assert "unbound variable" not in done.stderr, done.stderr
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


def _bearers(box: dict[str, Any]) -> list[str]:
    sent = Path(f"{box['log']}.bearers")
    return sent.read_text().splitlines() if sent.exists() else []


def test_a_token_left_in_the_shell_is_replaced_by_one_minted_for_the_persona(
        box, tmp_path, monkeypatch) -> None:
    """`source ~/pellier-token.sh theo` leaves $PELLIER_TOKEN in the participant's terminal.

    An hour later it has expired. The script sent it, the turn ran unsigned and the script blamed
    AgentCore: on the 2026-11-20 event box an 82-minute-old token failed `finish --lab 3` with
    "reported rail 'none' not gateway-mcp". A token for another shopper fails the same way.
    """
    helper = tmp_path / "pellier-token.sh"
    helper.write_text('export PELLIER_TOKEN="minted-for-$1"\n')
    monkeypatch.setenv("PELLIER_TOKEN_HELPER", str(helper))
    monkeypatch.setenv("PELLIER_TOKEN", "left-in-the-shell")
    done = _run(box, "theo")
    assert done.returncode == 0, done.stdout
    assert _bearers(box) == ["minted-for-theo"]
    assert "Cognito token minted for theo" in done.stdout


def test_a_supplied_token_is_used_where_no_helper_exists(box) -> None:
    done = _run(box, "theo")
    assert done.returncode == 0
    assert _bearers(box) == ["token"]
    assert "minted" not in done.stdout and "using the PELLIER_TOKEN supplied" in done.stdout


def test_a_helper_that_mints_nothing_stops_before_the_turn(box, tmp_path, monkeypatch) -> None:
    helper = tmp_path / "pellier-token.sh"
    helper.write_text('export PELLIER_TOKEN=""\n')
    monkeypatch.setenv("PELLIER_TOKEN_HELPER", str(helper))
    monkeypatch.setenv("PELLIER_TOKEN", "left-in-the-shell")
    done = _run(box, "theo")
    assert done.returncode == 1
    assert "Could not mint a Cognito token for 'theo'" in done.stdout + done.stderr
    assert _bearers(box) == []


def test_the_full_switch_is_unchanged(box) -> None:
    box["run_env"].write_text("USE_AGENTCORE_RUNTIME=false\n")
    done = _run(box, "theo")
    assert done.returncode == 0
    assert "USE_AGENTCORE_RUNTIME=true" in box["run_env"].read_text()
    assert _calls(box) == ["systemctl restart pellier", "chat"]
    assert "Pellier Lab 3 start: managed rail" in done.stdout
    assert "Turn turn-1 executed on rail gateway-mcp" in done.stdout
    assert "Lab 3 may proceed." in done.stdout


def test_lab4_switch_reports_its_managed_turn_without_lab3_instructions(box) -> None:
    done = _run(box, "--lab-4", "theo")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _calls(box) == ["systemctl restart pellier", "chat"]
    assert "Turn turn-1 executed on rail gateway-mcp" in done.stdout
    assert "The check request ran on AgentCore Runtime and Gateway." in done.stdout
    assert "Lab 3 may proceed" not in done.stdout
    assert "Pellier Lab 3 start" not in done.stdout


def test_a_failed_full_switch_still_says_the_flag_survives(box, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_RAIL", "in-process")
    done = _run(box, "theo")
    assert done.returncode == 1
    assert "Already written to" in done.stdout and "survives this failure" in done.stdout


# A test event, 25 Nov 2026: the AgentCore data plane answered a completed turn with an empty body.
# The app turns that into the stream's generic request_failed error (classify_chat_error), which
# is the only failure this read-only check turn asks again, each time in a new session.
def _sessions(box: dict[str, Any]) -> list[str]:
    path = Path(str(box["log"]) + ".sessions")
    return path.read_text().splitlines() if path.exists() else []


def test_an_empty_reply_is_asked_again_in_a_new_session(box, monkeypatch) -> None:
    record_dir = box["cwd"] / ".agentcore-project"
    record_dir.mkdir()
    box["run_env"].write_text("USE_AGENTCORE_RUNTIME=false\n")
    monkeypatch.setenv("FAKE_REPLIES", "error:request_failed,complete:gateway-mcp")
    done = _run(box, "theo")
    assert done.returncode == 0, done.stdout + done.stderr
    assert [c for c in _calls(box) if c == "chat"] == ["chat", "chat"]
    assert len(set(_sessions(box))) == 2, "each ask needs its own session"
    assert done.stdout.count("Lab 3 may proceed") == 1
    record = (record_dir / "runtime-reply-retries.log").read_text()
    assert record.count("\n") == 1 and "request_failed" in record


def test_verify_only_asks_again_without_printing(box, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_REPLIES", "error:request_failed,complete:gateway-mcp")
    done = _run(box, "--verify-only", "theo")
    assert done.returncode == 0 and done.stdout == "" and done.stderr == ""
    assert _calls(box) == ["chat", "chat"]


@pytest.mark.parametrize("code", ["service_unavailable", "request_timeout", "authentication_required",
                                  "policy_denied"])
def test_other_failures_are_not_asked_again(box, monkeypatch, code) -> None:
    monkeypatch.setenv("FAKE_REPLIES", f"error:{code},complete:gateway-mcp")
    done = _run(box, "--verify-only", "theo")
    assert done.returncode == 1 and _calls(box) == ["chat"]
    assert code in done.stdout + done.stderr


def test_replies_that_never_arrive_fail_after_four_asks(box, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_REPLIES", ",".join(["error:request_failed"] * 5))
    done = _run(box, "theo")
    assert done.returncode == 1
    assert [c for c in _calls(box) if c == "chat"] == ["chat"] * 4
    assert "request_failed" in done.stdout + done.stderr
