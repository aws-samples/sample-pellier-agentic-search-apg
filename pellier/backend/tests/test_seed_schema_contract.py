"""The catalog seeder runs between the schema and the seed, so 001 must satisfy it.

`scripts/setup/database-setup.sh` (which bootstrap calls) applies `001_schema.sql`,
then runs `scripts/seed_pellier_catalog.py`, then applies `002_seed.sql`. A
column the seeder writes that 001 does not define fails on a fresh cluster, and
because the script exits on the seeder's non-zero return, the seed never runs.

That shipped once: `persona_id` was added to the seeder's INSERT while a later
migration created the column. These tests pin the ordering contract so the next
column cannot repeat it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCHEMA = REPO / "scripts" / "migrations" / "001_schema.sql"
SEEDER = REPO / "scripts" / "seed_pellier_catalog.py"
DATABASE_SETUP = REPO / "scripts" / "setup" / "database-setup.sh"

_TABLE = "pellier.product_catalog"


def _columns_defined_by_the_base_schema() -> set[str]:
    """Every product_catalog column 001 creates, including its ALTER additions."""
    sql = SCHEMA.read_text()
    start = sql.index(f"CREATE TABLE {_TABLE}")
    body = sql[start : sql.index("\n);", start)]
    return {
        match.group(1).strip('"')
        for match in re.finditer(r'^\s{4}("?[A-Za-z_][A-Za-z0-9_]*"?)\s+\S', body, re.M)
    }


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
        "defined in scripts/migrations/001_schema.sql. The catalog seeder runs right "
        "after 001, so the seed fails on a fresh cluster and database-setup.sh exits "
        "before 002_seed.sql. Add the column to the table in 001."
    )


def test_the_catalog_seeder_runs_between_the_schema_and_the_seed() -> None:
    """Pin the ordering the first test assumes, so it cannot silently stop applying."""
    body = DATABASE_SETUP.read_text()
    schema = body.index("apply 001_schema.sql")
    catalog = body.index("seed_pellier_catalog.py --from-cache")
    seed = body.index("apply 002_seed.sql")
    assert schema < catalog < seed, (
        "database setup no longer applies 001, then loads the catalog, then the seed."
    )


# Failure propagation is exercised under Bash in test_bootstrap_failure_regressions:
# both dependencies must succeed, or bootstrap exits with its FAILED state intact.
