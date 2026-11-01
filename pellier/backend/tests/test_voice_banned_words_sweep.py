"""VOICE.md's banned words stay out of every authored shopper-facing surface.

VOICE.md bans "boutique", "luxury", "investment piece", "curated" and "exclusive"
in shopper copy, model prompts, runtime skills and product descriptions. The one
earlier scan covered only ``CATALOG_SYSTEM_PROMPT``; this sweeps the rest of the
authored text: the three agents' system prompts, the runtime skills, the
storefront copy, the frontend data files and the backend copy module.

Not swept: the 50,000-product catalog data, which is generated and covered by
its own provenance checks. ``services/operator_graph.py`` prompts belong to the
Operator surface and are outside this sweep; the files are read as source text,
so a prompt constant is checked wherever it is written in the listed files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

REPO = Path(__file__).resolve().parents[3]

BANNED = ("boutique", "luxury", "investment piece", "curated", "exclusive")
BANNED_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in BANNED)
    + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _swept_files() -> List[Path]:
    patterns = (
        "pellier/backend/agents/*_agent.py",
        "skills/*/SKILL.md",
        "pellier/frontend/src/copy.ts",
        "pellier/frontend/src/data/*.ts",
        "pellier/frontend/src/data/*.json",
        "data/personas.json",
        "data/scenarios.json",
        "pellier/backend/pellier_copy.py",
    )
    return sorted({p for pattern in patterns for p in REPO.glob(pattern)})


def _hits(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8")
    return [
        f"{path.relative_to(REPO).as_posix()}:{number}  {match.group(0)}"
        for number, line in enumerate(text.splitlines(), 1)
        for match in BANNED_RE.finditer(line)
    ]


def test_the_sweep_reaches_every_surface() -> None:
    """A sweep over an empty glob passes forever."""
    names = {p.relative_to(REPO).as_posix() for p in _swept_files()}
    assert {
        "pellier/backend/agents/catalog_agent.py",
        "pellier/backend/agents/stock_agent.py",
        "pellier/backend/agents/support_agent.py",
        "pellier/frontend/src/copy.ts",
        "pellier/backend/pellier_copy.py",
        "data/personas.json",
        "data/scenarios.json",
    } <= names
    assert len([n for n in names if n.startswith("skills/")]) >= 5


def test_the_banned_pattern_matches_whole_words_in_any_casing() -> None:
    for text in ("Boutique", "LUXURY goods", "an Investment  Piece", "curated", "Exclusive."):
        assert BANNED_RE.search(text), text
    for text in ("excluded", "luxurious", "unexclusive", "curate"):
        assert not BANNED_RE.search(text), text


@pytest.mark.parametrize("path", _swept_files(), ids=lambda p: p.relative_to(REPO).as_posix())
def test_no_banned_word_in_authored_copy(path: Path) -> None:
    assert not _hits(path), "VOICE.md banned words:\n" + "\n".join(_hits(path))
