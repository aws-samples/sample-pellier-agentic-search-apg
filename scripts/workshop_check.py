"""What every workshop check shares: how it reaches Aurora, and how it reports.

Every check prints three things: what was expected, what was observed, and the
evidence behind it (the row, the decision, the key). A check that did not pass
also says what to look at next. The lab checks and the evidence export render
through :func:`render`, so a participant reads one shape everywhere.

A finding is in one of four states, never two:

    PROVED        a durable row exists and satisfies the claim
    NOT YET       the lab has not left its evidence
    UNCHECKED     the check could not look (no database, no psql, no settings)
    CONTRADICTED  the check looked and found evidence against the claim

The database settings are the backend's own, read from its ``.env`` as data and
never sourced, so a password holding ``$(...)`` stays a password. A variable in
the environment overrides the file.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

REPO = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ENV = REPO / "pellier" / "backend" / ".env"

PROVED = "PROVED"
NOT_YET = "NOT YET"
UNCHECKED = "UNCHECKED"
CONTRADICTED = "CONTRADICTED"
STATES = (PROVED, NOT_YET, UNCHECKED, CONTRADICTED)

_KEYS = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
_REQUIRED = ("DB_HOST", "DB_NAME", "DB_USER")


@dataclass
class Finding:
    """One task's verdict, with the three things every check prints.

    Attributes:
        task: The task label, for example ``1B``.
        title: The claim, in a few plain words.
        state: One of :data:`STATES`.
        expected: What must be true for the claim to hold.
        observed: What the check saw.
        evidence: The rows, decisions or keys behind the observation.
        next_step: What to look at next; empty when the claim is proved.
    """

    task: str
    title: str
    state: str
    expected: str
    observed: str
    evidence: List[str] = field(default_factory=list)
    next_step: str = ""


# A laptop-size Code Editor terminal is about 124 columns wide.
WIDTH = 120
_INDENT = " " * 12
# A command a participant may copy stays on one line: from its first word to the next
# clause break or the end of the sentence.
_COMMAND = re.compile(r"\b(?:psql|python3|bash|sudo) .*?(?=, |; |\. |\.?$)")


def _wrapped(label: str, text: str) -> List[str]:
    """One field as lines no wider than WIDTH, the label on the first."""
    kept = _COMMAND.sub(lambda match: match.group(0).replace(" ", "\0"), text)
    lines = textwrap.wrap(kept, width=WIDTH - len(_INDENT), break_long_words=False,
                          break_on_hyphens=False) or [""]
    first = f"  {label:<8}  " if label else _INDENT
    return [(first if index == 0 else _INDENT) + line.replace("\0", " ")
            for index, line in enumerate(lines)]


def render(finding: Finding) -> str:
    """The finding as the lines a participant reads, wrapped to the terminal."""
    lines = [f"Task {finding.task}  {finding.state}  {finding.title}"]
    lines += _wrapped("Expected", finding.expected)
    lines += _wrapped("Observed", finding.observed)
    for index, line in enumerate(finding.evidence or ["(none)"]):
        lines += _wrapped("Evidence" if index == 0 else "", line)
    if finding.state != PROVED and finding.next_step:
        lines += _wrapped("Next", finding.next_step)
    return "\n".join(lines)


def table(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """A plain left-aligned table, sized to its widest cell."""
    cells = [[str(value) for value in header]] + [[str(value) for value in row] for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(header))]
    return "\n".join(
        "  " + "  ".join(value.ljust(widths[i]) for i, value in enumerate(row)).rstrip()
        for row in cells
    )


def parse_dotenv(env_path: pathlib.Path) -> Dict[str, str]:
    """Read KEY=value lines from a dotenv file without shell interpolation."""
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            values[key] = value.strip().strip('"').strip("'")
    return values


def db_config(env_path: pathlib.Path = DEFAULT_ENV) -> Optional[Dict[str, str]]:
    """The database settings, or None when the host, name or user is missing.

    The password may be empty: a local cluster can trust its socket, and a box
    can keep it in ``~/.pgpass``.
    """
    cfg = parse_dotenv(env_path)
    for key in _KEYS:
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    if not all(cfg.get(key) for key in _REQUIRED):
        return None
    return cfg


def missing_settings_reason(env_path: pathlib.Path = DEFAULT_ENV) -> str:
    """The sentence a check prints when :func:`db_config` found nothing."""
    return f"no database settings ({', '.join(_REQUIRED)}) in {env_path} or the environment"


def connect(cfg: Dict[str, str], *, timeout: int = 15) -> Any:
    """Open one dict-row connection to the database ``cfg`` names.

    Raises:
        RuntimeError: psycopg is not installed for this interpreter.
        psycopg.Error: the database refused or could not be reached.
    """
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is not installed for this Python") from exc
    return psycopg.connect(
        host=cfg["DB_HOST"],
        port=int(cfg.get("DB_PORT") or 5432),
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg.get("DB_PASSWORD") or None,
        connect_timeout=timeout,
        row_factory=dict_row,
    )


def psql_environment(cfg: Dict[str, str]) -> Dict[str, str]:
    """The environment that points ``psql`` at the same database."""
    env = dict(os.environ)
    env.update(
        PGHOST=cfg["DB_HOST"],
        PGPORT=str(cfg.get("DB_PORT") or 5432),
        PGDATABASE=cfg["DB_NAME"],
        PGUSER=cfg["DB_USER"],
    )
    if cfg.get("DB_PASSWORD"):
        env["PGPASSWORD"] = cfg["DB_PASSWORD"]
    return env


# ---------------------------------------------------------------------------
# Reset points: evidence from before a lab was reset no longer counts
# ---------------------------------------------------------------------------
# tool_audit and retrieval_receipts are append-only, so a reset cannot delete the turns a
# lab left behind. `uv run scripts/lab_run.py reset --lab N` instead records the
# database's own clock in a small file, and each lab's checks read only the evidence
# created at or after it. The file lives under .local/, which a repair never touches and
# the full reset removes (it empties the tables anyway).
RESET_POINTS_ENV = "PELLIER_LAB_RESET_POINTS"
RESET_POINTS_FILE = REPO / ".local" / "lab-reset-points.json"
# Bind this as ``since``: no reset point (None) admits every row.
SINCE_SQL = "coalesce(%(since)s::timestamptz, '-infinity'::timestamptz)"


@dataclass(frozen=True)
class Timeline:
    """When a task's file last changed and when the backend last started; None if unknown."""

    edited_at: Optional[datetime]
    started_at: Optional[datetime]


def service_started(value: str) -> Optional[datetime]:
    """systemd's ActiveEnterTimestamp (``Wed 2026-10-14 14:46:19.479163 UTC``, or without the
    microseconds) as UTC; None otherwise."""
    if not value.endswith((" UTC", " GMT")):
        return None
    shape = "%a %Y-%m-%d %H:%M:%S.%f" if "." in value else "%a %Y-%m-%d %H:%M:%S"
    try:
        return datetime.strptime(value[:-4], shape).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def edit_timeline(edited_file: pathlib.Path) -> Timeline:
    """This box's timeline: the task file's modification time and pellier's systemd start."""
    try:
        edited: Optional[datetime] = datetime.fromtimestamp(edited_file.stat().st_mtime,
                                                            tz=timezone.utc)
    except OSError:
        edited = None
    # Microseconds: the solution command writes the file and restarts within one second, and
    # whole seconds would date that restart before the edit.
    try:
        shown = subprocess.run(
            ["systemctl", "show", "pellier", "-p", "ActiveEnterTimestamp", "--value",
             "--timestamp=us+utc"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        shown = ""
    return Timeline(edited, service_started(shown))


def clock(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%H:%M:%S UTC")


def reset_points_path() -> pathlib.Path:
    """Where the reset points live; the environment overrides it for tests."""
    override = os.environ.get(RESET_POINTS_ENV)
    return pathlib.Path(override) if override else RESET_POINTS_FILE


def _read_points(path: pathlib.Path) -> Dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def reset_point(lab: int) -> Optional[datetime]:
    """When the lab was last reset (timezone-aware), or None if it never was."""
    raw = _read_points(reset_points_path()).get(str(lab))
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def record_reset_point(lab: int, moment: datetime) -> None:
    """Remember that the lab was reset at ``moment``, keeping the other labs' points."""
    path = reset_points_path()
    points = _read_points(path)
    points[str(lab)] = moment.astimezone(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(points, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def clear_reset_points() -> None:
    """Forget every reset point, as a full reset does when it empties the tables."""
    reset_points_path().unlink(missing_ok=True)


def since_note(lab: int, send_again: str) -> str:
    """The sentence a NOT YET finding adds when the lab was reset, else an empty string."""
    moment = reset_point(lab)
    if moment is None:
        return ""
    clock = moment.strftime("%H:%M:%S UTC")
    return (f" You reset Lab {lab} at {clock}, so turns from before that no longer count: "
            f"send the requests again since your reset ({send_again}).")


def region_body(text: str, label: str) -> Optional[str]:
    """The lines between one ``WORKSHOP - <label>`` marker pair, or None without one.

    Works for both comment styles the starters use (``#`` and ``--``).
    """
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if f"WORKSHOP - {label}: START ===" in line]
    ends = [i for i, line in enumerate(lines) if f"WORKSHOP - {label}: END ===" in line]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        return None
    return "\n".join(lines[starts[0] + 1:ends[0]]).rstrip()


STARTER = "starter"
EDITED = "edited"
MISSING = "missing"


def region_state(path: pathlib.Path, label: str, starter: pathlib.Path) -> str:
    """Whether a marked region still holds the starter, was edited, or is gone.

    ``starter`` is either the starter fragment itself or a whole starter file
    carrying the same markers.
    """
    try:
        body = region_body(path.read_text(encoding="utf-8"), label)
        starter_text = starter.read_text(encoding="utf-8")
    except OSError:
        return MISSING
    if body is None:
        return MISSING
    expected = region_body(starter_text, label)
    if expected is None:
        expected = starter_text.rstrip()
    return STARTER if body == expected else EDITED


def short(value: Any, width: int = 12) -> str:
    """A long identifier cut to a readable prefix."""
    text = str(value or "")
    return text if len(text) <= width + 3 else text[:width] + "..."
