"""No tracked file carries CRLF, and the trailing-whitespace debt cannot grow.

Why this exists rather than the shell gate
-----------------------------------------

`CLAUDE.md` lists `git diff --check` as a release gate, and it is the right check. It is
also easy to run in a way that proves nothing: run it against the WORKING TREE with
everything committed and it inspects an empty diff and exits 0. That happened, and a
passing gate was reported over 42 real offences in the commit range.

The offences were not hand-typed. `data/pellier_catalog_curated.csv` is written by
`csv.DictWriter`, whose `lineterminator` defaults to `\r\n` on every platform, so every
row the diff added carried a bare carriage return that `git diff --check` reads as
trailing whitespace. Nobody would find that by looking at the file.

So these checks run against the FILES. There is no revision range to get wrong, and they
fail the same way on a clean tree as on a dirty one.

Two different rules, and the asymmetry is deliberate
----------------------------------------------------

**CRLF is zero tolerance.** It is never intentional here and it has a single fixable
cause per generator.

**Trailing whitespace is a non-regression ceiling**, not zero. 527 such lines predate this
work across 20 files, and stripping them repo-wide is NOT safe: 106 of them sit inside
multi-line string literals, including model prompts in `services/agent_tools.py` and its
solution twins. Rewriting those changes what the model is told, which is a behavioural
change wearing a formatting change's clothes. Anyone reducing this ceiling should strip
only lines outside string literals, verify with `ast`, and keep the solution twins
byte-identical so `test_solutions_parity.py` still passes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parents[3]

TEXT_SUFFIXES = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".sql", ".sh", ".md", ".yml",
    ".yaml", ".css", ".html", ".cedar", ".dogwood", ".txt", ".csv", ".cfg",
    ".toml", ".svg", ".lock",
)
SKIP_PARTS = ("node_modules", "/dist/", "/build/", "__pycache__", ".venv", "audit/")

# Measured after fixing the offences in this commit range. A ceiling, not a target: it may
# fall, and must never rise.
TRAILING_WHITESPACE_CEILING = 527

# Files this effort owns. Zero tolerance here, because there is no legacy excuse for them.
OWNED = (
    "data/pellier_catalog_curated.csv",
    "pellier/backend/services/operator_graph.py",
    "pellier/backend/services/operator_review.py",
    "pellier/backend/services/governed_execution.py",
    "pellier/backend/routes/operator.py",
    "scripts/audit_product_assets.py",
    "scripts/describe_workshop_publication.py",
    "scripts/deploy/sdk_preflight.py",
    "scripts/deploy/plan_restock_alignment.py",
)


def _tracked_text_files() -> List[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    out = []
    for rel in filter(None, listed):
        if any(part in f"/{rel}" for part in SKIP_PARTS):
            continue
        if not rel.endswith(TEXT_SUFFIXES):
            continue
        path = REPO / rel
        if path.is_file():
            out.append(path)
    return out


def _trailing_lines(path: Path) -> List[int]:
    return [
        number
        for number, line in enumerate(path.read_bytes().split(b"\n"), start=1)
        if line.rstrip(b" \t") != line
    ]


def test_the_scan_covers_the_repository() -> None:
    """A guard that inspects nothing passes forever."""
    assert len(_tracked_text_files()) > 200


def test_no_tracked_file_uses_crlf_line_endings() -> None:
    """A bare carriage return is what `git diff --check` calls trailing whitespace.

    Fix the generator, not the file: a hand-converted artifact comes back CRLF the next
    time its writer runs.
    """
    offenders = []
    for path in _tracked_text_files():
        raw = path.read_bytes()
        if b"\r\n" in raw:
            rel = path.relative_to(REPO).as_posix()
            offenders.append(f"  {rel}  ({raw.count(b'\r\n')} CRLF line ending(s))")
    assert not offenders, "tracked files with CRLF line endings:\n" + "\n".join(offenders)


def test_the_csv_writer_pins_its_line_terminator() -> None:
    """The root cause, asserted at its source.

    `csv.writer` and `csv.DictWriter` default to `\r\n` regardless of platform, so an
    unpinned terminator reintroduces the whole class on the next regeneration.
    """
    source = (REPO / "scripts" / "seed_pellier_catalog.py").read_text(encoding="utf-8")
    assert 'lineterminator="\\n"' in source, (
        "seed_pellier_catalog.py must pin the CSV line terminator to \\n"
    )


def test_files_this_effort_owns_have_no_trailing_whitespace() -> None:
    findings = []
    for rel in OWNED:
        path = REPO / rel
        if not path.is_file():
            continue
        for number in _trailing_lines(path):
            findings.append(f"  {rel}:{number}")
    assert not findings, "trailing whitespace in owned files:\n" + "\n".join(findings)


def test_the_trailing_whitespace_debt_does_not_grow() -> None:
    """A ceiling on inherited debt, so new damage fails without forcing a risky sweep."""
    total = sum(len(_trailing_lines(path)) for path in _tracked_text_files())
    assert total <= TRAILING_WHITESPACE_CEILING, (
        f"trailing-whitespace lines rose to {total}, above the recorded ceiling of "
        f"{TRAILING_WHITESPACE_CEILING}. Strip the lines you added rather than raising "
        "the ceiling."
    )
