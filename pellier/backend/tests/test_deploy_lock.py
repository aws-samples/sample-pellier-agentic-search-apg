"""One deploy at a time, and a second run follows the first instead of hiding it.

Event 12: a participant who closes Code Editor mid-deploy and opens it again gets a new
terminal, while the deploy keeps running in one they can no longer see. The guide says
running the same command again updates the deployment, so they may well run it. A second
deploy of one AgentCore project must not start beside the first; it follows the running one
and ends with its result. These tests run the real provisioner as that second process.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest

REPO = Path(__file__).resolve().parents[3]
PROVISIONER = REPO / "scripts" / "provision_agentcore_end_to_end.py"
sys.path.insert(0, str(REPO / "scripts"))
import deploy_lock  # noqa: E402

STARTED = datetime(2026, 10, 22, 22, 36, 44, tzinfo=timezone.utc)

# Holds the lock as a deploy of the given kind and logs each line it is sent on stdin.
# "exit N" releases the lock with that exit code; "kill" dies without recording one.
HOLD = f"""
import os, signal, sys
sys.path.insert(0, {str(REPO / "scripts")!r})
import deploy_lock
from pathlib import Path
lock = deploy_lock.hold(Path(sys.argv[1]), sys.argv[2])
print("held", flush=True)
for line in sys.stdin:
    line = line.rstrip("\\n")
    if line.startswith("exit "):
        lock.release(int(line.split()[1]))
        break
    if line == "kill":
        os.kill(os.getpid(), signal.SIGKILL)
    lock.log.write(line + "\\n")
    lock.log.flush()
    print("logged", flush=True)
"""


def _lock(repo: Path) -> Path:
    return deploy_lock.lock_path(repo / ".agentcore-project" / "pellier")


def _bare_env() -> dict[str, str]:
    """No AWS or workshop settings: past the lock, the provisioner fails on AWS_REGION."""
    return {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")}


class Holder:
    """A deploy of one kind holding the lock, in its own process."""

    def __init__(self, repo: Path, kind: str = "participant") -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-c", HOLD, str(_lock(repo)), kind], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, text=True, env=_bare_env())
        assert self._read() == "held"

    def _read(self) -> str:
        assert self.process.stdout is not None
        return self.process.stdout.readline().strip()

    def send(self, line: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()
        if not line.startswith(("exit ", "kill")):
            assert self._read() == "logged"

    def end(self, line: str) -> None:
        self.send(line)
        self.process.wait(timeout=30)


def _deploy(repo: Path, receipt: Path, *flags: str, holder: Optional[Holder] = None,
            then: Optional[str] = None) -> subprocess.CompletedProcess[str]:
    """Run the provisioner as a participant; while it follows, end the holder with ``then``."""
    second = subprocess.Popen(
        [sys.executable, str(PROVISIONER), "--repo-path", str(repo), "--mode", "participant",
         "--output-json", str(receipt), *flags],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**_bare_env(), deploy_lock.POLL_ENV: "0.1"})
    seen = ""
    if holder is not None and then is not None:
        assert second.stdout is not None
        while "Following it here" not in seen:  # end the holder only once the second follows
            line = second.stdout.readline()
            assert line, "the second deploy ended without following the first"
            seen += line
        holder.end(then)
    out, err = second.communicate(timeout=120)
    # A terminal message wraps at deploy_lock.WIDTH; compare its words, not its line breaks.
    return subprocess.CompletedProcess(second.args, second.returncode, _flat(seen + out),
                                       _flat(err))


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_a_second_deploy_follows_the_first_and_ends_with_its_result(tmp_path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"status": "provisioning", "stage": "the first deploy"}\n')
    holder = Holder(tmp_path)
    holder.send("  + 0:00  1/4  Checked your files and the deployed project")
    second = _deploy(tmp_path, receipt, holder=holder, then="exit 0")
    assert second.returncode == 0, second.stdout + second.stderr
    assert "A deploy is already running: a deploy of your changes, started at " in second.stdout
    assert f"process {holder.process.pid}." in second.stdout
    assert "Following it here; this run deploys nothing new." in second.stdout
    assert "+ 0:00 1/4 Checked your files and the deployed project" in second.stdout
    assert "It finished. It deployed your files as they were at " in second.stdout
    assert receipt.read_text() == '{"status": "provisioning", "stage": "the first deploy"}\n'

    # Once nothing holds the lock, the same command goes on to deploy.
    third = _deploy(tmp_path, receipt)
    assert "already running" not in third.stdout + third.stderr
    assert "Missing required environment variable: AWS_REGION" in third.stderr


def test_following_a_failed_deploy_fails_and_points_at_its_lines(tmp_path) -> None:
    holder = Holder(tmp_path)
    holder.send("Deploy failed: agentcore deploy exited 1")
    second = _deploy(tmp_path, tmp_path / "receipt.json", holder=holder, then="exit 1")
    assert second.returncode == 1
    assert "Deploy failed: agentcore deploy exited 1" in second.stdout
    assert ("It failed; the lines above say why. Fix that, then run this command again."
            in second.stdout)


def test_following_a_deploy_that_was_killed_says_it_stopped(tmp_path) -> None:
    holder = Holder(tmp_path)
    second = _deploy(tmp_path, tmp_path / "receipt.json", holder=holder, then="kill")
    assert second.returncode == 1
    assert ("It stopped before it finished. Run this command again to deploy your changes."
            in second.stdout)


def test_following_the_resets_deploy_does_not_count_as_yours(tmp_path) -> None:
    holder = Holder(tmp_path, kind="reset")
    second = _deploy(tmp_path, tmp_path / "receipt.json", holder=holder, then="exit 0")
    assert second.returncode == 1
    assert ("It finished, but it was the reset's redeploy of the starters. Run this command "
            "again to deploy your changes.") in second.stdout


def test_a_reset_refuses_at_once_while_a_deploy_runs(tmp_path) -> None:
    holder = Holder(tmp_path)
    try:
        second = _deploy(tmp_path, tmp_path / "receipt.json", "--reset-to-starters")
    finally:
        holder.end("exit 0")
    assert second.returncode == 1
    assert "A deploy is already running: a deploy of your changes" in second.stderr
    assert "Following it" not in second.stdout + second.stderr


def test_a_deploy_killed_mid_run_leaves_no_stale_lock(tmp_path) -> None:
    holder = Holder(tmp_path)
    holder.end("kill")
    assert not deploy_lock.running(_lock(tmp_path))
    deploy_lock.hold(_lock(tmp_path), "participant").release(0)


def test_the_refusal_names_the_running_deploy_and_how_long_it_has_run(tmp_path) -> None:
    first = deploy_lock.hold(_lock(tmp_path), "reset", now=lambda: STARTED)
    try:
        with pytest.raises(deploy_lock.DeployAlreadyRunning) as running:
            deploy_lock.hold(_lock(tmp_path), "participant",
                             now=lambda: STARTED + timedelta(minutes=2, seconds=5))
    finally:
        first.release(0)
    message = str(running.value)
    assert message.startswith(
        "A deploy is already running: the reset's redeploy of the starters, started at "
        f"22:36:44 UTC, 2:05 ago, process {os.getpid()}.")
    assert ("It keeps running when Code Editor is closed, in a terminal a reopened window "
            "does not show.") in message


def test_an_unreadable_holder_still_stops_the_second_deploy(tmp_path) -> None:
    first = deploy_lock.hold(_lock(tmp_path), "full")
    _lock(tmp_path).write_text("not json")
    try:
        with pytest.raises(deploy_lock.DeployAlreadyRunning) as running:
            deploy_lock.hold(_lock(tmp_path), "participant")
    finally:
        first.release(0)
    assert str(running.value).startswith("A deploy is already running. It keeps running")


def test_each_deployment_identity_has_its_own_lock_beside_its_project(tmp_path) -> None:
    live = deploy_lock.lock_path(tmp_path / ".agentcore-project" / "pellier")
    rc = deploy_lock.lock_path(tmp_path / ".agentcore-project" / "pellierrc")
    assert live == tmp_path / ".agentcore-project" / "pellier.deploy.lock"
    assert rc == tmp_path / ".agentcore-project" / "pellierrc.deploy.lock"
    first = deploy_lock.hold(live, "participant")
    try:
        deploy_lock.hold(rc, "participant").release(0)
    finally:
        first.release(0)
    assert json.loads(live.read_text())["exit"] == 0


def test_files_root_creates_belong_to_the_directorys_owner(tmp_path, monkeypatch) -> None:
    # A deploy run as root (an SSM command) must leave files the participant can open.
    owned = []
    monkeypatch.setattr(deploy_lock.os, "geteuid", lambda: 0)
    monkeypatch.setattr(deploy_lock.os, "fchown", lambda fd, uid, gid: owned.append((uid, gid)))
    deploy_lock.hold(_lock(tmp_path), "full").release(0)
    directory = _lock(tmp_path).parent.stat()
    assert owned == [(directory.st_uid, directory.st_gid)] * 2  # the lock and its log


def test_the_log_keeps_whole_lines_and_drops_bar_redraws() -> None:
    terminal, log = io.StringIO(), io.StringIO()
    tee = deploy_lock.Tee(terminal, log)
    tee.write("\r\x1b[K  [2/4] Deploying your changes  ████░░  0:12, usually about 1:15")
    tee.write("\r\x1b[K  [2/4] Deploying your changes  █████░  0:13, usually about 1:15")
    tee.write("\r\x1b[K")
    tee.write("  + 1:07  2/4  Deployed your changes\n")
    tee.write("Pellier is already using AgentCore.\n")
    tee.write("\r\x1b[K  [3/4] Checking  ██░░  0:01\r\x1b[K  + 0:02  3/4  Checked\n")  # one write
    assert log.getvalue() == ("  + 1:07  2/4  Deployed your changes\n"
                              "Pellier is already using AgentCore.\n"
                              "  + 0:02  3/4  Checked\n")
    assert "\r\x1b[K  [3/4] Checking" in terminal.getvalue()  # the terminal still gets the bar


def test_a_reopened_window_is_told_a_deploy_is_running(tmp_path) -> None:
    notice = [sys.executable, str(REPO / "scripts" / "deploy_lock.py"), "--notice",
              "--repo", str(tmp_path)]
    assert subprocess.run(notice, capture_output=True, text=True, check=True).stdout == ""
    holder = Holder(tmp_path)
    try:
        shown = subprocess.run(notice, capture_output=True, text=True, check=True).stdout
    finally:
        holder.end("exit 0")
    assert "A deploy is still running, in a terminal this window does not show." in shown
    assert ('uv run scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode '
            "participant") in shown
    welcome = (REPO / "scripts" / "workshop-banner.sh").read_text()
    assert "scripts/deploy_lock.py --notice" in welcome


def test_the_workshop_reset_asks_first_whether_a_deploy_runs(tmp_path) -> None:
    refuse = [sys.executable, str(REPO / "scripts" / "deploy_lock.py"), "--refuse-if-running",
              "--repo", str(tmp_path)]
    free = subprocess.run(refuse, capture_output=True, text=True)
    assert (free.returncode, free.stdout, free.stderr) == (0, "", "")
    holder = Holder(tmp_path)
    try:
        busy = subprocess.run(refuse, capture_output=True, text=True)
    finally:
        holder.end("exit 0")
    assert busy.returncode == 1
    assert _flat(busy.stderr).startswith("A deploy is already running: a deploy of your changes")
    assert _flat(busy.stderr).endswith("Wait for it to finish, then run the reset again. "
                                       "Nothing was changed.")
    # The whole-workshop reset asks before it stops anything; a starter deploy refused later
    # would quarantine the box.
    script = (REPO / "scripts" / "reset-governed-workshop.sh").read_text()
    steps = script[script.index('echo "Pellier governed reset'):]
    assert steps.index("_assert_no_running_deploy") < steps.index("_quiesce_services")


def test_the_followers_bar_expects_as_many_steps_as_the_running_deploy_has() -> None:
    # Event 12: a four-step deploy that took 0:41 was followed with "usually about 2:17".
    assert deploy_lock.total_steps("Deploying your changes to AgentCore\n") is None
    assert deploy_lock.total_steps("  + 0:00  1/4  Checked your files and the deployed project\n") == 4
    assert deploy_lock.total_steps("  - 2/6  Publishing Gateway schemas (usually about 1:15)\n") == 6
    provisioner = sys.modules.get("deploy_lock_provisioner") or _provisioner()
    four, six = provisioner.participant_typical(4), provisioner.participant_typical(6)
    assert four == 110 and six == 230
    assert provisioner.participant_typical(None) == six


def _provisioner():
    import importlib.util

    spec = importlib.util.spec_from_file_location("deploy_lock_provisioner", PROVISIONER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Event 13: the deploy's last step runs lab3-start.sh, whose lines went straight to the
# terminal, past the log, so a reopened window following the deploy never saw them. A failed
# move then told the follower "the lines above say why" with no lines above.
HOLD_MOVE = f"""
import importlib.util, sys
from pathlib import Path
sys.path.insert(0, {str(REPO / "scripts")!r})
import deploy_lock
spec = importlib.util.spec_from_file_location("provisioner_move", {str(PROVISIONER)!r})
provisioner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provisioner)
repo = Path(sys.argv[1])
lock = deploy_lock.hold(Path(sys.argv[2]), "participant")
lock.tee_output()
print("held", flush=True)
sys.stdin.readline()
lock.release(provisioner.move_onto_agentcore(repo, run_env=repo / "absent-run.env"))
"""

FAILING_MOVE = """#!/bin/bash
echo "Pellier Lab 3 start: managed rail"
echo "  + OK    AGENTCORE_GATEWAY_URL set"
echo "  x FAIL  pellier service not healthy 90s after restart" >&2
exit 1
"""


class MovingHolder:
    """A participant deploy holding the lock that, once told, runs the real move step."""

    def __init__(self, repo: Path) -> None:
        (repo / "scripts").mkdir(exist_ok=True)
        (repo / "scripts" / "lab3-start.sh").write_text(FAILING_MOVE)
        (repo / ".env").write_text("AWS_REGION=us-east-1\n")
        self.process = subprocess.Popen(
            [sys.executable, "-c", HOLD_MOVE, str(repo), str(_lock(repo))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=_bare_env())
        assert self.process.stdout is not None
        assert self.process.stdout.readline().strip() == "held"

    def end(self, line: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()
        self.process.wait(timeout=60)


def test_a_follower_sees_the_move_steps_own_lines(tmp_path) -> None:
    holder = MovingHolder(tmp_path)
    second = _deploy(tmp_path, tmp_path / "receipt.json", holder=holder, then="go")
    assert second.returncode == 1, second.stdout + second.stderr
    assert "Pellier Lab 3 start: managed rail" in second.stdout
    assert "+ OK AGENTCORE_GATEWAY_URL set" in second.stdout
    assert "x FAIL pellier service not healthy 90s after restart" in second.stdout
    assert "the lines above say why" in second.stdout


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


# As scripts/lib/progress.sh does: a bar and its clearing on a terminal only, then lines.
BAR_THEN_LINES = (
    'if [ -t 1 ]; then printf "\\r  Restarting Pellier  ###--  0:07"; printf "\\r\\033[K"; fi; '
    'echo "  + OK    pellier service healthy"; echo "  x FAIL  no turn" >&2; exit 2'
)


def test_on_a_terminal_the_child_still_draws_its_bars_and_the_log_keeps_its_lines(
    tmp_path, monkeypatch,
) -> None:
    terminal, log = _Terminal(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", deploy_lock.Tee(terminal, log))
    completed = deploy_lock.run_logged(["bash", "-c", BAR_THEN_LINES], cwd=str(tmp_path))
    assert completed.returncode == 2
    assert "Restarting Pellier  ###--  0:07" in terminal.getvalue()  # it saw a terminal
    assert log.getvalue() == "  + OK    pellier service healthy\n  x FAIL  no turn\n"


def test_off_a_terminal_the_childs_streams_keep_their_own_way_out(tmp_path, capsys) -> None:
    completed = deploy_lock.run_logged(["bash", "-c", BAR_THEN_LINES], cwd=str(tmp_path))
    assert completed.returncode == 2
    captured = capsys.readouterr()
    assert captured.out == "  + OK    pellier service healthy\n"  # no terminal, so no bar
    assert captured.err == "  x FAIL  no turn\n"
