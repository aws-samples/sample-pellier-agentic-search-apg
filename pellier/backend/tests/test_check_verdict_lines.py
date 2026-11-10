"""A check's last lines: the verdict in colour on a terminal, then what to do next.

Green and red are for a person at a terminal. A pipe, a file and ``NO_COLOR`` get the same
words with no escape codes, so nothing that reads the output has to strip them. After a pass
the check names the next step, and every command it names exists in the repository.
"""

from __future__ import annotations

import io
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import lab_run  # noqa: E402
import workshop_check as check  # noqa: E402

GREEN, RED, OFF = "\033[32m", "\033[31m", "\033[0m"
SQL_FILES = sorted([*REPO.glob("workshop/*.sql"), *REPO.glob("workshop/starters/*.sql"),
                    *REPO.glob("solutions/*/sql/*.sql")])
VERDICT = re.compile(r"(?:check|reconstruction) (passed|failed)'")
COMMAND = re.compile(r"(?:uv run (scripts/\S+\.py)|psql -f (\S+\.sql))")


@pytest.fixture
def at_a_terminal(monkeypatch) -> None:
    """pytest replaces sys.stdout for each test phase, so the terminal test itself is patched."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(check, "_is_terminal", lambda stream: True)


def test_colour_follows_the_stream_it_is_asked_about(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    terminal = io.StringIO()
    terminal.isatty = lambda: True  # type: ignore[method-assign]
    assert check.colour_enabled(terminal) is True
    assert check.colour_enabled(io.StringIO()) is False


def test_a_verdict_is_plain_when_the_output_is_not_a_terminal(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert check.closing("Lab 1A check", True) == "Lab 1A check passed"
    assert check.closing("Lab 1A check", False) == "Lab 1A check failed"


def test_a_pass_is_green_and_a_failure_red_at_a_terminal(at_a_terminal) -> None:
    assert check.closing("Lab 1A check", True) == f"{GREEN}Lab 1A check passed{OFF}"
    assert check.closing("Lab 1A check", False) == f"{RED}Lab 1A check failed{OFF}"


@pytest.mark.parametrize(("name", "value"), [("NO_COLOR", "1"), ("TERM", "dumb")])
def test_a_terminal_that_asks_for_no_colour_gets_none(at_a_terminal, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    assert check.closing("Lab 1A check", False) == "Lab 1A check failed"


def test_only_passed_and_failed_take_a_colour(at_a_terminal) -> None:
    assert check.paint("NOT YET", check.NOT_YET) == "NOT YET"
    assert check.paint("COULD NOT CHECK", check.COULD_NOT_CHECK) == "COULD NOT CHECK"


@pytest.mark.parametrize("state", [check.PASSED, check.FAILED])
def test_the_colour_never_changes_the_box(at_a_terminal, monkeypatch, state) -> None:
    finding = check.Finding("1A", "the vector search ranks by meaning", state, "expected",
                            "observed", ["evidence"])
    coloured = check.render(finding)
    monkeypatch.setenv("NO_COLOR", "1")
    plain = check.render(finding)
    assert coloured != plain
    assert re.sub(r"\033\[\d+m", "", coloured) == plain
    assert coloured.count("\033[") == 2


def test_a_pass_says_what_to_do_next_and_a_failure_does_not() -> None:
    passed = check.closing("Lab 1A check", True, "1A").splitlines()
    assert passed[:2] == ["Lab 1A check passed", ""]
    assert passed[2].startswith("Next: Task 1B.")
    assert passed[3] == "      uv run scripts/lab_run.py send --lab 1 --task 1B"
    assert check.closing("Lab 1A check", False, "1A") == "Lab 1A check failed"


def test_every_task_has_a_next_step() -> None:
    assert sorted(check.NEXT_AFTER_PASS) == sorted(lab_run.TASKS)


def _commands(lines) -> list:
    return [found for line in lines for found in COMMAND.findall(line)]


def test_every_command_a_next_line_names_exists() -> None:
    lines = [line for steps in check.NEXT_AFTER_PASS.values() for line in steps]
    lines += [line for steps in lab_run.NEXT_AFTER_SEND.values() for line in steps]
    lines += [line for steps in lab_run.NEXT_AFTER_LAB_SEND.values() for line in steps]
    lines += [line for path in SQL_FILES for line in path.read_text().splitlines()
              if line.lstrip().startswith(r"\echo '") and ("uv run" in line or "Next:" in line)]
    named = _commands(lines)
    assert len(named) > 20
    for script, sql in named:
        assert (REPO / (script or sql)).exists(), script or sql


@pytest.mark.parametrize("task", sorted(lab_run.SEND_REGIONS))
def test_a_send_names_the_fault_before_the_fix_and_the_check_after(task, tmp_path) -> None:
    source, label, starter = lab_run.SEND_REGIONS[task]
    assert check.region_state(REPO / source, label, REPO / starter) == check.STARTER
    before = lab_run.next_after_send(int(task[0]), task)
    assert before == lab_run.NEXT_AFTER_SEND[(task, True)]
    for name in (source, starter):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, tmp_path / name)
    edited = (tmp_path / source).read_text().replace(
        f"WORKSHOP - {label}: START ===", f"WORKSHOP - {label}: START ===\n-- my fix\n# my fix")
    (tmp_path / source).write_text(edited)
    after = lab_run.next_after_send(int(task[0]), task, repo=tmp_path)
    assert after == lab_run.NEXT_AFTER_SEND[(task, False)] != before


def test_a_whole_lab_send_names_its_check_only_where_one_follows() -> None:
    assert lab_run.next_after_send(3, None)[-1] == "uv run scripts/lab3_check.py --task 3B"
    assert lab_run.next_after_send(1, None) == []


def test_every_sql_verdict_is_coloured_only_at_a_terminal() -> None:
    """The verdict line itself stays as it was; the lines around it switch the colour on and
    off, and print nothing unless stderr is a terminal and NO_COLOR is unset."""
    seen = 0
    for path in SQL_FILES:
        lines = path.read_text().splitlines()
        for number, line in enumerate(lines):
            found = VERDICT.search(line)
            if not found or "RAISE EXCEPTION" in line:
                continue
            seen += 1
            code = "32" if found.group(1) == "passed" else "31"
            guard = r'\echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '
            assert lines[number - 1].strip() == guard + rf"'\033[{code}m' || true`", path.name
            assert lines[number + 1].strip() == guard + r"'\033[0m' || true`", path.name
    assert seen >= 30

def test_a_catch_up_asks_its_commands_for_no_next_block(monkeypatch) -> None:
    """finish and fast-track run the next step themselves, so a Next block would mislead."""
    monkeypatch.delenv(check.NO_NEXT_ENV, raising=False)
    with lab_run._no_next_lines():
        assert check.closing("Lab 1A check", True, "1A") == "Lab 1A check passed"
    assert "Next: Task 1B." in check.closing("Lab 1A check", True, "1A")
    assert "quiet_next=1" in lab_run._executable(["psql", "-f", "x.sql"])


def test_every_sql_next_block_stays_quiet_inside_a_catch_up() -> None:
    blocks = 0
    for path in SQL_FILES:
        lines = path.read_text().splitlines()
        for number, line in enumerate(lines):
            if "\\echo 'Next: " in line:
                blocks += 1
                assert lines[number - 3].strip() == r"\if :{?quiet_next}", path.name
                assert lines[number - 2].strip() == r"\else", path.name
    assert blocks == 10


def _managed(state: str, observed: str) -> check.Finding:
    return check.Finding("4A", "the Gateway enforces your rule", state, "expected", observed)


def test_a_right_rule_that_is_not_deployed_yet_is_not_called_a_failure(at_a_terminal) -> None:
    """Task 4A runs its check between the fix and the deploy. Nothing is wrong at that point,
    so the closing line is plain, says what is still to do and gives the deploy command."""
    import lab4_policy

    waiting = _managed(check.NOT_YET, lab4_policy.NOT_DEPLOYED)
    lines = lab4_policy.closing(True, waiting).splitlines()
    assert lines[0] == lab4_policy.NOT_DEPLOYED_CLOSING
    assert "failed" not in lines[0] and "\033[" not in lines[0]
    assert lines[1] == "" and lines[2].startswith("Next: deploy your rule.")
    assert lines[3].strip() == lab_run.DEPLOY


def test_every_other_4a_outcome_keeps_its_pass_or_fail_line(at_a_terminal) -> None:
    import lab4_policy

    waiting = _managed(check.NOT_YET, lab4_policy.NOT_DEPLOYED)
    wrong_rule = lab4_policy.closing(False, waiting)
    deployed_wrong = lab4_policy.closing(
        True, _managed(check.NOT_YET, "your rule is deployed but did not pass Part 1"))
    passed = lab4_policy.closing(True, _managed(check.PASSED, "Cedar denied it"))
    assert wrong_rule == deployed_wrong == f"{RED}Lab 4A check failed{OFF}"
    assert passed.splitlines()[0] == f"{GREEN}Lab 4A check passed{OFF}"
