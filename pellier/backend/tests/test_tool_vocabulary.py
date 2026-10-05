"""The public tool vocabulary is frozen. This test stops it drifting back.

Tool identifiers were renamed from boutique names to plain functional ones, and
the set was then cut to nine tools. The names are load-bearing in places a
careless edit would not obviously break:

  * Cedar action identifiers embed them (``..._target___give_store_credit``), so a
    stale name means a policy that no longer matches its action;
  * ``tool_audit.tool`` records them, so evidence queries key off them;
  * the Lambda tool schemas publish them through the Gateway;
  * participant copy and the Operator UI show them.

Two rules, both enforced below.

1. **Old public names must not reappear** outside the documented migration
   history. A reintroduced ``floor_check`` in a prompt, a fixture, or a UI string
   is drift, not a typo.

2. **Database object names must NOT be renamed for cosmetic parity.**
   ``pellier.process_return_idempotent`` and ``pellier.restock_shelf_idempotent``
   keep their names even though no public tool carries them any more.
   Migration 016 grants EXECUTE against those exact identifiers; renaming them silently revokes permission on every deployed
   cluster and surfaces as a governed write that stops working in production.
   The mismatch is deliberate, so this test asserts it *stays*.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

# The frozen public vocabulary: the nine store tools.
CANONICAL_TOOLS = (
    "search_products",
    "browse_department",
    "compare_products",
    "check_stock",
    "get_orders",
    "get_return_policy",
    "get_tickets",
    "give_store_credit",
    "ask_a_person",
)

# The vocabulary the nine-tool set replaced. The names are assembled from parts
# so this file does not itself carry them, and they are checked only in the
# runtime sources that must never name them (migrations keep them as history).
_REPLACED_TOOL_PARTS = (
    ("initiate", "return"),
    ("issue", "credit"),
    ("escalate", "to", "human"),
    ("check", "inventory"),
    ("get", "ticket", "history"),
    ("restock", "inventory"),
    ("replace", "damaged", "item"),
    ("search", "products", "hybrid"),
    ("browse", "category"),
    ("get", "customer", "preferences"),
    ("get", "audit", "trail"),
    ("get", "trending", "products"),
    ("get", "related", "products"),
    ("get", "price", "analysis"),
    ("get", "low", "stock"),
)
REPLACED_TOOL_NAMES = tuple("_".join(parts) for parts in _REPLACED_TOOL_PARTS)
RUNTIME_SOURCE_ROOTS = ("pellier/backend", "scripts/deploy", "skills", "policies")

# Retired public names. These may appear only in the allow-listed history files.
RETIRED_TOOL_NAMES = (
    "floor_check",
    "running_low",
    "restock_shelf",
    "process_return",
    "find_pieces",
    "find_pieces_hybrid",
    "whats_trending",
    "price_intelligence",
    "explore_collection",
    "side_by_side",
    "returns_and_care",
    "style_match",
    "preference_snapshot",
    "trace_receipt",
    "escalate_to_stylist",
)

# Database identifiers that legitimately contain a retired name. Renaming any of
# these breaks a deployed GRANT or an unrelated API field.
PROTECTED_IDENTIFIERS = (
    "process_return_idempotent",
    "restock_shelf_idempotent",
    "running_low_count",
)

# Files whose job is to name what was renamed.
ALLOWED_HISTORY = {
    "pellier/backend/tests/test_tool_vocabulary.py",
    # The Gateway/Cedar vocabulary migration. Its whole job is to map retired
    # published names onto current ones, so it is the one runtime file that must
    # name both.
    "scripts/migrate_gateway_vocabulary.py",
    # Migration-only dispatch aliases, so the Lambda can serve the live Gateway's
    # retired names for the length of one release. Delete the map (and this
    # entry) once the Gateway has converged.
    "scripts/deploy/common/types.py",
    # Forward-only write-vocabulary convergence. It must name the historical
    # `process_return` value because the constraint deliberately keeps admitting
    # it: pre-rename evidence rows stay valid rather than being rewritten.
    "scripts/migrations/022_write_operation_vocabulary.sql",
    # Extends that same CHECK for replacement operations without invalidating
    # historical receipt rows that migration 022 deliberately retained.
    "scripts/migrations/052_replacement_recovery.sql",
    # Asserts that the retired names do NOT appear in the desired Gateway
    # schema, which requires naming them.
    "pellier/backend/tests/test_governed_execution.py",
    # Models the live pre-migration Gateway state, which is the retired
    # vocabulary, and asserts the migration converts it. It cannot do that
    # without naming both sides.
    "pellier/backend/tests/test_gateway_vocabulary_migration.py",
    # Asserts that a FRESH provision publishes no retired name and that the
    # generated Cedar names none either. Same shape as the two entries above: the
    # absence cannot be asserted without writing the names down once.
    "pellier/backend/tests/test_fresh_policy_set.py",
    "docs/superpowers/specs/2026-08-26-three-shoppers-governed-arc.md",
    "docs/superpowers/specs/2026-08-25-client-book-and-membership-design.md",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", ".worktrees", ".superpowers",
    ".agentcore-project", ".pytest_cache", ".venv", ".mypy_cache", ".ruff_cache",
    # Gitignored audit output, whose subject IS the retired vocabulary. Scanning it
    # makes the report of a rename into evidence that the rename did not happen.
    "audit",
}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".webp", ".avif", ".svg", ".ico", ".pdf", ".woff",
    ".woff2", ".ttf", ".zip", ".gz", ".pyc", ".map", ".csv", ".lock",
}
SKIP_NAMES = {"embeddings_cache.json", "package-lock.json"}


def _text_files():
    """Yield (repo-relative path, text) for every scannable file.

    Skip directories are matched against the path RELATIVE to the repo root, not
    the absolute path. An earlier version checked `path.parts`, which includes
    every component from `/` — and because this checkout lives under a
    `.worktrees/` directory, every single file was skipped and the scan silently
    covered nothing. A guard that inspects zero files passes forever.
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

    # A scan that covered nothing is a broken guard, not a clean repository.
    assert scanned > 200, (
        f"tool-vocabulary scan only inspected {scanned} files. The skip rules "
        "are excluding the repository; the guard is not actually checking "
        "anything."
    )


def _mask_protected(text: str) -> str:
    for token in PROTECTED_IDENTIFIERS:
        text = text.replace(token, "\x00")
    return text


def test_no_retired_public_tool_name_survives() -> None:
    """A retired name outside the migration history is drift."""
    findings: list[str] = []
    for rel, text in _text_files():
        masked = _mask_protected(text)
        for retired in RETIRED_TOOL_NAMES:
            # Word-bounded so a longer name does not trip on a shorter
            # one, and so a masked identifier cannot match.
            for match in re.finditer(rf"(?<![\w-]){re.escape(retired)}(?![\w-])", masked):
                line = masked.count("\n", 0, match.start()) + 1
                findings.append(f"  {rel}:{line}  {retired}")

    assert not findings, (
        "retired tool names found outside the documented migration history:\n"
        + "\n".join(sorted(findings)[:40])
        + "\n\nThe public vocabulary is frozen. Use the current identifier, or "
        "add the file to ALLOWED_HISTORY if its job is to record the rename."
    )


def test_every_canonical_tool_is_actually_defined() -> None:
    """A frozen vocabulary that names a tool nobody implements is fiction.

    The one implementation per tool lives in ``services/store_tools.py``; the
    agent wrappers and the Gateway Lambda both call it. ``give_store_credit``
    has no agent wrapper, so the shared module is the definition that counts.
    """
    store_tools = (
        REPO / "pellier" / "backend" / "services" / "store_tools.py"
    ).read_text()
    missing = [t for t in CANONICAL_TOOLS if f"def {t}(" not in store_tools]
    assert not missing, f"canonical tools with no shared implementation: {missing}"


def test_gateway_publishes_the_canonical_names() -> None:
    """Cedar actions embed these, so a mismatch breaks authorization."""
    import sys

    deploy = REPO / "scripts" / "deploy"
    if str(deploy) not in sys.path:
        sys.path.insert(0, str(deploy))
    from gateway_tool_schemas import canonical_tool_names

    published = set(canonical_tool_names())
    expected = set(CANONICAL_TOOLS)

    assert published == expected, (
        f"Gateway catalogue differs from the canonical nine: "
        f"missing {sorted(expected - published)}, extra {sorted(published - expected)}"
    )


def test_no_replaced_tool_name_survives_in_runtime_source() -> None:
    """The nine-tool cut deleted fifteen names; none may linger in runtime code."""
    findings: list[str] = []
    for root in RUNTIME_SOURCE_ROOTS:
        for path in sorted((REPO / root).rglob("*")):
            rel = path.relative_to(REPO)
            if not path.is_file() or path.suffix in SKIP_SUFFIXES:
                continue
            if any(part in SKIP_DIRS | {"tests"} for part in rel.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for name in REPLACED_TOOL_NAMES:
                if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text):
                    findings.append(f"  {rel.as_posix()}  {name}")

    assert not findings, "replaced tool names in runtime source:\n" + "\n".join(findings)


def test_the_one_write_function_keeps_its_name() -> None:
    """``store_tools.give_store_credit`` calls the function by this literal name."""
    schema = (REPO / "scripts" / "migrations" / "001_schema.sql").read_text()
    assert "CREATE FUNCTION pellier.apply_store_credit(" in schema
    for retired in ("process_return_idempotent", "restock_shelf_idempotent"):
        assert retired not in schema

    # The unrelated model field keeps its name.
    product_model = (REPO / "pellier" / "backend" / "models" / "product.py").read_text()
    assert "running_low_count" in product_model
