"""
Take It Further - Module 1 Challenge 1.

Drop-in replacement for services/hybrid_search.py that wires Cohere Rerank v3.5
(Amazon Bedrock) on top of the pgvector cosine-similarity + full-text candidate
pool. Used when the storefront is configured with RERANK_ENABLED=true.

The base class remains HybridSearchService; the only behavioural change is that
search() now returns results from search_with_rerank() whenever a RerankService
instance is available. The rerank path overfetches candidates (20 by default,
tunable via RERANK_CANDIDATE_POOL), then asks Cohere to re-score them against
the natural-language query for final ordering.

Why this matters for ambiguous queries:
  "something for long summer walks" is not a keyword match for linen. Vector
  similarity surfaces linen pieces but also pulls in tangentially-related
  items (shorts, hats) with similar embeddings. Rerank treats the full query
  as a semantic unit and suppresses the near-miss candidates that cosine
  distance alone rewards.
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from services.database import DatabaseService
from services.hybrid_search import HybridSearchService
from services.rerank import RerankService

logger = logging.getLogger(__name__)


class HybridSearchWithRerankService(HybridSearchService):
    """HybridSearchService with a Cohere Rerank v3.5 post-processing stage."""

    def __init__(
        self,
        db: DatabaseService,
        rerank_service: Optional[RerankService] = None,
        candidate_pool_size: int = 20,
    ):
        super().__init__(db)
        self.rerank_service = rerank_service or RerankService()
        self.candidate_pool_size = candidate_pool_size

    async def search(
        self,
        query: str,
        embedding: List[float],
        limit: int = 5,
        vector_weight: float = 0.6,
        fulltext_weight: float = 0.4,
        ef_search: int = 100,
    ) -> Dict[str, Any]:
        """Overrides HybridSearchService.search() to route through rerank."""
        if not self.rerank_service:
            return await super().search(
                query, embedding, limit, vector_weight, fulltext_weight, ef_search
            )

        total_start = time.time()
        result = await self.search_with_rerank(
            query=query,
            embedding=embedding,
            rerank_service=self.rerank_service,
            limit=limit,
            candidate_pool_size=self.candidate_pool_size,
            ef_search=ef_search,
        )
        result["total_time_ms"] = round((time.time() - total_start) * 1000, 2)
        return result
