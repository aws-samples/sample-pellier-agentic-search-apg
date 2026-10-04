"""
Vector Search Service — pgvector semantic search.

This module is the pure pgvector cosine-similarity branch. Hybrid
retrieval (vector + full-text + RRF) lives in ``hybrid_search.py`` and
Cohere Rerank in ``rerank.py`` — both live, not removed; this module
deliberately excludes them so the semantic branch stays readable on its
own.

``VectorSearch.vector_search`` is the canonical pgvector reference
called by ``agent_tools.search_products`` and covered by
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
              (strict, not relaxed: these rows are enumerated into
              ranks that feed RRF, and a relaxed scan may return
              them slightly out of order)
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

        """
        # === REFERENCE: START ===
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
                materials,
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

    async def vector_search_planned(
        self,
        embedding: List[float],
        limit: int,
        ef_search: int,
        predicates: List[str] | None = None,
        predicate_params: List[Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """Filtered vector search driven by a compiled ``SearchPlan``.

        This is the plan-aware entry point: ``services.search_plan``
        decides *which* predicates are legal and compiles them, and this
        method only executes them. Keeping compilation out of the
        retrieval layer is what lets one planner serve both the shipped
        Shopping agent path and the Lab 1 comparison without a second
        implementation drifting away from the first.

        Args:
            embedding: Query vector (Cohere Embed v4, 1024-dim).
            limit: Row cap for the returned pool.
            ef_search: HNSW ``ef_search`` for this query; clamped to the
                configured ceiling.
            predicates: SQL fragments from
                ``SearchPlan.compile_predicates``, ANDed onto the
                baseline. Each may contain ``%s`` placeholders.
            predicate_params: Bound parameters for those placeholders, in
                the same order. Never interpolated into the SQL string.

        Returns:
            Ranked product dicts, closest cosine match first.

        Raises:
            ValueError: If the placeholder count and the parameter count
                disagree — a mismatch would silently misbind a hard
                constraint, so it fails loudly instead.
        """
        clauses = list(predicates or [])
        clause_params = list(predicate_params or [])
        placeholders = sum(clause.count("%s") for clause in clauses)
        if placeholders != len(clause_params):
            raise ValueError(
                "compiled predicate placeholder/parameter mismatch: "
                f"{placeholders} placeholders vs {len(clause_params)} params"
            )
        return await self._vector_search_with_clauses(
            embedding=embedding,
            limit=limit,
            ef_search=ef_search,
            extra_clauses=clauses,
            extra_params=clause_params,
            query_type="vector_search_planned",
        )

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
        method always runs with ``hnsw.iterative_scan = 'strict_order'``
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
        clauses: List[str] = []
        clause_params: List[Any] = []
        if categories:
            clauses.append("category = ANY(%s)")
            clause_params.append(list(categories))
        if tags:
            clauses.append("tags ?| %s")
            clause_params.append(list(tags))
        if price_max_usd is not None:
            clauses.append("price <= %s")
            clause_params.append(float(price_max_usd))
        if in_stock_only:
            clauses.append("quantity > 0")

        return await self._vector_search_with_clauses(
            embedding=embedding,
            limit=limit,
            ef_search=ef_search,
            extra_clauses=clauses,
            extra_params=clause_params,
            query_type="vector_search_filtered",
        )

    async def _vector_search_with_clauses(
        self,
        *,
        embedding: List[float],
        limit: int,
        ef_search: int,
        extra_clauses: List[str],
        extra_params: List[Any],
        query_type: str,
    ) -> List[Dict[str, Any]]:
        """Execute filtered pgvector cosine search over compiled clauses.

        Single executor behind both ``vector_search_planned`` and
        ``vector_search_filtered``, so the two entry points cannot drift
        into two different WHERE baselines or two different binding
        orders — the class of bug that makes a hard constraint quietly
        stop applying.

        Filtered HNSW always runs with
        ``hnsw.iterative_scan = 'strict_order'``: a strict WHERE clause
        can drop the candidate count below the index's natural
        ``ef_search`` ceiling, which would cause silent recall loss.
        """
        clauses = [
            '"imgUrl" IS NOT NULL',
            "embedding IS NOT NULL",
            *extra_clauses,
        ]
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
                materials,
                1 - (embedding <=> (SELECT emb FROM query_embedding)) AS similarity
            FROM pellier.product_catalog
            WHERE {where}
            ORDER BY embedding <=> (SELECT emb FROM query_embedding)
            LIMIT %s
        """
        # Binding order mirrors the SQL exactly: the embedding binds once
        # (the CTE computes similarity and the SELECT/ORDER BY reference
        # the CTE alias), then each predicate's params in clause order,
        # then the LIMIT.
        bind: List[Any] = [embedding, *extra_params, limit]

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
                    "SET LOCAL hnsw.iterative_scan = 'strict_order'"
                )
                await cur.execute(sql, bind)
                rows = await cur.fetchall()
                results = [dict(r) for r in rows]

        try:
            get_query_logger().queries.append(
                QueryLog(
                    query_type=query_type,
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
