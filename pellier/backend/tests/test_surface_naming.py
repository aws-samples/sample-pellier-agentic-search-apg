"""Retired surface names stay retired.

The inspection surface was removed on 2026-10-03; Pellier is now the storefront
and the Operator desk. This guard keeps the names it went by from coming back:
"Observatory" in any casing, and the two names before it.

The surface has been renamed twice. "Observatory" and "Pellier Labs" each left
traces in a different layer: display strings, a route, an API prefix, source
directories, a CSS namespace, `data-testid` values, and a database table. A
partial rename is worse than either name, because a participant reading
"Pellier Observatory" in the chrome and `pellier-labs` in the URL cannot tell
which one the workshop guide means.

This scans the repository rather than a list of files. A rename that reaches
every file someone thought to check, and misses the one nobody did, is the
failure mode; only a sweep catches that.

A short allow-list below names the files that must keep a retired path,
each with the reason updating it would break something. Everything else
fails, and an allowance that stops being needed fails too.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, Iterator, List, Tuple


REPO = Path(__file__).resolve().parents[3]

# Retired names. Each pattern is matched case-insensitively, with the separator
# between words optional and any of "-", "_" or a space, so `Pellier Labs`,
# `pellier-Labs`, `PELLIER_LABS`, `PellierLabs`, `agent trace`, `Agent-Trace` and
# `agentTrace` are all one name.
RETIRED = (
    r"agent[-_ ]?trace",
    # The `--at-` custom-property prefix: 2,264 variable references survived a
    # rename that looked complete.
    r"--at-",
    # The inspection surface's second custom-property prefix, aliased in
    # daylight-bridge.css and consumed by the shared primitives until 2026-10-30.
    r"--obs-",
    r"pellier[-_ ]?labs",
)
RETIRED_RE = re.compile("|".join(RETIRED), re.IGNORECASE)

# The inspection surface's last name, matched in any casing so a CSS class,
# a route, a table and a display string are all caught by one token.
OBSERVATORY_RE = re.compile(r"observatory", re.IGNORECASE)

# Only tracked files are read, so gitignored output (build caches, vendored
# third-party source, local audit reports, coordination artifacts) never
# reaches the scan. What is skipped here is content that cannot hold text.
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".avif", ".pdf",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".zip", ".gz", ".tgz",
    ".parquet", ".npy", ".pptx", ".mp4", ".mov", ".webm", ".pyc",
}

# History is not current documentation and is never rewritten: dated release
# evidence and the design specs that record what was decided then. The design specs
# live under docs/superpowers/ and are history for the same reason.
HISTORY_PREFIXES = ("docs/release-readiness/", "docs/superpowers/")

# Files permitted to name a retired path, each for a reason that would break if
# the name were updated. Keyed by repo-relative path.
ALLOWED: Dict[str, str] = {
    # Old bookmarks must still land on the storefront, and only the old path
    # can show that they do.
    "pellier/frontend/src/App.routes.test.tsx":
        "asserts that retired paths land on the storefront",
    # A returning browser may still hold the retired chat keys; clearing them
    # needs the exact old key names.
    "pellier/frontend/src/contexts/PersonaContext.tsx":
        "clears localStorage keys that old browsers still hold",
    # The invariant has to name what it retires to be actionable.
    "CLAUDE.md":
        "states the one-name rule by naming both retired names",
    # A link to CLAUDE.md, for agents that read AGENTS.md: the same file.
    "AGENTS.md":
        "is CLAUDE.md under the name other coding agents read",
    # This file names what it forbids.
    "pellier/backend/tests/test_surface_naming.py":
        "the guard itself",
}


def _tracked_paths() -> List[str]:
    """Return every path git tracks, repo-relative."""
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [rel for rel in listed.split("\0") if rel]


def _scanned_files() -> Iterator[Tuple[str, str]]:
    """Yield (repo-relative path, text) for every tracked text file."""
    for relative in _tracked_paths():
        path = REPO / relative
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        yield relative, text


def _scan() -> List[Tuple[str, int, str]]:
    """Return (path, line, match) for every retired name outside the exceptions."""
    findings: List[Tuple[str, int, str]] = []
    for relative, text in _scanned_files():
        if relative in ALLOWED or relative.startswith(HISTORY_PREFIXES):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for match in RETIRED_RE.finditer(line):
                findings.append((relative, number, match.group(0)))
    return findings


def _observatory_scan() -> List[Tuple[str, int]]:
    """Return (path, line) for every "observatory", in any casing, outside the exceptions."""
    findings: List[Tuple[str, int]] = []
    for relative, text in _scanned_files():
        if relative in ALLOWED or relative.startswith(HISTORY_PREFIXES):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if OBSERVATORY_RE.search(line):
                findings.append((relative, number))
    return findings


def test_the_scan_reaches_the_source_tree() -> None:
    """A scan that silently matched nothing would pass every test below."""
    scanned = [relative for relative, _ in _scanned_files()]
    tsx = [p for p in scanned if p.endswith(".tsx")]
    assert len(tsx) > 100, f"only {len(tsx)} .tsx files reachable"
    assert len(scanned) > 500, f"only {len(scanned)} tracked text files reachable"


def test_every_casing_and_separator_of_a_retired_name_matches() -> None:
    """The patterns are the guard; prove them against the spellings that slipped."""
    spellings = [
        "pellier labs", "PELLIER LABS", "pellier-Labs", "Pellier_Labs", "PellierLabs",
        "agent trace", "Agent-Trace", "AGENT_TRACE", "agentTrace", "AgentTrace",
        "--AT-color", "--Obs-gap",
    ]
    missed = [s for s in spellings if not RETIRED_RE.search(s)]
    assert not missed, f"retired spellings the guard would miss: {missed}"
    assert OBSERVATORY_RE.search("OBSERVATORY") and OBSERVATORY_RE.search("Observatory")


def test_no_retired_surface_name_survives() -> None:
    findings = _scan()

    assert not findings, "retired surface names found:\n" + "\n".join(
        f"  {path}:{line}  {token}" for path, line, token in sorted(findings)[:40]
    )


def test_the_retired_inspection_surface_is_not_named() -> None:
    findings = _observatory_scan()

    assert not findings, '"Observatory" found outside history and the exceptions:\n' + "\n".join(
        f"  {path}:{line}" for path, line in sorted(findings)[:40]
    )


def test_every_allowance_is_still_needed() -> None:
    """An allowance whose file is clean is stale and hides the next regression."""
    stale = []
    for relative, reason in ALLOWED.items():
        path = REPO / relative
        if not path.exists():
            stale.append(f"{relative} (missing; reason was: {reason})")
            continue
        text = path.read_text(encoding="utf-8")
        named = bool(RETIRED_RE.search(text) or OBSERVATORY_RE.search(text))
        if not named:
            stale.append(f"{relative} (no retired name present; drop the allowance)")

    assert not stale, "stale allowances:\n" + "\n".join(f"  {s}" for s in stale)
