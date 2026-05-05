"""Tests for `VectorSearch.vector_search` (Module 1 reference implementation).

The Boutique's semantic-search path. psycopg is mocked so these tests
run offline without a live Aurora instance. The assertions check the
SQL shape (pgvector CTE + cosine similarity), the `SET LOCAL`
parameterization, the `iterative_scan` branch, and that
`sql_query_logger` is called with parameterized args only.

Runnable from the repo root per `pytest.ini`:
    blaize-bazaar/backend/.venv/bin/python -m pytest \
        blaize-bazaar/backend/tests/test_vector_search.py -v
"""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Sequence

import pytest

from services.vector_search import VectorSearch
from services.sql_query_logger import SQLQueryLogger
import services.sql_query_logger as sql_query_logger_module


def _run(coro: Any) -> Any:
    """Run an async coroutine from a sync test without needing a plugin."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake psycopg cursor + connection + pool (records the calls the test cares
# about without bringing in a real driver).
# ---------------------------------------------------------------------------


class FakeCursor:
    """Records every await cur.execute(sql, params) call."""

    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows
        self.calls: List[tuple[str, Optional[Sequence[Any]]]] = []

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def execute(
        self, sql: str, params: Optional[Sequence[Any]] = None
    ) -> None:
        self.calls.append((sql, params))

    async def fetchall(self) -> List[Dict[str, Any]]:
        return list(self._rows)


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakeDB:
    """Stand-in for `DatabaseService` exposing only `get_connection()`."""

    def __init__(self, rows: List[Dict[str, Any]]):
        self.cursor = FakeCursor(rows)
        self.conn = FakeConnection(self.cursor)

    @asynccontextmanager
    async def get_connection(self):
        yield self.conn


def _make_row(product_id: int, similarity: float) -> Dict[str, Any]:
    return {
        "product_id": product_id,
        "name": f"Test product {product_id}",
        "brand": "Blaize Editions",
        "color": "Sand",
        "description": f"Full description for test product {product_id}",
        "img_url": f"https://example.com/{product_id}.jpg",
        "category": "Linen",
        "price": 128.0,
        "reviews": "50",
        "rating": 4.7,
        "badge": None,
        "tags": ["minimal", "linen"],
        "similarity": similarity,
    }


@pytest.fixture
def embedding() -> List[float]:
    # 1024-dim placeholder; values are opaque to the test (parameterized).
    return [0.01] * 1024


@pytest.fixture(autouse=True)
def isolated_query_logger(monkeypatch: pytest.MonkeyPatch) -> SQLQueryLogger:
    """Use a fresh SQLQueryLogger for each test so assertions are isolated."""
    logger = SQLQueryLogger(max_logs=100)
    monkeypatch.setattr(sql_query_logger_module, "_query_logger", logger)
    return logger


def _call(embedding: List[float], **kwargs: Any) -> tuple[FakeDB, List[Dict[str, Any]]]:
    """Helper: build a FakeDB, run vector_search, return (db, results)."""
    rows = kwargs.pop("rows", None) or [_make_row(1, 0.9)]
    db = FakeDB(rows)
    svc = VectorSearch(db)  # type: ignore[arg-type]

    defaults = {"limit": 5, "ef_search": 40}
    defaults.update(kwargs)
    results = _run(svc.vector_search(embedding, **defaults))
    return db, results


# ---------------------------------------------------------------------------
# Requirement 2.3.2 - CTE + <=> + 1 - distance similarity
# ---------------------------------------------------------------------------


def test_uses_cte_embedding_pattern(embedding: List[float]) -> None:
    """SQL SHALL use the CTE pattern from database.md."""
    db, _ = _call(embedding)

    # The main SELECT is the last call (after the two SET LOCALs).
    sql, _params = db.cursor.calls[-1]
    assert "WITH query_embedding AS" in sql
    # SELECT %s::vector as emb — parameterized, never f-string'd.
    assert re.search(r"SELECT\s+%s::vector\s+as\s+emb", sql), sql


def test_uses_cosine_distance_and_similarity_formula(
    embedding: List[float],
) -> None:
    """Ordering SHALL use <=> and similarity SHALL be 1 - distance."""
    db, _ = _call(embedding)

    sql, _params = db.cursor.calls[-1]
    # 1 - (embedding <=> ...) as similarity — per database.md.
    assert re.search(
        r"1\s*-\s*\(\s*embedding\s*<=>\s*\(SELECT\s+emb\s+FROM\s+query_embedding\s*\)\s*\)\s+as\s+similarity",
        sql,
    ), sql
    # ORDER BY uses the cosine operator as well.
    assert re.search(
        r"ORDER\s+BY\s+embedding\s*<=>\s*\(SELECT\s+emb\s+FROM\s+query_embedding\s*\)",
        sql,
    ), sql


# ---------------------------------------------------------------------------
# Requirement 2.3.3 and 2.3.4 - SET LOCAL hnsw.ef_search + iterative_scan
# ---------------------------------------------------------------------------


def test_sets_ef_search_with_validated_int(embedding: List[float]) -> None:
    """SET LOCAL hnsw.ef_search SHALL interpolate a validated int.

    PostgreSQL disallows bind parameters on utility statements, so the
    value is coerced with ``int()`` and placed directly in the SQL — safe
    because the coercion rejects anything that isn't an integer before it
    reaches the server.
    """
    db, _ = _call(embedding, ef_search=64)

    # The first execute is SET LOCAL hnsw.ef_search.
    first_sql, first_params = db.cursor.calls[0]
    assert "SET LOCAL hnsw.ef_search" in first_sql
    assert "%s" not in first_sql, "ef_search must not be bound (Postgres rejects)"
    assert first_sql.strip().endswith("= 64")


def test_iterative_scan_true_sets_relaxed_order(embedding: List[float]) -> None:
    """When iterative_scan=True SHALL issue SET LOCAL hnsw.iterative_scan.

    Postgres disallows bind parameters on utility statements, so the value
    is a hardcoded literal (``'relaxed_order'``) — no external input ever
    reaches this SQL string.
    """
    db, _ = _call(embedding, iterative_scan=True)

    iterative_calls = [c for c in db.cursor.calls if "iterative_scan" in c[0]]
    assert len(iterative_calls) == 1
    sql, _params = iterative_calls[0]
    assert "SET LOCAL hnsw.iterative_scan" in sql
    assert "'relaxed_order'" in sql


def test_iterative_scan_false_skips_set_local(embedding: List[float]) -> None:
    """When iterative_scan=False SHALL NOT call the iterative_scan SET LOCAL."""
    db, _ = _call(embedding, iterative_scan=False)

    iterative_calls = [c for c in db.cursor.calls if "iterative_scan" in c[0]]
    assert iterative_calls == []


# ---------------------------------------------------------------------------
# Requirement 2.3.2 - image availability filter (catalog convention)
# ---------------------------------------------------------------------------


def test_filters_rows_with_null_image_url(embedding: List[float]) -> None:
    """SQL SHALL require a non-null ``imgUrl`` so unrendered rows stay out.

    The boutique catalog has no ``quantity`` column — the image-availability
    filter is the canonical "is this row ready to show?" guard.
    """
    db, _ = _call(embedding)

    sql, _params = db.cursor.calls[-1]
    assert re.search(r'"imgUrl"\s+IS\s+NOT\s+NULL', sql), sql


# ---------------------------------------------------------------------------
# Parameterized-only call pattern (Req 5.3.3 / 5.4.2)
# ---------------------------------------------------------------------------


def test_all_executes_use_parameterized_placeholders(
    embedding: List[float],
) -> None:
    """Every cur.execute call SHALL pass values via params, not f-strings."""
    db, _ = _call(embedding)

    for sql, params in db.cursor.calls:
        # The embedding itself — always parameterized.
        assert "0.01" not in sql, f"Embedding value leaked into SQL: {sql[:120]}"
        # Every SELECT / utility statement with a %s MUST carry its values
        # via params. (SET LOCAL lines have no %s — Postgres rejects them.)
        if "%s" in sql:
            assert params is not None and len(list(params)) > 0, sql


def test_select_passes_embedding_and_limit_via_params(
    embedding: List[float],
) -> None:
    """The SELECT SHALL pass exactly [embedding, limit] as parameters."""
    db, _ = _call(embedding, limit=7)

    select_sql, select_params = db.cursor.calls[-1]
    assert "SELECT" in select_sql.upper()
    assert select_params is not None
    params_list = list(select_params)
    # One for the CTE embedding, one for LIMIT. (The ORDER BY reuses the CTE.)
    assert len(params_list) == 2
    assert params_list[0] is embedding
    assert params_list[1] == 7


# ---------------------------------------------------------------------------
# Requirement 2.3.6 - limit bound on returned results
# ---------------------------------------------------------------------------


def test_limit_is_passed_to_sql(embedding: List[float]) -> None:
    """The passed `limit` SHALL be the LIMIT bound used in the SQL."""
    rows = [_make_row(i + 1, 0.9 - 0.01 * i) for i in range(20)]
    db, _ = _call(embedding, limit=5, rows=rows)

    select_sql, select_params = db.cursor.calls[-1]
    assert re.search(r"LIMIT\s+%s", select_sql), select_sql
    assert list(select_params)[-1] == 5


def test_results_are_returned_as_plain_dicts(embedding: List[float]) -> None:
    """Results SHALL be plain dicts including the similarity field."""
    rows = [
        _make_row(1, 0.92),
        _make_row(2, 0.88),
        _make_row(3, 0.85),
    ]
    _db, results = _call(embedding, limit=10, rows=rows)

    assert len(results) == 3
    assert all(isinstance(r, dict) for r in results)
    assert [r["product_id"] for r in results] == [1, 2, 3]
    # Similarity scores are preserved end-to-end.
    assert results[0]["similarity"] == pytest.approx(0.92)


# ---------------------------------------------------------------------------
# Requirement 5.4.2 - sql_query_logger called with parameterized args only
# ---------------------------------------------------------------------------


def test_sql_query_logger_receives_parameterized_args(
    embedding: List[float], isolated_query_logger: SQLQueryLogger
) -> None:
    """The logger SHALL receive the SQL string and params list, never
    interpolated values."""
    rows = [_make_row(1, 0.9), _make_row(2, 0.8)]
    _db, _ = _call(embedding, rows=rows)

    assert len(isolated_query_logger.queries) == 1
    log_entry = isolated_query_logger.queries[0]

    # SQL string MUST NOT contain interpolated values.
    assert "0.01" not in log_entry.sql
    assert " 40" not in log_entry.sql
    # The params list must carry the embedding + limit, not the SQL.
    assert log_entry.params[0] is embedding
    assert log_entry.params[-1] == 5
    assert log_entry.rows_returned == 2
