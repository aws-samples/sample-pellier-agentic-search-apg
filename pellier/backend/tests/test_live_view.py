"""The terminal's live turn: Ask Pellier's status, steps and character reveal, on a terminal
only."""

from __future__ import annotations

import io
import sys
import threading
from pathlib import Path
from typing import List

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
import live_view  # noqa: E402

PLAIN = "\033["


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def _turn(clock: Clock, fold: bool = False, stream=None) -> live_view.LiveTurn:
    return live_view.LiveTurn(
        answer_lines=lambda text: [f"Pellier: {text}"], width=lambda: 100,
        step_line=lambda label, tool: f"RUN {tool} {label}".replace("RUN  ", "RUN "),
        done_line=lambda label, finding, tool: f"DONE {label}: {finding}",
        fold=fold, stream=stream or Terminal(), now=clock)


# -- the reveal's pacing, as reveal.ts paces it ------------------------------------------
def test_one_character_every_24_ms_with_pauses_after_commas_and_sentence_ends() -> None:
    clock = Clock()
    reveal = live_view.Reveal(clock)
    reveal.set_target("ab, c. d")
    shown: List[str] = []
    for _ in range(40):
        reveal.advance()
        shown.append(reveal.shown)
        clock.t += 0.024
    # a, b at 24 ms; the comma then waits 4 ticks; the full stop waits 9.
    assert shown[0] == "a" and shown[1] == "ab" and shown[2] == "ab,"
    assert shown[3] == "ab," and shown[6] == "ab, "
    assert "ab, c." in shown and shown[shown.index("ab, c.") + 8] == "ab, c."


def test_a_long_backlog_catches_up_and_done_finishes_within_the_bound() -> None:
    clock = Clock()
    reveal = live_view.Reveal(clock)
    reveal.set_target("x" * 200)
    reveal.advance()
    clock.t += 0.024
    reveal.advance()
    # Past 120 waiting the cadence is 0.35 x 24 ms = 8.4 ms, by the clock: three in one tick.
    assert reveal.shown == "xxx"
    reveal.done()
    clock.t += live_view.FINISH_WITHIN
    reveal.advance()
    assert reveal.finished() and reveal.shown == "x" * 200


def test_more_text_keeps_what_is_shown_and_a_rewrite_keeps_only_the_shared_prefix() -> None:
    clock = Clock()
    reveal = live_view.Reveal(clock)
    reveal.set_target("Brooklyn has")
    clock.t += 1
    reveal.advance()
    assert reveal.shown == "Brooklyn has"
    reveal.set_target("Brooklyn has none")
    assert reveal.shown == "Brooklyn has"
    reveal.set_target("Brooklyn had")
    assert reveal.shown == "Brooklyn ha"


# -- the region ---------------------------------------------------------------------------
def test_a_running_step_shows_a_ring_and_leaves_when_it_finishes() -> None:
    turn = _turn(Clock())
    turn.observe({"type": "step", "id": "s1", "status": "running", "label": "Checking stock"})
    assert "RUN Checking stock" in turn.region()
    turn.observe({"type": "step", "id": "s1", "status": "done", "label": "Checking stock",
                  "finding": "Brooklyn 0"})
    assert "RUN Checking stock" not in turn.region(), (
        "the trace prints the finished step above the region; the status line keeps its label "
        "until the stream's next status, as the panel's does")


def test_folding_keeps_each_finished_step_with_its_finding() -> None:
    turn = _turn(Clock(), fold=True)
    turn.observe({"type": "step", "id": "route", "status": "done", "label": "Understanding",
                  "finding": "Sent to the Catalog agent"})
    assert "DONE Router: Sent to the Catalog agent" in turn.region(), (
        "the Router step is named as the full trace names it")


def test_a_step_sent_again_counts_once_and_draws_once() -> None:
    """Pellier sends the Router step again once the agent has answered (services/chat.py)."""
    turn = _turn(Clock(), fold=True)
    route = {"type": "step", "id": "route", "status": "done", "label": "Understanding",
             "finding": "Sent to the Catalog agent: gift"}
    turn.observe(route)
    turn.observe({"type": "step", "id": "s1", "status": "running", "label": "Searching",
                  "builder": {"tool": "search_products"}})
    turn.observe({"type": "step", "id": "s1", "status": "done", "label": "Searching",
                  "finding": "5 found", "builder": {"tool": "search_products"}})
    turn.observe(route)
    assert turn.steps_done == 2
    assert [line for line in turn.region() if line.startswith("DONE")] == [
        "DONE Router: Sent to the Catalog agent: gift", "DONE Searching: 5 found"]


def test_a_step_starting_erases_the_answer_streamed_before_it() -> None:
    """The model's sentence before its tool: Ask Pellier clears it, so the terminal does too."""
    clock = Clock()
    turn = _turn(clock)
    turn.observe({"type": "content_delta", "delta": "I'll check the warehouse records."})
    clock.t += 5
    turn.reveal.advance()
    assert any("I'll check" in line for line in turn.region())
    turn.observe({"type": "step", "id": "s1", "status": "running", "label": "Checking stock"})
    assert not any("I'll check" in line for line in turn.region())


@pytest.mark.parametrize("event", [{"type": "content_reset"},
                                   {"type": "content", "content": "Rewritten."}])
def test_a_reset_or_a_whole_replacement_starts_the_answer_over(event) -> None:
    clock = Clock()
    turn = _turn(clock)
    turn.observe({"type": "content_delta", "delta": "Draft words"})
    clock.t += 5
    turn.reveal.advance()
    turn.observe(event)
    assert turn.reveal.shown == "" and turn.reveal.target == event.get("content", "")


@pytest.mark.parametrize("no_color", [False, True])
def test_the_status_line_names_the_step_and_shows_seconds_after_five(no_color, monkeypatch) -> None:
    if no_color:
        monkeypatch.setenv("NO_COLOR", "1")
    else:
        monkeypatch.delenv("NO_COLOR", raising=False)
    clock = Clock()
    turn = _turn(clock)
    turn.observe({"type": "status", "label": "Understanding your request"})
    assert turn.region()[-1].endswith("Understanding your request")
    clock.t += 6
    suffix = "6 s" if no_color else live_view.DIM + "6 s" + live_view.OFF
    assert turn.region()[-1].endswith(suffix)


def test_the_dot_breathes_between_pellier_s_two_coppers_every_1_6_s(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert live_view.breathing_dot(0.0).startswith("\033[38;2;154;77;32m")
    assert live_view.breathing_dot(0.8).startswith("\033[38;2;218;149;98m")
    assert live_view.breathing_dot(1.6) == live_view.breathing_dot(0.0)
    shades = {live_view.breathing_dot(t / 10) for t in range(16)}
    assert len(shades) >= 8, "it eases through the shades, not a two-state blink"
    monkeypatch.setenv("COLORTERM", "")
    assert live_view.breathing_dot(0.8).startswith("\033[38;5;")
    monkeypatch.setenv("NO_COLOR", "1")
    assert live_view.breathing_dot(0.8) == live_view.DOT


def test_a_frame_is_one_write_and_an_unchanged_region_is_not_drawn_again() -> None:
    class Counting(Terminal):
        writes = 0

        def write(self, text):
            Counting.writes += 1
            return super().write(text)

    screen = Counting()
    clock = Clock()
    turn = _turn(clock, stream=screen)
    turn.observe({"type": "step", "id": "s1", "status": "running", "label": "Checking stock"})
    turn.observe({"type": "step", "id": "s2", "status": "running", "label": "Opening gifts"})
    before = Counting.writes
    turn.draw()
    turn.draw()
    assert Counting.writes == before, "nothing changed, so nothing is written"
    turn.observe({"type": "step", "id": "s1", "status": "done", "label": "Checking stock"})
    assert Counting.writes == before + 1, "erase and redraw arrive as one write"


# -- the terminal ---------------------------------------------------------------------------
def test_a_print_during_the_turn_lands_above_the_region(monkeypatch) -> None:
    screen = Terminal()
    monkeypatch.setattr(sys, "stdout", screen)
    turn = _turn(Clock(), stream=screen)
    turn.start()
    try:
        turn.observe({"type": "status", "label": "Writing your answer"})
        print("          1 Router  Sent to the Stock agent")
    finally:
        turn.stop()
    assert sys.stdout is screen
    out = screen.getvalue()
    assert out.index("1 Router") > 0 and out.rfind("Writing your answer") > out.index("1 Router")


def test_finish_leaves_the_answer_once_and_says_it_was_the_final_one(monkeypatch) -> None:
    screen = Terminal()
    monkeypatch.setattr(sys, "stdout", screen)
    clock = Clock()
    turn = _turn(clock, stream=screen)
    turn.start()
    turn.observe({"type": "content_delta", "delta": "Brooklyn has none."})
    done = threading.Event()
    result: List[bool] = []

    def finish() -> None:
        result.append(turn.finish("Brooklyn has none."))
        done.set()

    worker = threading.Thread(target=finish)
    worker.start()
    for _ in range(200):
        if done.is_set():
            break
        clock.t += 0.1
        done.wait(0.01)
    worker.join(2)
    assert result == [True] and sys.stdout is screen
    assert screen.getvalue().rstrip().endswith("Pellier: Brooklyn has none.")


def test_a_folded_turn_leaves_only_its_fold_line(monkeypatch) -> None:
    screen = Terminal()
    monkeypatch.setattr(sys, "stdout", screen)
    clock = Clock()
    turn = _turn(clock, fold=True, stream=screen)
    turn.start()
    turn.observe({"type": "content_delta", "delta": "For a slow morning."})
    clock.t += 10
    turn.finish("For a slow morning.", fold_line="FOLD")
    assert screen.getvalue().rstrip().endswith("FOLD")


def test_the_view_runs_only_on_a_terminal_and_the_switch_turns_it_off(monkeypatch) -> None:
    monkeypatch.delenv(live_view.OFF_ENV, raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert live_view.wanted(Terminal())
    assert not live_view.wanted(io.StringIO())
    for value in ("off", "0", "false", "no", "OFF"):
        monkeypatch.setenv(live_view.OFF_ENV, value)
        assert not live_view.wanted(Terminal())
    monkeypatch.delenv(live_view.OFF_ENV)
    monkeypatch.setenv("TERM", "dumb")
    assert not live_view.wanted(Terminal())


def test_the_fold_line_names_the_router_the_agent_its_reason_and_its_steps(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    line = live_view.fold_line("Catalog agent", 2, rail_local=True, reason="housewarming, gift")
    assert line == "✓ Router → local Catalog agent (housewarming, gift), answered in 2 steps"
    assert live_view.fold_line("Catalog agent", 1, rail_local=True).endswith(
        "local Catalog agent, answered in 1 step")
    assert live_view.fold_line("Catalog agent", 0, rail_local=True).endswith(
        "answered without calling a tool")


def test_a_running_step_shows_the_tool_it_calls_in_the_colour_of_where_it_runs() -> None:
    line = live_view.ring_line("  ", 10, tint=lambda tool: f"<{tool}>")
    assert line("Checking stock in three warehouses", "check_stock").endswith(
        "<check_stock>  Checking stock in three warehouses")
    assert line("Understanding your request", "").endswith(" Understanding your request")
    clock = Clock()
    turn = _turn(clock)
    turn.observe({"type": "step", "id": "s1", "status": "running",
                  "label": "Checking stock in three warehouses",
                  "builder": {"tool": "check_stock"}})
    assert "RUN check_stock Checking stock in three warehouses" in turn.region()


def test_the_fold_names_where_the_agent_ran_in_its_colour() -> None:
    line = live_view.fold_line("Catalog agent", 2, rail_local=True, tint=lambda who: f"<{who}>",
                               reason="gift")
    assert "Router" in line and line.endswith("<local Catalog agent> (gift), answered in 2 steps")


def test_the_lasting_lines_replace_the_region_in_the_same_write() -> None:
    """Erasing the region and printing the answer apart would blink the answer out for a
    frame, which a terminal across the network can show."""
    class Recording(Terminal):
        def __init__(self) -> None:
            super().__init__()
            self.writes = []

        def write(self, text):
            self.writes.append(text)
            return super().write(text)

    screen = Recording()
    clock = Clock()
    turn = _turn(clock, stream=screen)
    turn.observe({"type": "content_delta", "delta": "For a slow morning."})
    clock.t += 5
    turn.reveal.advance()
    turn.draw()
    turn.finish("For a slow morning.", timeout=0)
    last = screen.writes[-1]
    assert last.startswith("\r") and live_view.CLEAR_DOWN in last
    assert last.endswith("Pellier: For a slow morning.\n")
    assert not any(write.endswith(live_view.CLEAR_DOWN) for write in screen.writes)
