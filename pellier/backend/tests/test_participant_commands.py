"""Participants type the tools builders use: `uv run` for Python, plain `psql` for SQL.

Bootstrap builds the environment `uv run` uses and the ~/.psqlrc that makes plain `psql -f`
stop at a script's first error. Automation keeps its own explicit flags.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
STAGE2 = (REPO / "scripts/bootstrap-labs.sh").read_text(encoding="utf-8")
BOOTSTRAP = ("scripts/bootstrap-environment.sh", "scripts/bootstrap-labs.sh")
# Automation that runs commands itself, history that records what once ran, and the take-home
# skill, which is written for a reader's own database where our ~/.psqlrc does not exist.
NOT_PARTICIPANT_TEXT = ("takeaway/", "docs/release-readiness/", "docs/superpowers/",
                        ".github/", "scripts/setup/", *BOOTSTRAP,
                        "pellier/backend/tests/test_participant_commands.py")
OLD_FORMS = ("python3 scripts/", "psql -X -v ON_ERROR_STOP=1 -P pager=off")


def _participant_text() -> list[str]:
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.split()
    return [name for name in tracked if not name.startswith(NOT_PARTICIPANT_TEXT)
            and (REPO / name).is_file() and not (REPO / name).is_symlink()]


def test_participant_text_teaches_uv_run_and_plain_psql() -> None:
    stale = []
    for name in _participant_text():
        try:
            text = (REPO / name).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        stale += [f"{name}: {form}" for form in OLD_FORMS if form in text]
    assert stale == []


def test_bootstrap_builds_the_environment_uv_run_uses() -> None:
    assert 'UV_VERSION="0.11.26"' in STAGE2
    assert "https://astral.sh/uv/$UV_VERSION/install.sh" in STAGE2
    assert "venv --clear --quiet --python /usr/bin/python3.14 .venv" in STAGE2
    assert "pip sync --quiet --require-hashes --python .venv/bin/python" in STAGE2
    assert "pellier/backend/requirements.lock" in STAGE2
    assert "'$UV_BIN' run python -c '$VENV_PROBE' '$REPO_PATH/.venv'" in STAGE2


def test_bootstrap_and_readiness_pin_the_same_uv() -> None:
    start = (REPO / "scripts/workshop-start.sh").read_text(encoding="utf-8")
    assert 'UV_VERSION="0.11.26"' in STAGE2 and 'UV_VERSION="0.11.26"' in start


def test_bootstrap_writes_a_psqlrc_that_stops_on_error_without_a_pager() -> None:
    assert ("printf '%s\\n' '\\set QUIET 1' '\\pset pager off' '\\set ON_ERROR_STOP on' "
            "'\\unset QUIET'") in STAGE2
    assert '"$PGPASS_DIR/.psqlrc"' in STAGE2


@pytest.mark.parametrize("name", BOOTSTRAP)
def test_bootstrap_never_takes_uv_offline(name: str) -> None:
    """The Lab 3 and 4 deploy packages its Lambda with `uv pip install --target` from PyPI."""
    text = (REPO / name).read_text(encoding="utf-8")
    assert "UV_OFFLINE" not in text and "UV_PYTHON_DOWNLOADS" not in text


# ---------------------------------------------------------------------------
# The real bootstrap and readiness code, run against a stub uv on a fake box.
# ---------------------------------------------------------------------------

UV_STUB = """#!/bin/bash
# --version prints UV_STUB_VERSION (or fails); `venv` fails while the counter in
# UV_STUB_VENV_FAILS is above zero; `run python ...` runs the repo's .venv python,
# or this test's interpreter when the .venv has none, as a misconfigured uv would.
case "$1" in
  --version) [ -n "${UV_STUB_VERSION:-}" ] || exit 1; echo "$UV_STUB_VERSION"; exit 0 ;;
  venv)
    left="$(cat "$UV_STUB_VENV_FAILS" 2>/dev/null || echo 0)"
    if [ "$left" -gt 0 ]; then echo $((left - 1)) > "$UV_STUB_VENV_FAILS"; exit 1; fi
    exit 0 ;;
  pip) exit 0 ;;
  run)
    shift; [ "$1" = python ] && shift
    if [ -x "$PWD/.venv/bin/python" ]; then exec "$PWD/.venv/bin/python" "$@"; fi
    exec "$UV_STUB_FALLBACK_PYTHON" "$@" ;;
esac
exit 2
"""


def _box(tmp_path: Path, *, venv_is_this_python: bool) -> dict[str, str]:
    """A repo whose .venv is this test's Python environment (it has the lab packages), or an
    empty directory; a stub uv; and stub curl and python3.14 so nothing reaches the network."""
    repo, bin_dir = tmp_path / "repo", tmp_path / "bin"
    repo.mkdir()
    bin_dir.mkdir()
    if venv_is_this_python:
        (repo / ".venv").symlink_to(Path(sys.prefix).resolve())
    else:
        (repo / ".venv").mkdir()
    for name, body in (("uv", UV_STUB), ("curl", "#!/bin/bash\nexit 1\n"),
                       ("python3.14", "#!/bin/bash\nexit 1\n")):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}", "REPO": str(repo),
            "UV_BIN": str(bin_dir / "uv"), "UV_STUB_FALLBACK_PYTHON": sys.executable,
            "UV_STUB_VENV_FAILS": str(tmp_path / "venv-fails"),
            "UV_STUB_VERSION": "uv 0.11.26 (stub 2026-06-30 x86_64-unknown-linux-gnu)"}


def _slice(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end, text.index(start))]


def _run_bootstrap_step(box: dict[str, str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    script = "\n".join((
        "set -euo pipefail",
        'GREEN=""; YELLOW=""; RED=""; NC=""',
        'sudo() { if [ "$1" = "-u" ]; then shift 2; fi; "$@"; }',
        _slice(STAGE2, "log() {", "\n\n"),
        _slice(STAGE2, 'PELLIER_STATE_DIR="/var/lib/pellier"', 'mkdir -p "$PELLIER_STATE_DIR"'),
        _slice(STAGE2, "# STEP 7: INSTALL UV AND THE PARTICIPANT ENVIRONMENT", "# STEP 8:"),
    ))
    env = {**os.environ, **box, "CODE_EDITOR_USER": "participant", "REPO_PATH": box["REPO"],
           "PELLIER_UV_BIN": box["UV_BIN"], "PELLIER_VENV_LOG": str(tmp_path / "venv.log"),
           "PELLIER_PROVISION_STATE_FILE": str(tmp_path / "provision-state"),
           "PELLIER_VENV_RETRY_DELAY": "0"}
    return subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True,
                          check=False)


def _state(tmp_path: Path) -> str:
    path = tmp_path / "provision-state"
    return path.read_text().strip() if path.exists() else ""


def test_bootstrap_succeeds_when_uv_run_uses_the_participant_environment(tmp_path: Path) -> None:
    result = _run_bootstrap_step(_box(tmp_path, venv_is_this_python=True), tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Participant environment ready" in result.stdout
    assert _state(tmp_path) == ""


def test_bootstrap_retries_one_failed_build(tmp_path: Path) -> None:
    box = _box(tmp_path, venv_is_this_python=True)
    (tmp_path / "venv-fails").write_text("1")
    result = _run_bootstrap_step(box, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "retrying once" in result.stdout
    assert _state(tmp_path) == ""


def test_bootstrap_fails_when_the_environment_never_builds(tmp_path: Path) -> None:
    box = _box(tmp_path, venv_is_this_python=True)
    (tmp_path / "venv-fails").write_text("2")
    result = _run_bootstrap_step(box, tmp_path)
    assert result.returncode == 1
    assert "no participant uv run command can work" in result.stdout
    assert _state(tmp_path) == "FAILED"


def test_bootstrap_fails_when_uv_run_uses_another_environment(tmp_path: Path) -> None:
    result = _run_bootstrap_step(_box(tmp_path, venv_is_this_python=False), tmp_path)
    assert result.returncode == 1
    assert _state(tmp_path) == "FAILED"


def test_bootstrap_fails_without_the_pinned_uv(tmp_path: Path) -> None:
    box = {**_box(tmp_path, venv_is_this_python=True), "UV_STUB_VERSION": "uv 0.11.20 (stub)"}
    result = _run_bootstrap_step(box, tmp_path)
    assert result.returncode == 1
    assert "uv 0.11.26 did not install" in result.stdout
    assert _state(tmp_path) == "FAILED"


def _run_readiness_step(box: dict[str, str]) -> str:
    start = (REPO / "scripts/workshop-start.sh").read_text(encoding="utf-8")
    script = "\n".join(("set -uo pipefail", 'pass() { echo "PASS $1"; }',
                         'warn() { echo "WARN $1"; }',
                         _slice(start, "# --- 3. the environment every lab command runs in",
                                "# --- 4.")))
    result = subprocess.run(["bash", "-c", script],
                            env={**os.environ, **box}, text=True, capture_output=True,
                            check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_readiness_passes_when_uv_run_uses_the_participant_environment(tmp_path: Path) -> None:
    assert "PASS uv run is ready: uv 0.11.26" in _run_readiness_step(
        _box(tmp_path, venv_is_this_python=True))


@pytest.mark.parametrize("problem", ["uv fails", "wrong uv", "another environment"])
def test_readiness_warns_the_facilitator_when_uv_run_cannot_work(tmp_path: Path,
                                                                  problem: str) -> None:
    box = _box(tmp_path, venv_is_this_python=problem != "another environment")
    if problem == "uv fails":
        box["UV_STUB_VERSION"] = ""
    if problem == "wrong uv":
        box["UV_STUB_VERSION"] = "uv 0.11.20 (stub)"
    assert "WARN Facilitator: uv run is not ready" in _run_readiness_step(box)
