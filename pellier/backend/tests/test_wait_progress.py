"""The progress shown during a participant's waits: honest bars on a terminal, plain lines off it.

The deploy, the Cedar retry and the resets report no percentage, so a bar may only claim what is
known: the step it is on, how long that step has run, and how long it usually takes. These tests
drive the module with a fake clock and a fake terminal; nothing sleeps.
"""
from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from typing import Any, List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "wait_progress.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("pellier_wait_progress", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wait_progress = _load()


class Clock:
    def __init__(self) -> None:
        self.seconds = 1000.0

    def __call__(self) -> float:
        return self.seconds


class Terminal(io.StringIO):
    """A stream that says it is a terminal, as Code Editor's is."""

    encoding = "utf-8"

    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _a_capable_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")


def _last_frame(text: str) -> str:
    return text.split(wait_progress.CLEAR_LINE)[-1]


def test_the_bar_fills_toward_the_typical_duration_and_never_completes_early() -> None:
    assert wait_progress.bar(0, 60) == "░" * 20
    assert wait_progress.bar(30, 60).count("█") == 10
    assert wait_progress.bar(60, 60).count("█") == 19
    assert wait_progress.bar(600, 60).count("█") == 19, "an overrun step must not look finished"
    assert wait_progress.bar(5, 0) == "░" * 20


def test_an_overrun_says_so_and_names_the_limit_when_there_is_one() -> None:
    assert wait_progress.status(41, 60) == "0:41, usually about 1:00"
    assert wait_progress.status(84, 60) == "1:24, still working"
    assert wait_progress.status(84, 60, limit=420) == (
        "1:24, still working (gives up at 7:00)")


def test_off_a_terminal_each_step_prints_a_start_and_an_end_line_and_nothing_redraws() -> None:
    clock, out = Clock(), io.StringIO()
    progress = wait_progress.Progress("Deploying your changes to AgentCore", stream=out,
                                      now=clock, interval=None)
    progress.begin("Checking your files", typical=10, done="Checked your files")
    clock.seconds += 4
    progress.expect(3)
    progress.begin("Publishing policies", typical=60, done="Published policies")
    clock.seconds += 58
    progress.finish()

    assert out.getvalue().splitlines() == [
        "Deploying your changes to AgentCore",
        "  - 1  Checking your files (usually about 0:10)",
        "  + 0:04  1/3  Checked your files",
        "  - 2/3  Publishing policies (usually about 1:00)",
        "  + 0:58  2/3  Published policies",
        "  Done in 1:02.",
    ]
    assert wait_progress.CLEAR_LINE not in out.getvalue()


def test_a_named_progress_says_whose_steps_its_counters_count() -> None:
    """A catch-up runs a deploy that numbers its own steps; its counters must not look alike."""
    clock, out = Clock(), io.StringIO()
    progress = wait_progress.Progress(stream=out, now=clock, interval=None, name="Lab 3 step")
    progress.expect(2)
    progress.begin("Deploying", typical=215, done="Deployed", animate=False)
    clock.seconds += 200
    progress.begin("Sending Theo's requests", typical=40, animate=False)
    clock.seconds += 3
    progress.fail()

    assert out.getvalue().splitlines() == [
        "  - Lab 3 step 1/2  Deploying (usually about 3:35)",
        "  + 3:20  Lab 3 step 1/2  Deployed",
        "  - Lab 3 step 2/2  Sending Theo's requests (usually about 0:40)",
        "  x 0:03  Lab 3 step 2/2  Sending Theo's requests: failed",
    ]


def test_on_a_terminal_the_running_step_is_a_bar_that_its_end_line_replaces() -> None:
    clock, out = Clock(), Terminal()
    progress = wait_progress.Progress(stream=out, now=clock, interval=None)
    progress.expect(6)
    progress.begin("Publishing policies", typical=60, done="Published policies")
    clock.seconds += 41
    progress._live.draw()
    assert _last_frame(out.getvalue()) == (
        "  [1/6] Publishing policies  " + "█" * 13 + "░" * 7 + "  0:41, usually about 1:00")

    clock.seconds += 17
    progress.end()
    assert out.getvalue().endswith(wait_progress.CLEAR_LINE + "  + 0:58  1/6  Published policies\n")


def test_output_printed_while_the_bar_runs_lands_above_it(capsys: pytest.CaptureFixture[str],
                                                         ) -> None:
    clock, out = Clock(), Terminal()
    progress = wait_progress.Progress(stream=out, now=clock, interval=None)
    progress.begin("Proving your build answers", typical=30)
    sys_stdout = sys.stdout
    print("Runtime answered with the previous build, retrying in 20s (1/12)")
    assert sys.stdout is sys_stdout
    progress.end()

    assert sys.stdout is not sys_stdout, "the guard must hand stdout back when the step ends"
    assert "retrying in 20s (1/12)\n" in capsys.readouterr().out
    assert out.getvalue().count(wait_progress.CLEAR_LINE) >= 2


def test_a_failed_step_names_itself_and_restores_the_streams() -> None:
    clock, out = Clock(), Terminal()
    before = (sys.stdout, sys.stderr)
    progress = wait_progress.Progress(stream=out, now=clock, interval=None)
    progress.begin("Publishing policies", typical=60)
    clock.seconds += 70
    progress.fail()

    assert (sys.stdout, sys.stderr) == before
    assert out.getvalue().endswith("  x 1:10  1  Publishing policies: failed\n")
    progress.finish()
    assert "Done in" in out.getvalue(), "finish after a failure still closes the run once"


def test_a_step_whose_child_prints_to_the_terminal_does_not_redraw() -> None:
    out = Terminal()
    progress = wait_progress.Progress(stream=out, now=Clock(), interval=None)
    progress.begin("Moving Pellier onto AgentCore", typical=40, animate=False)
    assert progress._live is None
    assert out.getvalue() == "  - 1  Moving Pellier onto AgentCore (usually about 0:40)\n"


def test_finish_is_said_once() -> None:
    out = io.StringIO()
    progress = wait_progress.Progress(stream=out, now=Clock(), interval=None)
    progress.begin("Checking", typical=5)
    progress.finish()
    progress.finish()
    assert out.getvalue().count("Done in") == 1


def test_a_single_wait_draws_only_on_a_terminal() -> None:
    clock, plain = Clock(), io.StringIO()
    with wait_progress.waiting("Waiting for Cedar", typical=60, limit=420, stream=plain,
                               now=clock, interval=None):
        clock.seconds += 90
    assert plain.getvalue() == ""

    out = Terminal()
    frames: List[str] = []
    with wait_progress.waiting("Waiting for Cedar", typical=60, limit=420, stream=out,
                               now=clock, interval=None):
        clock.seconds += 90
        frames.append(out.getvalue())
    assert _last_frame(frames[0]) == (
        "  Waiting for Cedar  " + "░" * 20 + "  0:00, usually about 1:00")
    assert out.getvalue().endswith(wait_progress.CLEAR_LINE)


def test_a_dumb_terminal_gets_plain_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM", "dumb")
    out = Terminal()
    progress = wait_progress.Progress(stream=out, now=Clock(), interval=None)
    progress.begin("Checking", typical=5)
    assert progress._live is None
    progress.end()


def test_a_terminal_without_utf8_gets_ascii_blocks() -> None:
    class Latin1(Terminal):
        encoding = "latin-1"

    clock, out = Clock(), Latin1()
    progress = wait_progress.Progress(stream=out, now=clock, interval=None)
    progress.begin("Checking", typical=10)
    clock.seconds += 5
    progress._live.draw()
    assert _last_frame(out.getvalue()) == (
        "  [1] Checking  " + "#" * 10 + "-" * 10 + "  0:05, usually about 0:10")
    progress.end()


def test_the_bar_waits_for_a_half_printed_line_to_finish() -> None:
    clock, out = Clock(), Terminal()
    progress = wait_progress.Progress(stream=out, now=clock, interval=None)
    progress.begin("Checking", typical=10)
    guard = wait_progress._Guard(progress._live, out)
    guard.write("+ agentcore deploy")
    progress._live.draw()
    assert out.getvalue().endswith("+ agentcore deploy"), "a redraw would overwrite it"
    guard.write("\n")
    progress._live.draw()
    assert _last_frame(out.getvalue()).startswith("  [1] Checking  ")
    progress.end()


@pytest.mark.parametrize("columns", [200, 100, 80])
def test_the_line_never_wraps_and_the_status_stays_whole(columns: int) -> None:
    state = wait_progress.status(84, 60, limit=420)
    line = wait_progress.fit("  [3/6] Proving your build answers on AgentCore Runtime", 84, 60,
                             state, columns=columns)
    assert len(line) < columns
    assert line.endswith(state)
    assert "█" * 7 in line, "the bar keeps at least its narrowest width"


def test_a_wide_terminal_keeps_the_full_bar_and_label() -> None:
    line = wait_progress.fit("  [3/6] Publishing policies", 30, 60, "0:30, usually about 1:00",
                             columns=120)
    assert line == ("  [3/6] Publishing policies  " + "█" * 10 + "░" * 10
                    + "  0:30, usually about 1:00")


def test_a_terminal_too_narrow_for_the_status_still_never_wraps() -> None:
    state = wait_progress.status(84, 60, limit=420)
    line = wait_progress.fit("  [3/6] Proving your build answers", 84, 60, state, columns=60)
    assert len(line) == 59


def test_a_wait_that_ends_within_the_grace_period_draws_nothing() -> None:
    out = Terminal()
    with wait_progress.waiting("Waiting for Cedar", typical=60, stream=out, interval=0.05):
        pass
    assert out.getvalue() == "", "an instant call must not flash a bar"


def test_a_longer_wait_draws_after_the_grace_period(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wait_progress, "GRACE_SECONDS", 0.05)
    out = Terminal()
    with wait_progress.waiting("Waiting for Cedar", typical=60, stream=out, interval=0.05):
        import time
        time.sleep(0.3)
    assert "Waiting for Cedar" in out.getvalue()
    assert out.getvalue().endswith(wait_progress.CLEAR_LINE)


def test_a_running_step_can_say_what_it_found_when_it_ends() -> None:
    clock, out = Clock(), io.StringIO()
    progress = wait_progress.Progress(stream=out, now=clock, interval=None)
    progress.begin("Checking your files", typical=10, done="Checked your files")
    progress.amend("Checked your files; the Gateway runs your Lab 1 search")
    clock.seconds += 3
    progress.expect(2)
    progress.end()
    progress.amend("too late: no step is running")
    assert out.getvalue().splitlines()[-1] == (
        "  + 0:03  1/2  Checked your files; the Gateway runs your Lab 1 search")
