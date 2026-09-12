"""
Database service for Pellier

Manages PostgreSQL connections using psycopg 3 with connection pooling.
Provides async context managers for safe database access.
"""

import logging
import re
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncIterator, Optional, Any

import psycopg
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from config import settings
from services.workshop_run import RUN_ID_PATTERN, current_run_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-turn query logger — feeds the Observatory State Management live strip.
# ---------------------------------------------------------------------------
# ``chat_stream`` sets this ContextVar to a fresh list at the start of each
# turn. fetch_all / fetch_one / execute_query append to it with
# ``{op, table, sql, duration_ms, timestamp}``. At turn complete the chat
# service emits a ``db_queries`` SSE event with the collected entries and
# clears the list. ContextVars propagate into asyncio.to_thread workers so
# tool invocations fire into the same buffer.
db_query_log_var: ContextVar[Optional[list]] = ContextVar(
    "db_query_log_var", default=None
)


# Runtime roles created by migration 016. `SET ROLE` takes no parameters, so
# any role name reaching SQL must come from this set rather than from a
# caller-supplied string.
#
#   pellier_agent — business tables, INSERT-only on the evidence ledger
#   pellier_query — read-only, and deliberately blind to the ledger
#
# The owner is absent on purpose: assuming the owner would bypass RLS, which
# would make a "governed" session silently ungoverned.
_RUNTIME_ROLES = frozenset({"pellier_agent", "pellier_query"})


def _classify_op(sql: str) -> str:
    """Return 'READ' for SELECT/WITH/SHOW, 'WRITE' otherwise."""
    stripped = sql.lstrip().upper()
    if stripped.startswith(("SELECT", "WITH", "SHOW", "EXPLAIN")):
        return "READ"
    return "WRITE"


def _extract_table(sql: str) -> str:
    """Best-effort table extraction for the live strip. Returns '' on miss.

    Prefers schema-qualified tables (e.g. ``pellier.product_catalog``)
    over CTE aliases. Falls back to the first FROM/JOIN/UPDATE/INTO target
    if no schema-qualified match is found.
    """
    # Prefer schema-qualified references first — skips CTE aliases like
    # ``FROM query_embedding`` in pgvector search wrappers.
    schema_match = re.search(
        r"\b(?:FROM|JOIN|UPDATE|INTO|TABLE)\s+"
        r"([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)",
        sql,
        re.IGNORECASE,
    )
    if schema_match:
        return schema_match.group(1).split(".")[-1]
    # Fallback: any table-shaped token after a DML keyword.
    m = re.search(
        r"\b(?:FROM|JOIN|UPDATE|INTO|TABLE)\s+([a-zA-Z_][a-zA-Z0-9_.]*)",
        sql,
        re.IGNORECASE,
    )
    if not m:
        return ""
    return m.group(1).split(".")[-1]


def _truncate_sql(sql: str, limit: int = 200) -> str:
    """Collapse whitespace + truncate SQL for the live strip."""
    one_line = " ".join(sql.split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1] + "…"


def _record_query(sql: str, duration_ms: int) -> None:
    """Append one entry to the per-turn query log if active."""
    log = db_query_log_var.get()
    if log is None:
        return
    log.append(
        {
            "op": _classify_op(sql),
            "table": _extract_table(sql),
            "sql": _truncate_sql(sql),
            "duration_ms": duration_ms,
            "timestamp": int(time.time() * 1000),
        }
    )


def _instrument_connection(conn: AsyncConnection) -> None:
    """Wrap ``conn.cursor`` so cursor.execute records into db_query_log_var.

    Idempotent — subsequent calls are no-ops because we mark the
    connection after wrapping. Skips SET / BEGIN / COMMIT noise so the
    live strip stays focused on semantically meaningful queries.

    Psycopg's ``AsyncCursor`` is a C extension with read-only slots
    (``__aenter__``, ``execute``, etc.), so we can't monkey-patch it.
    We return a lightweight proxy that forwards attribute access to
    the real cursor and overrides only ``execute`` for timing capture.
    """
    if getattr(conn, "_pellier_instrumented", False):
        return
    setattr(conn, "_pellier_instrumented", True)
    orig_cursor = conn.cursor

    _SKIP_PREFIXES = ("SET ", "BEGIN", "COMMIT", "ROLLBACK", "DISCARD")

    class _CursorProxy:
        """Forwards all attribute lookups to the wrapped cursor.

        Only ``execute`` is overridden to capture SQL + duration into
        the per-turn query log. Async iteration and context manager
        semantics are inherited from the real cursor via __getattr__
        and explicit __aiter__ / __anext__ forwards.
        """

        def __init__(self, real: Any) -> None:
            self._real = real

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

        async def execute(self, query: Any, *xa: Any, **xkw: Any) -> Any:
            sql_str = query if isinstance(query, str) else str(query)
            skip = sql_str.lstrip().upper().startswith(_SKIP_PREFIXES)
            t0 = time.perf_counter()
            try:
                return await self._real.execute(query, *xa, **xkw)
            finally:
                if not skip:
                    _record_query(
                        sql_str, int((time.perf_counter() - t0) * 1000)
                    )

        def __aiter__(self) -> Any:
            return self._real.__aiter__()

    class _InstrumentedCursorCM:
        def __init__(self, inner_cm: Any) -> None:
            self._inner_cm = inner_cm

        async def __aenter__(self) -> Any:
            cur = await self._inner_cm.__aenter__()
            return _CursorProxy(cur)

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
            return await self._inner_cm.__aexit__(exc_type, exc, tb)

    def _wrapped_cursor(*args: Any, **kwargs: Any) -> Any:
        return _InstrumentedCursorCM(orig_cursor(*args, **kwargs))

    conn.cursor = _wrapped_cursor  # type: ignore[assignment]


async def _check_connection(conn: AsyncConnection) -> None:
    """Reject stale sockets before handing a connection to a request.

    Use the unwrapped cursor so a pool health probe never becomes a business
    query in the Observatory. Autocommit avoids opening a transaction for the
    empty protocol query; restore the caller's transaction mode even on error.
    """
    autocommit = conn.autocommit
    if not autocommit:
        await conn.set_autocommit(True)
    try:
        async with AsyncConnection.cursor(conn) as cur:
            await cur.execute("")
    finally:
        if not autocommit:
            await conn.set_autocommit(False)


async def _configure_connection(conn: AsyncConnection) -> None:
    """Pool configure callback — runs on every new connection from the pool.

    Sets hnsw.iterative_scan = 'strict_order' so filtered vector search
    (e.g., 'linen shirts under $100') returns complete result sets instead
    of fewer-than-LIMIT rows, AND returns them in exact distance order.

    Why strict and not relaxed. Both modes iterate, so both fix the short-list
    problem that motivated the setting. They differ in ordering: pgvector
    documents that a relaxed scan may return results slightly out of order.
    That is harmless when the rows are the answer, and not harmless here --
    ``services/hybrid_search.py`` enumerates this branch's rows into
    ``vec_rank`` and RRF weights that rank as ``1 / (k + rank)``. Under relaxed
    ordering an index artifact stops being an ordering detail and becomes a
    fusion input, recorded in ``retrieval_receipts.vector_ranks`` as the vector
    branch's considered opinion. The workshop then asks a participant to
    reconstruct the fused score from those ranks.

    Sorting in the query does not fix it: an outer ORDER BY over the same
    distance is elided by the planner, which has no way to know the index's
    output was only approximately sorted. Verified on pgvector 0.8.5 -- the
    plan carries no Sort node above the index scan either way. The ordering
    guarantee has to come from the scan mode.

    The catalog loader sets this at database level via ALTER DATABASE, but
    that only applies to NEW connections — existing pool connections need
    this configure callback to pick up the setting.

    Also binds ``pellier.run_id`` when a workshop run is in progress, so the
    ``run_id`` DEFAULT on every evidence table (migration 049) stamps rows
    written through this pool. The value is bound as a parameter and only
    after it matches the shape the database CHECKs; a malformed id is
    dropped with a warning rather than reaching SQL.
    """
    stmt_ms = int(max(1000, settings.DB_STATEMENT_TIMEOUT_MS))
    lock_ms = int(max(250, settings.DB_LOCK_TIMEOUT_MS))
    idle_ms = int(max(1000, settings.DB_IDLE_IN_TX_TIMEOUT_MS))
    work_mem_mb = int(max(4, settings.DB_WORK_MEM_MB))
    ef_default = int(max(8, min(settings.VECTOR_EF_SEARCH_DEFAULT, settings.VECTOR_EF_SEARCH_MAX)))

    async with conn.cursor() as cur:
        await cur.execute("SET hnsw.iterative_scan = 'strict_order'")
        try:
            await cur.execute(f"SET hnsw.ef_search = {ef_default}")
        except Exception:
            logger.warning(
                "hnsw.ef_search setting unavailable on this cluster; "
                "continuing with engine defaults"
            )
        await cur.execute(f"SET statement_timeout = '{stmt_ms}ms'")
        await cur.execute(f"SET lock_timeout = '{lock_ms}ms'")
        await cur.execute(f"SET idle_in_transaction_session_timeout = '{idle_ms}ms'")
        await cur.execute(f"SET work_mem = '{work_mem_mb}MB'")
        run_id = current_run_id()
        if run_id and RUN_ID_PATTERN.fullmatch(run_id):
            await cur.execute(
                "SELECT set_config('pellier.run_id', %s, false)", (run_id,)
            )
        elif run_id:
            logger.warning(
                "Ignoring malformed workshop run id %r; evidence rows will not "
                "carry a run_id until it matches run-<12 hex>",
                run_id,
            )
    await conn.commit()


class DatabaseService:
    """
    Database connection pool manager for PostgreSQL.
    
    Uses psycopg 3 with async connection pooling for optimal performance.
    Automatically registers pgvector extension for vector operations.
    """
    
    def __init__(self):
        """Initialize database service (pool created on connect)."""
        self._pool: Optional[AsyncConnectionPool] = None
        self._is_connected = False
    
    async def connect(self) -> None:
        """
        Initialize database connection pool.
        
        Creates and configures the async connection pool with pgvector support.
        This should be called during application startup.
        
        Raises:
            psycopg.OperationalError: If connection fails
        """
        if self._is_connected:
            logger.warning("Database service already connected")
            return
        
        logger.info("Initializing database connection pool...")
        logger.info(f"Connecting to: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
        
        try:
            # Create connection pool
            self._pool = AsyncConnectionPool(
                conninfo=settings.database_url,
                min_size=settings.DB_POOL_MIN_SIZE,
                max_size=settings.DB_POOL_MAX_SIZE,
                timeout=settings.DB_POOL_TIMEOUT,
                open=False,  # Open manually after configuration
                configure=_configure_connection,
                check=_check_connection,
                kwargs={
                    "row_factory": dict_row,  # Return rows as dictionaries
                    "autocommit": False,  # Explicit transaction control
                },
            )

            # Open the pool
            await self._pool.open()

            # Mark as connected before testing
            self._is_connected = True

            # Test connection
            await self._test_connection()
            await self._verify_iterative_scan()
            logger.info(
                f"✅ Database pool initialized "
                f"(min={settings.DB_POOL_MIN_SIZE}, max={settings.DB_POOL_MAX_SIZE})"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    

    
    async def _test_connection(self) -> None:
        """
        Test database connection and verify pgvector extension.
        
        Raises:
            Exception: If connection test fails
        """
        try:
            async with self.get_connection() as conn:
                async with conn.cursor() as cur:
                    # Test basic connectivity
                    await cur.execute("SELECT version();")
                    version = await cur.fetchone()
                    logger.info(f"PostgreSQL version: {version['version'].split(',')[0]}")
                    
                    # Verify pgvector extension
                    await cur.execute(
                        "SELECT * FROM pg_extension WHERE extname = 'vector';"
                    )
                    vector_ext = await cur.fetchone()
                    
                    if vector_ext:
                        logger.info("✅ pgvector extension is available")
                    else:
                        logger.warning("⚠️ pgvector extension not found")
                    
                    # Verify product_catalog table exists
                    await cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'pellier'
                            AND table_name = 'product_catalog'
                        );
                    """)
                    table_exists = await cur.fetchone()
                    
                    if table_exists and table_exists['exists']:
                        logger.info("✅ product_catalog table found")
                        
                        # Get row count
                        await cur.execute(
                            "SELECT COUNT(*) as count FROM pellier.product_catalog;"
                        )
                        count_result = await cur.fetchone()
                        logger.info(f"📊 Products in catalog: {count_result['count']:,}")
                    else:
                        logger.warning("⚠️ product_catalog table not found")
                        
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            raise

    async def _verify_iterative_scan(self) -> None:
        """Confirm pgvector iterative_scan is active on backend connections.

        Logs at INFO if 'strict_order'. Logs at WARNING for anything else,
        including 'off' (the pgvector default that causes filtered vector
        search to return incomplete results) and 'relaxed_order' (complete
        results, approximate ordering -- see ``_configure_connection`` for why
        the ranks this branch feeds cannot take that).
        """
        try:
            async with self.get_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SHOW hnsw.iterative_scan")
                    result = await cur.fetchone()
                    value = (
                        result.get("hnsw.iterative_scan")
                        if isinstance(result, dict)
                        else (result[0] if result else "unknown")
                    )
                    if value == "strict_order":
                        logger.info(f"✅ pgvector iterative_scan = {value}")
                    else:
                        logger.warning(
                            f"⚠️ pgvector iterative_scan = '{value}', "
                            f"expected 'strict_order'. Filtered vector search "
                            f"may return incomplete or mis-ordered results, and "
                            f"vector ranks feed RRF. Check connection pool "
                            f"configure callback."
                        )
        except Exception as e:
            logger.warning(f"Could not verify iterative_scan setting: {e}")

    async def disconnect(self) -> None:
        """
        Close database connection pool.
        
        This should be called during application shutdown.
        """
        if self._pool:
            logger.info("Closing database connection pool...")
            await self._pool.close()
            self._is_connected = False
            logger.info("✅ Database pool closed")

    async def check_health(self) -> None:
        """Check a pooled connection without running business-query setup.

        The pool's checkout callback performs a live PostgreSQL protocol probe.
        Registering vector types and setting query options adds several network
        round trips and is unnecessary for this connectivity check.
        """
        if not self._is_connected or not self._pool:
            raise RuntimeError("Database service not connected.")
        async with self._pool.connection(timeout=3):
            pass
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[AsyncConnection]:
        """
        Get a database connection from the pool.
        
        Context manager that automatically returns connection to pool.
        
        Yields:
            AsyncConnection: Database connection with dict_row factory
            
        Example:
            ```python
            async with db.get_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT * FROM products")
                    results = await cur.fetchall()
            ```
        
        Raises:
            RuntimeError: If database service not connected
        """
        if not self._is_connected or not self._pool:
            raise RuntimeError(
                "Database service not connected. Call connect() first."
            )
        
        async with self._pool.connection() as conn:
            try:
                # Adapters belong to the physical connection. Re-registering
                # on every borrow repeats four type-catalog round trips, which
                # can exhaust a request deadline over a remote SSM tunnel.
                if not getattr(conn, "_pellier_vector_registered", False):
                    from pgvector.psycopg import register_vector_async
                    await register_vector_async(conn)
                    conn._pellier_vector_registered = True
                # Defense in depth: re-assert iterative_scan on every acquire
                # in case the pool configure callback didn't run (invalidated
                # connection replay, future refactor, etc.)
                async with conn.cursor() as cur:
                    await cur.execute("SET hnsw.iterative_scan = 'strict_order'")
                # Wrap the connection's cursor factory to log queries for
                # the Observatory State Management live strip. This catches
                # raw cursor usage (VectorSearch, etc.) that bypasses
                # fetch_all / fetch_one.
                _instrument_connection(conn)
                yield conn
            except Exception as e:
                # Rollback on error
                await conn.rollback()
                logger.error(f"Database error (rolled back): {e}")
                raise
    
    @asynccontextmanager
    async def principal_session(
        self,
        principal_sub: Optional[str],
        *,
        role: str = "pellier_agent",
    ) -> AsyncIterator[AsyncConnection]:
        """Run statements under a non-owner role with the principal bound.

        Row-Level Security on ``pellier.orders`` and ``pellier.returns`` keys
        off ``pellier.principal_sub`` and applies to the *effective* role. Two
        things must therefore be true at once, on one physical connection,
        inside one transaction: the role is not the table owner, and the
        principal setting is present. This context manager is the only place
        that guarantees both.

        Why the other accessors cannot be used for protected statements:
        ``fetch_all``, ``fetch_one``, and ``execute_query`` each acquire their
        own pooled connection and release it. A ``SET LOCAL`` issued through
        one of them is invisible to the next call — and worse, the protected
        statement would then run with *no* principal, which fails closed and
        looks like "the row does not exist" rather than "you are not
        authorized". Two statements in the same Python function are not two
        statements in the same transaction.

        Both settings are transaction-local, so returning the connection to
        the pool cannot leak principal state into the next borrower. That is a
        structural property of ``SET LOCAL``, not a cleanup step that could be
        skipped on an error path.

        Args:
            principal_sub: Verified Cognito subject, or ``None`` for an
                anonymous turn. ``None`` binds an empty principal, which the
                policies resolve to no customer scope — access is denied, not
                widened. It is bound explicitly rather than left unset so the
                intent is legible in the transaction.
            role: Runtime role to assume. Must be a known non-owner role;
                ``SET ROLE`` cannot be parameterized, so the value is
                whitelisted rather than interpolated.

        Yields:
            AsyncConnection: inside an open transaction with the role and
            principal bound. Committing or rolling back is the caller's
            responsibility via the transaction block.

        Raises:
            ValueError: ``role`` is not a recognized runtime role.
            RuntimeError: The database service is not connected.

        Example:
            ```python
            async with db.principal_session(sub) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT id FROM pellier.returns WHERE customer_id = %s",
                        (customer_id,),
                    )
            ```
        """
        if role not in _RUNTIME_ROLES:
            raise ValueError(
                f"Unknown runtime role {role!r}; expected one of "
                f"{', '.join(sorted(_RUNTIME_ROLES))}"
            )

        async with self.get_connection() as conn:
            # An explicit transaction block makes the LOCAL scope unambiguous.
            # Outside a transaction, SET LOCAL is a no-op with a warning, and
            # a silently unbound principal is the failure mode this whole
            # method exists to prevent.
            async with conn.transaction():
                async with conn.cursor() as cur:
                    # Role name is a validated literal — SET ROLE takes no
                    # parameters. The principal IS parameterized, through
                    # set_config, so a subject value can never be SQL.
                    await cur.execute(f"SET LOCAL ROLE {role}")
                    await cur.execute(
                        "SELECT set_config('pellier.principal_sub', %s, true)",
                        (principal_sub or "",),
                    )
                yield conn

    @asynccontextmanager
    async def query_session(
        self,
        principal_sub: Optional[str],
        *,
        statement_timeout: str = "3s",
        search_path: str = "pellier, pg_temp",
    ) -> AsyncIterator[AsyncConnection]:
        """Run model-generated SQL under every containment the design requires.

        A separate primitive from ``principal_session`` on purpose. That one
        exists so a *known* statement can write within a principal's scope;
        this one exists so an *unknown* statement can read and nothing else.
        Conflating them behind a flag would make it possible to get the write
        role while believing the session was read-only.

        Four containments, none of which depends on the generated SQL being
        well-behaved:

        * ``pellier_query`` — SELECT on a scoped set, no write grants
          anywhere, and no access to ``pellier.tool_audit`` at all, so
          generated SQL can neither read the evidence ledger nor manufacture
          evidence.
        * ``READ ONLY`` transaction — the server refuses any write attempt
          regardless of what the statement asks for.
        * ``statement_timeout`` — a generated query cannot hold resources
          indefinitely.
        * fixed ``search_path`` — unqualified names resolve where expected
          rather than wherever the caller's search path happens to point.

        ``pellier.principal_sub`` is bound too, so Row-Level Security applies
        to generated SQL exactly as it does to a curated tool. Generated SQL
        does not get a wider view of customer data than the agent has.

        Args:
            principal_sub: Verified subject, or ``None`` for anonymous, which
                resolves to no customer scope.
            statement_timeout: Postgres interval string.
            search_path: Schemas unqualified names may resolve in.

        Yields:
            AsyncConnection inside an open read-only transaction.
        """
        async with self.get_connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    # READ ONLY first: `SET TRANSACTION` must precede the
                    # first query in the transaction, and putting it after the
                    # role switch would leave a window where it is not set.
                    await cur.execute("SET TRANSACTION READ ONLY")
                    await cur.execute("SET LOCAL ROLE pellier_query")
                    # `SET` takes no parameters — `SET LOCAL statement_timeout
                    # = %s` fails with `syntax error at or near "$1"`, and
                    # because that error aborts every query the module looks
                    # like a boundary that refuses everything, including
                    # legitimate questions. `set_config(..., is_local => true)`
                    # is the parameterizable equivalent.
                    await cur.execute(
                        "SELECT set_config('statement_timeout', %s, true)",
                        (statement_timeout,),
                    )
                    await cur.execute(
                        "SELECT set_config('search_path', %s, true)",
                        (search_path,),
                    )
                    await cur.execute(
                        "SELECT set_config('pellier.principal_sub', %s, true)",
                        (principal_sub or "",),
                    )
                yield conn

    async def fetch_all(self, query: str, *params: Any) -> list[dict]:
        """
        Execute query and fetch all results.
        
        Args:
            query: SQL query
            *params: Query parameters
            
        Returns:
            List of result rows as dictionaries
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return await cur.fetchall()
    
    async def fetch_one(self, query: str, *params: Any) -> Optional[dict]:
        """
        Execute query and fetch one result.
        
        Args:
            query: SQL query
            *params: Query parameters
            
        Returns:
            Single result row as dictionary, or None
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return await cur.fetchone()
    
    async def execute_query(self, query: str, *params: Any) -> None:
        """
        Execute query without returning results.
        
        Args:
            query: SQL query
            *params: Query parameters
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                await conn.commit()
    
    async def execute_many(
        self,
        query: str,
        params_list: list[tuple],
    ) -> None:
        """
        Execute a query multiple times with different parameters.
        
        Useful for batch inserts/updates.
        
        Args:
            query: SQL query to execute
            params_list: List of parameter tuples
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(query, params_list)
                await conn.commit()
    
    @property
    def is_connected(self) -> bool:
        """Check if database service is connected."""
        return self._is_connected
    
    async def health_check(self) -> dict:
        """
        Check database health status.
        
        Returns:
            dict: Health check results
        """
        if not self._is_connected:
            return {
                "status": "disconnected",
                "error": "Database not connected"
            }
        
        try:
            # Test query
            result = await self.fetch_one("SELECT 1 as test")
            
            # Get pool stats
            pool_stats = {
                "status": "healthy" if result else "unhealthy",
                "pool_size": self._pool.get_stats().pool_size if self._pool else 0,
                "pool_available": self._pool.get_stats().pool_available if self._pool else 0,
            }
            
            return pool_stats
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
