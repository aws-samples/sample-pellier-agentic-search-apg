"""Tests for `services.database` connection setup.

Ensures the pgvector `hnsw.iterative_scan` GUC is set on every backend
connection via three layers of defense:

  1. Pool-level `configure` callback (`_configure_connection`).
  2. On-acquire SET inside `DatabaseService.get_connection`.
  3. Startup verification log (`DatabaseService._verify_iterative_scan`).

psycopg is not exercised here — a fake connection/cursor/pool records
the executed SQL so the tests stay offline.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, List, Optional, Sequence, Tuple

import pytest

from services.database import DatabaseService, _configure_connection


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, rows: Optional[List[Any]] = None) -> None:
        self._rows = rows or []
        self.calls: List[Tuple[str, Optional[Sequence[Any]]]] = []

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> None:
        self.calls.append((sql, params))

    async def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None


class FakeConnection:
    def __init__(self, rows: Optional[List[Any]] = None) -> None:
        self._cursor = FakeCursor(rows)
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return self._cursor

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class FakePool:
    """Records connections handed out and mimics `AsyncConnectionPool.connection`."""

    def __init__(self, conn: FakeConnection) -> None:
        self._conn = conn

    @asynccontextmanager
    async def connection(self):
        yield self._conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pool_configure_sets_iterative_scan() -> None:
    """`_configure_connection` SHALL run SET hnsw.iterative_scan = 'relaxed_order'."""
    conn = FakeConnection()

    _run(_configure_connection(conn))  # type: ignore[arg-type]

    sql_calls = [c[0] for c in conn._cursor.calls]
    assert any(
        "SET hnsw.iterative_scan" in sql and "relaxed_order" in sql
        for sql in sql_calls
    ), sql_calls
    # Configure is expected to commit so the SET persists on the session.
    assert conn.commits == 1


def test_get_connection_sets_iterative_scan_on_acquire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense-in-depth: every `get_connection` acquire SHALL SET iterative_scan."""
    # register_vector_async is a no-op for the fake connection.
    import pgvector.psycopg as pgvec

    async def _noop_register(_conn: Any) -> None:
        return None

    monkeypatch.setattr(pgvec, "register_vector_async", _noop_register)

    conn = FakeConnection()
    svc = DatabaseService()
    svc._pool = FakePool(conn)  # type: ignore[assignment]
    svc._is_connected = True

    async def _acquire() -> None:
        async with svc.get_connection() as c:
            # Simulate a workload doing nothing — the acquire itself should
            # have already fired the SET.
            assert c is conn

    _run(_acquire())

    iterative_calls = [
        (sql, params)
        for sql, params in conn._cursor.calls
        if "iterative_scan" in sql
    ]
    assert len(iterative_calls) == 1, conn._cursor.calls
    sql, _params = iterative_calls[0]
    assert "relaxed_order" in sql


def test_verify_iterative_scan_warns_when_off(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Startup SHOW returning 'off' SHALL produce a WARNING log, not INFO."""
    import pgvector.psycopg as pgvec

    async def _noop_register(_conn: Any) -> None:
        return None

    monkeypatch.setattr(pgvec, "register_vector_async", _noop_register)

    # SHOW returns dict_row shape: {"hnsw.iterative_scan": "off"}.
    conn = FakeConnection(rows=[{"hnsw.iterative_scan": "off"}])
    svc = DatabaseService()
    svc._pool = FakePool(conn)  # type: ignore[assignment]
    svc._is_connected = True

    with caplog.at_level(logging.WARNING, logger="services.database"):
        _run(svc._verify_iterative_scan())

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "iterative_scan" in r.getMessage()
    ]
    assert warnings, caplog.records
    assert "off" in warnings[0].getMessage()
