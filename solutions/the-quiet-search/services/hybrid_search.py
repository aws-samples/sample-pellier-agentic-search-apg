"""
Hybrid Search Service — pgvector semantic branch (observe-only reference).

This file holds the pure pgvector cosine-similarity branch on its own.
Hybrid retrieval (vector + full-text + RRF) and Cohere Rerank are both
live in the application — see ``pellier/backend/services/hybrid_search.py``
and ``services/rerank.py``, plus the reranked reference in
``hybrid_search_with_rerank.py`` beside this file. Nothing was removed;
this copy deliberately excludes them so the semantic branch reads cleanly
next to the merged one.

The class name is retained (rather than renamed to ``VectorSearch``)
because ``HybridSearchService._vector_search`` is the canonical
pgvector reference called by the search tools and covered by
``tests/test_vector_search.py``. Renaming would ripple into the
solutions parity diff and recovery docs.
"""
import logging
import time
from datetime import datetime
from typing import Any, Dict, List

from services.database import DatabaseService
from services.sql_query_logger import QueryLog, get_query_logger
from services.store_tools import VISIBLE_CATALOG_SQL

logger = logging.getLogger(__name__)


class HybridSearchService:
    """Pgvector semantic search. Historical name; today it exposes only
    ``_vector_search``."""

    def __init__(self, db: DatabaseService):
        self.db = db

    async def _vector_search(
        self,
        embedding: List[float],
        limit: int,
        ef_search: int,
        iterative_scan: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Semantic vector similarity search using pgvector (retrieval reference).

        This is the core of semantic search — it finds products whose meaning
        is similar to the query, even when exact keywords don't match.

        The query follows Pellier's canonical pgvector pattern:
            - CTE: WITH query_embedding AS (SELECT %s::vector as emb)
            - Cosine distance operator: <=> (lower = more similar)
            - Similarity: 1 - (embedding <=> emb)  (higher = more similar)
            - HNSW tuning: SET LOCAL hnsw.ef_search = {int}  (per-query accuracy knob;
              Postgres disallows binds on utility statements — value coerced to int first)
            - Iterative scan: SET LOCAL hnsw.iterative_scan = 'strict_order'
              (pgvector 0.8.0+ — prevents overfiltering when WHERE clauses are strict)
            - In-stock filter: quantity > 0
            - Parameterized placeholders only — never f-string values into SQL.

        The method accepts a pre-computed embedding from the caller and does NOT
        call Bedrock Embed itself (Req 2.3.5).

        Args:
            embedding: Query embedding vector (1024 floats from Cohere Embed v4)
            limit: Maximum number of results
            ef_search: HNSW search parameter (higher = better recall, slower)
            iterative_scan: Enable pgvector 0.8.0+ iterative scanning (default: True)

        Returns:
            List of product dicts with similarity scores.

        ⏩ SHORT ON TIME? Run:
           cp solutions/the-quiet-search/services/hybrid_search.py pellier/backend/services/hybrid_search.py
        """
        # === REFERENCE: START ===
        sql = f"""
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
            WHERE {VISIBLE_CATALOG_SQL}
            ORDER BY embedding <=> (SELECT emb FROM query_embedding)
            LIMIT %s
        """
        params: List[Any] = [embedding, limit]

        # PostgreSQL disallows bind parameters on utility statements like SET,
        # so HNSW tuning values are interpolated directly. Inputs are coerced
        # (int for ef_search, whitelisted literal for iterative_scan) — no
        # user-supplied strings reach the SQL.
        ef_search_sql = int(ef_search)
        start_time = time.time()
        async with self.db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SET LOCAL hnsw.ef_search = {ef_search_sql}"
                )
                if iterative_scan:
                    await cur.execute(
                        "SET LOCAL hnsw.iterative_scan = 'strict_order'"
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
        # === REFERENCE: END ===
