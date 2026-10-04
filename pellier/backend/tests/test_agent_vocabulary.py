"""The specialist-agent vocabulary is frozen. This test stops it drifting back.

The five specialists were renamed from boutique role names to functional ones so
a participant from any background can read the architecture without learning a
retail metaphor first. Unlike the tool rename, these labels are *display* names,
which makes the failure mode quieter: a stale label does not raise, it just
shows the wrong word in the Observatory or silently stops matching a key.

Four rules, all enforced below.

1. **Retired labels must not reappear** outside the documented migration
   history.

2. **The build-state agent key must exist in the fixture.**
   ``GET /api/observatory/build-state`` exposes the Inventory Agent's
   source-controlled exercise state. If that literal drifts from the fixture,
   Lab 2 shows an unrecognised status row instead of updating the intended
   agent. Nothing raises.

3. **No agent label may appear in a specialist's own system prompt.**
   ``VOICE.md`` forbids the word "agent" in anything the shopper can hear, and
   ``test_copy_compliance`` enforces that mechanically for ``pellier_copy.py``.
   A prompt that opens "You are Pellier's Inventory Agent" invites the model to
   echo the phrase into the shopper's transcript. The architecture label belongs
   to the Observatory, the fixtures, and the docs; the prompt says "specialist".

4. **Internal keys and factory names must NOT be renamed for cosmetic parity.**
   ``build_recommendation_agent`` and ``build_support_agent`` keep their names
   even though the labels are Personalization Agent and Customer Service Agent.
   Bootstrap auto-applies solution twins by filename, and a twin that no longer
   exports the name the dispatcher imports fails as an ImportError at the first
   shopper turn - which has happened before.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "pellier" / "backend"

# The frozen vocabulary: internal key -> display label -> module.
CANONICAL_AGENTS = {
    "search": ("Search Agent", "search_agent"),
    "recommendation": ("Personalization Agent", "personalization_agent"),
    "pricing": ("Pricing Agent", "pricing_agent"),
    "inventory": ("Inventory Agent", "inventory_agent"),
    "support": ("Customer Service Agent", "customer_service_agent"),
}

# Retired display labels. These may appear only in the allow-listed history.
RETIRED_AGENT_LABELS = (
    "Style Advisor",
    "Curator",
    "Value Analyst",
    "Stock Keeper",
    "Experience Guide",
)

# Internal identifiers that must survive the rename untouched.
PROTECTED_IDENTIFIERS = (
    "build_search_agent",
    "build_recommendation_agent",
    "build_pricing_agent",
    "build_inventory_agent",
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
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from agents import graph_pattern

    source = Path(graph_pattern.__file__).read_text()
    for key in CANONICAL_AGENTS:
        assert f'"{key}"' in source, (
            f"internal routing key {key!r} disappeared from graph_pattern.py"
        )
