"""Progress for the waits a participant sits through: a bar while a step runs, a line when it ends.

Nothing these scripts wait on reports a percentage, so the bar claims only what is known. It
counts real steps, and within a step it fills toward that step's typical duration, measured on
test events, without ever reaching the end before the step does. Past the typical duration the
bar holds and says the step is still working. Each finished step leaves one line with how long it
took.

On a terminal the bar redraws in place, and anything printed while it runs appears above it.
Anywhere else (a log file, a pipe, a capture) nothing redraws: a step prints one line as it
starts and one as it ends, and a single wait prints nothing of its own.

    progress = Progress("Deploying your changes to AgentCore")
    progress.begin("Publishing policies", done="Published policies", typical=60)
    ...
    progress.finish()

    with waiting("Waiting for the backend to restart", typical=15, limit=120):
        ...
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from typing import Callable, Iterator, Optional, TextIO

BAR_WIDTH = 20
NARROWEST_BAR = 8
# The bar stops short of full until the step really ends.
MOST_OF_THE_BAR = 0.95
REDRAW_SECONDS = 0.5
# A wait that ends sooner than this draws nothing, so an instant call does not flash a bar.
GRACE_SECONDS = 1.0
CLEAR_LINE = "\r\x1b[K"


def clock(seconds: float) -> str:
    """``m:ss`` for a duration, as the terminal shows elapsed and typical times."""
    whole = max(0, int(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def status(elapsed: float, typical: float, limit: Optional[float] = None) -> str:
    """How a running step stands against its typical duration."""
    if elapsed <= typical:
        return f"{clock(elapsed)}, usually about {clock(typical)}"
    gives_up = f" (gives up at {clock(limit)})" if limit else ""
    return f"{clock(elapsed)}, still working{gives_up}"


def bar(elapsed: float, typical: float, blocks: str = "█░", width: int = BAR_WIDTH) -> str:
    """A bar filled toward ``typical``, never full: only the step's end completes it."""
    fraction = MOST_OF_THE_BAR * min(1.0, elapsed / typical) if typical > 0 else 0.0
    filled = min(width - 1, int(round(width * fraction)))
    return blocks[0] * filled + blocks[1] * (width - filled)


def fit(head: str, elapsed: float, typical: float, state: str, *, columns: int,
        blocks: str = "█░") -> str:
    """``head  bar  state`` in fewer than ``columns`` characters, so the line never wraps.

    A wrapped line cannot be redrawn in place. The state is what the participant reads, so it
    stays whole: the bar narrows first, then the head is shortened.
    """
    room = columns - 1 - len(state) - 4
    width = max(NARROWEST_BAR, min(BAR_WIDTH, room - len(head)))
    if len(head) > room - width:
        head = head[: max(0, room - width - 1)] + "…"
    return f"{head}  {bar(elapsed, typical, blocks, width)}  {state}"[: max(1, columns - 1)]


def columns() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def can_redraw(stream: TextIO) -> bool:
    """A terminal that understands carriage returns and line clears."""
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty()) and os.environ.get("TERM", "") != "dumb"


def _blocks(stream: TextIO) -> str:
    encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
    return "█░" if encoding.startswith("utf") else "#-"


class _Guard:
    """Stands in for stdout or stderr while a bar is drawn, so other output lands above it."""

    def __init__(self, live: "_Live", wrapped: TextIO) -> None:
        self._live, self._wrapped = live, wrapped

    def write(self, text: str) -> int:
        with self._live.lock:
            if can_redraw(self._wrapped):
                self._live.erase()
            written = self._wrapped.write(text)
            self._wrapped.flush()
            if text:
                self._live.at_line_start = text.endswith("\n")
            return written

    def flush(self) -> None:
        self._wrapped.flush()

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)


class _Live:
    """One line redrawn in place on a terminal, with stdout and stderr guarded meanwhile."""

    def __init__(self, stream: TextIO, render: Callable[[int], str],
                 interval: Optional[float] = REDRAW_SECONDS) -> None:
        self.stream, self.render, self.interval = stream, render, interval
        self.lock = threading.RLock()
        self.drawn = False
        self.at_line_start = True
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._saved: tuple = ()

    def start(self) -> None:
        """Guard the streams; draw after the grace period, or now when redrawn by hand."""
        self._saved = (sys.stdout, sys.stderr)
        sys.stdout, sys.stderr = _Guard(self, sys.stdout), _Guard(self, sys.stderr)
        if not self.interval:
            self.draw()
            return
        self._thread = threading.Thread(target=self._redraw, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        with self.lock:
            self.erase()
            sys.stdout, sys.stderr = self._saved

    def draw(self) -> None:
        with self.lock:
            if not self.at_line_start:
                return
            self.stream.write(CLEAR_LINE + self.render(columns()))
            self.stream.flush()
            self.drawn = True

    def erase(self) -> None:
        if self.drawn:
            self.stream.write(CLEAR_LINE)
            self.stream.flush()
            self.drawn = False

    def _redraw(self) -> None:
        if self._stop.wait(GRACE_SECONDS):
            return
        self.draw()
        while not self._stop.wait(self.interval):
            self.draw()


class Progress:
    """Numbered steps, each a bar while it runs and one line when it ends.

    Args:
        title: Printed once, before the first step.
        stream: Where the bar and the step lines go; defaults to stdout at the first step.
        now: The clock, for tests.
        interval: Seconds between redraws; ``None`` redraws only on demand, for tests.
    """

    def __init__(self, title: str = "", *, stream: Optional[TextIO] = None,
                 now: Callable[[], float] = time.monotonic,
                 interval: Optional[float] = REDRAW_SECONDS) -> None:
        self.title, self._stream, self.now, self.interval = title, stream, now, interval
        self.total: Optional[int] = None
        self.number = 0
        self._began = 0.0
        self._step: Optional[dict] = None
        self._live: Optional[_Live] = None
        self._finished = False

    @property
    def stream(self) -> TextIO:
        """Fixed at the first step, so a guarded stdout never becomes the bar's own stream."""
        if self._stream is None:
            self._stream = sys.stdout
        return self._stream

    def expect(self, total: int) -> None:
        """Set how many steps there are, once known; the counters read ``n/total`` from then."""
        self.total = total

    def counter(self) -> str:
        return f"{self.number}/{self.total}" if self.total else str(self.number)

    def begin(self, label: str, *, typical: float, done: Optional[str] = None,
              animate: bool = True) -> None:
        """End the running step, if any, and start the next.

        Args:
            label: What the step is doing, as the bar shows it.
            typical: Its usual duration in seconds, from measured runs.
            done: The line it leaves when it ends; defaults to ``label``.
            animate: ``False`` for a step whose own child process prints to the terminal,
                which a redrawn line would collide with: it prints a start line instead.
        """
        self.end()
        if self.number == 0:
            self._began = self.now()
            if self.title:
                self._print(self.title)
        self.number += 1
        self._step = {"label": label, "done": done or label, "typical": typical,
                      "started": self.now()}
        if animate and can_redraw(self.stream):
            self._live = _Live(self.stream, self._render, self.interval)
            self._live.start()
        else:
            self._print(f"  - {self.counter()}  {label} (usually about {clock(typical)})")

    def end(self, done: Optional[str] = None) -> None:
        """End the running step: its line says what it did and how long it took."""
        step = self._close()
        if step:
            self._print(f"  + {clock(self.now() - step['started'])}  {self.counter()}  "
                        f"{done or step['done']}")

    def fail(self) -> None:
        """End the running step as failed; the caller reports why."""
        step = self._close()
        if step:
            self._print(f"  x {clock(self.now() - step['started'])}  {self.counter()}  "
                        f"{step['label']}: failed")

    def finish(self) -> None:
        """End the running step and say how long the whole run took. Safe to call twice."""
        self.end()
        if self.number and not self._finished:
            self._finished = True
            self._print(f"  Done in {clock(self.now() - self._began)}.")

    def _close(self) -> Optional[dict]:
        if self._live is not None:
            self._live.stop()
            self._live = None
        step, self._step = self._step, None
        return step

    def _render(self, width: int) -> str:
        step = self._step or {"label": "", "typical": 0.0, "started": self.now()}
        elapsed = self.now() - step["started"]
        return fit(f"  [{self.counter()}] {step['label']}", elapsed, step["typical"],
                   status(elapsed, step["typical"]), columns=width, blocks=_blocks(self.stream))

    def _print(self, line: str) -> None:
        print(line, file=self.stream, flush=True)


@contextmanager
def waiting(label: str, *, typical: float, limit: Optional[float] = None,
            stream: Optional[TextIO] = None, now: Callable[[], float] = time.monotonic,
            interval: Optional[float] = REDRAW_SECONDS) -> Iterator[None]:
    """A bar for one wait, on a terminal only; the caller prints how it ended.

    Args:
        label: What is being waited for.
        typical: Its usual duration in seconds.
        limit: When the caller gives up, shown once the wait runs long.
        stream: Where the bar goes; defaults to stdout.
        now: The clock, for tests.
        interval: Seconds between redraws; ``None`` for tests.
    """
    target = stream or sys.stdout
    if not can_redraw(target):
        yield
        return
    started = now()

    def render(width: int) -> str:
        elapsed = now() - started
        return fit(f"  {label}", elapsed, typical, status(elapsed, typical, limit),
                   columns=width, blocks=_blocks(target))

    live = _Live(target, render, interval)
    live.start()
    try:
        yield
    finally:
        live.stop()
