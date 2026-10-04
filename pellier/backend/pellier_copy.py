"""Pellier backend user-facing copy.

This module is the single source of truth for every customer-facing string
that the backend authors. Error envelopes, validation messages, and any
server-rendered strings that surface in Pellier live here.

The Shopping agent's system prompt (SHOPPING_SYSTEM_PROMPT) also lives here
so a single file review catches copy regressions across every surface the
participant might edit. The compliance scanner applies the same forbidden-word and
no-emoji rules to these prompts; the prompts are phrased with "specialist"
and "Pellier" instead of the forbidden terms.

All strings in this module must satisfy the Pellier copy rules:
  - no emoji
  - no em dashes (use regular hyphens)
  - none of the forbidden words listed in the Pellier conventions

The companion scanner lives at tests/test_copy_compliance.py.
"""

# Announcement bar (Requirement 1.1.2) - rendered verbatim.
ANNOUNCEMENT = (
    "Free shipping on orders over $150 \u00b7 Returns within 30 days "
    "\u00b7 Summer Edit No. 06 is now live"
)

PAGE_TITLE = "Pellier Summer Edit"

# Top nav (Requirement 1.2.1)
NAV = {
    "HOME": "Home",
    "SHOP": "Shop",
    "STORYBOARD": "Storyboard",
    "DISCOVER": "Discover",
    "ACCOUNT": "Account",
    "ASK_PELLIER": "Ask Pellier",
    "WORDMARK": "Pellier",
}

# Account button labels (Requirement 1.2.2, 1.2.3)
ACCOUNT_LABEL_SIGNED_OUT = "Account"


def account_label_signed_in(given_name: str) -> str:
    """Return the signed-in account label using the verified given_name claim."""
    return f"Hi, {given_name}"


# Hero breadcrumb + curated chip (Requirement 1.3.4, 1.3.10)
HERO_BREADCRUMB = "Someone just asked"
CURATED_FOR_YOU_CHIP = "Curated for you"
SEARCH_PILL_PLACEHOLDER = "Tell Pellier what you're looking for..."
MEMORY_WRITE_WARNING = (
    "The action completed, but this turn was not added to managed memory. "
    "Do not repeat the action."
)
MEMORY_READ_WARNING = (
    "The action completed, but prior managed-memory context could not be read. "
    "Review the result before relying on earlier turns."
)

# What the shopper is told when a request is waiting for a person.
#
# When the shopper asks for store credit, ask_a_person opens a review and the
# answer must say a person confirms it before anything changes. Left to the model,
# that second clause was measurably dropped (2026-08-27), and a shopper told only
# that a request was "prepared" reasonably believes it is done. So the backend owns
# the sentence: what happened, what did not, and who acts next, as the error
# taxonomy in VOICE.md requires.
GOVERNED_REVIEW_PENDING = (
    "Your request is prepared and waiting for a Pellier specialist to confirm it. "
    "Nothing about your order has changed yet."
)

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
            "brand": "Pellier",
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
    "HEADLINE": "Sign in and watch Pellier tailor the storefront to you.",
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
        "COPYRIGHT": "\u00a9 Pellier",
        "LINKS": ["Privacy", "Terms", "Accessibility"],
    },
}

# Command pill (Requirement 1.11.1)
COMMAND_PILL = {
    "LABEL": "Ask Pellier",
    "KEY_CAP_MAC": "\u2318K",
    "KEY_CAP_WIN": "Ctrl K",
}

# Auth modal (storefront.md "Auth modal" section, Requirement 2.6.6)
AUTH_MODAL = {
    "HEADER": "Welcome to Pellier",
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
    "SUBHEADLINE": "Pick what resonates. Pellier will take it from here.",
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
                {"label": "Shoes"},
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
    "SEARCH_FALLBACK_LOADING": "Pellier is thinking...",
}

STOREFRONT_COPY = {
    "CATALOG_STATS_UNAVAILABLE": "Aurora catalog statistics could not be read.",
    "CATALOG_STATS_EMPTY": "Aurora returned no catalog statistics.",
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
# "Pellier", "concierge", and verbs like "find" or "look up".

# Shared by specialists that recommend current-catalog products.
PRODUCT_REQUIREMENTS_PROMPT = (
    "Treat budget, stock requirements, and exclusions as binding for every "
    "recommendation, including alternatives. Present pieces as individual "
    "options by default. Before suggesting any pair, bundle, or set, add its "
    "exact returned prices and compare that total with the shopper's ceiling; "
    "'under' means strictly less. Do not recommend a combination that exceeds "
    "the limit even if each piece qualifies individually. If no combination "
    "fits, offer one qualifying piece. A filtered empty result means no piece "
    "met those requirements; it does not prove the catalog has none in that "
    "category. Broaden a preference only, and keep every requirement.\n"
)

# The Shopping agent's instructions: what to find, browse and compare, in the
# store's own voice (VOICE.md). Preferences reach it from AgentCore Memory and
# the persona preamble, never from a tool.
SHOPPING_SYSTEM_PROMPT = (
    "You help shoppers at Pellier, a modern lifestyle store with everyday "
    "prices, choose what to buy. Sound like a friendly person who works "
    "there: warm, plain and brief. Say what a piece is made of, what it is "
    "for and what it costs.\n"
    "\n"
    "<persona-context>\n"
    "The message may open with a 'PERSONA CONTEXT - {name} ({id})' block "
    "listing what Pellier remembers about the shopper and their past orders. "
    "Treat it as the store's memory of them. When it is present:\n"
    "  - Weight the pieces you choose toward their known preferences and "
    "past purchases. For 'something like what I bought', call "
    "search_products with the attributes of those purchases.\n"
    "  - Reference only product names, prices and facts that appear in the "
    "block. Never invent an action it does not mention, such as a comparison "
    "or a saved piece.\n"
    "  - Never ask the shopper to sign in or describe their taste when the "
    "block already answers it.\n"
    "</persona-context>\n"
    "\n"
    "<tools>\n"
    "- search_products: the default for anything to find, from a named piece "
    "to an intent such as 'a cozy layer for cool summer nights' or 'a "
    "housewarming gift under $100'. Pass an explicit price ceiling as "
    "max_price. If the result has constraint_notice, tell the shopper what it "
    "says and never present the results as meeting a requirement it names. "
    "If it has search_notice, say that alternatives have not been checked.\n"
    "- browse_department: when the shopper wants to look around one "
    "department (Clothing, Shoes, Bags and travel, Accessories, Home, Kitchen "
    "and table, Bath and body, Stationery and gifts) rather than pursue an "
    "intent.\n"
    "- compare_products: when the shopper weighs two specific pieces. It "
    "needs both product ids; if the shopper names pieces, call "
    "search_products first to find each productId. Lead with what the price "
    "difference buys, not with the numbers alone.\n"
    "- ask_a_person: only when the shopper asks for a person, or the ask "
    "needs human judgment the catalog cannot give: sympathy or condolence "
    "gifting, body-image or fit-for-pregnancy questions, cultural dressing "
    "norms. Try the catalog first; a partial match is still an answer. Pass "
    "a one-sentence reason.\n"
    "</tools>\n"
    "\n"
    "<grounding-rules>\n"
    "Name only pieces a tool returned, by their exact names, so each can "
    "render as a product card. Give one concrete returned attribute per "
    "piece: material, color, use or price. Prefer pieces whose tags match the "
    "shopper's intent; never recommend an unrelated piece because it is "
    "popular. Mention availability only when a tool returned it. "
    + PRODUCT_REQUIREMENTS_PROMPT
    + "</grounding-rules>\n"
    "\n"
    "<output-rules>\n"
    "Call a tool before writing anything. After the tool returns, choose two "
    "or three returned pieces (or every piece when fewer than two qualify) "
    "and write one compact sentence for each. Do not name a piece you did "
    "not choose. The chosen pieces render as cards automatically. If a tool "
    "returns nothing or an error, say so in one sentence. Never use markdown "
    "tables, numbered lists, headers, emojis or em dashes. Never ask a "
    "follow-up question.\n"
    "</output-rules>"
)
