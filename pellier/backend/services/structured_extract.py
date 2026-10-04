"""
Structured query extraction via Claude Sonnet 5.

Path 2 retrieval, the agentic upgrade to hybrid+rerank, splits a
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

Why Sonnet 5 specifically:

  - Reliable JSON-shaped output against eight departments, 28 tags and
    30 materials.
  - Reporting-profile behavior: the structured path, not the editorial one.
  - Already configured at ``config.BEDROCK_REPORTING_MODEL``; no new
    model wiring.

Failure mode: malformed requirement fields or JSON are marked
``extraction_failed`` so the planner can refuse to treat failed extraction
as an unconstrained request, and ``extraction_reason`` says why: a reply
cut off at ``max_tokens`` is ``truncated``, a reply that is not the JSON
asked for is ``unreadable``, and a request that never answered is
``request_failed``. Unknown categories and tags are omitted rather
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
from services.catalog_vocabulary import KNOWN_CATEGORIES, KNOWN_MATERIALS, KNOWN_TAGS

logger = logging.getLogger(__name__)

# The reply is one short JSON object. Thinking is disabled on the request:
# on Claude 5 a thinking block counts against ``max_tokens`` and cuts the
# JSON off mid-key, which read as "no JSON object found".
EXTRACT_MAX_TOKENS = 400
THINKING_DISABLED = {"type": "disabled"}

REASON_TRUNCATED = "truncated"
REASON_UNREADABLE = "unreadable"
REASON_REQUEST_FAILED = "request_failed"


_SYSTEM_PROMPT = """You extract structured retrieval filters from a shopper's \
query for Pellier, a modern lifestyle store.

You return JSON with exactly these keys:
  - "required_categories" (list of strings): values from the allowed CATEGORIES \
list only when the shopper limits the request to them by naming the \
department ("only kitchen things", "show me shoes", "just Bath and body"). \
A product word is not a department: "linen shirts" or "a dopp kit" restricts \
nothing. Never derive one from an occasion, a recipient or a room \
("a housewarming gift", "for their new home"). Empty list otherwise.
  - "categories" (list of strings): CATEGORIES values that would likely fit. \
Recorded for explanation only; they never filter results.
  - "tags" (list of strings): zero or more values drawn from the allowed \
TAGS list. Empty list when no tag is implied.
  - "price_max_usd" (number or null): only set when the shopper names \
an explicit budget ceiling (e.g. "under $100"). Null otherwise.
  - "in_stock_only" (boolean): true when the shopper signals immediacy \
(e.g. "ready to ship", "in stock", "today"). False otherwise.
  - "exclusions" (list of strings): zero or more values drawn from the allowed \
TAGS or MATERIALS lists that the shopper asked NOT to see (e.g. "no candles", \
"nothing in leather", "avoid wool"). Use the listed name for a material: \
suede is leather, merino is wool, stoneware and terracotta are ceramic. \
Empty list when the shopper excluded nothing. A value belongs here or in \
"tags", never in both.
  - "unsupported_exclusions" (list of strings): anything else the shopper asked NOT \
to see that no TAGS or MATERIALS value names (e.g. "nothing scented", \
"no plastic"), each in a few of the shopper's own words. Empty list \
otherwise. Never drop an exclusion because it is not listed.
  - "soft_signal" (string): the residual taste/intent phrase the reranker \
should score against, with the structured constraints stripped out. \
Never empty; if the whole query is structured, repeat the most \
descriptive phrase verbatim.
  - "lifted" (list of strings): requirements from earlier in the chat that this \
message explicitly releases: "budget" ("ignore my budget"), "stock" \
("in stock or not"), "department", "all" ("show me anything"), or an \
excluded TAGS or MATERIALS value the shopper now allows ("candles are fine \
now" -> ["candle"]). Empty list otherwise. A limit the shopper simply did \
not repeat is not lifted, and neither is one a phrase merely resembles: \
"show me anything else for the kitchen" and "any price range you would \
suggest?" release nothing. A release inside a negation ("don't ignore my \
budget") is not a release.

Rules:
  - The query is the shopper's latest message only. The limits they stated \
earlier in the chat are kept for them elsewhere: report what this message \
states or releases, and never guess at an earlier one.
  - Never invent categories or tags outside the allowed lists.
  - Never echo the price ceiling into soft_signal.
  - A negative requirement is an exclusion, never a tag. "No candles" means \
exclusions ["candle"], not tags ["candle"]: the second one would rank the \
excluded thing higher.
  - Never echo an exclusion into soft_signal. The reranker scores similarity, \
so "no candles" in the soft signal pulls candles up.
  - Be conservative: leaving a field empty is better than guessing.
  - Output JSON only. No prose. No markdown. No code fences.
"""


class TruncatedReply(ValueError):
    """The model stopped at ``max_tokens`` before the JSON object closed."""


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


def request_body(query: str) -> Dict[str, Any]:
    """The InvokeModel body for one extraction: a short reply, no thinking."""
    return {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": EXTRACT_MAX_TOKENS,
        "thinking": dict(THINKING_DISABLED),
        "system": _SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": _build_prompt(query.strip())},
        ],
    }


class StructuredExtractor:
    """Sonnet-backed query to structured filters extractor.

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
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body(query)),
                contentType="application/json",
                accept="application/json",
            )
            payload = json.loads(response["body"].read())
            if payload.get("stop_reason") == "max_tokens":
                raise TruncatedReply("reply stopped at max_tokens before the JSON closed")
            text = "".join(
                block.get("text", "")
                for block in payload.get("content", [])
                if block.get("type") == "text"
            ).strip()
            parsed = self._parse_json(text)
            return self._sanitize(parsed, fallback_query=query)
        except Exception as exc:
            if isinstance(exc, TruncatedReply):
                reason = REASON_TRUNCATED
            elif isinstance(exc, ValueError):
                reason = REASON_UNREADABLE
            else:
                reason = REASON_REQUEST_FAILED
            logger.warning(
                "structured_extract failed (%s): %s; falling back to empty filters",
                reason,
                exc,
            )
            return self._empty(query, status="extraction_failed", reason=reason)

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------
    @staticmethod
    def _empty(
        query: str, status: str = "empty_query", reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """The unconstrained envelope, tagged with WHY it is unconstrained.

        "The model failed and we know nothing" and "the shopper genuinely
        constrained nothing" produce the same filters and are not the same
        finding. Only the first one can silently erase a requirement the
        shopper actually stated, so the caller is told which it got, and
        ``reason`` says how the model failed.
        """
        return {
            "categories": [],
            "required_categories": [],
            "tags": [],
            "price_max_usd": None,
            "in_stock_only": False,
            "exclusions": [],
            "unsupported_exclusions": [],
            "lifted": [],
            "soft_signal": query.strip() if query else "",
            "extraction_status": status,
            "extraction_reason": reason,
        }

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        # Defensive: Sonnet usually returns clean JSON, but strip code
        # fences in case the system prompt was ignored.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        # Find the outermost JSON object; this handles trailing prose
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
            "lifted",
        ):
            if parsed.get(name) is not None and not isinstance(parsed[name], list):
                raise ValueError(f"{name} must be a list")
        # What the latest message releases: a limit kind, "all", or an excluded
        # value now allowed. Anything else the model offers is ignored.
        releasable = {"budget", "stock", "department", "all"} | set(KNOWN_TAGS) | set(KNOWN_MATERIALS)
        lifted = [
            value.strip().lower()
            for value in parsed.get("lifted") or []
            if isinstance(value, str) and value.strip().lower() in releasable
        ]
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
            "lifted": lifted,
            "soft_signal": soft_signal.strip(),
            "extraction_status": "parsed",
            "extraction_reason": None,
        }


# -----------------------------------------------------------------
# Singleton accessor, the same shape as get_rerank_service().
# -----------------------------------------------------------------
_extractor: Optional[StructuredExtractor] = None


def get_structured_extractor() -> StructuredExtractor:
    global _extractor
    if _extractor is None:
        _extractor = StructuredExtractor()
    return _extractor
