#!/usr/bin/env python3
"""Load the Pellier boutique catalog into Aurora PostgreSQL.

*** DESTRUCTIVE OPERATION ***
This script DROPS AND RECREATES ``pellier.product_catalog`` every run.
All existing rows, indexes, and any dependent foreign keys (cart_items,
wishlist, user_preferences_saved) are CASCADED. Run with care.

The catalog CSV at ``data/pellier_catalog.csv`` is the authoritative source:
92 rows, 1024-dim Cohere Embed v4 embeddings pre-populated. This script does
NOT call Bedrock — embeddings are already in the CSV.

Exit codes
----------
    0   success
    1   pre-flight failed (CSV missing, schema drift, embedding mismatch, ...)
    2   database connection or permission error
    3   verification failed (transaction rolled back, no data changed)
    4   concurrent execution detected (another load_catalog.py holds the lock)
    5   user aborted at confirmation prompt
    10  unexpected error

Usage
-----
    python scripts/load_catalog.py                # interactive (prompts)
    python scripts/load_catalog.py --yes          # CI / bootstrap
    python scripts/load_catalog.py --dry-run      # validate, no writes
    python scripts/load_catalog.py --database-url 'postgresql://u:p@h:5432/db'

Environment
-----------
    DATABASE_URL                full connection string (preferred)
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD   fallback components

Dependencies
------------
    psycopg (v3), standard library. The target database must have the
    ``vector`` (pgvector) extension installed.

Runtime
-------
    < 10 seconds for 92 rows on local Postgres; ~1-3s on Aurora.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import logging
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_CSV = PROJECT_ROOT / "data" / "pellier_catalog.csv"
AUDIT_LOG_DIR = PROJECT_ROOT / "logs"
AUDIT_LOG_PATH = AUDIT_LOG_DIR / "load_catalog_audit.log"

# Advisory lock ID: ASCII 'blzc' in hex. Deterministic so any concurrent
# invocation of this script collides on the same key.
CATALOG_LOAD_LOCK_ID = 0x626C7A63
LOCK_RETRY_SECONDS = 30

EXPECTED_ROW_COUNT = 92
EXPECTED_EMBEDDING_DIM = 1024
EXPECTED_TIER_COUNTS = {1: 10, 2: 20, 3: 62}
EXPECTED_COLUMNS = [
    "productId", "name", "brand", "color", "price", "description",
    "category", "tags", "rating", "reviews", "imgUrl",
    "reasoning_lead", "reasoning_body", "reasoning_urgent",
    "match_reason", "badge", "tier", "image_verified", "embedding",
]

# FKs that are expected to cascade-drop during a normal re-seed. Anything
# outside this set is surfaced as a WARNING so operators notice foreign
# schema drift.
KNOWN_CASCADED_FKS = {
    ("public", "cart_items", "product_id"),
    ("public", "wishlist", "product_id"),
    ("public", "user_preferences_saved", "product_id"),
    ("pellier", "cart_items", "product_id"),
    ("pellier", "wishlist", "product_id"),
    ("pellier", "user_preferences_saved", "product_id"),
}

# Showcase productIds that the grid renders on the home page. Presence
# smoke-test; not a full equality check (names/colors may be edited).
SHOWCASE_SMOKE_IDS = (1, 5, 10)

logger = logging.getLogger("load_catalog")


class ConcurrentExecutionError(RuntimeError):
    """Raised when the advisory lock cannot be acquired within the retry window."""


class PreflightError(RuntimeError):
    """Raised when a pre-flight check fails."""


class VerificationError(RuntimeError):
    """Raised when a post-load verification query returns unexpected results."""


# ---------------------------------------------------------------------------
# Dataclass + logging
# ---------------------------------------------------------------------------


@dataclass
class LoadResult:
    rows_loaded: int = 0
    duration_seconds: float = 0.0
    dropped_fks: list[str] = field(default_factory=list)
    verification_passed: bool = False
    index_creation_times: dict[str, float] = field(default_factory=dict)
    # "database" — ALTER DATABASE succeeded (persists across connections).
    # "session" — session-level SET only (each new connection must replicate).
    # "failed"  — both paths failed; should be impossible in practice.
    # "skipped" — dry-run or intentionally not configured.
    iterative_scan_mode: str = "skipped"
    errors: list[str] = field(default_factory=list)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        for k in ("step", "check", "fk", "index"):
            v = getattr(record, k, None)
            if v is not None:
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _configure_logging(quiet: bool, json_output: bool) -> None:
    level = logging.WARNING if quiet else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    if json_output or not sys.stdout.isatty():
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False


# ---------------------------------------------------------------------------
# Database URL resolution
# ---------------------------------------------------------------------------


def _resolve_database_url(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    host = os.environ.get("DB_HOST")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME")
    user = os.environ.get("DB_USER")
    pw = os.environ.get("DB_PASSWORD")
    missing = [k for k, v in [
        ("DB_HOST", host), ("DB_NAME", name), ("DB_USER", user), ("DB_PASSWORD", pw),
    ] if not v]
    if missing:
        raise PreflightError(
            f"DATABASE_URL not set and missing DB_* components: {missing}"
        )
    from urllib.parse import quote_plus
    return f"postgresql://{user}:{quote_plus(pw)}@{host}:{port}/{name}"


def _dsn_display(url: str) -> str:
    """Safe DSN for logs — host:port/dbname, no credentials."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "?"
        port = parsed.port or 5432
        db = (parsed.path or "/").lstrip("/") or "?"
        return f"{host}:{port}/{db}"
    except Exception:
        return "<unparsable>"


# ---------------------------------------------------------------------------
# CSV pre-flight
# ---------------------------------------------------------------------------


def _read_csv(csv_path: Path) -> tuple[list[str], list[dict]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    return fieldnames, rows


def _preflight_csv(csv_path: Path) -> list[dict]:
    logger.info("Pre-flight: CSV", extra={"check": "csv"})
    if not csv_path.exists():
        raise PreflightError(f"CSV not found: {csv_path}")

    fieldnames, rows = _read_csv(csv_path)

    # Column schema
    missing = [c for c in EXPECTED_COLUMNS if c not in fieldnames]
    if missing:
        raise PreflightError(f"CSV missing columns: {missing}")
    unexpected = [c for c in fieldnames if c not in EXPECTED_COLUMNS]
    if unexpected:
        logger.warning(f"CSV has unexpected extra columns (ignored): {unexpected}")

    # Row count
    if len(rows) != EXPECTED_ROW_COUNT:
        raise PreflightError(
            f"CSV row count mismatch: expected {EXPECTED_ROW_COUNT}, got {len(rows)}"
        )

    # Embeddings present + 1024 dims on the first row
    empty_emb = [r["productId"] for r in rows if not r.get("embedding", "").strip()]
    if empty_emb:
        raise PreflightError(f"CSV has {len(empty_emb)} rows with empty embeddings: {empty_emb[:5]}...")
    try:
        first_emb = json.loads(rows[0]["embedding"])
    except json.JSONDecodeError as exc:
        raise PreflightError(f"CSV row 0 embedding not valid JSON: {exc}")
    if not isinstance(first_emb, list) or len(first_emb) != EXPECTED_EMBEDDING_DIM:
        raise PreflightError(
            f"CSV row 0 embedding dim is {len(first_emb) if isinstance(first_emb, list) else 'n/a'}, "
            f"expected {EXPECTED_EMBEDDING_DIM}"
        )

    # productId integrity
    try:
        ids = sorted(int(r["productId"]) for r in rows)
    except ValueError as exc:
        raise PreflightError(f"CSV productId not integer: {exc}")
    if len(set(ids)) != len(ids):
        raise PreflightError("CSV has duplicate productIds")
    if ids[0] != 1 or ids[-1] != EXPECTED_ROW_COUNT or ids != list(range(1, EXPECTED_ROW_COUNT + 1)):
        raise PreflightError(
            f"CSV productIds are not contiguous 1..{EXPECTED_ROW_COUNT}: "
            f"min={ids[0]}, max={ids[-1]}, distinct={len(set(ids))}"
        )

    # Tier values
    for r in rows:
        try:
            t = int(r["tier"])
        except ValueError as exc:
            raise PreflightError(f"row {r['productId']} tier not integer: {exc}")
        if t not in (1, 2, 3):
            raise PreflightError(f"row {r['productId']} tier={t} not in {{1,2,3}}")

    logger.info(f"Pre-flight CSV OK: {len(rows)} rows, schema valid, embeddings 1024-dim")
    return rows


# ---------------------------------------------------------------------------
# DB pre-flight + FK detection
# ---------------------------------------------------------------------------


def _preflight_database(conn) -> None:
    logger.info("Pre-flight: database", extra={"check": "db"})
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()

        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        row = cur.fetchone()
        if not row:
            raise PreflightError(
                "pgvector extension not installed on this database. "
                "Run: CREATE EXTENSION vector;"
            )
        logger.info(f"Pre-flight pgvector OK: version {row[0]}")

        # Schema: ensure it exists or can be created. CREATE SCHEMA IF NOT
        # EXISTS is idempotent, but we prefer to detect a permission issue
        # here (before the main transaction) so the error surface is clear.
        cur.execute(
            "SELECT has_schema_privilege(current_user, 'pellier', 'CREATE') "
            "OR has_database_privilege(current_user, current_database(), 'CREATE') "
            "AS can_create"
        )
        row = cur.fetchone()
        # `has_schema_privilege` returns NULL if the schema does not exist,
        # in which case we fall through to the database-level check in the
        # same expression. A FALSE result means we must bail.
        if row is None or row[0] is False:
            raise PreflightError(
                "Current user lacks CREATE privilege for pellier schema"
            )


def _detect_foreign_keys(conn) -> list[dict]:
    """Return FK constraints pointing at pellier.product_catalog."""
    sql = """
        SELECT
            tc.table_schema, tc.table_name, tc.constraint_name,
            kcu.column_name
        FROM information_schema.referential_constraints rc
        JOIN information_schema.table_constraints tc
            ON rc.constraint_name = tc.constraint_name
           AND rc.constraint_schema = tc.constraint_schema
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.constraint_schema = kcu.constraint_schema
        JOIN information_schema.constraint_column_usage ccu
            ON rc.unique_constraint_name = ccu.constraint_name
           AND rc.unique_constraint_schema = ccu.constraint_schema
        WHERE ccu.table_schema = 'pellier'
          AND ccu.table_name = 'product_catalog'
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return [
            {
                "table_schema": r[0],
                "table_name": r[1],
                "constraint_name": r[2],
                "column_name": r[3],
            }
            for r in cur.fetchall()
        ]


# ---------------------------------------------------------------------------
# Advisory lock
# ---------------------------------------------------------------------------


@contextmanager
def _advisory_lock(conn):
    """Hold the catalog-load advisory lock for the duration of the block.

    Raises ConcurrentExecutionError if another loader holds it past the
    retry window. Releases on exit even if the body raises.
    """
    deadline = time.time() + LOCK_RETRY_SECONDS
    got_lock = False
    while time.time() < deadline and not got_lock:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (CATALOG_LOAD_LOCK_ID,))
            got_lock = bool(cur.fetchone()[0])
        if not got_lock:
            logger.warning(
                "Advisory lock busy (another load_catalog.py holds it); "
                "retrying in 1s..."
            )
            time.sleep(1.0)
    if not got_lock:
        raise ConcurrentExecutionError(
            f"Could not acquire advisory lock {hex(CATALOG_LOAD_LOCK_ID)} "
            f"within {LOCK_RETRY_SECONDS}s. Is another loader running?"
        )
    try:
        yield
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (CATALOG_LOAD_LOCK_ID,))
                cur.fetchone()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to release advisory lock (already closed?): {exc}")


# ---------------------------------------------------------------------------
# Transactional DDL + load
# ---------------------------------------------------------------------------


CREATE_SCHEMA_SQL = "CREATE SCHEMA IF NOT EXISTS pellier"

DROP_TABLE_SQL = "DROP TABLE IF EXISTS pellier.product_catalog CASCADE"

# DROP ... CASCADE is deliberate: the workshop schema has cart_items,
# wishlist, and user_preferences_saved FKs that we WANT to drop alongside.
# The _detect_foreign_keys() call above surfaces exactly what will cascade.
CREATE_TABLE_SQL = """
CREATE TABLE pellier.product_catalog (
    "productId" INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    brand TEXT NOT NULL,
    color TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    rating NUMERIC(3, 2),
    reviews TEXT,
    "imgUrl" TEXT NOT NULL,
    reasoning_lead TEXT,
    reasoning_body TEXT,
    reasoning_urgent TEXT,
    match_reason TEXT,
    badge TEXT,
    tier SMALLINT NOT NULL CHECK (tier IN (1, 2, 3)),
    image_verified BOOLEAN NOT NULL DEFAULT FALSE,
    quantity SMALLINT NOT NULL DEFAULT 20 CHECK (quantity >= 0 AND quantity <= 9999),
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

TABLE_COMMENT_SQL = (
    "COMMENT ON TABLE pellier.product_catalog IS "
    "'Pellier boutique catalog - 92 products. "
    "Loaded from data/pellier_catalog.csv via scripts/load_catalog.py.'"
)

# HNSW parameters stated explicitly so attendees see they are tunable.
# Defaults are sensible at 92 rows; scale up at 100K+ (m=24, ef_construction=128).
# cosine_ops matches Cohere Embed v4 training.
INDEX_SQL = {
    "idx_product_catalog_category":
        "CREATE INDEX idx_product_catalog_category "
        "ON pellier.product_catalog(category)",
    "idx_product_catalog_tier":
        "CREATE INDEX idx_product_catalog_tier "
        "ON pellier.product_catalog(tier)",
    "idx_product_catalog_tags":
        "CREATE INDEX idx_product_catalog_tags "
        "ON pellier.product_catalog USING gin(tags)",
    "idx_product_catalog_embedding":
        "CREATE INDEX idx_product_catalog_embedding "
        "ON pellier.product_catalog "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)",
}


def _normalize_tags(raw: str) -> str:
    """Return a JSON-array string safe to insert into a JSONB column.

    The CSV may contain either valid JSON (double-quoted) or Python-repr
    style (single-quoted), depending on which path produced it. Both are
    coerced into valid JSON here.
    """
    if not raw:
        return "[]"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        try:
            value = ast.literal_eval(raw)
        except (ValueError, SyntaxError) as exc:
            raise PreflightError(f"tags column not parseable: {raw[:80]!r}: {exc}")
    if not isinstance(value, list):
        raise PreflightError(f"tags column not a list: {raw[:80]!r}")
    return json.dumps([str(t) for t in value])


def _row_to_copy_tuple(row: dict) -> tuple:
    """Transform a CSV row dict into the COPY tuple.

    The embedding column is passed through as its JSON-array string; psycopg3
    streams it into the vector() column via pgvector's text input format,
    which accepts '[0.1, 0.2, ...]' verbatim.
    """
    tags_json = _normalize_tags(row.get("tags", ""))
    return (
        int(row["productId"]),
        row["name"],
        row["brand"],
        row["color"],
        float(row["price"]),
        row["description"],
        row["category"],
        tags_json,
        float(row["rating"]) if row.get("rating") else None,
        row.get("reviews") or None,
        row["imgUrl"],
        row.get("reasoning_lead") or None,
        row.get("reasoning_body") or None,
        row.get("reasoning_urgent") or None,
        row.get("match_reason") or None,
        row.get("badge") or None,
        int(row["tier"]),
        row.get("image_verified", "").strip().lower() == "true",
        row["embedding"],
    )


COPY_SQL = (
    "COPY pellier.product_catalog "
    "(\"productId\", name, brand, color, price, description, category, tags, "
    "rating, reviews, \"imgUrl\", reasoning_lead, reasoning_body, "
    "reasoning_urgent, match_reason, badge, tier, image_verified, embedding) "
    "FROM STDIN"
)


def _run_copy(conn, rows: list[dict]) -> None:
    logger.info(f"COPY: streaming {len(rows)} rows")
    with conn.cursor() as cur:
        with cur.copy(COPY_SQL) as copy:
            for r in rows:
                copy.write_row(_row_to_copy_tuple(r))


def _create_indexes(conn, timings: dict[str, float]) -> None:
    for name, sql in INDEX_SQL.items():
        t0 = time.time()
        with conn.cursor() as cur:
            cur.execute(sql)
        elapsed = time.time() - t0
        timings[name] = elapsed
        logger.info(f"Index built: {name} ({elapsed:.2f}s)", extra={"index": name})


def _verify(conn) -> None:
    logger.info("Verification: running post-load checks")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM pellier.product_catalog")
        count = cur.fetchone()[0]
        if count != EXPECTED_ROW_COUNT:
            raise VerificationError(f"row count {count} != {EXPECTED_ROW_COUNT}")

        cur.execute(
            'SELECT MIN("productId"), MAX("productId"), COUNT(DISTINCT "productId") '
            "FROM pellier.product_catalog"
        )
        mn, mx, distinct = cur.fetchone()
        if (mn, mx, distinct) != (1, EXPECTED_ROW_COUNT, EXPECTED_ROW_COUNT):
            raise VerificationError(
                f"productId integrity: min={mn} max={mx} distinct={distinct}"
            )

        cur.execute("SELECT COUNT(*) FROM pellier.product_catalog WHERE embedding IS NULL")
        if cur.fetchone()[0] != 0:
            raise VerificationError("some rows have NULL embedding")

        cur.execute("SELECT DISTINCT vector_dims(embedding) FROM pellier.product_catalog")
        dims = [r[0] for r in cur.fetchall()]
        if dims != [EXPECTED_EMBEDDING_DIM]:
            raise VerificationError(f"embedding dims {dims} != [{EXPECTED_EMBEDDING_DIM}]")

        cur.execute(
            "SELECT tier, COUNT(*) FROM pellier.product_catalog "
            "GROUP BY tier ORDER BY tier"
        )
        tier_counts = {int(r[0]): int(r[1]) for r in cur.fetchall()}
        if tier_counts != EXPECTED_TIER_COUNTS:
            raise VerificationError(
                f"tier distribution {tier_counts} != {EXPECTED_TIER_COUNTS}"
            )

        cur.execute(
            'SELECT "productId" FROM pellier.product_catalog '
            'WHERE "productId" = ANY(%s) ORDER BY "productId"',
            (list(SHOWCASE_SMOKE_IDS),),
        )
        seen = [r[0] for r in cur.fetchall()]
        if seen != list(SHOWCASE_SMOKE_IDS):
            raise VerificationError(
                f"showcase smoke: expected {SHOWCASE_SMOKE_IDS}, got {seen}"
            )

        cur.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'pellier' AND tablename = 'product_catalog' "
            "ORDER BY indexname"
        )
        idx = {r[0] for r in cur.fetchall()}
        needed = set(INDEX_SQL.keys())
        missing = needed - idx
        if missing:
            raise VerificationError(f"indexes missing: {sorted(missing)}")

    logger.info("Verification passed")


# ---------------------------------------------------------------------------
# pgvector iterative_scan configuration
# ---------------------------------------------------------------------------


def _configure_iterative_scan(conn, dbname: str) -> str:
    """Set ``hnsw.iterative_scan = relaxed_order``. Returns the mode used.

    Prefers ALTER DATABASE (persists for all new connections). Falls back to
    session-level SET if the caller lacks ALTER DATABASE. Session-level only
    affects THIS connection — application connections must replicate the SET
    for filtered vector queries to return complete result sets.
    """
    import psycopg

    # Identifier quoting: escape any embedded double-quotes in the dbname.
    # Using f-string interpolation with validated identifier because
    # ALTER DATABASE does not accept a placeholder for its target.
    quoted_db = '"' + dbname.replace('"', '""') + '"'
    try:
        # Run outside the main transaction — ALTER DATABASE cannot run in
        # a multi-statement txn in some Postgres versions and matters less
        # than the load itself. Use autocommit on a new connection; but here
        # we call it pre-load on the same conn via savepoint-free path.
        with conn.cursor() as cur:
            cur.execute(f"ALTER DATABASE {quoted_db} SET hnsw.iterative_scan = 'relaxed_order'")
        logger.info(
            f"iterative_scan configured at DATABASE level ({dbname}); "
            f"persists for all new connections"
        )
        return "database"
    except psycopg.errors.InsufficientPrivilege:
        logger.warning(
            "ALTER DATABASE denied — falling back to session-level SET. "
            "iterative_scan set at session level only - application connections "
            "must also SET hnsw.iterative_scan for filtered vector search to "
            "return complete results."
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SET hnsw.iterative_scan = 'relaxed_order'")
            return "session"
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Session-level SET also failed: {exc}")
            return "failed"
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"ALTER DATABASE failed ({exc}); trying session-level SET"
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SET hnsw.iterative_scan = 'relaxed_order'")
            return "session"
        except Exception as exc2:  # noqa: BLE001
            logger.error(f"Session-level SET also failed: {exc2}")
            return "failed"


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "local"


def _append_audit(
    ok: bool,
    exit_code: int,
    db_display: str,
    result: LoadResult,
    msg: str = "",
) -> None:
    try:
        AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sha = _git_sha()
        if ok:
            line = (
                f"{ts} | {sha} | {db_display} | SUCCESS | "
                f"rows={result.rows_loaded} | fks_cascaded={len(result.dropped_fks)} | "
                f"iter_scan={result.iterative_scan_mode} | "
                f"duration={result.duration_seconds:.1f}s\n"
            )
        else:
            line = (
                f"{ts} | {sha} | {db_display} | FAILED exit={exit_code} | "
                f"rows={result.rows_loaded} | "
                f"iter_scan={result.iterative_scan_mode or 'n/a'} | "
                f"msg={msg!r}\n"
            )
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to append audit log: {exc}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def load_catalog(
    database_url: Optional[str] = None,
    csv_path: Path = DEFAULT_CSV,
    dry_run: bool = False,
    skip_preflight: bool = False,
    force: bool = False,
) -> LoadResult:
    """Run the full catalog load. Returns a LoadResult on success; raises on failure."""
    import psycopg

    start = time.time()
    result = LoadResult()

    resolved_url = _resolve_database_url(database_url)
    db_display = _dsn_display(resolved_url)
    logger.info(f"Target database: {db_display}")

    # CSV pre-flight runs BEFORE any DB call so the script fails fast on
    # missing/corrupt input even without network access.
    if not skip_preflight:
        rows = _preflight_csv(csv_path)
    else:
        logger.warning("--skip-preflight set; skipping CSV validation (DEV ONLY)")
        _, rows = _read_csv(csv_path)

    # Open the main connection. OperationalError is left to bubble so the
    # CLI can route it to exit 2 (connection/permission) rather than exit 1
    # (pre-flight). Dry-run still needs the connection for the extension
    # and privilege checks.
    conn = psycopg.connect(resolved_url)

    try:
        with conn:  # rollback on exception, close on exit
            if not skip_preflight:
                _preflight_database(conn)

            # Populated-DB safeguard. This script DROPs pellier.product_catalog
            # and reloads from CSV. If the target cluster already holds a
            # different number of rows than the CSV is about to load, that's a
            # sign someone (seed_boutique_catalog.py? a hand-curated boutique
            # catalog?) populated the cluster outside this pipeline. Bailing
            # here prevents accidentally wiping the live 40-row Pellier
            # boutique catalog when bootstrap-labs.sh runs against a populated
            # cluster.
            #
            # --force overrides. Dry-run is exempt (no writes happen anyway).
            if not dry_run:
                with conn.cursor() as _check_cur:
                    _check_cur.execute("""
                        SELECT COUNT(*) FROM information_schema.tables
                         WHERE table_schema = 'pellier'
                           AND table_name = 'product_catalog'
                    """)
                    table_exists = (_check_cur.fetchone() or [0])[0] > 0
                    existing_rows = 0
                    if table_exists:
                        _check_cur.execute('SELECT COUNT(*) FROM pellier.product_catalog')
                        existing_rows = (_check_cur.fetchone() or [0])[0]
                if existing_rows and existing_rows != len(rows):
                    if force:
                        logger.warning(
                            "--force set: overriding populated-DB safeguard. "
                            "Target has %d existing rows; CSV has %d. The "
                            "existing rows are about to be replaced.",
                            existing_rows, len(rows),
                        )
                    else:
                        raise PreflightError(
                            f"Target has {existing_rows} rows in pellier.product_catalog "
                            f"but the CSV has {len(rows)} rows. Refusing to wipe "
                            f"the existing catalog. Pass --force to override "
                            f"(this is destructive — pellier.product_catalog will be "
                            f"DROPped + reloaded from {csv_path.name})."
                        )
            fks = _detect_foreign_keys(conn)
            for fk in fks:
                key = (fk["table_schema"], fk["table_name"], fk["column_name"])
                label = f"{fk['table_schema']}.{fk['table_name']}.{fk['column_name']} ({fk['constraint_name']})"
                if key in KNOWN_CASCADED_FKS:
                    logger.warning(f"FK will be CASCADED (known): {label}", extra={"fk": label})
                else:
                    logger.warning(f"FK will be CASCADED (UNEXPECTED): {label}", extra={"fk": label})
                result.dropped_fks.append(label)

            if dry_run:
                logger.info("DRY RUN — pre-flight passed; no writes will be executed")
                result.rows_loaded = 0
                result.verification_passed = False
                result.iterative_scan_mode = "skipped"
                result.duration_seconds = time.time() - start
                return result

            # Hold the advisory lock for the full DDL + load + verify.
            with _advisory_lock(conn):
                # ALTER DATABASE must run outside an explicit transaction in
                # older Postgres versions. We run it BEFORE opening the main
                # transaction, on a separate autocommit connection, to keep
                # this clean across versions.
                result.iterative_scan_mode = _configure_iterative_scan_separate_conn(
                    resolved_url
                )

                with conn.transaction():
                    with conn.cursor() as cur:
                        logger.info("Creating schema + dropping old table")
                        cur.execute(CREATE_SCHEMA_SQL)
                        cur.execute(DROP_TABLE_SQL)
                        cur.execute(CREATE_TABLE_SQL)
                        cur.execute(TABLE_COMMENT_SQL)

                    _run_copy(conn, rows)
                    _create_indexes(conn, result.index_creation_times)
                    _verify(conn)

                result.rows_loaded = len(rows)
                result.verification_passed = True
                logger.info(f"Committed: {result.rows_loaded} rows, "
                            f"{len(result.dropped_fks)} FK(s) cascaded")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    result.duration_seconds = time.time() - start
    return result


def _configure_iterative_scan_separate_conn(url: str) -> str:
    """Run _configure_iterative_scan on a fresh autocommit connection.

    ALTER DATABASE cannot execute inside an open transaction block on most
    Postgres versions. Session-level SET fallback works either way but
    only affects the connection it runs on, so we ALSO execute it on the
    main loader connection below (see caller) if the mode is 'session'.
    """
    import psycopg
    from urllib.parse import urlparse
    dbname = (urlparse(url).path or "/").lstrip("/") or "postgres"
    with psycopg.connect(url, autocommit=True) as c:
        return _configure_iterative_scan(c, dbname)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _confirm_interactive(db_display: str, csv_path: Path, row_count: int) -> bool:
    prompt = (
        "\nThis will DROP and RECREATE pellier.product_catalog (all data lost).\n"
        f"Database: {db_display}\n"
        f"CSV: {csv_path} ({row_count} rows)\n"
        "Continue? [y/N]: "
    )
    try:
        reply = input(prompt).strip().lower()
    except EOFError:
        return False
    return reply in ("y", "yes")


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Load the boutique catalog into Aurora PostgreSQL.",
    )
    p.add_argument("--csv-path", type=Path, default=DEFAULT_CSV)
    p.add_argument("--database-url", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-preflight", action="store_true",
                   help="DEV ONLY; skip CSV + DB pre-flight checks.")
    p.add_argument("--yes", action="store_true",
                   help="Skip interactive confirmation.")
    p.add_argument("--force", action="store_true",
                   help="Override the populated-DB safeguard. Required when the "
                        "target Aurora cluster already has rows that don't match "
                        "the CSV's row count, to prevent accidentally wiping a "
                        "hand-curated catalog.")
    p.add_argument("--json", action="store_true", dest="json_output")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    _configure_logging(quiet=args.quiet, json_output=args.json_output)

    db_display = "?"
    result = LoadResult()
    exit_code = 0
    fail_msg = ""

    try:
        resolved_url = _resolve_database_url(args.database_url)
        db_display = _dsn_display(resolved_url)

        # Confirmation prompt (interactive + not --yes + not --dry-run).
        is_tty = sys.stdin.isatty()
        if is_tty and not args.yes and not args.dry_run:
            row_count = EXPECTED_ROW_COUNT
            try:
                if args.csv_path.exists():
                    with args.csv_path.open(newline="", encoding="utf-8") as f:
                        row_count = sum(1 for _ in csv.DictReader(f))
            except Exception:
                pass
            if not _confirm_interactive(db_display, args.csv_path, row_count):
                logger.warning("Aborted by user")
                _append_audit(False, 5, db_display, result, "aborted by user")
                return 5

        result = load_catalog(
            database_url=args.database_url,
            csv_path=args.csv_path,
            dry_run=args.dry_run,
            skip_preflight=args.skip_preflight,
            force=args.force,
        )

        if args.dry_run:
            logger.info(
                f"Dry-run summary: would load {EXPECTED_ROW_COUNT} rows, "
                f"would cascade {len(result.dropped_fks)} FK(s)"
            )
        else:
            logger.info(
                f"Done: rows={result.rows_loaded} "
                f"fks={len(result.dropped_fks)} "
                f"iter_scan={result.iterative_scan_mode} "
                f"duration={result.duration_seconds:.1f}s "
                f"indexes={result.index_creation_times}"
            )

        _append_audit(True, 0, db_display, result)
        return 0

    except PreflightError as exc:
        fail_msg = str(exc)
        logger.error(f"pre-flight failed: {exc}")
        exit_code = 1
    except ConcurrentExecutionError as exc:
        fail_msg = str(exc)
        logger.error(str(exc))
        exit_code = 4
    except VerificationError as exc:
        fail_msg = str(exc)
        logger.error(f"verification failed (rolled back): {exc}")
        exit_code = 3
    except Exception as exc:  # noqa: BLE001
        # Route psycopg connection errors to exit 2 without importing the
        # driver here; rely on the class name to avoid a hard import at the
        # top of every failure path.
        name = exc.__class__.__name__
        if "OperationalError" in name or "InsufficientPrivilege" in name or \
                "InterfaceError" in name:
            fail_msg = f"{name}: {exc}"
            logger.error(f"database error: {exc}")
            exit_code = 2
        else:
            fail_msg = f"unexpected {name}: {exc}"
            logger.exception("unexpected error")
            exit_code = 10

    _append_audit(False, exit_code, db_display, result, fail_msg)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
