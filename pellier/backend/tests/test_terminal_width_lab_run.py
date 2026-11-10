"""What ``lab_run.py`` and ``lab_reset.py`` print must fit a laptop's terminal.

Code Editor on a 1440-pixel laptop gives about 100 columns. A line longer than the terminal
breaks wherever the edge falls, mid-word. These tests render the participant's output at 100
and 84 columns and hold every line to the terminal's width, keep every word, and keep a command
on one line so it copies whole.
"""
from __future__ import annotations

import importlib
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

check = importlib.import_module("workshop_check")
lab_reset = importlib.import_module("lab_reset")
lab_run = importlib.import_module("lab_run")

CREDIT = ("1 store credit exists. A credit, the review a person approved and its tool_audit row "
          "are the evidence this lab produces, and none of them can be undone from a lab. "
          "Nothing was changed. To start Lab 4 over from a clean ledger reset the whole "
          f"workshop: {lab_reset.FULL_RESET}")
SENTENCE = ("review 12 already credited Jessica; nothing is investigated, approved or "
            "written again, because the same key finds the first credit and writes nothing")


@pytest.fixture(params=[100, 84])
def columns(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> int:
    """The terminal's columns; a script prints at most one fewer, so the cursor has room."""
    monkeypatch.setenv("COLUMNS", str(request.param))
    return request.param - 1


def words(text: str) -> List[str]:
    return text.split()


def assert_fits(text: str, width: int) -> None:
    for line in text.splitlines():
        assert len(line) <= width, f"{len(line)} columns: {line!r}"


def printed(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    return captured.out + captured.err


def test_ok_and_wait_lines_break_at_words_under_their_text(
        capsys: pytest.CaptureFixture[str], columns: int) -> None:
    lab_run.ok(SENTENCE)
    lab_run.wait(SENTENCE)
    out = printed(capsys)
    assert_fits(out, columns)
    first, second = out.split("  - WAIT  ")
    assert first.startswith("  + OK    review 12")
    assert all(line.startswith(" " * 10) for line in first.splitlines()[1:])
    assert words(first.replace("+ OK", "", 1)) == words(SENTENCE)
    assert words(second) == words(SENTENCE)


def test_the_credit_reset_refusal_wraps_and_keeps_its_command_whole(
        capsys: pytest.CaptureFixture[str], columns: int) -> None:
    lab_run.fail(CREDIT)
    out = printed(capsys)
    assert_fits(out, columns)
    assert words(out.replace("x FAIL", "", 1)) == words(CREDIT)
    assert any(line.endswith(lab_reset.FULL_RESET) for line in out.splitlines())


@pytest.mark.parametrize("lab", [3, 4])
def test_a_rail_refusal_keeps_each_command_on_its_own_whole_line(
        capsys: pytest.CaptureFixture[str], columns: int, lab: int) -> None:
    message = lab_run._rail_problem(lab, "in_process" if lab == 4 else "agentcore", {})
    lab_run.fail(message)
    out = printed(capsys)
    assert_fits(out.replace(lab_run.DEPLOY, ""), columns)
    assert any(line.strip() in (lab_run.DEPLOY, "bash scripts/lab3-start.sh theo")
               for line in out.splitlines())
    assert words(out.replace("x FAIL", "", 1)) == words(message)


def test_a_failure_line_is_one_line_when_it_fits(capsys: pytest.CaptureFixture[str]) -> None:
    lab_run.fail("short problem")
    assert printed(capsys) == "  x FAIL  short problem\n"


def test_the_next_sentence_wraps_and_each_command_stays_whole(
        capsys: pytest.CaptureFixture[str], columns: int) -> None:
    sentence = ("as Nadia in the Operator, investigate Jessica's case, approve the proposed "
                "credit and select Execute.")
    lab_run.print_next(sentence)
    out = printed(capsys)
    assert_fits(out, columns)
    assert words(out.replace("Next:", "")) == words(sentence)
    lab_run.print_next("uv run scripts/lab3_check.py --task 3A", lab_run.DEPLOY)
    out = printed(capsys)
    assert "  Next: uv run scripts/lab3_check.py --task 3A\n" in out
    assert f"        then {lab_run.DEPLOY}\n" in out


def test_lab_four_closing_separates_nadias_sign_in_from_the_next_step(
        capsys: pytest.CaptureFixture[str], columns: int, tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    credentials = tmp_path / "credentials.txt"
    credentials.write_text("username: nadia\npassword: " + "k" * 20 + "\n", encoding="utf-8")
    monkeypatch.setattr(lab_run, "CREDENTIALS_FILE", credentials)
    lab_run.print_nadia_next()
    out = printed(capsys)
    assert_fits(out, columns)
    lines = out.splitlines()
    assert lines[1].startswith("  Next: as Nadia in the Operator")
    blank = lines.index("", 2)
    assert lines[blank + 1].strip().startswith("Nadia's sign-in for the Operator: username nadia")
    assert "password " + "k" * 20 in out


RANKING: Dict[str, Any] = {
    "available": True, "method": "hybrid+rerank", "rrf_k": 60, "rerank_pool": 15,
    "arms": {"full_text": 20, "vector": 20},
    "filters": {"kept": 828, "of": 1000, "removed": {"budget": 86}},
    "rows": [{"name": "Tall Stoneware Vase With A Long Name", "fts_rank": 7, "vec_rank": 9,
              "similarity": 0.552, "rrf_score": 0.0283, "rerank_score": 0.62, "after": 2,
              "moved": 4},
             {"name": "Linen Throw", "fts_rank": 1, "vec_rank": 2, "similarity": 0.61,
              "rrf_score": 0.0301, "rerank_score": 0.55, "after": 1, "moved": 0}],
}


def table_lines(out: str) -> List[str]:
    return [line for line in out.splitlines() if line.strip()[:1] in ("┌", "│", "├", "└")]


def test_the_ranking_table_never_outgrows_the_terminal(
        capsys: pytest.CaptureFixture[str], columns: int) -> None:
    lab_run._ranking_key_shown = True
    lab_run._trace_ranking(RANKING)
    out = printed(capsys)
    assert_fits(out, columns)
    assert table_lines(out)


@pytest.mark.parametrize("width", [50, 84, 99, 120])
def test_the_ranking_table_has_one_indent_rule(
        capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, width: int) -> None:
    """Under the step's text (column 20) when the whole table fits there, else at column 2."""
    monkeypatch.setattr(check, "terminal_width", lambda: width)
    lab_run._ranking_key_shown = True
    lab_run._trace_ranking(RANKING)
    out = printed(capsys)
    assert_fits(out, width)
    lines = table_lines(out)
    starts = {len(line) - len(line.lstrip()) for line in lines}
    natural = max(len(line) for line in check.table(
        [name for name, _ in lab_run.RANKING_COLUMNS],
        [["2 ↑4", "Tall Stoneware Vase With A Long Name", "#7", "#9  0.55", "0.0283", "0.62"],
         ["1", "Linen Throw", "#1", "#2  0.61", "0.0301", "0.55"]],
        [side for _, side in lab_run.RANKING_COLUMNS], 10**6).splitlines())
    assert starts == ({20} if natural + 20 <= width else {2})


def test_the_diff_footer_and_reload_hint_fit(
        capsys: pytest.CaptureFixture[str], columns: int) -> None:
    lab_run.show_diff(1)
    lab_run.print_reload_hint()
    out = printed(capsys)
    prose = [line for line in out.splitlines()
             if not line.startswith(("-", "+", " @", "@", " ")) or "If the file" in line]
    assert_fits("\n".join(prose), columns)
    assert "  uv run scripts/lab_run.py solution --lab 1" in out.splitlines()
    assert words(lab_run.RELOAD_HINT) == words(out[out.index("If the file is open"):])


def test_a_catch_up_sentence_wraps(capsys: pytest.CaptureFixture[str], columns: int) -> None:
    sentence = ("The answers are in place, so this verdict came from the model's turn: sending "
                "the request Task 2A's check judges again (2 of 3)")
    lab_run.say(sentence)
    out = printed(capsys)
    assert_fits(out, columns)
    assert out.startswith("  The answers are in place")
    assert words(out) == words(sentence)


def test_a_status_line_wraps_under_its_text_and_a_short_one_stays_whole() -> None:
    restored = "restored 3 file regions from the originals (" + ", ".join(
        ["labs/01-retrieve/1A-vector-search.py"] * 3) + ")"
    text = lab_reset.status("+ OK", restored, 99)
    assert_fits(text, 99)
    assert text.startswith("  + OK    restored 3 file regions")
    assert words(text.replace("+ OK", "", 1)) == words(restored)
    assert lab_reset.status("+ OK", "short") == "  + OK    short"


def test_the_reset_report_fits(
        columns: int, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lines: List[str] = []
    point = datetime(2026, 10, 15, 12, 0, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(lab_reset, "apply_database", lambda conn, lab, repo: point)
    monkeypatch.setattr(lab_reset.exercises, "restore_lab",
                        lambda repo, lab, keep_edits: ["labs/03-deploy/3B-row-ownership.sql"] * 3)
    monkeypatch.setattr(lab_reset.check, "record_reset_point", lambda lab, when: None)
    monkeypatch.setattr(lab_reset.deploy_lock, "running_message", lambda repo: "")

    class Conn:
        def close(self) -> None:
            pass

    lab_reset.reset_lab(3, repo=tmp_path, connect=Conn, report=lines.append,
                        managed=lambda lab: None, restart=lambda: "no systemd here")
    text = "\n".join(lines)
    assert_fits(text, columns)
    assert "Not reset: " in text and "Next: start Task 3A again" in text
    assert "backend not restarted (no systemd here); restart it yourself" in " ".join(
        text.split())
