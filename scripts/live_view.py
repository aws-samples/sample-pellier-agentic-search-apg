"""Ask Pellier's live turn in the terminal: the status line, each step while it runs, and the
answer revealed character by character.

It mirrors the panel. ``StatusLine.tsx`` names what Pellier is doing beside a pulsing copper dot;
``StepList.tsx`` shows a ring while a step runs and its result when it returns; ``reveal.ts``
paces the answer at the owner-confirmed values below. Every state comes from a stream event;
the clock only paces the reveal, as the panel's does.

A small region at the foot of the terminal holds what is still changing: the steps running now,
the answer as revealed so far, and the status line. Everything else prints above it, as it
always has: while a turn runs, stdout and stderr are guarded, so a ``print`` from the send lands
above the region and the region is drawn again beneath it.

It runs on a terminal only. Redirected output (logs, the catch-up, tests) and
``PELLIER_LIVE_VIEW=off`` print exactly what the send printed before it existed.
"""

from __future__ import annotations

import math
import os
import re
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, TextIO, Tuple

OFF_ENV = "PELLIER_LIVE_VIEW"

# reveal.ts, owner-confirmed 2026-10-04: 24 ms a character, 9x after a sentence end, 4x after a
# comma, faster past 60 and 120 waiting characters, and done within 1.5 s of the stream's end.
CADENCE = 0.024
SENTENCE_PAUSE, COMMA_PAUSE = 9, 4
CATCH_UP_AT, CATCH_UP_FACTORS = (60, 120), (0.6, 0.35)
FINISH_WITHIN = 1.5
_SENTENCE_END, _CLAUSE_END = re.compile(r"[.!?]"), re.compile(r"[,;:]")

TICK = 0.016
# The panel's dot breathes every 1.6 s (turn.css, tn-pulse). The terminal eases the dot's color
# between Pellier's two coppers, the light theme's and the dark theme's, so it reads on either.
BREATH = 1.6
BREATH_STEPS = 20
COPPER_DEEP, COPPER_BRIGHT = (154, 77, 32), (218, 149, 98)
COPPER_RAMP_256 = (130, 137, 173, 180)
COPPER, DIM, GREEN, OFF = "\033[38;5;173m", "\033[2m", "\033[32m", "\033[0m"
CLEAR_DOWN, UP, CR = "\033[J", "\033[{}A", "\r"
RING, DOT, CHECK, ARROW = "◌", "●", "✓", "\u2192"


def colored() -> bool:
    """Color unless NO_COLOR asks for none (https://no-color.org)."""
    return "NO_COLOR" not in os.environ


def truecolor() -> bool:
    """The terminal says it takes 24-bit color; Code Editor's does."""
    return os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")


def breathing_dot(elapsed: float) -> str:
    """The status dot at this moment of its breath: deep copper, easing to bright and back."""
    if not colored():
        return DOT
    step = int((elapsed % BREATH) / BREATH * BREATH_STEPS)
    level = (1 - math.cos(2 * math.pi * step / BREATH_STEPS)) / 2
    if truecolor():
        red, green, blue = (round(deep + (bright - deep) * level)
                            for deep, bright in zip(COPPER_DEEP, COPPER_BRIGHT))
        return f"\033[38;2;{red};{green};{blue}m{DOT}{OFF}"
    shade = COPPER_RAMP_256[min(len(COPPER_RAMP_256) - 1, int(level * len(COPPER_RAMP_256)))]
    return f"\033[38;5;{shade}m{DOT}{OFF}"


def paint(text: str, color: str) -> str:
    return f"{color}{text}{OFF}" if colored() else text


def wanted(stream: Optional[TextIO] = None) -> bool:
    """A terminal that redraws in place, with the live view not switched off."""
    target = stream or sys.stdout
    isatty = getattr(target, "isatty", None)
    if not (isatty and isatty()) or os.environ.get("TERM", "") == "dumb":
        return False
    return os.environ.get(OFF_ENV, "").strip().lower() not in ("off", "0", "false", "no")


def _common_prefix(a: str, b: str) -> int:
    limit = min(len(a), len(b))
    index = 0
    while index < limit and a[index] == b[index]:
        index += 1
    return index


class Reveal:
    """The answer's pacing, as ``reveal.ts`` paces it: by the clock, a due time per character.

    ``set_target`` takes the full text received so far; the reveal keeps whatever prefix it has
    already shown that the new text shares. ``done`` bounds the rest to ``FINISH_WITHIN``.
    """

    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self.now = now
        self.target = self.shown = ""
        self.due = 0.0
        self.deadline: Optional[float] = None

    def set_target(self, text: str) -> None:
        keep = _common_prefix(self.shown, text)
        if keep < len(self.shown):
            self.shown = self.shown[:keep]
        if not self.shown or self.due < self.now():
            self.due = max(self.due, self.now())
        self.target = text

    def done(self) -> None:
        self.deadline = self.now() + FINISH_WITHIN

    def finished(self) -> bool:
        return self.deadline is not None and len(self.shown) >= len(self.target)

    def _delay(self, char: str, at: float) -> float:
        delay = CADENCE
        if _SENTENCE_END.match(char):
            delay *= SENTENCE_PAUSE
        elif _CLAUSE_END.match(char):
            delay *= COMMA_PAUSE
        backlog = len(self.target) - len(self.shown)
        if backlog > CATCH_UP_AT[1]:
            delay *= CATCH_UP_FACTORS[1]
        elif backlog > CATCH_UP_AT[0]:
            delay *= CATCH_UP_FACTORS[0]
        if self.deadline is not None and backlog > 0:
            delay = min(delay, max(0.0, self.deadline - at) / backlog)
        return delay

    def advance(self) -> bool:
        """Show every character due by now; True when something new is shown."""
        at, before = self.now(), len(self.shown)
        while len(self.shown) < len(self.target) and self.due <= at:
            char = self.target[len(self.shown)]
            self.shown += char
            self.due += self._delay(char, at)
        return len(self.shown) != before


class _Guard:
    """A stream whose writes land above the live region."""

    def __init__(self, view: "LiveTurn", stream: TextIO) -> None:
        self._view, self._stream = view, stream

    def write(self, text: str) -> int:
        self._view.write_above(self._stream, text)
        return len(text)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


class LiveTurn:
    """One turn's live region on a terminal.

    Args:
        answer_lines: Wraps the answer as revealed so far into its printed lines.
        width: The terminal's width now.
        step_line: Formats a running step's label and tool as a line.
        done_line: Formats a finished step's label, finding and tool as a line, for folding.
        fold: When true the region keeps each finished step too and, at the end, folds the
            whole turn into one line (Lab 1's compact sends); else the trace prints finished
            steps above the region, as it always has.
    """

    def __init__(self, answer_lines: Callable[[str], List[str]], width: Callable[[], int],
                 step_line: Callable[[str, str], str],
                 done_line: Callable[[str, str, str], str],
                 fold: bool = False, stream: Optional[TextIO] = None,
                 now: Callable[[], float] = time.monotonic) -> None:
        self.answer_lines, self.width, self.step_line = answer_lines, width, step_line
        self.done_line = done_line
        self.fold, self.now = fold, now
        self.stream = stream or sys.stdout
        self.lock = threading.RLock()
        self.reveal = Reveal(now)
        self.status = ""
        self.running: Dict[str, Tuple[str, str]] = {}
        # Each finished step once, by id: Pellier sends the Router step again when the turn ends.
        self.finished_steps: Dict[str, str] = {}
        self.steps_done = 0
        self.route = ""
        self.drawn = 0
        self.frame = ""
        self.at_line_start = True
        self.started = now()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._saved: tuple = ()
        # Set when the view itself failed and stepped aside; the send goes on in plain text.
        self.failure = ""

    # -- presentation never costs a turn ---------------------------------------------------
    def _guarded(self, work: Callable[[], Any], fallback: Any = None) -> Any:
        """Run ``work``; any fault in it retires the view instead of failing the send. Work
        takes the lock itself: ``finish`` waits on the tick, which needs it."""
        if self.failure:
            return fallback
        try:
            return work()
        except Exception as exc:  # noqa: BLE001  (display only: the turn must go on)
            with self.lock:
                self.failure = f"{type(exc).__name__}: {exc}"
                self._retire()
            return fallback

    def _retire(self) -> None:
        """Put the terminal back as it was: no region, no guard, no tick."""
        self._stop.set()
        if self._saved:
            sys.stdout, sys.stderr = self._saved
            self._saved = ()
        erase, self.drawn, self.frame = self._erasure(), 0, ""
        try:
            self.stream.write(erase)
            self.stream.flush()
        except OSError:
            pass  # the terminal itself is gone; there is nothing left on it to tidy

    # -- lifecycle -------------------------------------------------------------------------
    def start(self) -> None:
        self._guarded(self._start)

    def _start(self) -> None:
        self._saved = (sys.stdout, sys.stderr)
        sys.stdout, sys.stderr = _Guard(self, sys.stdout), _Guard(self, sys.stderr)
        self.draw()
        self._thread = threading.Thread(target=self._tick, daemon=True)
        self._thread.start()

    def stop(self, leave: str = "") -> None:
        """End the region: no thread, no guard, nothing left drawn but ``leave``, which replaces
        it in the same write so the lasting lines never blink out first. Safe to call twice."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()  # outside the lock: the tick takes it
            self._thread = None
        with self.lock:
            erase = self._erasure()
            if erase or leave:
                self.stream.write(erase + leave)
                self.stream.flush()
            self.drawn, self.frame = 0, ""
            if self._saved:
                sys.stdout, sys.stderr = self._saved
                self._saved = ()

    def begin(self) -> None:
        """A new attempt: its steps and answer start over."""
        self._guarded(self._begin)

    def _begin(self) -> None:
        with self.lock:
            self.reveal = Reveal(self.now)
            self.running, self.finished_steps, self.status = {}, {}, ""
            self.steps_done, self.route = 0, ""
            self.draw()

    # -- stream events ---------------------------------------------------------------------
    def observe(self, event: Dict[str, Any]) -> None:
        """Take in one stream event of the turn."""
        self._guarded(lambda: self._observe(event))

    def _observe(self, event: Dict[str, Any]) -> None:
        kind = event.get("type")
        with self.lock:
            if kind == "status" and event.get("label"):
                self.status = str(event["label"])
            elif kind == "step":
                self._step(event)
            elif kind == "content_delta":
                self.reveal.set_target(self.reveal.target + str(event.get("delta") or ""))
            elif kind == "content_reset":
                self.reveal = Reveal(self.now)
            elif kind == "content":
                self.reveal = Reveal(self.now)
                self.reveal.set_target(str(event.get("content") or ""))
            self.draw()

    def _step(self, event: Dict[str, Any]) -> None:
        step_id, label = str(event.get("id") or ""), str(event.get("label") or "")
        tool = str((event.get("builder") or {}).get("tool") or "")
        if step_id == "route":
            label = "Router"  # as the full trace names it
        if event.get("status") == "running":
            # A step starting means any answer streamed before it was the model's preamble,
            # which Ask Pellier clears too (content_reset follows the tool).
            self.reveal = Reveal(self.now)
            self.running[step_id] = (label, tool)
            self.status = label or self.status
            return
        if self.running.pop(step_id, None) is not None or event.get("status") in ("done",
                                                                                 "failed"):
            self.finished_steps.setdefault(step_id, "")
            self.steps_done = len(self.finished_steps)
            if step_id == "route":
                self.route = str(event.get("finding") or "")
            if self.fold:
                self.finished_steps[step_id] = self.done_line(
                    label, str(event.get("finding") or ""), tool)

    def finish(self, answer: str, fold_line: Optional[str] = None,
               timeout: float = FINISH_WITHIN + 0.5) -> bool:
        """The stream is complete: let the reveal end, then leave the turn's lasting lines.

        Returns True when the revealed answer is the final one, so the caller need not print
        it again. Folding replaces the whole region with ``fold_line``. A view that failed
        returns False, so the caller prints the answer as a log would.
        """
        if self.failure:
            self.stop()
            return False
        done = self._guarded(lambda: self._finish(answer, fold_line, timeout), fallback=None)
        if done is None:
            self.stop()
            return False
        return done

    def _finish(self, answer: str, fold_line: Optional[str], timeout: float) -> bool:
        with self.lock:
            if not self.reveal.target and answer:
                self.reveal.set_target(answer)
            self.reveal.done()
        give_up = self.now() + timeout
        while not self.reveal.finished() and self.now() < give_up and not self.failure:
            time.sleep(TICK)
        with self.lock:
            # Past the bound, show the rest at once, as reveal.ts's flush does.
            self.reveal.shown = self.reveal.target
            shown = self.reveal.shown
        if self.fold:
            self.stop(leave=f"{fold_line}\n" if fold_line else "")
            return True
        self.stop(leave="".join(f"{line}\n" for line in self.answer_lines(shown))
                  if shown.strip() else "")
        return _same(shown, answer)

    # -- drawing ---------------------------------------------------------------------------
    def region(self) -> List[str]:
        """The lines still changing, foot of the terminal last."""
        lines = list(self.finished_steps.values()) if self.fold else []
        lines += [self.step_line(label, tool) for label, tool in self.running.values()]
        if self.reveal.shown:
            lines += self.answer_lines(self.reveal.shown)
        if self.status:
            elapsed = self.now() - self.started
            seconds = int(elapsed)
            took = f"  {paint(f'{seconds} s', DIM)}" if seconds >= 5 else ""
            lines.append(f"  {breathing_dot(elapsed)} {self.status}{took}")
        room = max(3, _rows() - 2)
        return lines[-room:]

    def draw(self, force: bool = False) -> None:
        """Draw the region again when it changed, erase and lines in one write, so a terminal
        across the network never shows the erase without what replaces it."""
        with self.lock:
            if not self.at_line_start:
                return
            lines = self.region()
            frame = "\n".join(lines)
            if frame == self.frame and self.drawn == len(lines) and not force:
                return
            self.stream.write(self._erasure() + frame)
            self.stream.flush()
            self.drawn, self.frame = len(lines), frame

    def _erasure(self) -> str:
        if not self.drawn:
            return ""
        return CR + (UP.format(self.drawn - 1) if self.drawn > 1 else "") + CLEAR_DOWN

    def _erase(self) -> None:
        if self.drawn:
            self.stream.write(self._erasure())
            self.stream.flush()
            self.drawn, self.frame = 0, ""

    def write_above(self, stream: TextIO, text: str) -> None:
        """Print ``text`` above the region; if the view fails, print it as a log would."""
        if self._guarded(lambda: self._write_above(stream, text), fallback=False) is False:
            stream.write(text)
            stream.flush()

    def _write_above(self, stream: TextIO, text: str) -> bool:
        with self.lock:
            erase = self._erasure()
            self.drawn, self.frame = 0, ""
            if stream is self.stream:
                stream.write(erase + text)
            else:
                if erase:
                    self.stream.write(erase)
                    self.stream.flush()
                stream.write(text)
            stream.flush()
            if text:
                self.at_line_start = text.endswith("\n")
            self.draw()
            return True

    def _tick(self) -> None:
        while not self._stop.wait(TICK):
            self._guarded(self._advance)

    def _advance(self) -> None:
        with self.lock:
            self.reveal.advance()
            self.draw()


def _same(shown: str, answer: str) -> bool:
    return " ".join(shown.split()) == " ".join(answer.split())


def _rows() -> int:
    try:
        return os.get_terminal_size().lines
    except OSError:
        return 24


def _plain(text: str) -> str:
    return text


def _called(tool: str, tint: Callable[[str], str]) -> str:
    """The tool the step calls, in the colour of where it runs, before the step's words."""
    return f"{tint(tool)}  " if tool else ""


def ring_line(indent: str, label_width: int,
              tint: Callable[[str], str] = _plain) -> Callable[[str, str], str]:
    """A running step's line, in the trace's columns: the ring where the number will be, then
    the tool it calls (``tint`` colours it by where it runs) and the step's words."""
    def line(label: str, tool: str = "") -> str:
        return f"{indent}{paint(RING, COPPER)}{'':<{label_width - 1}}{_called(tool, tint)}{label}"
    return line


def check_line(indent: str, label_width: int,
               tint: Callable[[str], str] = _plain) -> Callable[[str, str, str], str]:
    """A finished step's line while folding: a check, the tool, the label and what it found."""
    def line(label: str, finding: str, tool: str = "") -> str:
        said = f"{label}: {finding}" if finding else label
        return (f"{indent}{paint(CHECK, GREEN)}{'':<{label_width - 1}}"
                f"{_called(tool, tint)}{said}")
    return line


def fold_line(agent: str, steps: int, rail_local: bool,
              tint: Callable[[str], str] = _plain, reason: str = "") -> str:
    """Lab 1's fold: the Router, the agent it chose (``tint`` colours it by where it ran) and
    the words that chose it, then the agent's own steps."""
    who = f"local {agent}" if rail_local else agent
    why = f" ({reason})" if reason else ""
    did = (f"answered in {steps} step{'' if steps == 1 else 's'}" if steps > 0
           else "answered without calling a tool")
    return f"{paint(CHECK, GREEN)} Router {paint(ARROW, DIM)} {tint(who)}{why}, {did}"
