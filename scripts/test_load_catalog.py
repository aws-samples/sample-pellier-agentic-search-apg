"""Tests for ``load_catalog``.

psycopg is mocked — no real database is touched. Each test builds a
temporary CSV with the minimum columns the loader needs.
"""

from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


CSV_FIELDS = [
    "productId", "name", "brand", "color", "price", "description",
    "category", "tags", "rating", "reviews", "imgUrl",
    "reasoning_lead", "reasoning_body", "reasoning_urgent",
    "match_reason", "badge", "tier", "image_verified", "embedding",
]


def _emb_str(dim: int = 1024, fill: float = 0.01) -> str:
    return json.dumps([fill] * dim, separators=(",", ":"))


def _minimal_row(pid: int, tier: int = 3, emb_dim: int = 1024) -> dict:
    return {
        "productId": pid,
        "name": f"Product {pid}",
        "brand": "Pellier Editions",
        "color": "Oatmeal",
        "price": "100.00",
        "description": "A nice linen shirt",
        "category": "Linen",
        "tags": json.dumps(["minimal", "linen"]),
        "rating": "4.7",
        "reviews": "100",
        "imgUrl": "https://example.com/img.jpg",
        "reasoning_lead": "",
        "reasoning_body": "",
        "reasoning_urgent": "",
        "match_reason": "",
        "badge": "",
        "tier": str(tier),
        "image_verified": "true",
        "embedding": _emb_str(emb_dim),
    }


def _write_csv(path: Path, row_count: int = 92) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        # Tier 1: IDs 1-10, Tier 2: 11-30, Tier 3: 31-92 — matches expected.
        for i in range(1, row_count + 1):
            if i <= 10:
                tier = 1
            elif i <= 30:
                tier = 2
            else:
                tier = 3
            w.writerow(_minimal_row(i, tier=tier))


@pytest.fixture
def module():
    if "load_catalog" in sys.modules:
        del sys.modules["load_catalog"]
    mod = importlib.import_module("load_catalog")
    mod._configure_logging(quiet=True, json_output=False)
    return mod


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "pellier_catalog.csv"
    _write_csv(p, row_count=92)
    return p


# --- Fake psycopg connection helpers --------------------------------------


class _FakeTxn:
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self._last = None
        self._copy = MagicMock()
        self._copy.__enter__ = MagicMock(return_value=self._copy)
        self._copy.__exit__ = MagicMock(return_value=False)
        self._copy.write_row = MagicMock()
        self.executed = []

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._conn._handle_execute(sql, params)
        return self

    def fetchone(self):
        return self._conn._fetchone()

    def fetchall(self):
        return self._conn._fetchall()

    def copy(self, sql):
        self._conn.copy_sql = sql
        return self._copy


class _FakeConn:
    """Scripted fake psycopg connection.

    Routes SELECT/DDL to a response queue keyed by substring match. Tests pre-load
    the expected responses before invoking the loader.
    """

    def __init__(self):
        # (substring, response) — first substring match wins. Responses are
        # either a list (fetchall) or a tuple (fetchone).
        self.responses: list[tuple[str, object]] = []
        self._pending: object = None
        self._pending_kind: str = "none"  # "one" or "all"
        self.executed_sqls: list[str] = []
        self.copy_sql = None
        self.copy_rows: list[tuple] = []
        self.closed = False
        self.transaction_begun = 0
        self.transaction_exited = 0
        # Hooks the test can override to inject failures.
        self.on_execute = None  # callable(sql, params)

    def queue(self, substring: str, response: object) -> None:
        self.responses.append((substring, response))

    def _handle_execute(self, sql: str, params):
        self.executed_sqls.append(sql)
        if self.on_execute is not None:
            self.on_execute(sql, params)
        for i, (sub, resp) in enumerate(self.responses):
            if sub in sql:
                self._pending = resp
                if isinstance(resp, list):
                    self._pending_kind = "all"
                else:
                    self._pending_kind = "one"
                del self.responses[i]
                return
        self._pending = None
        self._pending_kind = "none"

    def _fetchone(self):
        if self._pending_kind == "one":
            r = self._pending
            self._pending = None
            self._pending_kind = "none"
            return r
        if self._pending_kind == "all":
            items = list(self._pending or [])
            return items[0] if items else None
        return None

    def _fetchall(self):
        if self._pending_kind == "all":
            items = list(self._pending or [])
            self._pending = None
            self._pending_kind = "none"
            return items
        if self._pending_kind == "one":
            r = self._pending
            self._pending = None
            self._pending_kind = "none"
            return [r] if r is not None else []
        return []

    def cursor(self):
        c = _FakeCursor(self)
        # Capture COPY rows for the test. No recursion into the underlying
        # MagicMock — we only care about the row payloads here.
        def _capture(row):
            self.copy_rows.append(row)
        c._copy.write_row = MagicMock(side_effect=_capture)
        return c

    def transaction(self):
        self.transaction_begun += 1
        t = _FakeTxn()
        outer = self
        class _T:
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, et, ev, tb):
                outer.transaction_exited += 1
                return False
        return _T()

    # `with conn:` pattern
    def __enter__(self): return self
    def __exit__(self, *a):
        # psycopg semantics: commit on success, rollback on exception. For
        # our tests we only track exits; behavior is opaque.
        return False

    def close(self): self.closed = True


def _stub_db_preflight(conn):
    # Queue pre-flight expectations: SELECT 1; pg_extension; has_schema_privilege.
    conn.queue("SELECT 1", (1,))
    conn.queue("pg_extension", ("0.8.0",))
    conn.queue("has_schema_privilege", (True,))


def _stub_no_fks(conn):
    conn.queue("referential_constraints", [])


def _stub_lock(conn, got: bool = True):
    conn.queue("pg_try_advisory_lock", (got,))
    conn.queue("pg_advisory_unlock", (True,))


def _stub_verification(conn):
    # Order matters — these match the SELECTs in _verify exactly.
    conn.queue("SELECT COUNT(*) FROM pellier.product_catalog", (92,))  # row count
    conn.queue('MIN("productId"), MAX("productId")', (1, 92, 92))
    conn.queue("embedding IS NULL", (0,))
    conn.queue("vector_dims", [(1024,)])
    conn.queue(
        "GROUP BY tier",
        [(1, 10), (2, 20), (3, 62)],
    )
    conn.queue('WHERE "productId" = ANY', [(1,), (5,), (10,)])
    conn.queue(
        "pg_indexes",
        [
            ("idx_product_catalog_category",),
            ("idx_product_catalog_tier",),
            ("idx_product_catalog_tags",),
            ("idx_product_catalog_embedding",),
            ("product_catalog_pkey",),
        ],
    )


@pytest.fixture
def fake_conn(module, monkeypatch):
    """Install a _FakeConn for both the main connection and the autocommit one."""
    main_conn = _FakeConn()
    alter_conn = _FakeConn()
    alter_conn.queue("ALTER DATABASE", None)

    connections = {"main": main_conn, "alter": alter_conn}

    def _fake_connect(url, autocommit=False):
        return connections["alter"] if autocommit else connections["main"]

    # Provide a mocked psycopg module surface that the loader touches at call-time.
    fake_psycopg = MagicMock()
    fake_psycopg.connect = _fake_connect
    # Error taxonomy the loader catches by class name / isinstance.
    class _Insuf(Exception): pass
    class _OpErr(Exception): pass
    class _IntfErr(Exception): pass
    fake_psycopg.errors = MagicMock()
    fake_psycopg.errors.InsufficientPrivilege = _Insuf
    fake_psycopg.OperationalError = _OpErr
    fake_psycopg.InterfaceError = _IntfErr

    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    return {"main": main_conn, "alter": alter_conn, "psycopg": fake_psycopg}


def _stub_full_happy_path(conns):
    main = conns["main"]
    _stub_db_preflight(main)
    _stub_no_fks(main)
    _stub_lock(main, got=True)
    _stub_verification(main)


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


def test_preflight_fails_on_missing_csv(module, tmp_path):
    with pytest.raises(module.PreflightError, match="CSV not found"):
        module._preflight_csv(tmp_path / "nope.csv")


def test_preflight_fails_on_wrong_row_count(module, tmp_path):
    p = tmp_path / "c.csv"
    _write_csv(p, row_count=5)
    with pytest.raises(module.PreflightError, match="row count mismatch"):
        module._preflight_csv(p)


def test_preflight_fails_on_missing_embeddings(module, tmp_path):
    p = tmp_path / "c.csv"
    _write_csv(p, row_count=92)
    # Blank out one row's embedding column.
    with p.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows[0]["embedding"] = ""
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(module.PreflightError, match="empty embeddings"):
        module._preflight_csv(p)


def test_preflight_fails_on_wrong_embedding_dim(module, tmp_path):
    p = tmp_path / "c.csv"
    _write_csv(p, row_count=92)
    with p.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows[0]["embedding"] = _emb_str(dim=1536)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(module.PreflightError, match="embedding dim"):
        module._preflight_csv(p)


def test_preflight_fails_without_pgvector_extension(module, fake_conn, csv_path, monkeypatch):
    main = fake_conn["main"]
    main.queue("SELECT 1", (1,))
    main.queue("pg_extension", None)  # no vector row
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")

    with pytest.raises(module.PreflightError, match="pgvector extension not installed"):
        module.load_catalog(csv_path=csv_path, dry_run=True)


# ---------------------------------------------------------------------------
# FK detection
# ---------------------------------------------------------------------------


def test_fk_detection_lists_cascading_drops(module, fake_conn, csv_path, monkeypatch):
    main = fake_conn["main"]
    _stub_db_preflight(main)
    main.queue("referential_constraints", [
        ("public", "cart_items", "fk_cart_product", "product_id"),
        ("public", "wishlist", "fk_wishlist_product", "product_id"),
        ("public", "user_preferences_saved", "fk_ups_product", "product_id"),
    ])
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")

    result = module.load_catalog(csv_path=csv_path, dry_run=True)
    assert len(result.dropped_fks) == 3
    joined = " ".join(result.dropped_fks)
    assert "cart_items" in joined
    assert "wishlist" in joined
    assert "user_preferences_saved" in joined


# ---------------------------------------------------------------------------
# Advisory lock
# ---------------------------------------------------------------------------


def test_advisory_lock_blocks_concurrent_run(module, fake_conn, csv_path, monkeypatch):
    main = fake_conn["main"]
    _stub_db_preflight(main)
    _stub_no_fks(main)
    # Script retries for up to LOCK_RETRY_SECONDS; queue enough False answers
    # that we always hit the timeout.
    for _ in range(100):
        main.queue("pg_try_advisory_lock", (False,))

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    monkeypatch.setattr(module, "LOCK_RETRY_SECONDS", 0)  # fail fast

    with pytest.raises(module.ConcurrentExecutionError):
        module.load_catalog(csv_path=csv_path, dry_run=False)


# ---------------------------------------------------------------------------
# Transaction rollback
# ---------------------------------------------------------------------------


def test_transaction_rolls_back_on_copy_failure(module, fake_conn, csv_path, monkeypatch):
    main = fake_conn["main"]
    _stub_full_happy_path(fake_conn)

    # Override write_row to raise on first call.
    original_cursor = main.cursor
    def _broken_cursor():
        c = original_cursor()
        c._copy.write_row.side_effect = RuntimeError("network blip")
        return c
    main.cursor = _broken_cursor

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    with pytest.raises(RuntimeError, match="network blip"):
        module.load_catalog(csv_path=csv_path, dry_run=False)
    # transaction context was entered and then exited (rollback semantics).
    assert main.transaction_begun >= 1
    assert main.transaction_exited >= 1


def test_transaction_rolls_back_on_verification_failure(module, fake_conn, csv_path, monkeypatch):
    main = fake_conn["main"]
    _stub_db_preflight(main)
    _stub_no_fks(main)
    _stub_lock(main, got=True)
    # Corrupt verification: wrong row count.
    main.queue("SELECT COUNT(*) FROM pellier.product_catalog", (77,))

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    with pytest.raises(module.VerificationError, match="row count"):
        module.load_catalog(csv_path=csv_path, dry_run=False)
    assert main.transaction_begun >= 1
    assert main.transaction_exited >= 1


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


def test_dry_run_does_not_modify_database(module, fake_conn, csv_path, monkeypatch):
    main = fake_conn["main"]
    _stub_db_preflight(main)
    _stub_no_fks(main)

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    result = module.load_catalog(csv_path=csv_path, dry_run=True)

    assert result.rows_loaded == 0
    assert result.verification_passed is False
    assert result.iterative_scan_mode == "skipped"
    # Critically: no COPY was issued, no DROP/CREATE ran.
    assert main.copy_sql is None
    assert not any("DROP TABLE" in s for s in main.executed_sqls)
    assert not any("CREATE TABLE" in s for s in main.executed_sqls)


# ---------------------------------------------------------------------------
# Interactive confirmation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply,expected",
    [("y", True), ("yes", True), ("Y", True), ("YES", True),
     ("n", False), ("no", False), ("", False), ("anything", False)],
)
def test_interactive_confirmation_requires_yes(module, monkeypatch, reply, expected):
    monkeypatch.setattr("builtins.input", lambda prompt="": reply)
    assert module._confirm_interactive("host/db", Path("/x.csv"), 92) is expected


# ---------------------------------------------------------------------------
# Row transforms
# ---------------------------------------------------------------------------


def test_tags_stringified_python_list_converts_to_valid_jsonb(module):
    # Python-repr style (single quotes) — not valid JSON on its own.
    raw = "['minimal', 'serene', 'linen']"
    result = module._normalize_tags(raw)
    parsed = json.loads(result)  # must be valid JSON now
    assert parsed == ["minimal", "serene", "linen"]

    # Already-valid JSON passes through.
    raw = '["bold", "warm"]'
    parsed = json.loads(module._normalize_tags(raw))
    assert parsed == ["bold", "warm"]

    # Empty string → empty array.
    assert module._normalize_tags("") == "[]"


def test_embedding_string_casts_to_vector_type(module):
    row = _minimal_row(1)
    tup = module._row_to_copy_tuple(row)
    # The embedding column is the 19th and last tuple slot and matches the
    # JSON-array text format pgvector accepts for vector() columns.
    assert tup[-1] == row["embedding"]
    assert tup[-1].startswith("[") and tup[-1].endswith("]")


# ---------------------------------------------------------------------------
# iterative_scan configuration
# ---------------------------------------------------------------------------


def test_iterative_scan_set_at_database_level_when_permitted(module, fake_conn, csv_path, monkeypatch):
    _stub_full_happy_path(fake_conn)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")

    result = module.load_catalog(csv_path=csv_path, dry_run=False)
    assert result.iterative_scan_mode == "database"


def test_iterative_scan_falls_back_to_session_on_permission_error(module, fake_conn, csv_path, monkeypatch):
    _stub_full_happy_path(fake_conn)
    alter = fake_conn["alter"]
    psycopg_mock = fake_conn["psycopg"]

    # Force ALTER DATABASE to raise InsufficientPrivilege; SET must then succeed.
    def _on_execute(sql, params):
        if "ALTER DATABASE" in sql:
            raise psycopg_mock.errors.InsufficientPrivilege("permission denied")
    alter.on_execute = _on_execute

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    result = module.load_catalog(csv_path=csv_path, dry_run=False)
    assert result.iterative_scan_mode == "session"


# ---------------------------------------------------------------------------
# HNSW index parameters
# ---------------------------------------------------------------------------


def test_hnsw_index_created_with_explicit_m_and_ef_construction(module):
    sql = module.INDEX_SQL["idx_product_catalog_embedding"]
    assert "USING hnsw" in sql
    assert "vector_cosine_ops" in sql
    # Explicit tunables — the whole point of stating them.
    assert "m = 16" in sql
    assert "ef_construction = 64" in sql
