"""Deterministic intent routing shared by local and managed execution rails."""

from __future__ import annotations

import re


PRICING_KEYWORDS = {
    "deal",
    "deals",
    "cheap",
    "cheapest",
    "price",
    "pricing",
    "discount",
    "affordable",
    "budget",
    "value",
    "cost",
    "save",
    "best price",
    "on sale",
    "bargain",
    "compare price",
}
INVENTORY_KEYWORDS = {
    "restock",
    "inventory",
    "stock",
    "out of stock",
    "low stock",
    "available",
    "availability",
    "in stock",
    "running low",
    "sold out",
    "back in stock",
    "warehouse",
    "at the brooklyn",
    "at the austin",
    "at the portland",
    "in brooklyn",
    "in austin",
    "in portland",
    "from brooklyn",
    "from austin",
    "from portland",
    "on the floor",
}
SUPPORT_KEYWORDS = {
    "ticket",
    "tickets",
    "return",
    "refund",
    "policy",
    "troubleshoot",
    "issue",
    "problem",
    "warranty",
    "broken",
    "defective",
    "chipped",
    "damaged",
    "arrived",
    "what now",
}
SEARCH_KEYWORDS = {
    "search for",
    "looking for",
    "where can I",
    "compare",
    "browse",
    "what do you have",
    "do you have",
    "show me",
    "find me",
}
PAIRING_PATTERN = re.compile(
    r"\b(go(?:es)? with|go(?:es)? well with|pair(?:s|ed)? with|what pairs with|"
    r"what would go with|complement(?:s|ary)?)\b",
    re.IGNORECASE,
)
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
PRODUCT_SEEKING_PATTERNS = re.compile(
    r"\b(find|show|get|give|suggest|recommend|looking for|want|need|buy)\b.*"
    r"\b(shirt|dress|shoe|bag|jacket|pants|top|linen|cotton|silk|leather|"
    r"cashmere|wool|sandal|sneaker|boot|tote|candle|throw|towel|hat|cuff|"
    r"earring|scarf|vest|cardigan|blazer|trench|anorak)\b",
    re.IGNORECASE,
)


def classify_intent(query: str) -> str:
    """Return the specialist intent for a shopper request."""
    q = query.lower()
    words = set(re.findall(r"\w+", q))

    if PAST_PURCHASE_PATTERN.search(query):
        return "recommendation"

    is_product_seeking = bool(PRODUCT_SEEKING_PATTERNS.search(query))
    # Availability is often a search constraint: Anna is choosing a gift,
    # not asking for a warehouse count. Preserve explicit inventory operations.
    selecting_products = (
        is_product_seeking
        or bool(PAIRING_PATTERN.search(query))
        or bool(words & {"gift", "gifts", "housewarming", "options", "shortlist"})
        or any(phrase in q for phrase in SEARCH_KEYWORDS if " " in phrase)
    )
    inventory_operation = bool(
        words & {"inventory", "warehouse", "warehouses", "restock", "brooklyn", "austin", "portland"}
        or re.search(r"\b(how many|how much|low stock|running low|sold out|out of stock)\b", q)
    )
    if (
        selecting_products
        and words & {"stock", "available", "availability"}
        and not inventory_operation
        and not words & SUPPORT_KEYWORDS
    ):
        return "search"
    if not is_product_seeking:
        for phrase in PRICING_KEYWORDS:
            if " " in phrase and phrase in q:
                return "pricing"
    for phrase in INVENTORY_KEYWORDS:
        if " " in phrase and phrase in q:
            return "inventory"

    if not is_product_seeking and words & {
        word for word in PRICING_KEYWORDS if " " not in word
    }:
        return "pricing"
    if words & {word for word in INVENTORY_KEYWORDS if " " not in word}:
        return "inventory"
    if words & SUPPORT_KEYWORDS:
        return "customer_support"
    if is_product_seeking or PAIRING_PATTERN.search(query):
        return "search"
    for phrase in SEARCH_KEYWORDS:
        if " " in phrase and phrase in q:
            return "search"
    if words & {word for word in SEARCH_KEYWORDS if " " not in word}:
        return "search"
    return "recommendation"
