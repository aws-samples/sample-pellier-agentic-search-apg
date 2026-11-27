"""scripts/recheck_model_access.sh: a late Opus 5.5 is picked up, and a box is never made worse.

A new account's Bedrock access can still be switching on when bootstrap's first preflight runs,
and that run lets Sonnet 5.5 stand in for Opus 5.5 by writing BEDROCK_OPUS_MODEL. Bootstrap runs
this script again just before its health gate, and a facilitator runs it on a box whose
readiness says the Catalog and Support agents are not on Opus 5.5 (owner, 2026-11-25).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "recheck_model_access.sh"
BOOTSTRAP = REPO / "scripts" / "bootstrap-labs.sh"
BASH = shutil.which("bash")
CURL = shutil.which("curl")
OPUS = "global.anthropic.claude-opus-5-5"
SONNET = "global.anthropic.claude-sonnet-5-5"

# The stand-in for python3.14: it answers the Opus ID question, and as check_model_access.py it
# writes what the test says the preflight resolved, then exits with the test's status.
PYTHON_STUB = """#!/bin/sh
echo "$@" >> "$CALLS"
case "$*" in
  *check_model_access.py*--write-env*)
    prev=""; for arg in "$@"; do
      [ "$prev" = "--write-env" ] && target="$arg"; prev="$arg"
    done
    grep -v '^BEDROCK_OPUS_MODEL=\\|^BEDROCK_MODEL_ACCESS_READY=' "$target" > "$target.next"
    if [ "$PREFLIGHT_EXIT" = "0" ]; then ready=true; else ready=false; fi
    printf 'BEDROCK_MODEL_ACCESS_READY=%s\\nBEDROCK_OPUS_MODEL=%s\\n' "$ready" "$PREFLIGHT_OPUS" \\
      >> "$target.next"
    mv "$target.next" "$target"
    echo "Editorial agents: preflight says $PREFLIGHT_OPUS"
    exit "$PREFLIGHT_EXIT" ;;
  *) echo "OPUS_ID" ;;
esac
""".replace("OPUS_ID", OPUS)


class _Box:
    """A stand-in box: the repository, its .env, and stubs for Python, systemctl and sudo."""

    def _box(self, tmp_path: Path, env_text: str, *, linked: bool = False) -> Path:
        repo = tmp_path / "repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "pellier" / "backend").mkdir(parents=True)
        (repo / "scripts" / "check_model_access.py").write_text("# stand-in\n")
        if linked:  # a box keeps backend/.env as a link to the root .env
            (repo / ".env").write_text(env_text)
            (repo / "pellier" / "backend" / ".env").symlink_to(repo / ".env")
        else:
            (repo / "pellier" / "backend" / ".env").write_text(env_text)
        return repo

    def _run(self, tmp_path: Path, repo: Path, *, preflight_opus: str = OPUS,
             preflight_exit: int = 0, healthy: Optional[bool] = True, loaded_opus: bool = True,
             as_root: bool = False) -> subprocess.CompletedProcess:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        calls = tmp_path / "calls.log"
        python = bin_dir / "python3.14"
        python.write_text(PYTHON_STUB)
        python.chmod(0o755)
        if as_root:  # bootstrap runs it as the participant, a facilitator over SSM may be root
            (bin_dir / "id").write_text("#!/bin/sh\necho 0\n")
            (bin_dir / "id").chmod(0o755)
        for tool in ("systemctl", "sudo"):
            stub = bin_dir / tool
            stub.write_text(f'#!/bin/sh\necho "{tool} $*" >> "$CALLS"\n'
                            'exit "${RESTART_EXIT:-0}"\n')
            stub.chmod(0o755)
        health = tmp_path / "health.json"
        if healthy:
            health.write_text('{"status":"healthy","editorial_model_is_default":'
                              + ('true' if loaded_opus else 'false') + '}')
        else:
            health.unlink(missing_ok=True)
        env = {
            "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
            "HOME": str(tmp_path),
            "PELLIER_REPO": str(repo),
            "PELLIER_PYTHON": str(python),
            "HEALTH_URL": health.as_uri(),
            "HEALTH_TRIES": "2",
            "HEALTH_PAUSE": "0",
            "CALLS": str(calls),
            "PREFLIGHT_OPUS": preflight_opus,
            "PREFLIGHT_EXIT": str(preflight_exit),
        }
        return subprocess.run([BASH, str(SCRIPT)], capture_output=True, text=True, timeout=60,
                              env=env)

    @staticmethod
    def _calls(tmp_path: Path) -> str:
        log = tmp_path / "calls.log"
        return log.read_text() if log.exists() else ""


@pytest.mark.skipif(BASH is None or CURL is None, reason="bash and curl required")
class TestRecheck(_Box):

    def test_a_box_already_on_opus_is_left_alone(self, tmp_path: Path) -> None:
        repo = self._box(tmp_path, f"BEDROCK_MODEL_ACCESS_READY=true\nBEDROCK_OPUS_MODEL={OPUS}\n")
        result = self._run(tmp_path, repo)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--write-env" not in self._calls(tmp_path), "no second preflight was needed"
        assert "restart" not in self._calls(tmp_path)
        assert "already use Claude Opus 5.5" in result.stdout

    def test_a_late_opus_moves_the_agents_back_and_restarts_pellier(self, tmp_path: Path) -> None:
        repo = self._box(tmp_path, f"DB_HOST=h\nBEDROCK_MODEL_ACCESS_READY=true\n"
                                   f"BEDROCK_OPUS_MODEL={SONNET}\n")
        result = self._run(tmp_path, repo)
        assert result.returncode == 0, result.stdout + result.stderr
        env_text = (repo / "pellier" / "backend" / ".env").read_text()
        assert f"BEDROCK_OPUS_MODEL={OPUS}" in env_text and "DB_HOST=h" in env_text
        assert re.search(r"(sudo -n )?systemctl restart pellier", self._calls(tmp_path))
        assert "Pellier answers /api/health again" in result.stdout

    def test_a_failed_second_preflight_changes_nothing(self, tmp_path: Path) -> None:
        before = f"BEDROCK_MODEL_ACCESS_READY=true\nBEDROCK_OPUS_MODEL={SONNET}\n"
        repo = self._box(tmp_path, before)
        result = self._run(tmp_path, repo, preflight_exit=1)
        assert result.returncode == 1
        assert (repo / "pellier" / "backend" / ".env").read_text() == before, \
            "a failed re-run must not mark a working box not ready"
        assert "restart" not in self._calls(tmp_path)
        assert "keeps its current model settings" in result.stdout

    def test_opus_still_silent_keeps_sonnet_and_says_so(self, tmp_path: Path) -> None:
        repo = self._box(tmp_path, f"BEDROCK_MODEL_ACCESS_READY=true\n"
                                   f"BEDROCK_OPUS_MODEL={SONNET}\n")
        result = self._run(tmp_path, repo, preflight_opus=SONNET)
        assert result.returncode == 3, result.stdout + result.stderr
        assert "restart" not in self._calls(tmp_path)
        assert "Opus 5.5 still does not answer" in result.stdout

    def test_the_root_env_behind_the_link_is_updated_and_the_link_kept(
        self, tmp_path: Path,
    ) -> None:
        repo = self._box(tmp_path, f"BEDROCK_MODEL_ACCESS_READY=true\n"
                                   f"BEDROCK_OPUS_MODEL={SONNET}\n", linked=True)
        result = self._run(tmp_path, repo)
        assert result.returncode == 0, result.stdout + result.stderr
        link = repo / "pellier" / "backend" / ".env"
        assert link.is_symlink(), "an atomic replace of the link broke the 2026-11-01 event"
        assert f"BEDROCK_OPUS_MODEL={OPUS}" in (repo / ".env").read_text()

    def test_pellier_that_does_not_come_back_is_a_failure(self, tmp_path: Path) -> None:
        repo = self._box(tmp_path, f"BEDROCK_MODEL_ACCESS_READY=true\n"
                                   f"BEDROCK_OPUS_MODEL={SONNET}\n")
        result = self._run(tmp_path, repo, healthy=False)
        assert result.returncode == 1
        assert "did not answer /api/health" in result.stdout

    def test_retry_verifies_the_running_service_after_saving_the_settings(self, tmp_path: Path) -> None:
        repo = self._box(tmp_path, f"BEDROCK_MODEL_ACCESS_READY=true\nBEDROCK_OPUS_MODEL={SONNET}\n")
        assert self._run(tmp_path, repo, healthy=False).returncode == 1
        # The file now says Opus. Neither a down backend nor a healthy one still
        # serving Sonnet confirms that the restart loaded the change.
        assert self._run(tmp_path, repo, healthy=False).returncode == 1
        assert self._run(tmp_path, repo, loaded_opus=False).returncode == 1
        calls = self._calls(tmp_path)
        assert calls.count("systemctl restart pellier") == 3
        assert self._run(tmp_path, repo).returncode == 0
        assert self._calls(tmp_path).count("systemctl restart pellier") == 3


def test_bootstrap_rechecks_the_models_after_the_managed_setup_and_before_the_gate() -> None:
    bootstrap = BOOTSTRAP.read_text()
    recheck = bootstrap.index("scripts/recheck_model_access.sh")
    gate = bootstrap.index("STEP 19: POST-BOOT HEALTH GATE")
    assert bootstrap.index("STEP 18d:") < recheck < gate
    first = bootstrap.index("python3.14 scripts/check_model_access.py --write-env")
    assert first < recheck, "the second run follows bootstrap's first preflight"


@pytest.mark.skipif(BASH is None or CURL is None, reason="bash and curl required")
class TestRecheckEdges(_Box):
    """The reviewer's cases (2026-11-25): settings other than Opus, a failed write, root."""

    def test_opus_with_a_failed_first_preflight_is_rechecked_and_reloaded(
        self, tmp_path: Path,
    ) -> None:
        repo = self._box(tmp_path, f"BEDROCK_MODEL_ACCESS_READY=false\n"
                                   f"BEDROCK_OPUS_MODEL={OPUS}\n")
        result = self._run(tmp_path, repo)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--write-env" in self._calls(tmp_path)
        assert "BEDROCK_MODEL_ACCESS_READY=true" in (repo / "pellier/backend/.env").read_text()
        assert "systemctl restart pellier" in self._calls(tmp_path), \
            "a changed setting other than Opus still has to reach the running app"

    def test_a_write_that_fails_leaves_pellier_alone_and_fails(self, tmp_path: Path) -> None:
        repo = self._box(tmp_path, f"BEDROCK_MODEL_ACCESS_READY=true\n"
                                   f"BEDROCK_OPUS_MODEL={SONNET}\n")
        env_file = repo / "pellier" / "backend" / ".env"
        env_file.chmod(0o444)
        try:
            result = self._run(tmp_path, repo)
        finally:
            env_file.chmod(0o644)
        if os.geteuid() == 0:
            pytest.skip("root writes a read-only file")
        assert result.returncode == 1
        assert "Could not write" in result.stdout
        assert "restart" not in self._calls(tmp_path)

    def test_as_root_it_restarts_with_systemctl_itself(self, tmp_path: Path) -> None:
        repo = self._box(tmp_path, f"BEDROCK_MODEL_ACCESS_READY=true\n"
                                   f"BEDROCK_OPUS_MODEL={SONNET}\n")
        result = self._run(tmp_path, repo, as_root=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "systemctl restart pellier" in self._calls(tmp_path)
        assert "sudo" not in self._calls(tmp_path)


def _step_18e(log_file: Path) -> str:
    """Bootstrap's STEP 18e block exactly as it ships, with its log path made writable."""
    bootstrap = BOOTSTRAP.read_text()
    start = bootstrap.index('log "Checking Bedrock model access again before the health gate..."')
    end = bootstrap.index("# SUMMARY", start)
    block = bootstrap[start:end].rsplit("# ====", 1)[0]
    return block.replace("/var/log/model-access-preflight.log", str(log_file))


@pytest.mark.skipif(BASH is None, reason="bash required")
@pytest.mark.parametrize("status, expected", [
    (0, "LOG ✅ Bedrock model access: the Catalog and Support agents use Claude Opus 5.5"),
    (3, "WARN Claude Opus 5.5 still does not answer; the readiness record will say so"),
    (1, "WARN Second model-access preflight failed; see "),
])
def test_bootstrap_step_18e_reports_each_outcome_and_never_stops_bootstrap(
    tmp_path: Path, status: int, expected: str,
) -> None:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "recheck_model_access.sh").write_text(
        f'#!/usr/bin/env bash\necho "recheck as $(whoami) in $PELLIER_REPO"\nexit {status}\n')
    log_file = tmp_path / "preflight.log"
    script = (
        "set -euo pipefail\n"
        'log() { echo "LOG $1"; }\nwarn() { echo "WARN $1"; }\n'
        'sudo() { shift 2; "$@"; }\n'  # sudo -u USER CMD...: run CMD as this test's user
        f'REPO_PATH="{repo}"\nCODE_EDITOR_USER=participant\nAWS_REGION=us-east-1\n'
        + _step_18e(log_file) +
        'echo "BOOTSTRAP CONTINUES"\n'
    )
    result = subprocess.run([BASH, "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert expected in result.stdout
    assert "BOOTSTRAP CONTINUES" in result.stdout
    assert f"in {repo}" in log_file.read_text(), "the run is appended to the preflight log"
