"""Blaize Bazaar backend user-facing copy.

This module is the single source of truth for every customer-facing string
that the backend authors. Error envelopes, validation messages, and any
server-rendered strings that surface to the boutique live here.

Specialist system prompts (RECOMMENDATION_SYSTEM_PROMPT, and later the
orchestrator prompt) also live here so a single file review catches copy
regressions across every surface the participant might edit (tasks 2.3
and 2.4). The compliance scanner applies the same forbidden-word and
no-emoji rules to these prompts; the prompts are phrased with "specialist"
and "Blaize" instead of the forbidden terms.

All strings in this module must satisfy the boutique copy rules:
  - no emoji
  - no em dashes (use regular hyphens)
  - none of the forbidden words listed in the boutique conventions

The companion scanner lives at tests/test_copy_compliance.py.
"""

# Announcement bar (Requirement 1.1.2) - rendered verbatim.
ANNOUNCEMENT = (
    "Free shipping on orders over $150 \u00b7 Returns within 30 days "
    "\u00b7 Summer Edit No. 06 is now live"
)

PAGE_TITLE = "Blaize Bazaar - Summer Edit No. 06"

# Top nav (Requirement 1.2.1)
NAV = {
    "HOME": "Home",
    "SHOP": "Shop",
    "STORYBOARD": "Storyboard",
    "DISCOVER": "Discover",
    "ACCOUNT": "Account",
    "ASK_BLAIZE": "Ask Blaize",
    "WORDMARK": "Blaize Bazaar",
}

# Account button labels (Requirement 1.2.2, 1.2.3)
ACCOUNT_LABEL_SIGNED_OUT = "Account"


def account_label_signed_in(given_name: str) -> str:
    """Return the signed-in account label using the verified given_name claim."""
    return f"Hi, {given_name}"


# Hero breadcrumb + curated chip (Requirement 1.3.4, 1.3.10)
HERO_BREADCRUMB = "Someone just asked"
CURATED_FOR_YOU_CHIP = "Curated for you"
SEARCH_PILL_PLACEHOLDER = "Tell Blaize what you're looking for..."

# The 8 rotating intents (Requirement 1.3.1, storefront.md "The 8 rotating intents").
# Intent 2 carries a productOverride: the Featherweight Trail Runner at $168
# with a 4.9 rating and an athletic running shoe image.
INTENTS = [
    {
        "id": 1,
        "query": "something for long summer walks",
        "matchedOn": ["linen", "warm", "everyday"],
        "productRef": {"name": "Italian Linen Camp Shirt"},
    },
    {
        "id": 2,
        "query": "a thoughtful gift for someone who runs",
        "matchedOn": ["athletic", "footwear", "gift"],
        "productOverride": {
            "name": "Featherweight Trail Runner",
            "brand": "Blaize Editions",
            "color": "Stone",
            "price": 168,
            "rating": 4.9,
            "reviewCount": 412,
            "imageUrl": "/images/featherweight-trail-runner.jpg",
        },
    },
    {
        "id": 3,
        "query": "something to wear for warm evenings out",
        "matchedOn": ["evening", "warm", "dresses"],
        "productRef": {"name": "Sundress in Washed Linen"},
    },
    {
        "id": 4,
        "query": "pieces that travel well",
        "matchedOn": ["travel", "accessories", "neutral"],
        "productRef": {"name": "Signature Straw Tote"},
    },
    {
        "id": 5,
        "query": "something for slow Sunday mornings",
        "matchedOn": ["slow", "soft", "home"],
        "productRef": {"name": "Ceramic Tumbler Set"},
    },
    {
        "id": 6,
        "query": "a linen piece that earns its golden hour",
        "matchedOn": ["linen", "evening", "warm"],
        "productRef": {"name": "Sundress in Washed Linen"},
    },
    {
        "id": 7,
        "query": "a cozy layer for cool summer nights",
        "matchedOn": ["outerwear", "evening", "slow"],
        "productRef": {"name": "Cashmere-Blend Cardigan"},
    },
    {
        "id": 8,
        "query": "something relaxed for weekend markets",
        "matchedOn": ["everyday", "linen", "classic"],
        "productRef": {"name": "Relaxed Oxford Shirt"},
    },
]

# Sign-in strip (Requirement 1.4.1)
SIGN_IN_STRIP = {
    "EYEBROW": "PERSONALIZED VISIONS",
    "HEADLINE": "Sign in and watch Blaize tailor the storefront to you.",
    "CTA": "Sign in for personalized visions",
    "DISMISS": "Not now",
}

# Curated banner (Requirement 1.4.3)
CURATED_BANNER_LABEL = "CURATED FOR YOU"
CURATED_BANNER_ADJUST_LINK = "Adjust preferences"


def curated_headline(given_name: str, prefs: list[str]) -> str:
    """Return the curated banner headline given the top three preferences.

    Expects a list of three preference display strings. Extra entries are
    ignored; short lists render whatever is present separated by middle dots.
    """
    top_three = prefs[:3]
    joined = " \u00b7 ".join(top_three)
    return f"Tailored to your preferences, {given_name}. {joined}"


CURATED_BANNER = {
    "LABEL": CURATED_BANNER_LABEL,
    "ADJUST_LINK": CURATED_BANNER_ADJUST_LINK,
    "headline": curated_headline,
}

# Live status strip (Requirement 1.5.1)
LIVE_STATUS = "Live inventory \u00b7 refreshed daily \u00b7 curated by hand"
SHIPPING = "Shipping"
RETURNS = "Returns"
SECURE_CHECKOUT = "Secure checkout"

# Category chips (Requirement 1.5.3)
CATEGORY_CHIPS = ["All", "Linen", "Dresses", "Accessories", "Outerwear", "Footwear", "Home"]

# Refinement panel (Requirement 1.8.1)
REFINEMENT = {
    "B_MARK_PREFIX": "B",
    "PROMPT": "Blaize here, want me to narrow this down?",
    "CHIPS": ["Under $100", "Ships by Friday", "Gift-wrappable", "From smaller makers"],
}

# Reasoning chip copy (Requirement 1.7). The pricing style exposes its urgent
# clause separately so the UI can render it in terracotta.
def reasoning_picked(reason: str) -> str:
    """Picked because {reason} - italic Fraunces with B mark prefix."""
    return f"Picked because {reason}"


def reasoning_matched(attr1: str, attr2: str, attr3: str) -> str:
    """Matched on: a \u00b7 b \u00b7 c - attributes drawn from product tags."""
    return f"Matched on: {attr1} \u00b7 {attr2} \u00b7 {attr3}"


def reasoning_pricing(amount_below: int, units_left: int) -> dict:
    """Price watch line. The urgent clause renders in terracotta."""
    return {
        "lead": f"Price watch: ${amount_below} below category average.",
        "urgent": f"Only {units_left} left.",
    }


def reasoning_context(text: str) -> str:
    """Context line, for example gift-ready copy."""
    return text


REASONING = {
    "picked": reasoning_picked,
    "matched": reasoning_matched,
    "pricing": reasoning_pricing,
    "context": reasoning_context,
    "DEFAULT_CONTEXT": "Gift-ready: signature packaging, arrives tomorrow",
}

# Storyboard teaser cards (Requirement 1.9.4)
STORYBOARD_TEASERS = [
    {
        "badge": "MOOD FILM",
        "volume": "Vol. 12",
        "title": "A summer worth slowing for.",
        "excerpt": (
            "Linen, ceramic, light that lingers. Three days in the hills with "
            "the pieces we kept reaching for."
        ),
        "link": "Read the full vision \u203a",
    },
    {
        "badge": "VISION BOARD",
        "volume": "Vol. 11",
        "title": "The last clay studio in Ojai.",
        "excerpt": (
            "One kiln, two hands, forty years of practice. A visit with the "
            "makers behind our ceramic line."
        ),
        "link": "Read the full vision \u203a",
    },
    {
        "badge": "BEHIND THE SCENES",
        "volume": "Vol. 10",
        "title": "How we chose this season.",
        "excerpt": (
            "Nine pieces survived the cut. A quiet walk-through of the edit "
            "room conversations that got us here."
        ),
        "link": "Read the full vision \u203a",
    },
]

# Minimal Storyboard and Discover routes (Requirement 1.13)
STORYBOARD_PAGE_COMING_SOON = (
    "Coming soon - the full editorial hub arrives with the next Edit."
)
DISCOVER_PAGE_SIGNED_OUT = (
    "Discover is tailored to you. Sign in and watch the storefront tune itself."
)
DISCOVER_PAGE_COMING_SOON = STORYBOARD_PAGE_COMING_SOON

# Footer (Requirement 1.10)
FOOTER = {
    "BRAND": {
        "TAGLINE": "Carefully curated goods from makers who care about craft",
    },
    "SHOP": {
        "HEADING": "Shop",
        "ITEMS": ["New arrivals", "Summer Edit", "Gift guide", "Sale"],
    },
    "ABOUT": {
        "HEADING": "About",
        "ITEMS": ["Our story", "Makers we love", "Sustainability", "Press"],
    },
    "SERVICE": {
        "HEADING": "Service",
        "ITEMS": ["Shipping", "Returns", "Contact", "FAQ"],
    },
    "STORYBOARD_NEWSLETTER": {
        "HEADING": "Storyboard",
        "COPY": "A weekly letter on craft, makers, and a slower kind of shopping",
        "EMAIL_PLACEHOLDER": "Your email",
        "SUBMIT": "Subscribe",
    },
    "BOTTOM_STRIP": {
        "COPYRIGHT": "\u00a9 Blaize Bazaar",
        "LINKS": ["Privacy", "Terms", "Accessibility"],
    },
}

# Command pill (Requirement 1.11.1)
COMMAND_PILL = {
    "LABEL": "Ask Blaize",
    "KEY_CAP_MAC": "\u2318K",
    "KEY_CAP_WIN": "Ctrl K",
}

# Auth modal (storefront.md "Auth modal" section, Requirement 2.6.6)
AUTH_MODAL = {
    "HEADER": "Welcome to Blaize Bazaar",
    "SUBHEADER": "Sign in for a storefront built for you",
    "EYEBROW": "PERSONALIZED VISIONS",
    "ITALIC_HEADLINE": "Let the storefront find you.",
    "BUTTON_GOOGLE": "Continue with Google",
    "BUTTON_APPLE": "Continue with Apple",
    "BUTTON_EMAIL": "Continue with email",
    "DISCLAIMER": "By continuing, you agree to our terms and privacy policy.",
    "FOOTER": "Secured by AgentCore Identity",
    "VERSION": "v2.4",
}

# Preferences onboarding modal (storefront.md "Preferences onboarding modal")
PREFERENCES_MODAL = {
    "HEADER": "A quick tune-up",
    "SUBHEADER": "Takes about 20 seconds. You can change these anytime.",
    "ITALIC_HEADLINE": "What moves you?",
    "SUBHEADLINE": "Pick what resonates. Blaize will take it from here.",
    "GROUPS": [
        {
            "heading": "Your overall vibe",
            "kind": "card",
            "chips": [
                {"label": "Minimal", "descriptor": "Quiet \u00b7 Considered"},
                {"label": "Bold", "descriptor": "Statement \u00b7 Saturated"},
                {"label": "Serene", "descriptor": "Soft \u00b7 Calming"},
                {"label": "Adventurous", "descriptor": "Outdoor \u00b7 Durable"},
                {"label": "Creative", "descriptor": "Layered \u00b7 Textured"},
                {"label": "Classic", "descriptor": "Timeless \u00b7 Refined"},
            ],
        },
        {
            "heading": "Favorite colors",
            "kind": "pill",
            "chips": [
                {"label": "Warm tones", "swatch": "terracotta-to-amber"},
                {"label": "Neutrals", "swatch": "sand-to-ink-soft"},
                {"label": "Earth", "swatch": "ink-soft-to-dusk"},
                {"label": "Soft pastels", "swatch": "cream-warm-to-cream"},
                {"label": "Deep and moody", "swatch": "ink-to-near-black"},
            ],
        },
        {
            "heading": "Where you wear it",
            "kind": "pill",
            "chips": [
                {"label": "Everyday"},
                {"label": "Travel"},
                {"label": "Evenings out"},
                {"label": "Outdoor"},
                {"label": "Slow mornings"},
                {"label": "Work"},
            ],
        },
        {
            "heading": "Categories you love",
            "kind": "pill",
            "chips": [
                {"label": "Linen"},
                {"label": "Footwear"},
                {"label": "Outerwear"},
                {"label": "Accessories"},
                {"label": "Home"},
                {"label": "Dresses"},
            ],
        },
    ],
    "SKIP": "Skip for now",
    "SUBMIT": "Save and see my storefront",
    "FOOTER": "Preferences stored with AgentCore Memory",
}

# Error copy (design.md "Error Handling" table). These strings surface to the
# user via the storefront UI; the backend sends machine codes, the frontend
# renders these strings. Kept here so the compliance scanner covers them.
ERRORS = {
    "AGENT_TIMEOUT": "Taking a moment. Try again?",
    "DB_UNAVAILABLE": "I can't reach the catalog right now.",
    "AUTH_INTERRUPTED": "Something interrupted the sign-in. Try again.",
    "EMPTY_SEARCH_RESULT": "Nothing yet. Try a different wording.",
    "SILENT_REFRESH_SAY": "",
    "STATUS_STRIP_STALE": "Catalog refreshing...",
    "SEARCH_FALLBACK_LOADING": "Blaize is thinking...",
}

# Machine codes used in SSE envelopes. These are NOT user-facing strings but
# are colocated for grep-ability when wiring the error table in later tasks.
ERROR_CODES = {
    "AGENT_TIMEOUT": "agent_timeout",
    "AUTH_FAILED": "auth_failed",
    "INVALID_STATE": "invalid_state",
    "INVALID_PREFERENCES": "invalid_preferences",
    "UNAVAILABLE": "unavailable",
    "DB_UNAVAILABLE": "db_unavailable",
}


# ============================================================
# Specialist system prompts (tasks 2.3, 2.4)
# ============================================================
# These are LLM-facing instructions, not shopper-visible copy. They still
# pass the compliance scanner so the same forbidden-word list applies: no
# "AI", "intelligent", "smart", "agent", "LLM", "vector", "embedding", and
# no "search" used as a standalone noun. Phrasing uses "specialist",
# "Blaize", "concierge", and verbs like "find" or "look up".

# Recommendation specialist prompt (Requirement 2.4.4). Emphasizes warm,
# editorial, catalog-style reasoning grounded in specific product
# attributes (brand, color, fabric, tags, price). Grounded recommendations
# should name specific pieces rather than hand-waving about categories.
RECOMMENDATION_SYSTEM_PROMPT = (
    "You are Blaize Bazaar's Recommendation Specialist. Your voice is warm, "
    "editorial, and catalog-style, like a thoughtful shop keeper writing a "
    "short note about what to try. Read like Aesop or Toast, not like a "
    "big-box retailer.\n"
    "\n"
    "<persona-context>\n"
    "The user message may open with a 'PERSONA CONTEXT - {name} ({id})' "
    "block that lists the shopper's known preferences (LTM facts) and past "
    "orders. Treat this block as authoritative ground truth about the "
    "shopper - it IS the store's memory of them, equivalent to a saved "
    "account, wish list, or order history. When it's present:\n"
    "  - For retrospective questions ('what did I buy', 'what I saved', "
    "'my last order', 'show me what I saved last time', 'my history'), "
    "answer DIRECTLY from the 'Past orders' list in the preamble. Do NOT "
    "call a tool. Do NOT apologize for lacking access - you have access "
    "via the preamble. Name 2-3 specific pieces with their exact prices "
    "as listed in the preamble, and a warm one-sentence tie-back to the "
    "shopper's known preferences.\n"
    "  - For 'something similar to what I bought' queries, read the "
    "preamble to identify the shopper's past purchases and preferences, "
    "then call find_pieces with terms that match those attributes "
    "(e.g. 'linen shirt' if they bought linen). This produces product "
    "cards grounded in their history.\n"
    "  - For other forward-looking questions ('recommend', 'find', 'show "
    "me something for…'), call a tool and weight the results toward the "
    "shopper's known preferences and past-order patterns.\n"
    "  - GROUNDING RULE: only reference product names, prices, categories, "
    "and facts that appear VERBATIM in the PERSONA CONTEXT block. Do NOT "
    "invent details like 'you compared two shirts side by side' or 'you "
    "bookmarked this' unless the preamble explicitly says so. If the "
    "preamble says 'Compared two camp shirts; saved a sage-green one', "
    "you may reference that. If it doesn't, don't fabricate the action.\n"
    "  - Never ask the shopper to 'log into your account' or 'describe "
    "what caught your eye' when the PERSONA CONTEXT block is present - "
    "that block already answers the question.\n"
    "</persona-context>\n"
    "\n"
    "<tools>\n"
    "- find_pieces: Use for intent-shaped queries such as 'something for "
    "warm evenings out' or 'a cozy layer for cool summer nights'. This finds "
    "pieces by meaning, not keywords.\n"
    "- whats_trending: Use when the shopper asks for bestsellers, "
    "popular picks, or what is in the Edit right now. Pass the category "
    "parameter when they name one (e.g. 'popular dresses').\n"
    "- side_by_side: Use when the shopper wants a side-by-side look at "
    "two specific pieces. Requires product IDs; if the shopper names pieces "
    "instead, call find_pieces first to resolve each productId, then "
    "compare.\n"
    "- explore_collection: Use for browsing a named category (linen, "
    "dresses, outerwear, accessories, footwear, home) when the shopper is "
    "browsing rather than pursuing a specific intent.\n"
    "</tools>\n"
    "\n"
    "<grounding-rules>\n"
    "Ground every recommendation in concrete product attributes. Always "
    "name at least one specific piece by its full product name (e.g. "
    "'Sundress in Washed Linen' or 'Cashmere-Blend Cardigan'), and include "
    "brand, color, and price drawn from the tool result. Never invent "
    "products or substitute generic descriptors. Prefer pieces whose tags "
    "genuinely match the shopper's intent (e.g. 'evening' and 'warm' for "
    "warm evenings; 'travel' and 'everyday' for pieces that travel well). "
    "Never recommend an irrelevant piece just because it is popular.\n"
    "</grounding-rules>\n"
    "\n"
    "<output-rules>\n"
    "For forward-looking queries: ALWAYS call a tool first. Do NOT write "
    "any text before calling a tool. After tool results come back, write "
    "1-2 short sentences in the warm, catalog-style voice that name the "
    "piece and explain, in attribute terms, why it suits the moment.\n"
    "\n"
    "For retrospective queries answered from the PERSONA CONTEXT preamble: "
    "do NOT call a tool. Write 2-3 short sentences naming specific past "
    "orders from the preamble with their prices.\n"
    "\n"
    "Products render as visual cards automatically, so do not list them in "
    "text. If a tool returns zero products or an error, say so briefly "
    "(e.g. 'Nothing that fits that mood right now; try a different "
    "wording.'). Never use markdown tables, numbered lists, headers, or "
    "emojis. Never ask follow-up questions.\n"
    "</output-rules>"
)


# Orchestrator system prompt (Requirements 2.4.6-2.4.8, 4.3.1). Routes an
# incoming shopper query to exactly one specialist from the five-tool
# roster. Priority order (pricing > inventory > support > search >
# recommendation) is lifted verbatim from coding-standards.md and is the
# single tie-breaker for ambiguous queries. Tool names use underscores
# so they pass the compliance scanner (the forbidden-word match requires
# a non-word boundary that the trailing underscore blocks).
ORCHESTRATOR_SYSTEM_PROMPT = (
    "You are the Blaize Bazaar concierge. Your one job is to pick the "
    "correct specialist for the shopper's request and pass the full query "
    "through to that specialist. You never answer the shopper directly.\n"
    "\n"
    "<specialists>\n"
    "- pricing: pricing, deals, budget constraints, "
    "price comparisons, under-$N framing, sale watch.\n"
    "- inventory: stock levels, availability, restock "
    "requests, low-stock checks, inventory health.\n"
    "- support: returns, refunds, warranties, exchanges, "
    "troubleshooting, policy questions.\n"
    "- search: finding specific pieces by name or attribute, "  # copy-allow: search-as-verb
    "browsing a named category, side-by-side product comparisons.\n"
    "- recommendation: open-ended curation, trending "
    "picks, gift ideas, intent-shaped questions like 'something for "
    "warm evenings out'. This is the default when nothing more specific "
    "fits.\n"
    "</specialists>\n"
    "\n"
    "<priority>\n"
    "When a query fits more than one specialist, apply this priority "
    "order strictly and pick the highest-priority match only:\n"
    "  1. pricing\n"
    "  2. inventory\n"
    "  3. support\n"
    "  4. search\n"  # copy-allow: search-as-verb
    "  5. recommendation\n"
    "Example: 'do you have the linen camp shirt in stock under $100' "
    "mentions both price and stock; pricing wins, so route to "
    "pricing. Example: 'can I return the wrong-size "
    "cardigan and find a replacement' mentions both support and "
    "finding a piece; support wins, so route to support.\n"
    "</priority>\n"
    "\n"
    "<rules>\n"
    "Call exactly one specialist per query. Pass the shopper's full "
    "original message as the query argument so the specialist has "
    "complete context. Do not summarize, rephrase, or add commentary "
    "before the call. Do not call more than one specialist in the same "
    "turn. Do not answer the shopper without a specialist call unless "
    "the message is a pure greeting or a question outside shopping "
    "(in which case reply with one short warm sentence and stop).\n"
    "</rules>\n"
    "\n"
    "<output-rules>\n"
    "Never use markdown tables, numbered lists, headers, or emojis. "
    "Never ask follow-up questions. The specialist's response is "
    "returned to the shopper as-is; you do not wrap or edit it.\n"
    "</output-rules>"
)
