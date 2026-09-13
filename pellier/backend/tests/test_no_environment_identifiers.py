"""No tracked file names a real AWS account or a specific deployment's resources.

The finding this closes
-----------------------

`scripts/deploy/ownership.py` pinned a real 12-digit account id, the live Gateway id,
the policy engine id, the Aurora cluster name and a Lambda code SHA as module
constants. The pinning itself is correct: the Gateway vocabulary migration mutates
named resources in one audited account, and running it elsewhere would change
something nobody reviewed. Publishing those values in an aws-samples repository is
not. Together they tell a reader exactly which resources to go looking for.

They are now read from the environment and the migration refuses to run without them,
so the hard stop survives and the identifiers do not ship. This test is what keeps
them out.

Why a 12-digit scan rather than a secret scanner
------------------------------------------------

An AWS account id is not a secret, so no credential scanner flags it. It is a
deployment identifier, which is a different problem with the same fix: it must not be
in tracked source. The scan below is therefore shaped around the false positives that
matter here, and every allowance is a documented example value rather than a path.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Set

REPO = Path(__file__).resolve().parents[3]

# Documentation account ids. AWS uses 123456789012 throughout its own docs, and its
# examples use three repeated four-digit blocks (111122223333, 444455556666) for a
# second and third party. This repository's fakes use the same forms on purpose, so a
# test can be wrong about an account without naming a real one.
ALLOWED_ACCOUNT_IDS: Set[str] = {"123456789012"}

# Three repeated four-digit blocks. Matched as a rule rather than enumerated so a new
# fake party in a future test does not have to be allow-listed by hand; no real
# account id has this shape.
FABRICATED_RE = re.compile(r"^(\d)\1{3}(\d)\2{3}(\d)\3{3}$")

ACCOUNT_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
# A public asset digest can contain twelve consecutive decimal digits. Exclude
# only complete SHA-256 values in explicitly named JSON digest fields, while
# continuing to inspect the rest of the same provenance document.
SHA256_FIELD_RE = re.compile(
    r'"(?:sha256|sourceSha256)"\s*:\s*"([0-9a-fA-F]{64})"'
)


def _account_candidates(text: str):
    hash_spans = [match.span(1) for match in SHA256_FIELD_RE.finditer(text)]
    return (
        match for match in ACCOUNT_RE.finditer(text)
        if not any(start <= match.start() and match.end() <= end for start, end in hash_spans)
    )


def test_asset_digests_do_not_hide_other_account_fields() -> None:
    account = "123456789012"
    digest = "ab" * 13 + account + "cd" * 13
    text = f'{{"sha256":"{digest}","accountId":"{account}"}}'
    matches = list(_account_candidates(text))
    assert len(matches) == 1
    assert matches[0].start() == text.rindex(account)
    # A short value masquerading as a checksum is still inspected.
    assert len(list(_account_candidates(f'{{"sha256":"{account}"}}'))) == 1

SCAN_SUFFIXES = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".sql", ".sh", ".md", ".yml",
    ".yaml", ".cedar", ".dogwood", ".txt", ".cfg", ".toml", ".html", ".css",
)

# Files whose 12-digit runs are not account ids. Each is a data file where a long
# numeric literal is ordinary content.
SKIP_PATHS: Set[str] = {
    "pellier/frontend/package-lock.json",
    "data/embeddings_cache.json",
    "data/pellier_catalog_curated.csv",
}

SKIP_DIR_PARTS = (
    "node_modules", "dist", "build", "__pycache__", ".venv", "audit",
)


def _tracked_text_files() -> List[Path]:
    """Only tracked files. An untracked local scratch file is not published."""
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    files = []
    for rel in filter(None, listed):
        if rel in SKIP_PATHS:
            continue
        if any(part in f"/{rel}" for part in SKIP_DIR_PARTS):
            continue
        if not rel.endswith(SCAN_SUFFIXES):
            continue
        path = REPO / rel
        if path.is_file():
            files.append(path)
    return files


def test_the_scan_covers_the_repository() -> None:
    """A guard that inspects nothing passes forever."""
    assert len(_tracked_text_files()) > 200


def test_no_tracked_file_contains_a_real_account_id() -> None:
    findings: List[str] = []
    for path in _tracked_text_files():
        rel = path.relative_to(REPO).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in _account_candidates(text):
            value = match.group(0)
            if value in ALLOWED_ACCOUNT_IDS or FABRICATED_RE.match(value):
                continue
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"  {rel}:{line}  {value}")
    assert not findings, (
        "these tracked files contain a 12-digit value that looks like an AWS account "
        "id. Read it from the environment, or use a documentation account id:\n"
        + "\n".join(sorted(set(findings))[:30])
    )


def test_the_migration_pins_come_from_the_environment() -> None:
    """The pins must be resolved, not literal, and unset must be a hard stop."""
    source = (REPO / "scripts" / "deploy" / "ownership.py").read_text(encoding="utf-8")
    for pin in (
        "EXPECTED_ACCOUNT", "EXPECTED_GATEWAY_ID", "EXPECTED_POLICY_ENGINE_ID",
        "EXPECTED_DB_CLUSTER", "EXPECTED_EXPERIENCE_SHA",
    ):
        assert re.search(rf"^{pin} = os\.environ\.get\(", source, re.M), (
            f"{pin} must be read from the environment, not written into source"
        )
    assert "def require_environment_pins()" in source


def test_the_migration_refuses_to_run_without_its_pins(monkeypatch) -> None:
    """An unset pin is worse than a wrong one.

    A preflight that compared two empty strings would report a match against any
    account in the world, which is the opposite of a hard stop.
    """
    import importlib
    import sys

    deploy = str(REPO / "scripts" / "deploy")
    if deploy not in sys.path:
        sys.path.insert(0, deploy)
    for name in (
        "PELLIER_EXPECTED_ACCOUNT", "PELLIER_EXPECTED_GATEWAY_ID",
        "PELLIER_EXPECTED_POLICY_ENGINE_ID", "PELLIER_EXPECTED_DB_CLUSTER",
        "PELLIER_EXPECTED_EXPERIENCE_SHA",
    ):
        monkeypatch.delenv(name, raising=False)

    import ownership

    reloaded = importlib.reload(ownership)
    try:
        assert set(reloaded.missing_environment_pins()) == set(reloaded.REQUIRED_PINS)
        try:
            reloaded.require_environment_pins()
        except SystemExit as exc:
            assert "refuses to run" in str(exc)
        else:  # pragma: no cover - the assertion above is the point
            raise AssertionError("require_environment_pins accepted an unpinned run")
    finally:
        # Other modules hold references to this module object, so leaving it reloaded
        # with empty pins would break any test that imported it earlier.
        monkeypatch.undo()
        importlib.reload(ownership)
