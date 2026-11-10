"""Three colours in the terminal: green is good, red is bad, orange is waiting or not yet.

Only a state word, a status label or one verdict line is painted, and only at a terminal with
``NO_COLOR`` unset. Painting never changes a column: a box and a wrapped status line lay out
exactly as they do without colour.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import lab4_policy  # noqa: E402
import lab_reset  # noqa: E402
import workshop_check as check  # noqa: E402
import workshop_evidence as evidence  # noqa: E402

GREEN, RED, ORANGE, OFF = "\033[32m", "\033[31m", "\033[38;5;208m", "\033[0m"
SQL_FILES = sorted([*REPO.glob("workshop/*.sql"), *REPO.glob("workshop/starters/*.sql"),
                    *REPO.glob("solutions/*/sql/*.sql")])
UNFINISHED = re.compile(r"(?:check|reconstruction) (not yet|unchecked)'")
GUARD = r'\echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '
STATE_COLOUR = {check.PASSED: GREEN, check.FAILED: RED, check.NOT_YET: ORANGE,
                check.COULD_NOT_CHECK: ORANGE}


@pytest.fixture
def at_a_terminal(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(check, "_is_terminal", lambda stream: True)


@pytest.mark.parametrize("state", check.STATES)
def test_each_state_has_its_colour_at_a_terminal(at_a_terminal, state) -> None:
    assert check.paint(state, state) == f"{STATE_COLOUR[state]}{state}{OFF}"


@pytest.mark.parametrize("state", check.STATES)
def test_no_state_is_coloured_off_a_terminal_or_under_no_colour(monkeypatch, state) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert check.paint(state, state) == state
    monkeypatch.setattr(check, "_is_terminal", lambda stream: True)
    monkeypatch.setenv("NO_COLOR", "1")
    assert check.paint(state, state) == state


@pytest.mark.parametrize("state", check.STATES)
def test_a_box_keeps_its_borders_with_or_without_colour(at_a_terminal, monkeypatch, state):
    finding = check.Finding("1A", "the vector search ranks by meaning", state, "expected",
                            "observed", ["evidence"], "next step")
    coloured = check.render(finding)
    assert f"{STATE_COLOUR[state]}{state}{OFF}" in coloured
    monkeypatch.setenv("NO_COLOR", "1")
    bare = check.render(finding)
    assert "\033" not in bare
    assert check.plain(coloured) == bare
    assert [len(line) for line in check.plain(coloured).splitlines()] == \
        [len(line) for line in bare.splitlines()]
    assert len({len(line) for line in bare.splitlines()}) == 1


@pytest.mark.parametrize("width", [100, 84])
@pytest.mark.parametrize("label, colour", [("+ OK", GREEN), ("x FAIL", RED), ("- WAIT", ORANGE)])
def test_a_status_label_is_painted_and_the_wrapping_is_not_changed(
        monkeypatch, width, label, colour) -> None:
    message = ("restored 3 file regions from the originals (" + ", ".join(
        ["labs/01-retrieve/1A-vector-search.py"] * 3) + ")\n  uv run scripts/lab_run.py x")
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    bare = lab_reset.status(label, message, width)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(check, "_is_terminal", lambda stream: True)
    painted = lab_reset.status(label, message, width)
    assert painted.startswith(f"  {colour}{label}{OFF}")
    assert painted.count("\033[") == 2
    assert check.plain(painted) == bare
    assert all(len(line) <= width for line in bare.splitlines())


def test_a_status_line_is_painted_for_the_stream_it_goes_to(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    terminal = io.StringIO()
    terminal.isatty = lambda: True  # type: ignore[method-assign]
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert lab_reset.status("x FAIL", "bad", stream=terminal) == f"  {RED}x FAIL{OFF}  bad"
    assert lab_reset.status("x FAIL", "bad") == "  x FAIL  bad"


def test_a_right_rule_that_is_not_deployed_yet_is_orange(at_a_terminal) -> None:
    waiting = check.Finding("4A", "t", check.NOT_YET, "e", lab4_policy.NOT_DEPLOYED)
    first = lab4_policy.closing(True, waiting).splitlines()[0]
    assert first == f"{ORANGE}{lab4_policy.NOT_DEPLOYED_CLOSING}{OFF}"
    assert check.plain(first) == lab4_policy.NOT_DEPLOYED_CLOSING


def test_the_next_line_is_never_painted(at_a_terminal) -> None:
    waiting = check.Finding("4A", "t", check.NOT_YET, "e", lab4_policy.NOT_DEPLOYED)
    lines = lab4_policy.closing(True, waiting).splitlines()
    assert all("\033" not in line for line in lines[1:])


@pytest.mark.parametrize("states, colour", [
    ((check.PASSED, check.NOT_YET), ORANGE), ((check.PASSED, check.COULD_NOT_CHECK), ORANGE),
    ((check.PASSED, check.PASSED), GREEN), ((check.PASSED, check.FAILED), RED),
])
def test_the_saved_evidence_file_has_no_escape_code(
        at_a_terminal, monkeypatch, tmp_path, capsys, states, colour) -> None:
    findings = [check.Finding(task, "title", state, "expected", "observed", ["row"])
                for task, state in zip(("1A", "1B"), states)]
    monkeypatch.setattr(evidence, "collect", lambda: findings)
    target = tmp_path / "evidence.txt"
    assert evidence.main(["--save", str(target)]) == 0
    last = capsys.readouterr().out.rstrip().splitlines()[-1]
    assert last.startswith(colour) and last.endswith(OFF)
    saved = target.read_text(encoding="utf-8")
    assert "\033" not in saved
    assert saved.rstrip().endswith(f"{states.count(check.PASSED)} of 2 tasks passed")


def test_every_sql_not_yet_verdict_has_its_orange_guards() -> None:
    """The verdict line is unchanged; the lines around it switch orange on and off, and print
    nothing unless stderr is a terminal and NO_COLOR is unset."""
    seen = 0
    for path in SQL_FILES:
        lines = path.read_text().splitlines()
        for number, line in enumerate(lines):
            if not UNFINISHED.search(line):
                continue
            seen += 1
            assert lines[number - 1].strip() == GUARD + r"'\033[38;5;208m' || true`", path
            assert lines[number + 1].strip() == GUARD + r"'\033[0m' || true`", path
    assert seen == 7
