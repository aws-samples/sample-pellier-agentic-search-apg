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

from services.database import (
    AsyncConnection, DatabaseService, _check_connection, _configure_connection,
    _instrument_connection, db_query_log_var,
)


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


@pytest.mark.parametrize("autocommit", [False, True])
@pytest.mark.parametrize("broken", [False, True])
def test_checkout_probe_preserves_transactions_and_business_telemetry(
    monkeypatch: pytest.MonkeyPatch, autocommit: bool, broken: bool,
) -> None:
    import psycopg

    conn = FakeConnection()
    conn.autocommit = autocommit

    async def set_autocommit(value: bool) -> None:
        conn.autocommit = value

    async def probe(_sql: str) -> None:
        assert conn.autocommit is True
        if broken:
            raise psycopg.OperationalError("closed tunnel")

    conn.set_autocommit = set_autocommit
    monkeypatch.setattr(conn._cursor, "execute", probe)
    monkeypatch.setattr(AsyncConnection, "cursor", lambda connection: connection._cursor)
    _instrument_connection(conn)
    queries = []
    token = db_query_log_var.set(queries)
    try:
        if broken:
            with pytest.raises(psycopg.OperationalError, match="closed tunnel"):
                _run(_check_connection(conn))
        else:
            _run(_check_connection(conn))
        assert conn.autocommit is autocommit
        assert queries == []
        assert conn.commits == 0
    finally:
        db_query_log_var.reset(token)


def test_pool_configure_sets_iterative_scan() -> None:
    """`_configure_connection` SHALL run SET hnsw.iterative_scan = 'strict_order'.

    Strict, not relaxed: this branch's rows are enumerated into vector ranks
    that feed RRF, so an approximately-ordered scan becomes a fusion input.
    """
    conn = FakeConnection()

    _run(_configure_connection(conn))  # type: ignore[arg-type]

    sql_calls = [c[0] for c in conn._cursor.calls]
    assert any(
        "SET hnsw.iterative_scan" in sql and "strict_order" in sql
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
    assert "strict_order" in sql


def test_vector_adapters_register_once_per_physical_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pgvector.psycopg as pgvec
    registered = []

    async def register(conn: Any) -> None:
        registered.append(conn)

    monkeypatch.setattr(pgvec, "register_vector_async", register)
    first, second = FakeConnection(), FakeConnection()
    pool = FakePool(first)
    svc = DatabaseService()
    svc._pool = pool
    svc._is_connected = True

    async def acquire_reused_then_new() -> None:
        for _ in range(2):
            async with svc.get_connection():
                pass
        pool._conn = second
        async with svc.get_connection():
            pass

    _run(acquire_reused_then_new())
    assert registered == [first, second]
    # Reuse still reasserts the retrieval invariant for every request.
    assert sum("strict_order" in sql for sql, _ in first._cursor.calls) == 2
    assert sum("strict_order" in sql for sql, _ in second._cursor.calls) == 1


def test_failed_vector_registration_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pgvector.psycopg as pgvec
    attempts = []

    async def register(conn: Any) -> None:
        attempts.append(conn)
        if len(attempts) == 1:
            raise RuntimeError("interrupted type lookup")

    monkeypatch.setattr(pgvec, "register_vector_async", register)
    conn = FakeConnection()
    svc = DatabaseService()
    svc._pool = FakePool(conn)
    svc._is_connected = True

    async def retry() -> None:
        with pytest.raises(RuntimeError, match="interrupted type lookup"):
            async with svc.get_connection():
                pytest.fail("failed setup must not yield a connection")
        assert not getattr(conn, "_pellier_vector_registered", False)
        async with svc.get_connection():
            pass

    _run(retry())
    assert attempts == [conn, conn]
    assert conn._pellier_vector_registered is True


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


# ---------------------------------------------------------------------------
# Workshop run id: the session setting migration 049 reads as a DEFAULT
# ---------------------------------------------------------------------------


def _set_config_calls(conn: FakeConnection) -> List[Tuple[str, Optional[Sequence[Any]]]]:
    return [
        (sql, params)
        for sql, params in conn._cursor.calls
        if "pellier.run_id" in sql
    ]


def test_pool_configure_sets_the_run_id_when_one_is_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid run id SHALL be bound with set_config as a parameter, not a literal."""
    import services.database as database

    monkeypatch.setattr(database, "current_run_id", lambda: "run-0123456789ab")
    conn = FakeConnection()

    _run(_configure_connection(conn))  # type: ignore[arg-type]

    calls = _set_config_calls(conn)
    assert len(calls) == 1, conn._cursor.calls
    sql, params = calls[0]
    assert "set_config('pellier.run_id'" in sql
    assert "run-0123456789ab" not in sql
    assert params == ("run-0123456789ab",)


def test_pool_configure_skips_the_run_id_when_none_is_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.database as database

    monkeypatch.setattr(database, "current_run_id", lambda: None)
    conn = FakeConnection()

    _run(_configure_connection(conn))  # type: ignore[arg-type]

    assert _set_config_calls(conn) == []


def test_pool_configure_refuses_a_malformed_run_id(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Anything outside run-<12 hex> never reaches SQL, and the refusal is logged."""
    import services.database as database

    monkeypatch.setattr(database, "current_run_id", lambda: "run-zz; DROP TABLE x")
    conn = FakeConnection()

    with caplog.at_level(logging.WARNING, logger="services.database"):
        _run(_configure_connection(conn))  # type: ignore[arg-type]

    assert _set_config_calls(conn) == []
    assert any("run id" in r.getMessage() for r in caplog.records), caplog.records
