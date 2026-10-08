"""
Hybrid Search Service — pgvector + Postgres full-text + RRF.

Anna's anchor capability on the workshop's Aurora ladder:
    Marco  → pgvector cosine similarity (foundation)
    Anna   → vector + Postgres FTS in parallel → RRF merge → Cohere Rerank v3.5
    Theo   → Aurora as agent system-of-record (writes + audit)

Why hybrid? Pure cosine struggles when the query carries a mix of
soft semantic intent and hard explicit constraints — e.g. Anna's T2
"something beautiful under $100". The embedding sees "beautiful" as a
vibe and "$100" as a fuzzy number; Postgres full-text search over
name/brand/category/tags catches literal tokens and the agent's
max_price hint filters by the actual number. Each modality contributes
what it's best at; RRF (Reciprocal Rank Fusion) merges the two ranked
lists without needing the score scales to be comparable.

The RRF formula is intentionally simple:
    score(d) = sum over each list L : 1 / (rrf_k + rank_L(d))

A document at rank 1 in both lists scores ~0.0328 (with rrf_k=60);
a document at rank 1 in only one list scores ~0.0164. The constant
``rrf_k`` (60 by convention) damps the contribution of low ranks so
a tail-of-list match doesn't drown out a head-of-list match.

This service does NOT call Bedrock. The caller passes an
already-computed embedding; reranking is a separate service
(services/rerank.py) so the failure modes stay decoupled — a bad
embedding doesn't bring down FTS; a Bedrock outage doesn't bring
down hybrid retrieval.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Sequence

from config import settings
from services.database import DatabaseService
from services.sql_query_logger import QueryLog, get_query_logger
from services.store_tools import fts_branch_sql, or_tsquery, rrf_merge, vector_branch_sql

logger = logging.getLogger(__name__)

# RRF constant. 60 is the value used in the original RRF paper
# (Cormack et al. 2009) and is the de-facto default across most
# hybrid-search systems. We do NOT expose it as a per-call knob —
# the workshop teaches that you tune the *retrieval* pieces and the
# *reranker*, not the fusion constant.
_RRF_K_DEFAULT = 60


# The branch SQL, the lexical query builder and RRF are stated once, in
# ``services.store_tools``, the module the shopper's ``search_products`` runs on
# both rails. This class runs the same statements asynchronously for the Lab 1
# strategy comparison and the Search teaching surface, so the SQL a participant
# reads there is the SQL a shopper's search ran.


class HybridSearch:
    """Hybrid pgvector + Postgres tsvector retrieval with RRF merge."""

    def __init__(self, db: DatabaseService):
        self.db = db

    async def search(
        self,
        query: str,
        query_embedding: List[float],
        k_vector: int = 0,
        k_fts: int = 0,
        rrf_k: int = 0,
        top_n: int = 0,
        hard_clauses: Sequence[str] = (),
        hard_params: Sequence[Any] = (),
    ) -> List[Dict[str, Any]]:
        """
        Run vector + Postgres FTS in parallel, RRF-merge, return top_n candidates.

        The two SQL queries run concurrently via ``asyncio.gather``; this
        gives Anna's path the same wall-clock latency as a single query
        on a warm cache (both indexes — HNSW + GIN — are independent).

        Args:
            query: Raw user query text. Used for FTS only.
            query_embedding: 1024-dim Cohere Embed v4 vector. Used for
                pgvector cosine search.
            k_vector: Pool size for the vector branch (default 20).
            k_fts: Pool size for the FTS branch (default 20).
            rrf_k: RRF damping constant (default 60).
            top_n: Maximum candidates returned after fusion (default 30).
                The downstream reranker typically asks for top_n=30 so
                Cohere has enough material to reorder meaningfully.
            hard_clauses: Compiled hard predicates from
                ``SearchPlan.compile_predicates``, applied to *both*
                branches before RRF so invalid candidates never enter the
                pool or consume reranker capacity.
            hard_params: Bound parameters for ``hard_clauses``.

        Returns:
            List of product dicts with the same keys as
            ``VectorSearch.vector_search`` plus an ``rrf_score: float``
            field. Sorted by rrf_score descending.
        """
        start_time = time.time()
        k_vector = int(k_vector or settings.HYBRID_VECTOR_K)
        k_fts = int(k_fts or settings.HYBRID_FTS_K)
        rrf_k = int(rrf_k or settings.HYBRID_RRF_K or _RRF_K_DEFAULT)
        top_n = int(top_n or settings.HYBRID_TOP_N)
        k_vector = max(5, min(k_vector, 100))
        k_fts = max(5, min(k_fts, 100))
        top_n = max(5, min(top_n, 100))

        # Run both branches in parallel. asyncio.gather propagates the
        # first exception immediately — if FTS fails (e.g. tsvector
        # column missing) we surface the real error rather than silently
        # falling back to vector-only.
        vector_rows, fts_rows = await asyncio.gather(
            self._vector_search(query_embedding, k_vector, hard_clauses, hard_params),
            self._fts_search(query, k_fts, hard_clauses, hard_params),
        )

        # RRF merge.
        merged = rrf_merge(vector_rows, fts_rows, rrf_k)

        # Cap at top_n. The reranker is the next stage; over-shipping
        # candidates wastes Bedrock tokens, under-shipping starves it.
        results = merged[:top_n]

        elapsed_ms = (time.time() - start_time) * 1000
        try:
            get_query_logger().queries.append(
                QueryLog(
                    query_type="hybrid_search",
                    sql=f"hybrid: vector(k={k_vector}) + fts(k={k_fts}) + rrf(k={rrf_k})",
                    params=[query, "<embedding>"],
                    execution_time_ms=elapsed_ms,
                    timestamp=datetime.now(),
                    rows_returned=len(results),
                )
            )
        except Exception as log_err:  # pragma: no cover
            logger.debug(f"sql_query_logger append failed: {log_err}")

        return results

    async def vector_only(
        self,
        query_embedding: List[float],
        k: int = 0,
        hard_clauses: Sequence[str] = (),
        hard_params: Sequence[Any] = (),
    ) -> List[Dict[str, Any]]:
        """Run the vector branch alone, annotated like a fused row.

        This is the ``vector`` retrieval strategy a ``SearchPlan`` may
        declare. Rows carry ``vec_rank`` (1-based) with ``fts_rank`` and
        ``rrf_score`` set to ``None``, so receipts and the executor's
        eligibility recheck read them the same way as ``search`` output.

        Args:
            query_embedding: 1024-dim Cohere Embed v4 vector.
            k: Pool size for the vector branch (default ``HYBRID_VECTOR_K``).
            hard_clauses: Compiled hard predicates ANDed into the WHERE.
            hard_params: Bound parameters for ``hard_clauses``.
        """
        k = max(5, min(int(k or settings.HYBRID_VECTOR_K), 100))
        rows = await self._vector_search(query_embedding, k, hard_clauses, hard_params)
        for rank_zero, row in enumerate(rows):
            row["vec_rank"] = rank_zero + 1
            row["fts_rank"] = None
            row["rrf_score"] = None
        return rows

    async def keyword_only(
        self,
        query: str,
        k: int = 0,
        hard_clauses: Sequence[str] = (),
        hard_params: Sequence[Any] = (),
    ) -> List[Dict[str, Any]]:
        """Run the full-text branch alone, annotated like a fused row.

        Rows carry ``fts_rank`` (1-based) with ``vec_rank`` and ``rrf_score``
        set to ``None``, mirroring ``vector_only``. A query made only of stop
        words has no lexical tokens and returns no rows.

        Args:
            query: Raw user query text.
            k: Pool size for the full-text branch (default ``HYBRID_FTS_K``).
            hard_clauses: Compiled hard predicates ANDed into the WHERE.
            hard_params: Bound parameters for ``hard_clauses``.
        """
        k = max(5, min(int(k or settings.HYBRID_FTS_K), 100))
        rows = await self._fts_search(query, k, hard_clauses, hard_params)
        for rank_zero, row in enumerate(rows):
            row["vec_rank"] = None
            row["fts_rank"] = rank_zero + 1
            row["rrf_score"] = None
        return rows

    # -----------------------------------------------------------------
    # Teaching surface — explain the merge with per-branch ranks
    # -----------------------------------------------------------------
    async def search_explained(
        self,
        query: str,
        query_embedding: List[float],
        k_vector: int = 0,
        k_fts: int = 0,
        rrf_k: int = 0,
        top_n: int = 0,
    ) -> Dict[str, Any]:
        """Run the same hybrid retrieval as :meth:`search`, but return the
        *intermediate* state instead of just the final ranking.

        It re-uses the exact same branch queries and the exact same
        ``store_tools.rrf_merge`` as the shipped path, so what a participant sees
        is what actually runs — there is no parallel "demo" pipeline.

        ``rrf_merge`` preserves each branch's 1-based rank on the merged
        rows, so this teaching view and the durable retrieval receipt inspect
        the same evidence produced by the shipped search path.

        Returns a dict with:
          - ``vector_rows``  — ordered vector-branch rows (carry ``similarity``)
          - ``fts_rows``    — ordered FTS-branch rows (carry ``fts_rank_score``)
          - ``merged``       — RRF-merged rows, each annotated with
            ``vec_rank`` / ``fts_rank`` (1-based, or ``None`` when the row
            did not appear in that branch) and ``rrf_score``
          - ``params``       — the resolved ``{k_vector, k_fts, rrf_k, top_n}``
            so the surface can label the knobs honestly
          - ``vector_sql`` / ``fts_sql`` — the literal branch SQL strings
        """
        k_vector = int(k_vector or settings.HYBRID_VECTOR_K)
        k_fts = int(k_fts or settings.HYBRID_FTS_K)
        rrf_k = int(rrf_k or settings.HYBRID_RRF_K or _RRF_K_DEFAULT)
        top_n = int(top_n or settings.HYBRID_TOP_N)
        k_vector = max(5, min(k_vector, 100))
        k_fts = max(5, min(k_fts, 100))
        top_n = max(5, min(top_n, 100))

        vector_rows, fts_rows = await asyncio.gather(
            self._vector_search(query_embedding, k_vector),
            self._fts_search(query, k_fts),
        )

        merged = rrf_merge(vector_rows, fts_rows, rrf_k)

        return {
            "vector_rows": vector_rows,
            "fts_rows": fts_rows,
            "merged": merged[:top_n],
            "params": {
                "k_vector": k_vector,
                "k_fts": k_fts,
                "rrf_k": rrf_k,
                "top_n": top_n,
            },
            "vector_sql": vector_branch_sql(),
            "fts_sql": fts_branch_sql(),
        }

    # -----------------------------------------------------------------
    # Internal — vector branch
    # -----------------------------------------------------------------
    async def _vector_search(
        self,
        embedding: List[float],
        k: int,
        extra_clauses: Sequence[str] = (),
        extra_params: Sequence[Any] = (),
    ) -> List[Dict[str, Any]]:
        """Pgvector cosine search over the filtered catalog.

        This query sets no HNSW knobs of its own. ``hnsw.iterative_scan``
        and ``hnsw.ef_search`` are session settings applied once per pooled
        connection in ``services.database._configure_connection``, so every
        branch query already runs with strict-order iterative scan and the
        configured ``ef_search``. A hard predicate in ``extra_clauses`` is
        therefore safe here: iterative scan keeps walking the graph until
        the filtered LIMIT is met instead of returning a short list.

        Two things this branch does not do. The FTS branch is an independent
        lexical signal fused by RRF; it does not backfill vector recall and
        it cannot see what this branch failed to retrieve. The reranker only
        reorders the pool it is given; a candidate absent from both branches
        cannot be recovered downstream, which is why the pool size matters.

        Args:
            embedding: Query vector.
            k: Branch pool size.
            extra_clauses: Compiled hard predicates ANDed into the WHERE.
            extra_params: Bound parameters for those predicates.
        """
        sql = vector_branch_sql(extra_clauses)
        params: List[Any] = [embedding, *extra_params, k]
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
                    params=["<embedding>", *extra_params, k],
                    execution_time_ms=(time.time() - start) * 1000,
                    timestamp=datetime.now(),
                    rows_returned=len(results),
                )
            )
        except Exception:  # pragma: no cover
            pass
        return results

    # -----------------------------------------------------------------
    # Internal — Postgres FTS branch
    # -----------------------------------------------------------------
    async def _fts_search(
        self,
        query: str,
        k: int,
        extra_clauses: Sequence[str] = (),
        extra_params: Sequence[Any] = (),
    ) -> List[Dict[str, Any]]:
        """Postgres full-text search via tsvector + ts_rank_cd.

        Note on query shape: we use ``to_tsquery`` with an OR-joined
        token string (built by ``store_tools.or_tsquery``) rather than
        ``plainto_tsquery`` or ``websearch_to_tsquery``. Both convenience
        wrappers default to AND-of-all-stems for plain text input,
        which over-filters conversational queries to zero results.

        ``ts_rank_cd`` is the cover-density variant of ts_rank. It
        rewards documents where matched terms sit close together.

        This is **not** BM25, and the distinction matters at this level.
        PostgreSQL cover-density ranking and BM25 are different families
        of lexical ranking function: BM25 is a probabilistic model that
        scores on term frequency saturation plus document-length
        normalization against corpus-wide inverse document frequency,
        whereas ``ts_rank_cd`` scores on the density and proximity of
        matched lexemes within the document's ``tsvector``. Neither the
        branch, its score field, nor its settings are named ``bm25``
        anywhere in this codebase — the field is ``fts_rank_score`` and
        the pool knob is ``k_fts``.

        The ``description_tsv @@ ts_query`` predicate is index-scanned
        via the GIN index on ``description_tsv`` (scripts/migrations/001_schema.sql).

        Args:
            query: Raw user query text.
            k: Branch pool size.
            extra_clauses: Compiled hard predicates ANDed into the WHERE.
            extra_params: Bound parameters for those predicates.
        """
        or_query = or_tsquery(query)
        if not or_query:
            # Pure stop-word query (rare). Return empty so RRF falls
            # back to vector-only ranking.
            return []
        sql = fts_branch_sql(extra_clauses)
        params: List[Any] = [or_query, *extra_params, k]
        start = time.time()
        async with self.db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
                results = [dict(r) for r in rows]

        try:
            get_query_logger().queries.append(
                QueryLog(
                    query_type="hybrid_fts_branch",
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
