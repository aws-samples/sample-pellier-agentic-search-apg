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

  - Reliable JSON-shaped output against eight departments, 28 tags and
    30 materials.
  - Reporting-profile behavior: the structured path, not the editorial one.
  - Already configured at ``config.BEDROCK_REPORTING_MODEL``; no new
    model wiring.

Failure mode: malformed requirement fields or JSON are marked
``extraction_failed`` so the planner can refuse to treat failed extraction
as an unconstrained request. Unknown categories and tags are omitted rather
than interpolated into SQL; an exclusion outside the vocabulary is kept as
unsupported so the answer can say it went unchecked. A successfully parsed
query with no structured signal (e.g. "something nice") may still use unconstrained retrieval;
that is distinct from losing requirements because extraction failed.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

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


_SYSTEM_PROMPT = """You extract structured retrieval filters from a shopper's \
query for Pellier, a modern lifestyle store.

You return JSON with exactly these keys:
  - "required_categories": list[str] — values from the allowed CATEGORIES \
list only when the shopper limits the request to them by naming the \
department ("only kitchen things", "show me shoes", "just Bath and body"). \
A product word is not a department: "linen shirts" or "a dopp kit" restricts \
nothing. Never derive one from an occasion, a recipient or a room \
("a housewarming gift", "for their new home"). Empty list otherwise.
  - "categories": list[str] — CATEGORIES values that would likely fit. \
Recorded for explanation only; they never filter results.
  - "tags": list[str] — zero or more values drawn from the allowed \
TAGS list. Empty list when no tag is implied.
  - "price_max_usd": number or null — only set when the shopper names \
an explicit budget ceiling (e.g. "under $100"). Null otherwise.
  - "in_stock_only": boolean — true when the shopper signals immediacy \
(e.g. "ready to ship", "in stock", "today"). False otherwise.
  - "exclusions": list[str] — zero or more values drawn from the allowed \
TAGS or MATERIALS lists that the shopper asked NOT to see (e.g. "no candles", \
"nothing in leather", "avoid wool"). Use the listed name for a material: \
suede is leather, merino is wool, stoneware and terracotta are ceramic. \
Empty list when the shopper excluded nothing. A value belongs here or in \
"tags", never in both.
  - "unsupported_exclusions": list[str] — anything else the shopper asked NOT \
to see that no TAGS or MATERIALS value names (e.g. "nothing scented", \
"no plastic"), each in a few of the shopper's own words. Empty list \
otherwise. Never drop an exclusion because it is not listed.
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


_UPDATE_SYSTEM_PROMPT = """You read one shopper message in an ongoing shopping \
conversation for Pellier, a modern lifestyle store, and report how it changes \
the shopper's requirements.

You are given the CURRENT requirements and the MESSAGE. Return JSON with:
  - "change": "keep" when the message adds, changes or lifts no requirement \
("show me more", "what about the second one?"); "update" when it does; \
"new_request" only when the shopper clearly starts shopping for something \
else ("now something for my brother").
  - "price_max_usd": number or null. A budget the message states or changes.
  - "remove_budget": true only when the message lifts the budget.
  - "in_stock_only": true or false only when the message says so; else null.
  - "required_categories": list or null. CATEGORIES values the message limits \
the request to by naming them ("only kitchen things", "show me shoes"). A \
product word, a recipient or an occasion is not a department.
  - "categories": CATEGORIES values that would likely fit. Recorded only.
  - "preferences": list or null. TAGS the message says the shopper prefers.
  - "add_exclusions": TAGS or MATERIALS values the message refuses. Use the \
listed name: suede is leather, merino is wool, stoneware and terracotta are \
ceramic.
  - "unsupported_exclusions": refusals no TAGS or MATERIALS value names, each \
in a few of the shopper's own words ("nothing scented", "no plastic").
  - "remove_exclusions": CURRENT exclusions the message lifts ("candles are \
fine now").
  - "quotes": an object that maps each field you set, and "new_request" when \
you return it, to the exact words in the MESSAGE that support it.

Rules:
  - Only the MESSAGE changes requirements. Never drop a CURRENT requirement \
because the message does not repeat it.
  - Leave a field null or empty when the message does not address it.
  - Output JSON only. No prose. No markdown. No code fences.
"""

_UPDATE_LISTS = (
    "required_categories", "categories", "preferences", "add_exclusions",
    "unsupported_exclusions", "remove_exclusions",
)


def _build_update_prompt(message: str, current: Dict[str, Any]) -> str:
    return (
        "CATEGORIES: " + ", ".join(KNOWN_CATEGORIES) + "\n"
        + "TAGS: " + ", ".join(KNOWN_TAGS) + "\n"
        + "MATERIALS: " + ", ".join(KNOWN_MATERIALS) + "\n\n"
        + "CURRENT: " + json.dumps(current) + "\n\n"
        + f"MESSAGE: {message.strip()}\n\n"
        + "JSON:"
    )


def _sanitize_update(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Reject a malformed proposal outright; vocabulary is checked when applied."""
    if not isinstance(parsed, dict):
        raise ValueError("update must be an object")
    if parsed.get("change") not in ("keep", "update", "new_request"):
        raise ValueError("change must be keep, update or new_request")
    for name in _UPDATE_LISTS:
        if parsed.get(name) is not None and not isinstance(parsed[name], list):
            raise ValueError(f"{name} must be a list")
    for name in ("in_stock_only", "remove_budget"):
        if parsed.get(name) is not None and not isinstance(parsed[name], bool):
            raise ValueError(f"{name} must be a boolean")
    if parsed.get("quotes") is not None and not isinstance(parsed["quotes"], dict):
        raise ValueError("quotes must be an object")
    return {**parsed, "extraction_status": "parsed"}


def _split_exclusions(values: List[Any]) -> Tuple[List[str], List[str]]:
    """Sort stated exclusions into checkable values and unsupported phrases."""
    vocabulary = set(KNOWN_TAGS) | set(KNOWN_MATERIALS)
    checkable: List[str] = []
    unsupported: List[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        phrase = " ".join(value.split()).lower()
        target = checkable if phrase in vocabulary else unsupported
        if phrase not in target:
            target.append(phrase)
    return checkable, unsupported


def _build_prompt(query: str) -> str:
    return (
        "CATEGORIES: " + ", ".join(KNOWN_CATEGORIES) + "\n"
        + "TAGS: " + ", ".join(KNOWN_TAGS) + "\n"
        + "MATERIALS: " + ", ".join(KNOWN_MATERIALS) + "\n\n"
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

        try:
            parsed = self._invoke_json(_SYSTEM_PROMPT, _build_prompt(query.strip()), 400)
            return self._sanitize(parsed, fallback_query=query)
        except Exception as exc:
            logger.warning(
                "structured_extract failed: %s — falling back to empty filters",
                exc,
            )
            return self._empty(query, status="extraction_failed")

    def extract_update(self, message: str, current: Dict[str, Any]) -> Dict[str, Any]:
        """Propose how one shopper message changes their current requirements.

        ``services.shopping_requirements`` applies the proposal and keeps only
        changes the message's own words support. Returns
        ``{"extraction_status": "extraction_failed"}`` when the message cannot
        be read, so the caller keeps every earlier requirement.
        """
        try:
            parsed = self._invoke_json(
                _UPDATE_SYSTEM_PROMPT, _build_update_prompt(message, current), 600
            )
            return _sanitize_update(parsed)
        except Exception as exc:
            logger.warning("requirements update extraction failed: %s", exc)
            return {"extraction_status": "extraction_failed"}

    def _invoke_json(self, system: str, prompt: str, max_tokens: int) -> Dict[str, Any]:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
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
        return self._parse_json(text)

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
            "required_categories": [],
            "tags": [],
            "price_max_usd": None,
            "in_stock_only": False,
            "exclusions": [],
            "unsupported_exclusions": [],
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
        for name in (
            "categories", "required_categories", "tags", "exclusions", "unsupported_exclusions",
        ):
            if parsed.get(name) is not None and not isinstance(parsed[name], list):
                raise ValueError(f"{name} must be a list")
        stock_raw = parsed.get("in_stock_only", False)
        if not isinstance(stock_raw, bool):
            raise ValueError("in_stock_only must be a boolean")
        cat_set = {c.lower(): c for c in KNOWN_CATEGORIES}

        def known_categories(name: str) -> List[str]:
            return [
                cat_set[c.lower()]
                for c in parsed.get(name, []) or []
                if isinstance(c, str) and c.lower() in cat_set
            ]

        categories = known_categories("categories")
        required_categories = known_categories("required_categories")
        tag_set = set(KNOWN_TAGS)
        # Exclusions are resolved first so a tag the model put on both sides
        # resolves to the safe reading. A false negative drops one candidate;
        # a false positive ranks the thing the shopper just refused.
        exclusions, unsupported = _split_exclusions(
            [*(parsed.get("exclusions") or []), *(parsed.get("unsupported_exclusions") or [])]
        )
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
            "required_categories": required_categories,
            "tags": tags,
            "price_max_usd": price_max,
            "in_stock_only": in_stock,
            # `SearchPlan.exclusions` renders a NOT predicate over tags and
            # materials and carries it through every relaxation rung.
            "exclusions": exclusions,
            # Kept, never dropped, so the answer can say what went unchecked.
            "unsupported_exclusions": unsupported,
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
