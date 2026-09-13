"""The catalog seeder runs before the 002-onward migrations, so 001 must satisfy it.

`bootstrap-labs.sh::setup_database` applies `001_schema.sql`, then runs
`scripts/seed_pellier_catalog.py`, and only then loops over migrations 002
onward. A column the seeder writes that 001 does not define therefore fails on
a fresh cluster, and because the seeder's non-zero return leaves that function
early, the whole migration loop is skipped too: the box comes up with an empty
catalog and no workshop schema, behind a warning.

That shipped once. `persona_id` was added to the seeder's INSERT while the
column was created by migration 029, which runs after the seed. These tests
pin the ordering contract so the next column cannot repeat it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCHEMA = REPO / "scripts" / "migrations" / "001_schema.sql"
SEEDER = REPO / "scripts" / "seed_pellier_catalog.py"
BOOTSTRAP = REPO / "scripts" / "bootstrap-labs.sh"

_TABLE = "pellier.product_catalog"


def _columns_defined_by_the_base_schema() -> set[str]:
    """Every product_catalog column 001 creates, including its ALTER additions."""
    sql = SCHEMA.read_text()
    start = sql.index(f"CREATE TABLE IF NOT EXISTS {_TABLE}")
    body = sql[start : sql.index(");", start)]
    columns = {
        match.group(1).strip('"')
        for match in re.finditer(r'^\s{4}("?[A-Za-z_][A-Za-z0-9_]*"?)\s+\S', body, re.M)
    }
    for match in re.finditer(
        rf'ALTER TABLE {re.escape(_TABLE)}\s+ADD COLUMN IF NOT EXISTS\s+("?[A-Za-z_]\w*"?)',
        sql,
    ):
        columns.add(match.group(1).strip('"'))
    return columns


def _columns_the_seeder_writes() -> set[str]:
    """The column list of the seeder's INSERT into product_catalog."""
    source = SEEDER.read_text()
    start = source.index(f"INSERT INTO {_TABLE}")
    column_list = source[source.index("(", start) + 1 : source.index(")", start)]
    return {
        token.strip().strip('"')
        for token in column_list.split(",")
        if token.strip()
    }


def test_the_base_schema_defines_every_column_the_seeder_writes() -> None:
    """A seeder column missing from 001 is a fresh-cluster provisioning failure."""
    defined = _columns_defined_by_the_base_schema()
    written = _columns_the_seeder_writes()
    missing = sorted(written - defined)
    assert not missing, (
        f"{sorted(missing)} are written by scripts/seed_pellier_catalog.py but not "
        "defined in scripts/migrations/001_schema.sql. Bootstrap seeds before the "
        "002-onward migration loop, so the seed fails on a fresh cluster, "
        "setup_database returns early, and no later migration is applied. Add the "
        "column to 001 as an idempotent ADD COLUMN IF NOT EXISTS; the migration "
        "that assigns its values can still land later."
    )


def test_the_seeder_still_runs_before_the_migration_loop() -> None:
    """Pin the ordering the first test assumes, so it cannot silently stop applying."""
    body = BOOTSTRAP.read_text()
    seed = body.index("seed_pellier_catalog.py --from-cache")
    schema = body.index("Applying migration 001_schema.sql")
    loop = body.index("for migration in", seed)
    assert schema < seed < loop, (
        "bootstrap no longer applies 001, then seeds, then loops over the rest. "
        "If the seeder now runs after the migration loop, this contract is obsolete "
        "and both tests in this file should be reconsidered."
    )


# Failure propagation is exercised under Bash in test_bootstrap_failure_regressions:
# both dependencies must succeed, or bootstrap exits with its FAILED state intact.
