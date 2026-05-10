"""
Rerank Service — Cohere Rerank v3.5 via Bedrock.

Anna's hybrid pipeline (vector + BM25 → RRF) produces a candidate
pool of ~30 products. The reranker reads the user's exact query
plus a short text rendering of each candidate and reorders by
relevance — usually with a markedly different ranking than what
either retrieval branch produced alone.

Why Cohere Rerank v3.5 specifically:

  - Trained on multilingual e-commerce-shaped data; product
    descriptions land in-distribution.
  - Returns calibrated relevance scores in [0, 1], so we can
    threshold ("don't show below 0.4") if we want.
  - Latency ~250-350ms for 30 candidates; the workshop's "is the
    extra spend worth it?" question has a real answer instead of
    a hand-wave.
  - Already configured at config.py:51 as
    ``BEDROCK_RERANK_MODEL = "cohere.rerank-v3-5:0"`` so wiring is
    a single import away.

This module deliberately keeps the rerank step decoupled from the
retrieval step: a Bedrock outage degrades Anna's path to plain
hybrid (still a meaningful upgrade over Marco's pure vector), it
doesn't take the chat down. The find_pieces_hybrid tool catches
the Bedrock exception and falls back to RRF order.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import boto3

from config import settings

logger = logging.getLogger(__name__)


class RerankService:
    """Cohere Rerank v3.5 via Bedrock invoke_model.

    Bedrock exposes Cohere Rerank as a standard invoke_model target;
    the request body uses the Cohere Rerank API v2 schema. We send the
    candidate documents as plain strings — the agent_tools wrapper
    builds these from product fields (name/description/category) so
    the reranker has enough signal to make a meaningful judgment.
    """

    def __init__(self, region: Optional[str] = None):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=region or settings.AWS_REGION,
        )
        self.model_id = settings.BEDROCK_RERANK_MODEL

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
            WARNING level so the failure is visible in the Atelier
            without crashing the request path.
        """
        if not documents:
            return []
        if top_n <= 0:
            return []

        # Cohere's v2 API expects a JSON body with these fields. The
        # api_version is part of the body (not a Bedrock-level header).
        body = {
            "query": query,
            "documents": documents,
            "top_n": min(top_n, len(documents)),
            "api_version": 2,
        }

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            payload = json.loads(response["body"].read())
            return payload.get("results", [])
        except Exception as exc:
            # Don't crash the pipeline — return empty so the caller
            # falls back to RRF order. The Atelier will surface this
            # as a missing rerank stage in telemetry, which is the
            # honest signal.
            logger.warning(
                "Cohere Rerank failed: %s — caller should fall back to RRF order",
                exc,
            )
            return []


# -----------------------------------------------------------------
# Singleton accessor — mirrors the get_policy_service / get_db_service
# pattern used elsewhere in services/.
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
