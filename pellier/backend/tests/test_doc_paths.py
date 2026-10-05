"""Every file path the front-door documents name exists.

A participant, reviewer or maintainer follows these documents to a file. When
a change renames or deletes that file, the document keeps pointing at it and
nothing goes red; that is how deleted scripts, routes and directories survived
in the docs before. This reads every back-tick span and fenced code block in
the documents below, takes each token that looks like a repository path, and
requires it to exist in this checkout.

A token counts as a path when it contains a slash or ends in a known file
suffix. Commands are read token by token, so `psql -f workshop/lab-1-rrf.sql`
checks the worksheet. URLs, routes (`/operator`), absolute and home paths,
placeholders (`<file>`, `$PWD`, `{actorId}`) and globs are not repository
paths and are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, List, Tuple

import pytest

REPO = Path(__file__).resolve().parents[3]

DOCS = (
    "CLAUDE.md",
    "WORKSHOP.md",
    "README.md",
    "solutions/README.md",
    "workshop/README.md",
)

# Where a document may name a path from: the repository root, the document's
# own directory, and the two app roots the docs abbreviate (`services/...`).
APP_ROOTS = ("pellier/backend", "pellier/frontend")

PATH_SUFFIXES = {
    ".py", ".sql", ".md", ".json", ".sh", ".cedar", ".ts", ".tsx", ".jq",
    ".yml", ".yaml", ".txt", ".lock", ".toml", ".csv", ".css", ".html",
    ".example",
}

# Local build output and environments: present on a developer's disk, never
# at HEAD, so they cannot be checked here.
LOCAL_ONLY = {".venv", "venv", "node_modules", "dist"}

_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_SPAN = re.compile(r"`([^`\n]+)`")
_NOT_A_PATH = re.compile(r"[<>${}*~@=]|://")


def _code_text(markdown: str) -> Iterator[str]:
    """Yield each fenced block, then each inline back-tick span outside them."""
    for block in _FENCE.finditer(markdown):
        yield block.group(1)
    yield from _SPAN.findall(_FENCE.sub("", markdown))


def _path_tokens(code: str) -> Iterator[str]:
    for raw in code.split():
        token = raw.strip("\"'(),;:").rstrip(".")
        if raw.endswith("/") and not token.endswith("/"):
            token += "/"
        if not token or token.startswith(("/", "-")) or _NOT_A_PATH.search(token):
            continue
        token = token.removeprefix("./")
        if token.split("/", 1)[0] in LOCAL_ONLY:
            continue
        if "/" in token or Path(token).suffix in PATH_SUFFIXES:
            yield token


def _exists(token: str, doc: str) -> bool:
    bases = ("", str(Path(doc).parent)) + APP_ROOTS
    return any((REPO / base / token).exists() for base in bases)


def _missing() -> List[Tuple[str, str]]:
    missing: List[Tuple[str, str]] = []
    for doc in DOCS:
        text = (REPO / doc).read_text(encoding="utf-8")
        for code in _code_text(text):
            missing.extend((doc, token) for token in _path_tokens(code) if not _exists(token, doc))
    return sorted(set(missing))


def test_the_scan_finds_paths_in_every_document() -> None:
    """A scan that matched nothing would pass the test below."""
    for doc in DOCS:
        text = (REPO / doc).read_text(encoding="utf-8")
        tokens = [token for code in _code_text(text) for token in _path_tokens(code)]
        assert tokens, f"{doc} names no repository path in back-ticks"


def test_every_named_path_exists() -> None:
    missing = _missing()

    assert not missing, "paths named in back-ticks that do not exist:\n" + "\n".join(
        f"  {doc}: {token}" for doc, token in missing
    )


@pytest.mark.parametrize(("code", "expected"), [
    ("psql -X -P pager=off -f workshop/lab-1-rrf.sql", ["workshop/lab-1-rrf.sql"]),
    ("cp solutions/a.py \\\n  pellier/backend/b.py", ["solutions/a.py", "pellier/backend/b.py"]),
    ("/operator", []),
    ("https://example.com/x.md", []),
    ("skills/<name>/SKILL.md", []),
    ("python3 scripts/workshop_evidence.py --save <file>", ["scripts/workshop_evidence.py"]),
    ("./.venv/bin/python -m pytest -q", []),
    ("pellier.tool_audit", []),
    ("cp .env.example .env", [".env.example"]),
    ("run scripts/lab1_compare.py.", ["scripts/lab1_compare.py"]),
])
def test_path_tokens(code: str, expected: List[str]) -> None:
    assert list(_path_tokens(code)) == expected
