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

from pathlib import Path
from typing import Dict, Iterator, List, Tuple


REPO = Path(__file__).resolve().parents[3]

# Retired names, in every casing and separator they were written with.
RETIRED = (
    "agent-trace",
    "agent_trace",
    "AgentTrace",
    "agentTrace",
    "AGENT_TRACE",
    # The spaced display form and the `--at-` custom-property prefix were both
    # swept after this guard was first written, and neither was covered by the
    # tokens above. 312 display strings and 2,264 variable references survived
    # a rename that looked complete.
    "Agent Trace",
    "AGENT TRACE",
    "--at-",
    "pellier-labs",
    "pellier_labs",
    "PellierLabs",
    "PELLIER_LABS",
    "Pellier Labs",
)

SCAN_SUFFIXES = {
    ".ts", ".tsx", ".js", ".jsx", ".css", ".py", ".sql",
    ".md", ".sh", ".json", ".yml", ".yaml", ".html",
}

SKIP_PARTS = {
    "node_modules", ".git", "dist", "build", "__pycache__",
    ".venv", "venv", ".pytest_cache", "coverage", "playwright-report",
    "test-results", ".kiro",
    # Generated build output, all of it gitignored. `.agentcore-project` holds
    # the CDK build cache, which stages vendored third-party source: Strands'
    # own `agent_trace` identifier collides with a retired Pellier surface name
    # and cannot be fixed by anyone here. A guard that fails on a dependency's
    # internals inside an ignored directory reports noise, not drift.
    ".agentcore-project", ".cache", ".cli",
    # Gitignored audit output. A retired-name census names retired names because
    # that is its subject, so scanning it turns the report into the finding.
    "audit",
    # Gitignored coordination artifacts: implementation plans, per-package
    # reports, and review packages. A report that explains why a retired name
    # had to be removed has to name it, so scanning these turns the write-up
    # into the finding. Same reasoning as the audit output above. Neither
    # directory ships: `docs/*` and `.superpowers/` are both gitignored.
    "superpowers", ".superpowers",
}

# The inspection surface's last name, matched case-insensitively so a CSS class,
# a route, a table and a display string are all caught by one token.
OBSERVATORY = "observatory"

# History is not current documentation and is never rewritten: dated release
# evidence and the design specs that record what was decided then. The specs
# directory is already skipped above as `superpowers`.
HISTORY_PREFIXES = ("docs/release-readiness/",)

# Frontend files that still name the retired surface in comments, class names
# or the localStorage keys a returning browser clears. Cut 5c owns
# `pellier/frontend/src` while this guard lands, so they are swept after it.
# The list may only shrink: a file that is not on it fails on its first
# mention, and nothing outside `pellier/frontend/` may be added.
PENDING_FRONTEND_SWEEP = frozenset({
    "pellier/frontend/src/__tests__/operator_type_floor.test.ts",
    "pellier/frontend/src/components/AnnouncementBar.tsx",
    "pellier/frontend/src/components/ChatFailureCard.tsx",
    "pellier/frontend/src/components/ChatOutcomeCards.test.tsx",
    "pellier/frontend/src/components/EditorialBrief.tsx",
    "pellier/frontend/src/components/Footer.test.tsx",
    "pellier/frontend/src/components/ProductArtifactCard.tsx",
    "pellier/frontend/src/contexts/AuthContext.test.tsx",
    "pellier/frontend/src/contexts/PersonaContext.tsx",
    "pellier/frontend/src/data/personaCurations.ts",
    "pellier/frontend/src/data/workshopJourneys.test.ts",
    "pellier/frontend/src/design/cssVars.ts",
    "pellier/frontend/src/design/primitives/index.ts",
    "pellier/frontend/src/hooks/useAgentChat.test.tsx",
    "pellier/frontend/src/hooks/useScrollAndFlash.ts",
    "pellier/frontend/src/services/chat.ts",
    "pellier/frontend/src/shared/AppErrorBoundary.test.tsx",
    "pellier/frontend/src/shared/AppErrorBoundary.tsx",
    "pellier/frontend/src/shared/DataTable.test.tsx",
    "pellier/frontend/src/shared/EmptyState.test.tsx",
    "pellier/frontend/src/shared/EmptyState.tsx",
    "pellier/frontend/src/shared/EvidenceCard.test.tsx",
    "pellier/frontend/src/shared/EvidenceCard.tsx",
    "pellier/frontend/src/shared/SectionEyebrow.test.tsx",
    "pellier/frontend/src/shared/SectionEyebrow.tsx",
    "pellier/frontend/src/shared/TraceChip.tsx",
    "pellier/frontend/src/shared/agentVocabulary.ts",
    "pellier/frontend/src/shared/governedTypes.ts",
    "pellier/frontend/src/shared/index.ts",
    "pellier/frontend/src/shared/primitives.css",
    "pellier/frontend/src/styles/chat-outcomes.css",
    "pellier/frontend/src/styles/daylight-bridge.css",
    "pellier/frontend/src/styles/governed-tokens.css",
    "pellier/frontend/src/utils/assetPath.test.ts",
    "pellier/frontend/src/utils/resolveProductImageUrl.ts",
    "pellier/frontend/tsconfig.build.json",
})

# Files permitted to name a retired path, each for a reason that would break if
# the name were updated. Keyed by repo-relative path.
ALLOWED: Dict[str, str] = {
    # Old bookmarks must still land on the storefront, and only the old path
    # can show that they do.
    "pellier/frontend/src/App.routes.test.tsx":
        "asserts that retired paths land on the storefront",
    # The invariant has to name what it retires to be actionable.
    "CLAUDE.md":
        "states the one-name rule by naming both retired names",
    # This file names what it forbids.
    "pellier/backend/tests/test_surface_naming.py":
        "the guard itself",
}


def _scanned_files() -> Iterator[Tuple[str, str]]:
    """Yield (repo-relative path, text) for every file the guards read."""
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if SKIP_PARTS & set(path.relative_to(REPO).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        yield path.relative_to(REPO).as_posix(), text


def _scan() -> List[Tuple[str, int, str]]:
    """Return (path, line, token) for every retired name outside ALLOWED."""
    findings: List[Tuple[str, int, str]] = []
    for relative, text in _scanned_files():
        if relative in ALLOWED:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for token in RETIRED:
                if token in line:
                    findings.append((relative, number, token))
    return findings


def _observatory_scan() -> List[Tuple[str, int]]:
    """Return (path, line) for every "observatory", in any casing, outside the exceptions."""
    findings: List[Tuple[str, int]] = []
    for relative, text in _scanned_files():
        if relative in ALLOWED or relative in PENDING_FRONTEND_SWEEP:
            continue
        if relative.startswith(HISTORY_PREFIXES):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if OBSERVATORY in line.lower():
                findings.append((relative, number))
    return findings


def test_the_scan_reaches_the_source_tree() -> None:
    """A scan that silently matched nothing would pass every test below."""
    scanned = [
        p for p in REPO.rglob("*.tsx")
        if p.is_file() and not (SKIP_PARTS & set(p.relative_to(REPO).parts))
    ]
    assert len(scanned) > 100, f"only {len(scanned)} .tsx files reachable"


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


def test_the_pending_sweep_is_frontend_only() -> None:
    """The pending list is for the files cut 5c owns, never a general escape hatch."""
    outside = sorted(p for p in PENDING_FRONTEND_SWEEP if not p.startswith("pellier/frontend/"))

    assert not outside, f"pending sweep entries outside the frontend: {outside}"


def test_every_allowance_is_still_needed() -> None:
    """An allowance whose file is clean is stale and hides the next regression."""
    stale = []
    for relative, reason in ALLOWED.items():
        path = REPO / relative
        if not path.exists():
            stale.append(f"{relative} (missing; reason was: {reason})")
            continue
        text = path.read_text(encoding="utf-8")
        named = any(token in text for token in RETIRED) or OBSERVATORY in text.lower()
        if not named:
            stale.append(f"{relative} (no retired name present; drop the allowance)")

    assert not stale, "stale allowances:\n" + "\n".join(f"  {s}" for s in stale)
