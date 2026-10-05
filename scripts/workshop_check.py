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

import os
import pathlib
from dataclasses import dataclass, field
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


def render(finding: Finding) -> str:
    """The finding as the lines a participant reads."""
    lines = [
        f"Task {finding.task}  {finding.state}  {finding.title}",
        f"  Expected  {finding.expected}",
        f"  Observed  {finding.observed}",
    ]
    for index, line in enumerate(finding.evidence or ["(none)"]):
        lines.append(("  Evidence  " if index == 0 else "            ") + line)
    if finding.state != PROVED and finding.next_step:
        lines.append(f"  Next      {finding.next_step}")
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
