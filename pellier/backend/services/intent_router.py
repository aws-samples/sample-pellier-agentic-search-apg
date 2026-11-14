"""The Router: deterministic intent routing shared by local and managed rails.

``classify_intent`` returns exactly one of three intents, and each reaches one
agent:

    stock     warehouse and stock-count questions: how many, which warehouse,
              sold out, restock
    support   tickets, returns, refunds, store credit, damaged items, and the
              shopper's own past purchases ("what did I buy", "my orders")
    catalog   everything else, including price, compare, browse and gifts

``route_query`` returns the same decision with the rule that made it and the
words that matched, so the Router's step can say why. ``classify_intent`` is
its intent alone.

Availability is often a constraint while choosing, not a stock question: Anna
asking for "an in-stock housewarming gift" is a catalog request. Only an explicit stock
operation routes to the Stock agent.
"""

from __future__ import annotations

import re
from typing import NamedTuple

CATALOG = "catalog"
STOCK = "stock"
SUPPORT = "support"
INTENTS = (CATALOG, STOCK, SUPPORT)

SUPPORT_WORDS = frozenset({
    "ticket",
    "tickets",
    "return",
    "returns",
    "returned",
    "refund",
    "refunds",
    "refunded",
    "credit",
    "credited",
    "policy",
    "warranty",
    "broken",
    "defective",
    "chipped",
    "cracked",
    "damaged",
    "torn",
    "ripped",
    "exception",
    "arrived",
    "issue",
    "problem",
})
SUPPORT_PHRASES = ("store credit", "what now")

PAST_PURCHASE_PATTERN = re.compile(
    r"\b("
    r"what (did|have) i (buy|bought|purchase|purchased|order|ordered)|"
    r"what i (bought|purchased|ordered)|"
    r"(my|last) (purchase|purchases|order|orders|time)|"
    r"last time i (bought|purchased|ordered)|"
    r"previous (purchase|order|orders)|"
    r"order history|purchase history|buy again|reorder"
    r")\b",
    re.IGNORECASE,
)

# An explicit stock operation: a count, a warehouse, or a sell-through state.
STOCK_OPERATION_WORDS = frozenset({
    "inventory",
    "warehouse",
    "warehouses",
    "restock",
    "restocked",
    "brooklyn",
    "austin",
    "portland",
})
STOCK_OPERATION_PATTERN = re.compile(
    r"\b(how many|how much stock|low stock|running low|sold out|out of stock|"
    r"back in stock|on the floor)\b",
    re.IGNORECASE,
)
# Availability words: a stock question unless the shopper is choosing products.
AVAILABILITY_WORDS = frozenset({"stock", "available", "availability"})

PRODUCT_SEEKING_PATTERN = re.compile(
    r"\b(find|show|get|give|suggest|recommend|looking for|want|need|buy)\b.*"
    r"\b(shirt|dress|shoe|bag|jacket|pants|top|linen|cotton|silk|leather|"
    r"cashmere|wool|sandal|sneaker|boot|tote|candle|candles|throw|towel|hat|cuff|"
    r"earring|scarf|vest|cardigan|blazer|trench|anorak)\b",
    re.IGNORECASE,
)
PAIRING_PATTERN = re.compile(
    r"\b(go(?:es)? with|go(?:es)? well with|pair(?:s|ed)? with|what pairs with|"
    r"what would go with|complement(?:s|ary)?)\b",
    re.IGNORECASE,
)
CHOOSING_WORDS = frozenset({"gift", "gifts", "housewarming", "options", "shortlist", "choose"})
CHOOSING_PHRASES = ("looking for", "show me", "find me", "do you have any", "compare")


# How many matched words the Router's step line shows.
MAX_SHOWN_WORDS = 3
# The reason for a request no rule matched: slide 8's "Default: Catalog".
DEFAULT_REASON = "default"
# Shown for an availability question in place of its bare word "stock".
AVAILABILITY_SHOWN_PHRASES = ("in stock",)

RULE_PAST_PURCHASE = "past_purchase"
RULE_SUPPORT = "support"
RULE_STOCK_OPERATION = "stock_operation"
RULE_AVAILABILITY = "availability"
RULE_CHOOSING = "choosing"
RULE_DEFAULT = "default"


class Route(NamedTuple):
    """One routing decision: the intent, the rule that chose it and the words that matched."""

    intent: str
    rule: str
    words: tuple[str, ...]


def _as_written(query: str, start: int, word: str) -> str:
    """The matched word as the shopper wrote it, without a sentence-initial capital."""
    written = query[start:start + len(word)]
    if written.lower() != word:
        return word  # lowercasing changed the text's length; keep the rule's word
    before = query[:start].rstrip()
    if not before or before[-1] in ".!?:":
        return written.lower() if written.isupper() else written[:1].lower() + written[1:]
    return written


def _in_order(found: list[tuple[int, str]], query: str) -> tuple[str, ...]:
    """Matched words in the order the shopper wrote them, each once, as written.

    Where a phrase and a word start together, the phrase comes first, and a word
    already inside a phrase shown ("credit" in "store credit") is not repeated.
    """
    ordered: list[str] = []
    for start, word in sorted(found, key=lambda hit: (hit[0], -len(hit[1]))):
        shown = _as_written(query, start, word)
        if any(re.search(rf"\b{re.escape(shown)}\b", kept, re.IGNORECASE) for kept in ordered):
            continue
        ordered.append(shown)
    return tuple(ordered)


def _word_hits(q: str, vocabulary: frozenset[str]) -> list[tuple[int, str]]:
    return [(m.start(), m.group()) for m in re.finditer(r"\w+", q) if m.group() in vocabulary]


def _phrase_hits(q: str, phrases: tuple[str, ...]) -> list[tuple[int, str]]:
    return [(q.find(phrase), phrase) for phrase in phrases if phrase in q]


def _pattern_hits(q: str, pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    return [(m.start(), m.group().lower()) for m in pattern.finditer(q)]


def _seeking_hits(q: str) -> list[tuple[int, str]]:
    """The verb and the product a product-seeking request names, and any pairing phrase."""
    hits = [(m.start(), m.group()) for m in PAIRING_PATTERN.finditer(q)]
    for m in PRODUCT_SEEKING_PATTERN.finditer(q):
        hits += [(m.start(1), m.group(1)), (m.start(2), m.group(2))]
    return hits


def _choosing_words(query: str, q: str) -> tuple[bool, tuple[str, ...]]:
    """Whether the shopper is picking products, and the choosing words they used."""
    hits = _word_hits(q, CHOOSING_WORDS) + _phrase_hits(q, CHOOSING_PHRASES) + _seeking_hits(q)
    words = _in_order(hits, query)
    return bool(words), words


def route_query(query: str) -> Route:
    """Route one shopper request: its intent, the rule that chose it and the matched words."""
    query = query or ""
    q = query.lower()

    past = _pattern_hits(q, PAST_PURCHASE_PATTERN)
    if past:
        return Route(SUPPORT, RULE_PAST_PURCHASE, _in_order(past, query))
    support = _word_hits(q, SUPPORT_WORDS) + _phrase_hits(q, SUPPORT_PHRASES)
    if support:
        return Route(SUPPORT, RULE_SUPPORT, _in_order(support, query))

    stock_operation = _word_hits(q, STOCK_OPERATION_WORDS) + _pattern_hits(
        q, STOCK_OPERATION_PATTERN)
    if stock_operation:
        return Route(STOCK, RULE_STOCK_OPERATION, _in_order(stock_operation, query))

    choosing, choosing_words = _choosing_words(query, q)
    availability = _word_hits(q, AVAILABILITY_WORDS)
    if availability and not choosing:
        shown = availability + _phrase_hits(q, AVAILABILITY_SHOWN_PHRASES)
        return Route(STOCK, RULE_AVAILABILITY, _in_order(shown, query))
    if choosing:
        return Route(CATALOG, RULE_CHOOSING, choosing_words)
    return Route(CATALOG, RULE_DEFAULT, ())


def classify_intent(query: str) -> str:
    """Return ``catalog``, ``stock`` or ``support`` for one shopper request."""
    return route_query(query).intent


def routing_reason(query: str, intent: str) -> str | None:
    """Why the Router chose ``intent`` for ``query``: the shopper's words that matched.

    At most ``MAX_SHOWN_WORDS`` words, in the order written; ``DEFAULT_REASON`` when no
    rule matched. ``None`` when the rules would not choose ``intent`` for this query, so a
    caller never explains a decision the Router did not make.
    """
    route = route_query(query)
    if route.intent != intent:
        return None
    if route.rule == RULE_DEFAULT:
        return DEFAULT_REASON
    return ", ".join(route.words[:MAX_SHOWN_WORDS])
