"""
Rerank Service — Cohere Rerank v3.5 via Bedrock.

Anna's hybrid pipeline (vector + Postgres FTS → RRF) produces a candidate
pool of ~30 products. The reranker reads the user's exact query
plus a short text rendering of each candidate and reorders by
relevance — usually with a markedly different ranking than what
either retrieval branch produced alone.

Why Cohere Rerank v3.5 specifically:

  - Trained on multilingual e-commerce-shaped data; product
    descriptions land in-distribution.
  - Returns relevance scores in [0, 1], so we can
    threshold ("don't show below 0.4") if we want. The magnitudes are
    not calibrated probabilities and a 0.8 is not "twice as relevant"
    as a 0.4 -- Cohere's own guidance is that the scores order results
    and that any threshold has to be chosen against labelled data for
    the corpus it will run on, not read off the number.
  - Adds one extra Bedrock call per request; the Lab 1 compare
    endpoint reports the observed latency per strategy, so the
    workshop's "is the extra spend worth it?" question has a live
    answer instead of a hand-wave.
  - Already configured in config.py as
    ``BEDROCK_RERANK_MODEL = "cohere.rerank-v3-5:0"`` so wiring is a
    single import away.

This module deliberately keeps the rerank step decoupled from the
retrieval step: a Bedrock outage degrades Anna's path to plain
hybrid (still a meaningful upgrade over Marco's pure vector), it
doesn't take the chat down. The search_products tool catches
the Bedrock exception and falls back to RRF order.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import boto3

from config import settings
from services.cache import get_cache

logger = logging.getLogger(__name__)


class RerankService:
    """Cohere Rerank v3.5 via the Bedrock Agent Runtime Rerank API.

    Bedrock exposes Cohere Rerank through the Bedrock Agent Runtime
    ``rerank`` operation. We send the candidate documents as inline text
    sources — the agent_tools wrapper builds these from product fields
    (name/description/category) so the reranker has enough signal to make
    a meaningful judgment.

    Deliberate branch divergence: this branch (``governed``) calls the
    ``bedrock-agent-runtime`` Rerank API (IAM: ``bedrock:Rerank``), which
    is also what the Lambda-backed Gateway tool uses, so the in-process
    and Gateway rails exercise the same Bedrock surface. ``main`` calls
    ``bedrock-runtime`` ``invoke_model`` instead (IAM:
    ``bedrock:InvokeModel``). Both are valid surfaces for
    ``cohere.rerank-v3-5:0``; the Workshop Studio template grants both
    actions.
    """

    def __init__(self, region: Optional[str] = None):
        self.region = region or settings.aws_region_resolved
        self.client = boto3.client(
            "bedrock-agent-runtime",
            region_name=self.region,
        )
        self.model_id = settings.BEDROCK_RERANK_MODEL
        self.model_arn = (
            self.model_id
            if self.model_id.startswith("arn:")
            else f"arn:aws:bedrock:{self.region}::foundation-model/{self.model_id}"
        )

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: int = 5,
    ) -> List[Dict[str, Any]]:
        """Rerank ``documents`` against ``query``; return top_n with scores.

        Args:
            query: User query string (what the agent is searching for).
            documents: Plain-text renderings of candidate products. Each
                document is a single string — name + description + tags
                concatenated by the caller. Length cap is implicit
                (Bedrock will return 4xx if any single document exceeds
                the model's per-doc limit, currently ~1024 tokens).
            top_n: Number of reranked results to return. Cohere returns
                top_n entries with their original-list indices and
                relevance_score in [0, 1].

        Returns:
            List of ``{"index": int, "relevance_score": float}`` dicts
            sorted by ``relevance_score`` descending. The ``index`` is
            into the *input* ``documents`` list so the caller can
            project candidate metadata back from their own pool.

            On any Bedrock error, returns an empty list — the caller
            is responsible for falling back to RRF order. We log at
            WARNING level so the failure is visible in the backend log
            without crashing the request path.
        """
        if not documents:
            return []
        if top_n <= 0:
            return []
        max_docs = max(1, int(settings.RERANK_MAX_DOCUMENTS))
        documents = documents[:max_docs]
        top_n = min(top_n, len(documents))

        cache = get_cache()
        cache_key = None
        if cache:
            cache_key = json.dumps(
                {
                    "query": query,
                    "documents": documents,
                    "top_n": top_n,
                    "model_id": self.model_id,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )
            cached = cache.get("rerank", cache_key)
            if cached is not None:
                return cached

        sources = [
            {
                "type": "INLINE",
                "inlineDocumentSource": {
                    "type": "TEXT",
                    "textDocument": {"text": doc},
                },
            }
            for doc in documents
        ]

        try:
            response = self.client.rerank(
                queries=[
                    {
                        "type": "TEXT",
                        "textQuery": {"text": query},
                    }
                ],
                sources=sources,
                rerankingConfiguration={
                    "type": "BEDROCK_RERANKING_MODEL",
                    "bedrockRerankingConfiguration": {
                        "modelConfiguration": {"modelArn": self.model_arn},
                        "numberOfResults": top_n,
                    },
                },
            )
            results = [
                {
                    "index": item.get("index"),
                    "relevance_score": item.get("relevanceScore", 0.0),
                }
                for item in response.get("results", [])
            ]
            if cache and cache_key:
                cache.set("rerank", cache_key, results, ttl=settings.RERANK_CACHE_TTL_SEC)
            return results
        except Exception as exc:
            # Don't crash the pipeline — return empty so the caller
            # falls back to RRF order. Telemetry then shows a missing
            # rerank stage, which is the honest signal.
            logger.warning(
                "Cohere Rerank failed: %s — caller should fall back to RRF order",
                exc,
            )
            return []


# -----------------------------------------------------------------
# Singleton accessor — mirrors the get_db_service pattern used
# elsewhere in services/.
# -----------------------------------------------------------------
_rerank_service: Optional[RerankService] = None


def get_rerank_service() -> RerankService:
    """Lazy singleton. The boto3 client is cheap to construct but the
    cached instance saves a few ms per turn and keeps Bedrock client
    config (region, retry policy) consistent."""
    global _rerank_service
    if _rerank_service is None:
        _rerank_service = RerankService()
    return _rerank_service
