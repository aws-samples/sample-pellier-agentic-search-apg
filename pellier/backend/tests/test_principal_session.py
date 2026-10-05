"""`DatabaseService.principal_session`: the same-transaction guarantee.

Row-level security on `pellier.orders` and `pellier.support_tickets` binds the
*effective* role and reads `pellier.principal_username`. Both must hold on one
physical connection inside one transaction, which the ordinary accessors
cannot provide: `fetch_all`, `fetch_one` and `execute_query` each take their
own pooled connection and release it.

That failure mode is quiet. A `SET LOCAL` issued through `execute_query` is
invisible to the next call, so the protected statement runs with no name,
which fails closed and reads as "no such row" rather than "not authorized".
So these tests assert the mechanics:

  1. Role and name are set on the *same* connection as the caller's
     statements, and inside a transaction.
  2. The name is bound with `set_config`, parameterized, never interpolated.
  3. The role is the one application role, a constant, never the owner.

The enforcement proof itself (another customer's rows are hidden) runs on real
PostgreSQL in `test_rls_customer_reads_postgres.py`.
"""

from __future__ import annotations

from typing import Any, List, Tuple

import pytest

from services.database import CUSTOMER_ROLE, PRINCIPAL_SETTING, DatabaseService


class _Cursor:
    # No result set: the bound read under test returns no rows.
    description = None

    def __init__(self, calls: List[Tuple[str, Any]]) -> None:
        self._calls = calls

    async def __aenter__(self) -> "_Cursor":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None

    async def execute(self, sql: str, params: Any = None) -> None:
        self._calls.append((sql, params))


class _Transaction:
    def __init__(self, events: List[str]) -> None:
        self._events = events

    async def __aenter__(self) -> "_Transaction":
        self._events.append("begin")
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        self._events.append("end")


class _Connection:
    """Records the statement order and transaction boundaries."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Any]] = []
        self.events: List[str] = []

    def cursor(self) -> _Cursor:
        return _Cursor(self.calls)

    def transaction(self) -> _Transaction:
        return _Transaction(self.events)


@pytest.fixture
def service(monkeypatch) -> Tuple[DatabaseService, _Connection]:
    """A service whose `get_connection` yields one recording connection."""
    from contextlib import asynccontextmanager

    db = DatabaseService()
    conn = _Connection()

    @asynccontextmanager
    async def _get_connection():
        yield conn

    monkeypatch.setattr(db, "get_connection", _get_connection)
    return db, conn


# ---------------------------------------------------------------------------
# Same connection, same transaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_role_and_principal_are_bound_before_caller_statements(service):
    db, conn = service

    async with db.principal_session("marco") as session:
        async with session.cursor() as cur:
            await cur.execute("SELECT 1 FROM pellier.orders", None)

    statements = [sql for sql, _params in conn.calls]
    assert statements[0] == "SET LOCAL ROLE pellier_agent"
    assert statements[1] == "SELECT set_config(%s, %s, true)"
    assert conn.calls[1][1] == ("pellier.principal_username", "marco")
    # The caller's statement runs last, on the same connection.
    assert statements[2] == "SELECT 1 FROM pellier.orders"


@pytest.mark.asyncio
async def test_binding_happens_inside_a_transaction(service):
    """Outside a transaction `SET LOCAL` is a no-op with a warning.

    An unbound principal fails closed, so the symptom would be missing rows
    rather than an error — which is why the transaction is asserted.
    """
    db, conn = service

    async with db.principal_session("marco"):
        pass

    assert conn.events == ["begin", "end"]


@pytest.mark.asyncio
async def test_caller_statements_share_the_bound_connection(service):
    """One connection for the whole block, or RLS sees no principal."""
    db, conn = service

    async with db.principal_session("marco") as session:
        assert session is conn


# ---------------------------------------------------------------------------
# The principal is data, not SQL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_principal_is_parameterized_not_interpolated(service):
    db, conn = service
    hostile = "x'; DROP TABLE pellier.orders; --"

    async with db.principal_session(hostile):
        pass

    set_config = next(
        (sql, params) for sql, params in conn.calls if "set_config" in sql
    )
    assert set_config[1] == (PRINCIPAL_SETTING, hostile)
    assert "DROP TABLE" not in set_config[0]


@pytest.mark.asyncio
async def test_anonymous_binds_an_empty_principal_explicitly(service):
    """Absent must be bound, not skipped.

    Binding it makes the intent legible in the transaction, and the policies
    match an empty name to no customer: denied, not widened.
    """
    db, conn = service

    async with db.principal_session(None):
        pass

    set_config = next(params for sql, params in conn.calls if "set_config" in sql)
    assert set_config == (PRINCIPAL_SETTING, "")


@pytest.mark.asyncio
async def test_local_scope_is_used_so_pool_reuse_cannot_leak(service):
    """The third `set_config` argument is `is_local`.

    This is the release-blocking pool-leakage property in its unit form: a
    transaction-local setting cannot survive into the next borrower of the
    same pooled connection. Session-scoped state could, and would silently
    grant transaction B the principal of transaction A.
    """
    db, conn = service

    async with db.principal_session("marco"):
        pass

    set_config_sql = next(sql for sql, _p in conn.calls if "set_config" in sql)
    assert ", true)" in set_config_sql, "must bind transaction-locally"
    assert "SET LOCAL ROLE" in " ".join(sql for sql, _p in conn.calls)


# ---------------------------------------------------------------------------
# One role, never the owner
# ---------------------------------------------------------------------------


def test_the_role_is_the_application_role_not_the_owner():
    """Assuming the owner would bypass row-level security."""
    assert CUSTOMER_ROLE == "pellier_agent"
    assert PRINCIPAL_SETTING == "pellier.principal_username"


@pytest.mark.asyncio
async def test_fetch_all_as_runs_inside_the_bound_session(service):
    db, conn = service

    rows = await db.fetch_all_as(
        "theo", "SELECT 1 FROM pellier.orders WHERE customer_id = %s", "CUST-THEO"
    )

    assert rows == []
    assert [sql for sql, _ in conn.calls][:2] == [
        "SET LOCAL ROLE pellier_agent", "SELECT set_config(%s, %s, true)",
    ]
    assert conn.calls[2] == ("SELECT 1 FROM pellier.orders WHERE customer_id = %s", ("CUST-THEO",))
    assert conn.events == ["begin", "end"]
