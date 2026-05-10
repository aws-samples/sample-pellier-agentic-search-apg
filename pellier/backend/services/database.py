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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-turn query logger — feeds the Atelier State Management live strip.
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


async def _configure_connection(conn: AsyncConnection) -> None:
    """Pool configure callback — runs on every new connection from the pool.

    Sets hnsw.iterative_scan = 'relaxed_order' so filtered vector search
    (e.g., 'linen shirts under $100') returns complete result sets instead
    of fewer-than-LIMIT rows. See pgvector 0.7+ iterative_scan docs.

    The catalog loader sets this at database level via ALTER DATABASE, but
    that only applies to NEW connections — existing pool connections need
    this configure callback to pick up the setting.
    """
    async with conn.cursor() as cur:
        await cur.execute("SET hnsw.iterative_scan = 'relaxed_order'")
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

        Logs at INFO if 'relaxed_order'. Logs at WARNING for anything else,
        including 'off' (the pgvector default that causes filtered vector
        search to return incomplete results).
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
                    if value == "relaxed_order":
                        logger.info(f"✅ pgvector iterative_scan = {value}")
                    else:
                        logger.warning(
                            f"⚠️ pgvector iterative_scan = '{value}', "
                            f"expected 'relaxed_order'. Filtered vector search "
                            f"may return incomplete results. Check connection "
                            f"pool configure callback."
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
                # Register pgvector for this connection (async version)
                from pgvector.psycopg import register_vector_async
                await register_vector_async(conn)
                # Defense in depth: re-assert iterative_scan on every acquire
                # in case the pool configure callback didn't run (invalidated
                # connection replay, future refactor, etc.)
                async with conn.cursor() as cur:
                    await cur.execute("SET hnsw.iterative_scan = 'relaxed_order'")
                # Wrap the connection's cursor factory to log queries for
                # the Atelier State Management live strip. This catches
                # raw cursor usage (VectorSearch, etc.) that bypasses
                # fetch_all / fetch_one.
                _instrument_connection(conn)
                yield conn
            except Exception as e:
                # Rollback on error
                await conn.rollback()
                logger.error(f"Database error (rolled back): {e}")
                raise
    
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