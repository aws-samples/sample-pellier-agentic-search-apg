"""The specialist-agent vocabulary is frozen. This test stops it drifting back.

Three agents (Shopping, Stock, Support) sit behind a deterministic Router. The
labels are *display* names, which makes the failure mode quiet: a stale label
does not raise, it just shows the wrong word in the Observatory or silently
stops matching a key.

Four rules, all enforced below.

1. **Retired labels must not reappear** outside the documented migration
   history.

2. **Every canonical agent has a module and names its own label.**

3. **No agent label may appear in a specialist's own system prompt.**
   ``VOICE.md`` forbids the word "agent" in anything the shopper can hear, and
   ``test_copy_compliance`` enforces that mechanically for ``pellier_copy.py``.
   A prompt that opens "You are Pellier's Stock agent" invites the model to
   echo the phrase into the shopper's transcript. The architecture label belongs
   to the Observatory, the fixtures, and the docs; the prompt says "specialist".

4. **Internal keys and factory names must NOT be renamed for cosmetic parity.**
   ``build_stock_agent`` is imported by the dispatcher and exported by its
   solution twin. Bootstrap auto-applies solution twins by filename, and a twin that no longer
   exports the name the dispatcher imports fails as an ImportError at the first
   shopper turn - which has happened before.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "pellier" / "backend"

# The frozen vocabulary: internal key -> display label -> module.
CANONICAL_AGENTS = {
    "shopping": ("Shopping agent", "shopping_agent"),
    "stock": ("Stock agent", "stock_agent"),
    "support": ("Support agent", "support_agent"),
}

# Retired display labels. These may appear only in the allow-listed history.
# The second generation is assembled so this file does not itself carry them.
RETIRED_AGENT_LABELS = (
    "Style Advisor",
    "Curator",
    "Value Analyst",
    "Stock Keeper",
    "Experience Guide",
)

# The five-specialist labels this architecture replaced. Checked only in
# backend source (not tests, docs or the README, which a later cut rewrites).
RETIRED_FIVE_AGENT_LABELS = (
    *(
        f"{word} Agent"
        for word in ("Search", "Personalization", "Pricing", "Inventory", "Customer Service")
    ),
)

# Internal identifiers that must survive for the dispatcher and solution twins.
PROTECTED_IDENTIFIERS = (
    "build_shopping_agent",
    "build_stock_agent",
    "build_support_agent",
)

# Files whose job is to name what was renamed.
ALLOWED_HISTORY = {
    "pellier/backend/tests/test_agent_vocabulary.py",
    "docs/superpowers/specs/2026-08-26-three-shoppers-governed-arc.md",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", ".worktrees",
    ".agentcore-project", ".pytest_cache", ".venv", ".mypy_cache", ".ruff_cache",
    # Gitignored coordination artifacts: implementation plans, per-package
    # reports, and review packages. A report that explains why a retired name
    # had to be removed has to name it, so scanning these turns the write-up
    # into the finding, which is noise rather than drift. Neither directory
    # ships: `docs/*` and `.superpowers/` are both gitignored.
    "superpowers", ".superpowers",
}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".webp", ".avif", ".svg", ".ico", ".pdf", ".woff",
    ".woff2", ".ttf", ".zip", ".gz", ".pyc", ".map", ".csv", ".lock",
}
SKIP_NAMES = {"embeddings_cache.json", "package-lock.json"}


def _text_files():
    """Yield (repo-relative path, text) for every scannable file.

    Skip directories are matched against the path RELATIVE to the repo root. An
    absolute-path check silently excludes everything when the checkout lives
    under a `.worktrees/` directory, and a guard that inspects zero files passes
    forever.
    """
    scanned = 0
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(REPO)
        if any(part in SKIP_DIRS for part in rel_path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES or path.name in SKIP_NAMES:
            continue
        rel = rel_path.as_posix()
        if rel in ALLOWED_HISTORY:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        yield rel, text

    assert scanned > 200, (
        f"agent-vocabulary scan only inspected {scanned} files. The skip rules "
        "are excluding the repository; the guard is not actually checking "
        "anything."
    )


def test_no_retired_agent_label_survives() -> None:
    """A retired label outside the migration history is drift."""
    findings: list[str] = []
    for rel, text in _text_files():
        for retired in RETIRED_AGENT_LABELS:
            for match in re.finditer(rf"(?<![\w-]){re.escape(retired)}(?![\w-])", text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"  {rel}:{line}  {retired}")

    assert not findings, (
        "retired specialist labels found outside the documented migration "
        "history:\n" + "\n".join(sorted(findings)[:40])
        + "\n\nThe vocabulary is frozen. Use the current label, or add the file "
        "to ALLOWED_HISTORY if its job is to record the rename."
    )


def test_no_five_agent_label_survives_in_backend_source() -> None:
    """The Router reaches three agents; the five-agent labels are gone."""
    findings: list[str] = []
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND)
        if any(part in {"tests", ".venv", "__pycache__"} for part in rel.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for retired in RETIRED_FIVE_AGENT_LABELS:
            if retired in text:
                findings.append(f"  {rel.as_posix()}  {retired}")

    assert not findings, "retired agent labels in backend source:\n" + "\n".join(findings)


def test_every_canonical_agent_has_a_module_and_a_factory() -> None:
    """A frozen vocabulary that names an agent nobody builds is fiction."""
    for key, (label, module) in CANONICAL_AGENTS.items():
        path = BACKEND / "agents" / f"{module}.py"
        assert path.exists(), f"{label} has no module at agents/{module}.py"
        source = path.read_text()
        assert label in source, (
            f"agents/{module}.py never names its own label {label!r}"
        )


def test_no_specialist_prompt_names_itself_an_agent() -> None:
    """Rule 3. The label is architecture vocabulary, not the shopper's word.

    Asserted on the prompt constants rather than the whole module, because the
    modules legitimately use the label in docstrings, comments, and workshop
    markers - all of which the shopper never sees.
    """
    offenders: list[str] = []
    for _key, (label, module) in CANONICAL_AGENTS.items():
        source = (BACKEND / "agents" / f"{module}.py").read_text()
        for match in re.finditer(r"You are Pellier's ([^.\"]+)", source):
            described = match.group(1).strip()
            if re.search(r"(?<![\w-])agents?(?![\w-])", described, re.IGNORECASE):
                line = source.count("\n", 0, match.start()) + 1
                offenders.append(
                    f"  agents/{module}.py:{line}  \"You are Pellier's {described}\""
                )
            assert label != described, (
                f"agents/{module}.py opens its prompt with the architecture "
                f"label {label!r}"
            )

    copy_source = (BACKEND / "pellier_copy.py").read_text()
    for match in re.finditer(r"You are Pellier's ([^.\"]+)", copy_source):
        described = match.group(1).strip()
        if re.search(r"(?<![\w-])agents?(?![\w-])", described, re.IGNORECASE):
            line = copy_source.count("\n", 0, match.start()) + 1
            offenders.append(f"  pellier_copy.py:{line}  \"You are Pellier's {described}\"")

    assert not offenders, (
        "a specialist prompt describes itself with the word 'agent':\n"
        + "\n".join(offenders)
        + "\n\nVOICE.md forbids that word in anything the shopper can hear, and "
        "a prompt is the one place the model reads its own name. Say "
        "'specialist' in the prompt; keep the label for the Observatory."
    )


def test_protected_factory_names_are_not_renamed() -> None:
    """Rule 4. Bootstrap imports these by name from auto-applied twins."""
    sources = {
        module: (BACKEND / "agents" / f"{module}.py").read_text()
        for _label, module in CANONICAL_AGENTS.values()
    }
    joined = "\n".join(sources.values())
    for factory in PROTECTED_IDENTIFIERS:
        assert f"def {factory}(" in joined, (
            f"{factory} is gone. The dispatcher and the solution twin import it "
            "by name; renaming it for parity with the new label surfaces as an "
            "ImportError on the first shopper turn, not as a test failure here."
        )


def test_the_dispatcher_internal_keys_are_unchanged() -> None:
    """The routing keys are a lower-layer contract, not display text."""
    from services.intent_router import INTENTS
    from services.specialist_models import AGENT_NAMES

    assert set(INTENTS) == set(CANONICAL_AGENTS)
    assert set(AGENT_NAMES) == set(CANONICAL_AGENTS)
    assert {key: label for key, (label, _m) in CANONICAL_AGENTS.items()} == AGENT_NAMES
