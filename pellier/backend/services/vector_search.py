"""
Vector Search Service — pgvector semantic search.

The Module 1 teaching surface is pure pgvector cosine similarity. The
earlier hybrid (vector + keyword + RRF) and Cohere Rerank branches were
removed after the concierge switched to semantic-only retrieval.

``VectorSearch.vector_search`` is the canonical ``CHALLENGE 1`` block
referenced from ``agent_tools.find_pieces`` and from
``tests/test_vector_search.py``.
"""
import logging
import time
from datetime import datetime
from typing import Any, Dict, List

from config import settings
from services.database import DatabaseService
from services.sql_query_logger import QueryLog, get_query_logger

logger = logging.getLogger(__name__)


class VectorSearch:
    """Pgvector cosine-similarity semantic search over the product catalog."""

    def __init__(self, db: DatabaseService):
        self.db = db

    async def vector_search(
        self,
        embedding: List[float],
        limit: int,
        ef_search: int,
        iterative_scan: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Semantic vector similarity search using pgvector (Module 1 — Challenge 1).

        This is the core of semantic search — it finds products whose meaning
        is similar to the query, even when exact keywords don't match.

        The query follows the pgvector pattern documented in `.kiro/steering/database.md`:
            - CTE: WITH query_embedding AS (SELECT %s::vector as emb)
            - Cosine distance operator: <=> (lower = more similar)
            - Similarity: 1 - (embedding <=> emb)  (higher = more similar)
            - HNSW tuning: SET LOCAL hnsw.ef_search = {int}  (per-query accuracy knob;
              Postgres disallows binds on utility statements — value coerced to int first)
            - Iterative scan: SET LOCAL hnsw.iterative_scan = 'relaxed_order'
              (pgvector 0.8.0 — prevents overfiltering when WHERE clauses are strict)
            - In-stock filter: quantity > 0
            - Parameterized placeholders only — never f-string values into SQL.

        The method accepts a pre-computed embedding from the caller and does NOT
        call Bedrock Embed itself (Req 2.3.5).

        Args:
            embedding: Query embedding vector (1024 floats from Cohere Embed v4)
            limit: Maximum number of results
            ef_search: HNSW search parameter (higher = better recall, slower)
            iterative_scan: Enable pgvector 0.8.0 iterative scanning (default: True)

        Returns:
            List of product dicts with similarity scores.

        """
        # === CHALLENGE 1: START ===
        sql = """
            WITH query_embedding AS (
                SELECT %s::vector as emb
            )
            SELECT
                "productId" as product_id,
                name,
                brand,
                color,
                description,
                "imgUrl" as img_url,
                category,
                price,
                rating,
                reviews,
                badge,
                tags,
                1 - (embedding <=> (SELECT emb FROM query_embedding)) as similarity
            FROM pellier.product_catalog
            WHERE "imgUrl" IS NOT NULL
              AND embedding IS NOT NULL
            ORDER BY embedding <=> (SELECT emb FROM query_embedding)
            LIMIT %s
        """
        params: List[Any] = [embedding, limit]

        # PostgreSQL disallows bind parameters on utility statements like SET,
        # so HNSW tuning values are interpolated directly. Inputs are coerced
        # (int for ef_search, whitelisted literal for iterative_scan) — no
        # user-supplied strings reach the SQL.
        ef_search_sql = int(ef_search or settings.VECTOR_EF_SEARCH_DEFAULT)
        ef_search_sql = max(8, min(ef_search_sql, settings.VECTOR_EF_SEARCH_MAX))
        start_time = time.time()
        async with self.db.get_connection() as conn:
            async with conn.cursor() as cur:
                try:
                    await cur.execute(
                        f"SET LOCAL hnsw.ef_search = {ef_search_sql}"
                    )
                except Exception:
                    logger.debug("hnsw.ef_search not supported; skipping per-query tuning")
                if iterative_scan:
                    await cur.execute(
                        "SET LOCAL hnsw.iterative_scan = 'relaxed_order'"
                    )

                await cur.execute(sql, params)
                rows = await cur.fetchall()
                results = [dict(r) for r in rows]

        # Observability — log SQL with parameterized args only (Req 5.3.3, 5.4.2).
        # The logger redacts the embedding vector; we never interpolate values
        # into the SQL string itself.
        try:
            get_query_logger().queries.append(
                QueryLog(
                    query_type="vector_search",
                    sql=sql,
                    params=params,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    timestamp=datetime.now(),
                    rows_returned=len(results),
                )
            )
        except Exception as log_err:  # pragma: no cover - never break search on log failure
            logger.debug(f"sql_query_logger append failed: {log_err}")

        return results
        # === CHALLENGE 1: END ===

    async def vector_search_filtered(
        self,
        embedding: List[float],
        limit: int,
        ef_search: int,
        categories: List[str] | None = None,
        tags: List[str] | None = None,
        price_max_usd: float | None = None,
        in_stock_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Filtered vector cosine search — Path 2 retrieval.

        Combines structured WHERE-clause filters (extracted by
        ``StructuredExtractor``) with pgvector cosine ranking. The
        method always runs with ``hnsw.iterative_scan = 'relaxed_order'``
        because filtered HNSW is exactly the workload that ``iterative_scan``
        was designed for: a strict WHERE clause can drop the candidate
        count below the index's natural ``ef_search`` ceiling, which
        would cause silent recall loss without iterative scanning.

        Filters are applied as additional predicates on the same
        ``WHERE "imgUrl" IS NOT NULL AND embedding IS NOT NULL`` baseline
        the unfiltered branch uses. Empty/None filters are no-ops; an
        all-empty filter set degenerates to the same ranking as
        ``vector_search()`` plus the unconditional ``imgUrl`` /
        ``embedding`` checks.
        """
        params: List[Any] = [embedding]
        clauses: List[str] = [
            '"imgUrl" IS NOT NULL',
            "embedding IS NOT NULL",
        ]
        if categories:
            clauses.append("category = ANY(%s)")
            params.append(list(categories))
        if tags:
            clauses.append("tags ?| %s")
            params.append(list(tags))
        if price_max_usd is not None:
            clauses.append("price <= %s")
            params.append(float(price_max_usd))
        if in_stock_only:
            clauses.append("quantity > 0")
        where = " AND ".join(clauses)
        sql = f"""
            WITH query_embedding AS (
                SELECT %s::vector AS emb
            )
            SELECT
                "productId" AS product_id,
                name,
                brand,
                color,
                description,
                "imgUrl"   AS img_url,
                category,
                price,
                rating,
                reviews,
                badge,
                tags,
                1 - (embedding <=> (SELECT emb FROM query_embedding)) AS similarity
            FROM pellier.product_catalog
            WHERE {where}
            ORDER BY embedding <=> (SELECT emb FROM query_embedding)
            LIMIT %s
        """
        # ``WITH ... %s::vector`` consumed the embedding param above; the
        # filter params follow positionally; ``LIMIT %s`` closes the list.
        # Reorder into the final binding sequence.
        bind: List[Any] = [embedding] + params[1:] + [limit]
        # Recreate ``params[0]`` was the embedding placeholder for clause
        # accounting; the actual SQL has the embedding twice (once in the
        # CTE, once in the SELECT/ORDER BY through the CTE alias). Simpler
        # to rebuild ``bind`` cleanly:
        bind = [embedding]
        if categories:
            bind.append(list(categories))
        if tags:
            bind.append(list(tags))
        if price_max_usd is not None:
            bind.append(float(price_max_usd))
        bind.append(limit)

        ef_search_sql = int(ef_search or settings.VECTOR_EF_SEARCH_DEFAULT)
        ef_search_sql = max(8, min(ef_search_sql, settings.VECTOR_EF_SEARCH_MAX))
        start_time = time.time()
        async with self.db.get_connection() as conn:
            async with conn.cursor() as cur:
                try:
                    await cur.execute(
                        f"SET LOCAL hnsw.ef_search = {ef_search_sql}"
                    )
                except Exception:
                    logger.debug("hnsw.ef_search not supported; skipping per-query tuning")
                # Filtered HNSW always benefits from iterative_scan.
                await cur.execute(
                    "SET LOCAL hnsw.iterative_scan = 'relaxed_order'"
                )
                await cur.execute(sql, bind)
                rows = await cur.fetchall()
                results = [dict(r) for r in rows]

        try:
            get_query_logger().queries.append(
                QueryLog(
                    query_type="vector_search_filtered",
                    sql=sql,
                    params=bind,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    timestamp=datetime.now(),
                    rows_returned=len(results),
                )
            )
        except Exception as log_err:  # pragma: no cover
            logger.debug(f"sql_query_logger append failed: {log_err}")
        return results
