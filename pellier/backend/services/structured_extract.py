"""
Structured query extraction via Claude Sonnet 4.6.

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

Why Sonnet 4.6 specifically:

  - Reliable JSON-shaped output against a eight-department / 28-tag enum.
  - Reporting-profile behavior: the structured path, not the editorial one.
  - Already configured at ``config.BEDROCK_REPORTING_MODEL``; no new
    model wiring.

Failure mode: malformed requirement fields or JSON are marked
``extraction_failed`` so the planner can refuse to treat failed extraction
as an unconstrained request. Unknown enum values are omitted rather than
interpolated into SQL. A successfully parsed query with no structured
signal (e.g. "something nice") may still use unconstrained retrieval;
that is distinct from losing requirements because extraction failed.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, List, Optional

import boto3

from config import settings

logger = logging.getLogger(__name__)


# Catalog facets — kept in sync with pellier.product_catalog seed data.
# The categories are the eight store departments (`DEPARTMENTS` in
# scripts/seed_pellier_catalog.py). If the catalog adds a department or tag,
# update both lists. The enum whitelist below uses these to drop
# hallucinated model values.
KNOWN_CATEGORIES: List[str] = [
    "Clothing",
    "Shoes",
    "Bags and travel",
    "Accessories",
    "Home",
    "Kitchen and table",
    "Bath and body",
    "Stationery and gifts",
]

KNOWN_TAGS: List[str] = [
    "accessories", "activewear", "apothecary", "artisanal", "beauty",
    "candle", "canvas", "ceramic", "classic", "earth", "everyday",
    "footwear", "gift", "home", "leather", "linen", "loungewear",
    "merino", "minimal", "neutral", "resort", "sculptural", "slow",
    "timeless", "travel", "warm", "watch", "wellness",
]

# Everything a product is made of, components and blends included. A material
# exclusion ("no wool") is enforced against this list, because the merchandising
# tags above name only a product's main material. Merino and cashmere products
# also list wool; suede is leather; stoneware and terracotta are ceramic.
KNOWN_MATERIALS: List[str] = [
    "acetate", "beeswax", "brass", "canvas", "cashmere", "ceramic", "cotton", "foam",
    "glass", "gold", "iron", "jute", "leather", "linen", "merino", "nylon", "paper",
    "polyester", "rattan", "rubber", "seagrass", "silicone", "silk", "silver",
    "soy wax", "steel", "stone", "straw", "wood", "wool",
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
  - "exclusions": list[str] — zero or more values drawn from the allowed \
TAGS list that the shopper asked NOT to see (e.g. "no candles", "nothing \
in leather", "avoid wool"). Empty list when the shopper excluded nothing. \
A tag belongs here or in "tags", never in both.
  - "soft_signal": string — the residual taste/intent phrase the reranker \
should score against, with the structured constraints stripped out. \
Never empty; if the whole query is structured, repeat the most \
descriptive phrase verbatim.

Rules:
  - Never invent categories or tags outside the allowed lists.
  - Never echo the price ceiling into soft_signal.
  - A negative requirement is an exclusion, never a tag. "No candles" means \
exclusions ["candle"], not tags ["candle"]: the second one would rank the \
excluded thing higher.
  - Never echo an exclusion into soft_signal. The reranker scores similarity, \
so "no candles" in the soft signal pulls candles up.
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
    """Sonnet-backed query → structured filters extractor.

    Synchronous boto3 invoke under the hood; the caller offloads to a
    worker thread when running inside the FastAPI event loop. Cost and
    latency are recorded at the comparison endpoint, not here.
    """

    def __init__(self, region: Optional[str] = None):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=region or settings.aws_region_resolved,
        )
        self.model_id = settings.BEDROCK_REPORTING_MODEL

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
            return self._empty(query, status="extraction_failed")

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------
    @staticmethod
    def _empty(query: str, status: str = "empty_query") -> Dict[str, Any]:
        """The unconstrained envelope, tagged with WHY it is unconstrained.

        "The model failed and we know nothing" and "the shopper genuinely
        constrained nothing" produce the same filters and are not the same
        finding. Only the first one can silently erase a requirement the
        shopper actually stated, so the caller is told which it got.
        """
        return {
            "categories": [],
            "tags": [],
            "price_max_usd": None,
            "in_stock_only": False,
            "exclusions": [],
            "soft_signal": query.strip() if query else "",
            "extraction_status": status,
        }

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        # Defensive: Sonnet usually returns clean JSON, but strip code
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
        # Malformed requirements cannot be treated as absent. The caller
        # catches validation errors and marks this as extraction_failed.
        for name in ("categories", "tags", "exclusions"):
            if parsed.get(name) is not None and not isinstance(parsed[name], list):
                raise ValueError(f"{name} must be a list")
        stock_raw = parsed.get("in_stock_only", False)
        if not isinstance(stock_raw, bool):
            raise ValueError("in_stock_only must be a boolean")
        cat_set = {c.lower(): c for c in KNOWN_CATEGORIES}
        categories = [
            cat_set[c.lower()]
            for c in parsed.get("categories", []) or []
            if isinstance(c, str) and c.lower() in cat_set
        ]
        tag_set = set(KNOWN_TAGS)
        # Exclusions are resolved first so a tag the model put on both sides
        # resolves to the safe reading. A false negative drops one candidate;
        # a false positive ranks the thing the shopper just refused.
        exclusions = [
            t.lower()
            for t in parsed.get("exclusions", []) or []
            if isinstance(t, str) and t.lower() in tag_set
        ]
        exclusion_set = set(exclusions)
        tags = [
            t.lower()
            for t in parsed.get("tags", []) or []
            if isinstance(t, str)
            and t.lower() in tag_set
            and t.lower() not in exclusion_set
        ]
        price_raw = parsed.get("price_max_usd")
        price_max: Optional[float]
        if price_raw is not None:
            if (
                isinstance(price_raw, bool)
                or not isinstance(price_raw, (int, float))
                or not math.isfinite(price_raw)
                or price_raw < 0
            ):
                raise ValueError("price_max_usd must be a finite, nonnegative price")
            price_max = float(price_raw)
        else:
            price_max = None
        in_stock = stock_raw
        soft_signal = parsed.get("soft_signal")
        if not isinstance(soft_signal, str) or not soft_signal.strip():
            soft_signal = fallback_query.strip()
        return {
            "categories": categories,
            "tags": tags,
            "price_max_usd": price_max,
            "in_stock_only": in_stock,
            # `SearchPlan.exclusions` already renders `NOT (tags ?| %s)` and
            # carries the predicate through every relaxation rung. Dropping the
            # field here was the only reason a stated "no candles" never
            # reached SQL.
            "exclusions": exclusions,
            "soft_signal": soft_signal.strip(),
            "extraction_status": "parsed",
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
