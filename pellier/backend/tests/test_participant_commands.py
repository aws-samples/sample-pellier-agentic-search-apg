"""Participants type the tools builders use: `uv run` for Python, plain `psql` for SQL.

Bootstrap builds the environment `uv run` uses and the ~/.psqlrc that makes plain `psql -f`
stop at a script's first error. Automation keeps its own explicit flags.
"""
from __future__ import annotations

import subprocess
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
    assert '.venv/bin/python" \\\n        -c "import boto3, fastapi, psycopg, strands, uvicorn"' in STAGE2


def test_bootstrap_writes_a_psqlrc_that_stops_on_error_without_a_pager() -> None:
    assert ("printf '%s\\n' '\\set QUIET 1' '\\pset pager off' '\\set ON_ERROR_STOP on' "
            "'\\unset QUIET'") in STAGE2
    assert '"$PGPASS_DIR/.psqlrc"' in STAGE2


@pytest.mark.parametrize("name", BOOTSTRAP)
def test_bootstrap_never_takes_uv_offline(name: str) -> None:
    """The Lab 3 and 4 deploy packages its Lambda with `uv pip install --target` from PyPI."""
    text = (REPO / name).read_text(encoding="utf-8")
    assert "UV_OFFLINE" not in text and "UV_PYTHON_DOWNLOADS" not in text


def test_readiness_reports_a_box_where_uv_run_cannot_work() -> None:
    start = (REPO / "scripts/workshop-start.sh").read_text(encoding="utf-8")
    assert '"$REPO/.venv/bin/python" -c "import boto3, psycopg, strands"' in start
    assert 'warn "Facilitator: uv run is not ready' in start
