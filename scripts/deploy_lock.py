#!/usr/bin/env python3
"""One AgentCore deploy at a time, and a way to follow the one that is running.

A deploy holds an exclusive lock on ``.agentcore-project/<project>.deploy.lock`` while it runs,
writes who it is into that file, and copies every whole line it prints into
``<project>.deploy.log``. The kernel releases the lock however the deploy ends, so a killed
deploy never leaves a stale one; a deploy that ends normally records its exit code first.

Code Editor gives every new window a new terminal, and a deploy started in an earlier window
keeps running in a terminal the new one does not show. So a second participant deploy follows
the first instead of starting beside it: it replays the log, prints new lines as they arrive,
and ends with the first deploy's result. A new terminal says when a deploy is running, and a
reset refuses to start during one:

    python3 scripts/deploy_lock.py --notice
    python3 scripts/deploy_lock.py --refuse-if-running

Standard library only, so a new terminal can ask without loading the provisioner.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional, TextIO, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wait_progress import clock, waiting  # noqa: E402

# What a second run calls the deploy that holds the lock.
KINDS = {
    "full": "the workshop's provisioning",
    "participant": "a deploy of your changes",
    "reset": "the reset's redeploy of the starters",
}
POLL_ENV = "PELLIER_DEPLOY_FOLLOW_POLL"
DEPLOY_COMMAND = ('uv run scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" '
                  "--mode participant")
STILL_RUNS = ("It keeps running when Code Editor is closed, in a terminal a reopened window "
              "does not show.")
REFUSE_RESET = "Wait for it to finish, then run the reset again. Nothing was changed."
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# A step line from wait_progress.Progress: "  + 0:24  2/4  Deployed..." or "  - 2/4  Deploying...".
STEP_LINE = re.compile(r"^\s+[-+x] (?:\d+:\d\d\s+)?\d+/(\d+)\s", re.MULTILINE)
# Messages wrap here: a terminal draws a longer line by breaking it mid-word at its edge.
WIDTH = 100
# A shared probe (a follower or a new terminal's notice) holds the lock for an instant, so a
# deploy that finds it busy after the last one ended tries again for this long.
PROBE_RETRY_SECONDS = 1.0

Now = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def wrapped(text: str) -> str:
    """The message in lines no wider than ``WIDTH``, for a terminal."""
    return textwrap.fill(text, width=WIDTH)


def _say(text: str) -> None:
    print(wrapped(text), flush=True)


class DeployAlreadyRunning(Exception):
    """Another process is deploying this AgentCore project; this run deployed nothing."""


def lock_path(project_root: Path) -> Path:
    """The lock beside the CLI project, which a first deploy removes and recreates."""
    return project_root.with_name(f"{project_root.name}.deploy.lock")


def log_path(lock: Path) -> Path:
    return lock.with_suffix(".log")


def _open_shared(path: Path) -> int:
    """Open ``path`` read-write, creating it; a file root creates goes to the directory's owner.

    A deploy run as root (an SSM command) must leave files the participant's next deploy can
    open.
    """
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return os.open(path, os.O_RDWR)
    if os.geteuid() == 0:
        owner = path.parent.stat()
        os.fchown(descriptor, owner.st_uid, owner.st_gid)
    return descriptor


def _holder(text: str) -> Dict[str, Any]:
    try:
        holder = json.loads(text)
    except ValueError:
        return {}
    return holder if isinstance(holder, dict) else {}


def _read_holder(path: Path) -> Dict[str, Any]:
    try:
        return _holder(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _started(holder: Dict[str, Any]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(holder["started_at"])).astimezone(timezone.utc)
    except (KeyError, ValueError):
        return None


def _describe(holder: Dict[str, Any], now: datetime) -> str:
    started = _started(holder)
    if started is None or "pid" not in holder:
        return "A deploy is already running."
    what = KINDS.get(str(holder.get("kind")), "a deploy")
    return (f"A deploy is already running: {what}, started at {started:%H:%M:%S} UTC, "
            f"{clock((now - started).total_seconds())} ago, process {holder['pid']}.")


class Tee:
    """Writes through to a stream and copies each whole line, without bar redraws, to a log."""

    def __init__(self, wrapped: TextIO, log: TextIO) -> None:
        self._wrapped, self._log, self._pending = wrapped, log, ""

    def write(self, text: str) -> int:
        written = self._wrapped.write(text)
        *lines, self._pending = (self._pending + text).split("\n")
        # A bar redraws its line after a carriage return; only what follows the last one stays.
        self._pending = self._pending.rsplit("\r", 1)[-1]
        for line in lines:
            line = ANSI.sub("", line.rsplit("\r", 1)[-1])
            if line.strip():
                self._log.write(line + "\n")
                self._log.flush()
        return written

    def flush(self) -> None:
        self._wrapped.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


class DeployLock:
    """The held lock, the log the deploy copies its lines into, and its release."""

    def __init__(self, path: Path, handle: TextIO, log: TextIO, holder: Dict[str, Any],
                 now: Now) -> None:
        self.path, self.log, self.holder = path, log, holder
        self._handle, self._now = handle, now
        self._streams: Tuple[TextIO, ...] = ()

    def tee_output(self) -> None:
        """Copy every whole line written to stdout and stderr into the log, until release."""
        self._streams = (sys.stdout, sys.stderr)
        sys.stdout, sys.stderr = Tee(sys.stdout, self.log), Tee(sys.stderr, self.log)

    def release(self, code: int) -> None:
        """Record how the deploy ended, then let the next one run."""
        if self._streams:
            sys.stdout, sys.stderr = self._streams
            self._streams = ()
        self.log.close()
        self._handle.seek(0)
        self._handle.truncate()
        self._handle.write(json.dumps({**self.holder, "exit": code,
                                       "ended_at": self._now().isoformat()}))
        self._handle.flush()
        self._handle.close()


def hold(path: Path, kind: str, *, now: Now = _utc_now) -> DeployLock:
    """Hold the deploy lock until ``release``, or until this process ends however it ends.

    Raises:
        DeployAlreadyRunning: another deploy holds it; the message names that deploy.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.fdopen(_open_shared(path), "r+", encoding="utf-8")
    deadline = time.monotonic() + PROBE_RETRY_SECONDS
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            handle.seek(0)
            holder = _holder(handle.read())
            if "exit" not in holder or time.monotonic() > deadline:
                handle.close()
                raise DeployAlreadyRunning(
                    f"{_describe(holder, now())} {STILL_RUNS} Nothing new was deployed. Wait "
                    "for it to finish, then run this command again.") from None
            time.sleep(0.05)
    holder = {"pid": os.getpid(), "kind": kind, "started_at": now().isoformat()}
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps(holder))
    handle.flush()
    log_descriptor = _open_shared(log_path(path))
    os.ftruncate(log_descriptor, 0)
    return DeployLock(path, handle, os.fdopen(log_descriptor, "w", encoding="utf-8"), holder, now)


def running(path: Path) -> bool:
    """Whether a deploy holds the lock now. A shared probe never blocks the deploy for long."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(descriptor)


class _LogReader:
    """The whole lines a deploy has logged since the last read."""

    def __init__(self, path: Path) -> None:
        self.path, self.offset = path, 0

    def new_lines(self) -> str:
        try:
            with open(self.path, "rb") as stream:
                stream.seek(self.offset)
                data = stream.read()
        except OSError:
            return ""
        end = data.rfind(b"\n") + 1
        self.offset += end
        return data[:end].decode("utf-8", "replace")


def total_steps(log_text: str) -> Optional[int]:
    """How many steps the logged deploy has, once its first step line is in the log."""
    found = STEP_LINE.search(log_text)
    return int(found.group(1)) if found else None


def _show(text: str) -> None:
    if text:
        sys.stdout.write(text)
        sys.stdout.flush()


def follow(path: Path, kind: str, *, typical: Callable[[Optional[int]], float],
           now: Now = _utc_now, sleep: Callable[[float], None] = time.sleep) -> int:
    """Show the running deploy until it ends, then end with its result.

    ``typical`` gives the usual duration of a deploy with that many steps (None: not yet
    logged), for the bar. It exits 0 only when the deploy it followed was the same kind and
    succeeded, and says that the deploy took the files as they were when it started.
    """
    holder = _read_holder(path)
    _say(f"{_describe(holder, now())} {STILL_RUNS} Following it here; this run deploys "
         "nothing new.")
    poll = float(os.environ.get(POLL_ENV, "") or 1.0)
    started = _started(holder)
    elapsed = (now() - started).total_seconds() if started else 0.0
    log = _LogReader(log_path(path))
    try:
        logged = log_path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        logged = ""
    usual = typical(total_steps(logged))
    with waiting("Waiting for it to finish", typical=max(30.0, usual - elapsed)):
        while running(path):
            _show(log.new_lines())
            sleep(poll)
    _show(log.new_lines())
    ended = _read_holder(path)
    code = ended.get("exit")
    if not isinstance(code, int):
        _say("It stopped before it finished. Run this command again to deploy your changes.")
        return 1
    if code != 0:
        _say("It failed; the lines above say why. Fix that, then run this command again.")
        return code
    if ended.get("kind") != kind:
        what = KINDS.get(str(ended.get("kind")), "another deploy")
        _say(f"It finished, but it was {what}. Run this command again to deploy your changes.")
        return 1
    at = f"{started:%H:%M:%S} UTC" if started else "the time it started"
    _say(f"It finished. It deployed your files as they were at {at}; if you changed one "
         "since, run this command again.")
    return 0


def _running_locks(repo: Path) -> Iterator[Path]:
    for lock in sorted((repo / ".agentcore-project").glob("*.deploy.lock")):
        if running(lock):
            yield lock


def running_message(repo: Path, *, now: Now = _utc_now) -> str:
    """Which deploy of this checkout is running now, in a refusal's words, or nothing."""
    for lock in _running_locks(repo):
        return f"{_describe(_read_holder(lock), now())} {STILL_RUNS}"
    return ""


def notice(repo: Path) -> str:
    """What a new terminal says when a deploy is running, or nothing."""
    for _ in _running_locks(repo):
        return ("A deploy is still running, in a terminal this window does not show.\n"
                f"To follow it here, run the deploy command again:\n  {DEPLOY_COMMAND}\n")
    return ""


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--notice", action="store_true",
                      help="print a line when a deploy is running, and nothing otherwise")
    mode.add_argument("--refuse-if-running", action="store_true",
                      help="exit 1, saying why, when a deploy is running; exit 0 otherwise")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    if args.notice:
        sys.stdout.write(notice(args.repo))
        return 0
    busy = running_message(args.repo)
    if busy:
        print(wrapped(f"{busy} {REFUSE_RESET}"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
