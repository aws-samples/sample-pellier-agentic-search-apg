"""
Hybrid Search Service — pgvector + Postgres full-text + RRF.

Anna's anchor capability on the workshop's Aurora ladder:
    Marco  → pgvector cosine similarity (foundation)
    Anna   → vector + BM25 in parallel → RRF merge → Cohere Rerank v3.5
    Theo   → Aurora as agent system-of-record (writes + audit)

Why hybrid? Pure cosine struggles when the query carries a mix of
soft semantic intent and hard explicit constraints — e.g. Anna's T2
"something beautiful under $100". The embedding sees "beautiful" as a
vibe and "$100" as a fuzzy number; BM25 over name/brand/category/tags
catches "beautiful" as a literal token and the agent's max_price hint
filters by the actual number. Each modality contributes what it's
best at; RRF (Reciprocal Rank Fusion) merges the two ranked lists
without needing the score scales to be comparable.

The RRF formula is intentionally simple:
    score(d) = sum over each list L : 1 / (rrf_k + rank_L(d))

A document at rank 1 in both lists scores ~0.0328 (with rrf_k=60);
a document at rank 1 in only one list scores ~0.0164. The constant
``rrf_k`` (60 by convention) damps the contribution of low ranks so
a tail-of-list match doesn't drown out a head-of-list match.

This service does NOT call Bedrock. The caller passes an
already-computed embedding; reranking is a separate service
(services/rerank.py) so the failure modes stay decoupled — a bad
embedding doesn't bring down BM25; a Bedrock outage doesn't bring
down hybrid retrieval.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

from services.database import DatabaseService
from services.sql_query_logger import QueryLog, get_query_logger

logger = logging.getLogger(__name__)

# RRF constant. 60 is the value used in the original RRF paper
# (Cormack et al. 2009) and is the de-facto default across most
# hybrid-search systems. We do NOT expose it as a per-call knob —
# the workshop teaches that you tune the *retrieval* pieces and the
# *reranker*, not the fusion constant.
_RRF_K_DEFAULT = 60


class HybridSearch:
    """Hybrid pgvector + Postgres tsvector retrieval with RRF merge."""

    def __init__(self, db: DatabaseService):
        self.db = db

    async def search(
        self,
        query: str,
        query_embedding: List[float],
        k_vector: int = 20,
        k_bm25: int = 20,
        rrf_k: int = _RRF_K_DEFAULT,
        top_n: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Run vector + BM25 in parallel, RRF-merge, return top_n candidates.

        The two SQL queries run concurrently via ``asyncio.gather``; this
        gives Anna's path the same wall-clock latency as a single query
        on a warm cache (both indexes — HNSW + GIN — are independent).

        Args:
            query: Raw user query text. Used for BM25 only.
            query_embedding: 1024-dim Cohere Embed v4 vector. Used for
                pgvector cosine search.
            k_vector: Pool size for the vector branch (default 20).
            k_bm25: Pool size for the BM25 branch (default 20).
            rrf_k: RRF damping constant (default 60).
            top_n: Maximum candidates returned after fusion (default 30).
                The downstream reranker typically asks for top_n=30 so
                Cohere has enough material to reorder meaningfully.

        Returns:
            List of product dicts with the same keys as
            ``VectorSearch.vector_search`` plus an ``rrf_score: float``
            field. Sorted by rrf_score descending.
        """
        start_time = time.time()

        # Run both branches in parallel. asyncio.gather propagates the
        # first exception immediately — if BM25 fails (e.g. tsvector
        # column missing) we surface the real error rather than silently
        # falling back to vector-only.
        vector_rows, bm25_rows = await asyncio.gather(
            self._vector_search(query_embedding, k_vector),
            self._bm25_search(query, k_bm25),
        )

        # RRF merge.
        merged = self._rrf_merge(vector_rows, bm25_rows, rrf_k)

        # Cap at top_n. The reranker is the next stage; over-shipping
        # candidates wastes Bedrock tokens, under-shipping starves it.
        results = merged[:top_n]

        elapsed_ms = (time.time() - start_time) * 1000
        try:
            get_query_logger().queries.append(
                QueryLog(
                    query_type="hybrid_search",
                    sql=f"hybrid: vector(k={k_vector}) + bm25(k={k_bm25}) + rrf(k={rrf_k})",
                    params=[query, "<embedding>"],
                    execution_time_ms=elapsed_ms,
                    timestamp=datetime.now(),
                    rows_returned=len(results),
                )
            )
        except Exception as log_err:  # pragma: no cover
            logger.debug(f"sql_query_logger append failed: {log_err}")

        return results

    # -----------------------------------------------------------------
    # Internal — vector branch
    # -----------------------------------------------------------------
    async def _vector_search(
        self, embedding: List[float], k: int,
    ) -> List[Dict[str, Any]]:
        """Pgvector cosine search, no HNSW knobs.

        We deliberately don't tune ``ef_search`` or enable iterative_scan
        in the hybrid path — the BM25 branch covers the recall floor that
        iterative_scan was designed to protect, and a smaller HNSW pool
        keeps this stage fast (the reranker is the recall amplifier).
        """
        sql = """
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
            FROM blaize_bazaar.product_catalog
            WHERE "imgUrl" IS NOT NULL
            ORDER BY embedding <=> (SELECT emb FROM query_embedding)
            LIMIT %s
        """
        params: List[Any] = [embedding, k]
        start = time.time()
        async with self.db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
                results = [dict(r) for r in rows]

        try:
            get_query_logger().queries.append(
                QueryLog(
                    query_type="hybrid_vector_branch",
                    sql=sql,
                    params=["<embedding>", k],
                    execution_time_ms=(time.time() - start) * 1000,
                    timestamp=datetime.now(),
                    rows_returned=len(results),
                )
            )
        except Exception:  # pragma: no cover
            pass
        return results

    # -----------------------------------------------------------------
    # Internal — BM25 branch
    # -----------------------------------------------------------------
    async def _bm25_search(
        self, query: str, k: int,
    ) -> List[Dict[str, Any]]:
        """Postgres full-text BM25-ish search via ts_rank_cd.

        ``plainto_tsquery`` is intentional over ``websearch_to_tsquery``
        — the workshop's queries are short conversational phrases, not
        Google-style queries with quotes/operators. ``plainto`` gives
        us implicit AND across stems, which is what we want.

        The ``description_tsv @@ ts_query`` predicate is index-scanned
        via the GIN index on ``description_tsv`` (migration 005).

        ``ts_rank_cd`` is the cover-density variant of ts_rank — it
        rewards documents where the matched terms are close together,
        which approximates BM25's term-frequency saturation reasonably
        well without Postgres needing a real BM25 extension.
        """
        sql = """
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
                ts_rank_cd(description_tsv, plainto_tsquery('english', %s)) AS bm25_score
            FROM blaize_bazaar.product_catalog
            WHERE "imgUrl" IS NOT NULL
              AND description_tsv @@ plainto_tsquery('english', %s)
            ORDER BY bm25_score DESC
            LIMIT %s
        """
        params: List[Any] = [query, query, k]
        start = time.time()
        async with self.db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
                results = [dict(r) for r in rows]

        try:
            get_query_logger().queries.append(
                QueryLog(
                    query_type="hybrid_bm25_branch",
                    sql=sql,
                    params=params,
                    execution_time_ms=(time.time() - start) * 1000,
                    timestamp=datetime.now(),
                    rows_returned=len(results),
                )
            )
        except Exception:  # pragma: no cover
            pass
        return results

    # -----------------------------------------------------------------
    # Internal — RRF merge
    # -----------------------------------------------------------------
    @staticmethod
    def _rrf_merge(
        vector_rows: List[Dict[str, Any]],
        bm25_rows: List[Dict[str, Any]],
        rrf_k: int,
    ) -> List[Dict[str, Any]]:
        """Reciprocal Rank Fusion across two ranked lists.

        For each candidate that appears in either list, sum
        ``1 / (rrf_k + rank)`` over the lists it appears in. Documents
        in both lists necessarily score higher than documents in only
        one — that's the point. Sort descending; the result is a
        consensus ranking.

        Returns a list of merged rows with an ``rrf_score`` field
        appended. Each row carries through the original SQL projection
        (name/price/category/...). When a candidate appears in both
        branches we keep the vector-branch row as the source of truth
        so the per-row similarity score survives.
        """
        scores: Dict[Any, float] = {}
        rows_by_id: Dict[Any, Dict[str, Any]] = {}

        # Vector branch.
        for rank_zero, row in enumerate(vector_rows):
            pid = row["product_id"]
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (rrf_k + rank_zero + 1)
            # First time seeing this id, capture the row.
            if pid not in rows_by_id:
                rows_by_id[pid] = dict(row)

        # BM25 branch.
        for rank_zero, row in enumerate(bm25_rows):
            pid = row["product_id"]
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (rrf_k + rank_zero + 1)
            # If we didn't see this id in the vector branch, capture it
            # now. We deliberately do NOT overwrite the vector row when
            # it exists — preserving the cosine similarity field is
            # useful downstream (e.g. for telemetry).
            if pid not in rows_by_id:
                rows_by_id[pid] = dict(row)
            else:
                # Carry the BM25 score over for the cases where it's
                # the only signal for this row's diagnostic value.
                if "bm25_score" in row and "bm25_score" not in rows_by_id[pid]:
                    rows_by_id[pid]["bm25_score"] = row["bm25_score"]

        # Merge final scores into rows and sort.
        for pid, row in rows_by_id.items():
            row["rrf_score"] = scores[pid]

        merged = list(rows_by_id.values())
        merged.sort(key=lambda r: r["rrf_score"], reverse=True)
        return merged
