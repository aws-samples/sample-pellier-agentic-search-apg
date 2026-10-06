"""The Router: deterministic intent routing shared by local and managed rails.

``classify_intent`` returns exactly one of three intents, and each reaches one
agent:

    stock     warehouse and stock-count questions: how many, which warehouse,
              sold out, restock
    support   tickets, returns, refunds, store credit, damaged items, and the
              shopper's own past purchases ("what did I buy", "my orders")
    shopping  everything else, including price, compare, browse and gifts

Availability is often a constraint while choosing, not a stock question: Anna
asking for "an in-stock housewarming gift" is shopping. Only an explicit stock
operation routes to the Stock agent.
"""

from __future__ import annotations

import re

SHOPPING = "shopping"
STOCK = "stock"
SUPPORT = "support"
INTENTS = (SHOPPING, STOCK, SUPPORT)

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


def _is_choosing_products(query: str, words: set[str]) -> bool:
    """True when the shopper is picking products rather than asking a count."""
    q = query.lower()
    return bool(
        PRODUCT_SEEKING_PATTERN.search(query)
        or PAIRING_PATTERN.search(query)
        or words & CHOOSING_WORDS
        or any(phrase in q for phrase in CHOOSING_PHRASES)
    )


def classify_intent(query: str) -> str:
    """Return ``shopping``, ``stock`` or ``support`` for one shopper request."""
    q = (query or "").lower()
    words = set(re.findall(r"\w+", q))

    if PAST_PURCHASE_PATTERN.search(q):
        return SUPPORT
    if words & SUPPORT_WORDS or any(phrase in q for phrase in SUPPORT_PHRASES):
        return SUPPORT

    stock_operation = bool(words & STOCK_OPERATION_WORDS or STOCK_OPERATION_PATTERN.search(q))
    if stock_operation:
        return STOCK
    if words & AVAILABILITY_WORDS and not _is_choosing_products(query or "", words):
        return STOCK
    return SHOPPING
