"""
Structured query extraction via Claude Haiku 4.5.

Path 2 retrieval — the agentic upgrade to hybrid+rerank — splits a
shopper query into:

  - **filters**: structured WHERE-clause material (categories, tag list,
    price ceiling, in-stock requirement)
  - **soft_signal**: the residual taste phrase the reranker should
    actually score against (e.g. "milestone gift for a homeowner",
    not "under $100 milestone gift for a homeowner with wrap-ready")

The downstream pipeline runs vector cosine over rows that pass the
filters (with ``hnsw.iterative_scan`` so a strict WHERE doesn't drop
the candidate count below ``ef_search``), then sends a smaller pool
through Cohere Rerank using ``soft_signal`` as the query.

Why Haiku 4.5 specifically:

  - Latency: ~150–300 ms at temperature 0 for a JSON-shaped output
    against a 6-category / 28-tag enum. Cheap to add to every
    retrieval turn.
  - Determinism at T=0: the reporting persona, not the editorial one.
  - Already configured at ``config.BEDROCK_HAIKU_MODEL``; no new
    model wiring.

Failure mode: if Haiku returns malformed JSON or an unknown enum
value, the caller drops the filter and falls back to vector+rerank
with the raw query. The empty-extract path is *not* an error — it's
a query that has no structured signal (e.g. "something nice"), and
the pipeline degrades to plain vector+rerank cleanly.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import boto3

from config import settings

logger = logging.getLogger(__name__)


# Catalog facets — kept in sync with pellier.product_catalog seed data.
# If migrations add a category or tag, update both lists. The enum
# whitelist below uses these to drop hallucinated values from Haiku.
KNOWN_CATEGORIES: List[str] = [
    "Accessories",
    "Apparel",
    "Beauty",
    "Footwear",
    "Gifts",
    "Home Decor",
]

KNOWN_TAGS: List[str] = [
    "accessories", "activewear", "apothecary", "artisanal", "beauty",
    "candle", "canvas", "ceramic", "classic", "earth", "everyday",
    "footwear", "gift", "home", "leather", "linen", "loungewear",
    "merino", "minimal", "neutral", "resort", "sculptural", "slow",
    "timeless", "travel", "warm", "watch", "wellness",
]


_SYSTEM_PROMPT = """You extract structured retrieval filters from a boutique \
shopper's query.

You return JSON with exactly these keys:
  - "categories": list[str] — zero or more values drawn from the \
allowed CATEGORIES list. Empty list when the query is category-agnostic.
  - "tags": list[str] — zero or more values drawn from the allowed \
TAGS list. Empty list when no tag is implied.
  - "price_max_usd": number or null — only set when the shopper names \
an explicit budget ceiling (e.g. "under $100"). Null otherwise.
  - "in_stock_only": boolean — true when the shopper signals immediacy \
(e.g. "ready to ship", "in stock", "today"). False otherwise.
  - "soft_signal": string — the residual taste/intent phrase the reranker \
should score against, with the structured constraints stripped out. \
Never empty; if the whole query is structured, repeat the most \
descriptive phrase verbatim.

Rules:
  - Never invent categories or tags outside the allowed lists.
  - Never echo the price ceiling into soft_signal.
  - Be conservative — leaving a field empty is better than guessing.
  - Output JSON only. No prose. No markdown. No code fences.
"""


def _build_prompt(query: str) -> str:
    return (
        "CATEGORIES: " + ", ".join(KNOWN_CATEGORIES) + "\n"
        + "TAGS: " + ", ".join(KNOWN_TAGS) + "\n\n"
        + f"Query: {query}\n\n"
        + "JSON:"
    )


class StructuredExtractor:
    """Haiku-backed query → structured filters extractor.

    Synchronous boto3 invoke under the hood; the caller offloads to a
    worker thread when running inside the FastAPI event loop. Cost and
    latency are recorded at the comparison endpoint, not here.
    """

    def __init__(self, region: Optional[str] = None):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=region or settings.AWS_REGION,
        )
        self.model_id = settings.BEDROCK_HAIKU_MODEL

    def extract(self, query: str) -> Dict[str, Any]:
        """Extract filters + soft_signal. On any failure, return an
        empty-filter envelope so the caller falls back to plain vector
        + rerank with the raw query.
        """
        if not query or not query.strip():
            return self._empty(query)

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 400,
            "temperature": 0.0,
            "system": _SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": _build_prompt(query.strip())},
            ],
        }

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            payload = json.loads(response["body"].read())
            text = "".join(
                block.get("text", "")
                for block in payload.get("content", [])
                if block.get("type") == "text"
            ).strip()
            parsed = self._parse_json(text)
            return self._sanitize(parsed, fallback_query=query)
        except Exception as exc:
            logger.warning(
                "structured_extract failed: %s — falling back to empty filters",
                exc,
            )
            return self._empty(query)

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------
    @staticmethod
    def _empty(query: str) -> Dict[str, Any]:
        return {
            "categories": [],
            "tags": [],
            "price_max_usd": None,
            "in_stock_only": False,
            "soft_signal": query.strip() if query else "",
        }

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        # Defensive: Haiku at T=0 returns clean JSON, but strip code
        # fences in case the system prompt was ignored.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        # Find the outermost JSON object — handles trailing prose
        # the model occasionally adds.
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise ValueError("no JSON object found")
        return json.loads(text[first : last + 1])

    def _sanitize(
        self, parsed: Dict[str, Any], fallback_query: str,
    ) -> Dict[str, Any]:
        cat_set = {c.lower(): c for c in KNOWN_CATEGORIES}
        categories = [
            cat_set[c.lower()]
            for c in parsed.get("categories", []) or []
            if isinstance(c, str) and c.lower() in cat_set
        ]
        tag_set = set(KNOWN_TAGS)
        tags = [
            t.lower()
            for t in parsed.get("tags", []) or []
            if isinstance(t, str) and t.lower() in tag_set
        ]
        price_raw = parsed.get("price_max_usd")
        price_max: Optional[float]
        if isinstance(price_raw, (int, float)) and price_raw > 0:
            price_max = float(price_raw)
        else:
            price_max = None
        in_stock = bool(parsed.get("in_stock_only", False))
        soft_signal = parsed.get("soft_signal")
        if not isinstance(soft_signal, str) or not soft_signal.strip():
            soft_signal = fallback_query.strip()
        return {
            "categories": categories,
            "tags": tags,
            "price_max_usd": price_max,
            "in_stock_only": in_stock,
            "soft_signal": soft_signal.strip(),
        }


# -----------------------------------------------------------------
# Singleton accessor — same shape as get_rerank_service().
# -----------------------------------------------------------------
_extractor: Optional[StructuredExtractor] = None


def get_structured_extractor() -> StructuredExtractor:
    global _extractor
    if _extractor is None:
        _extractor = StructuredExtractor()
    return _extractor
