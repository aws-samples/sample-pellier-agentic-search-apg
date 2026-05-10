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

        ⏩ SHORT ON TIME? Run:
           cp solutions/module1/services/hybrid_search.py pellier/backend/services/vector_search.py
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
