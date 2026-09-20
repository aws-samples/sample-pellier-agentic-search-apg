#!/usr/bin/env python3
"""Canonical AgentCore Gateway tool schemas for Pellier's four MCP targets."""

try:
    from common.replacement_contract import REPLACEMENT_TOOL
except ModuleNotFoundError as exc:
    if exc.name != "common":
        raise
    # Observatory reads this checked-in contract with runpy from the backend,
    # without adding deployment modules to the application's import path.
    import runpy
    from pathlib import Path

    REPLACEMENT_TOOL = runpy.run_path(
        str(Path(__file__).parent / "common" / "replacement_contract.py")
    )["REPLACEMENT_TOOL"]

# AgentCore Gateway targets accept only this JSON-Schema keyword subset per
# (sub)property. The CLI owns target deployment; this sanitizer keeps its
# generated target input within the service schema.
_ALLOWED_SCHEMA_KEYS = {"type", "properties", "required", "items", "description"}


def _sanitize_tool_schema(node):
    """Recursively drop JSON-Schema keywords AgentCore's gateway target API does
    not accept, keeping only _ALLOWED_SCHEMA_KEYS. Recurses into `properties`
    (per-field dicts) and `items` (array element schema). Returns a new object;
    the source TOOL_SCHEMAS are left intact for readability."""
    if not isinstance(node, dict):
        return node
    cleaned = {}
    for key, value in node.items():
        if key not in _ALLOWED_SCHEMA_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            cleaned[key] = {
                prop_name: _sanitize_tool_schema(prop_schema)
                for prop_name, prop_schema in value.items()
            }
        elif key == "items":
            cleaned[key] = _sanitize_tool_schema(value)
        else:
            cleaned[key] = value
    return cleaned


# Tool schemas for Pellier MCP servers
TOOL_SCHEMAS = {
    "search": {
        "target_name": "pellier-discovery-search-target",
        "description": "Pellier search and inventory MCP server",
        "tools": [
            {
                "name": "search_products",
                "description": "Search products by natural language query using vector similarity.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language search query"},
                        "limit": {"type": "integer", "description": "Max results", "default": 5},
                        "max_price": {"type": "number", "description": "Maximum price filter"},
                        "min_rating": {"type": "number", "description": "Minimum star rating"},
                        "category": {"type": "string", "description": "Optional category substring"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "search_products_hybrid",
                "description": (
                    "Hybrid retrieval: pgvector cosine + Postgres FTS merged via "
                    "RRF, then reranked by Cohere Rerank v3.5. Higher quality "
                    "than search_products at the cost of one extra Bedrock call."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language search query"},
                        "max_price": {"type": "number", "description": "Maximum price filter (post-rerank)"},
                        "min_rating": {"type": "number", "description": "Minimum star rating (post-rerank)", "default": 0.0},
                        "category": {"type": "string", "description": "Category substring filter (post-rerank)"},
                        "limit": {"type": "integer", "description": "Max results", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "browse_category",
                "description": "Browse a category with rating and price filters.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "min_rating": {"type": "number", "default": 0.0},
                        "max_price": {"type": "number"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["category"],
                },
            },
            {
                "name": "check_inventory",
                "description": "Check aggregate inventory or one product across warehouses.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"product_query": {"type": "string"}},
                    "required": [],
                },
            },
            {
                "name": "get_low_stock",
                "description": "Get products with critically low stock.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 5}},
                    "required": [],
                },
            },
            {
                "name": "restock_inventory",
                "description": "Restock a product (max 500 per policy).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer"},
                        "quantity": {"type": "integer"},
                        "idempotency_key": {"type": "string"},
                        "warehouse_id": {"type": "string"},
                    },
                    "required": ["product_id", "quantity", "idempotency_key"],
                },
            },
        ],
    },
    "pricing": {
        "target_name": "pellier-value-pricing-target",
        "description": "Pellier pricing analysis MCP server",
        "tools": [
            {
                "name": "get_price_analysis",
                "description": "Price statistics by category.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"category": {"type": "string"}},
                    "required": [],
                },
            },
            {
                "name": "compare_products",
                "description": "Compare two products side by side.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_id_1": {"type": "integer"},
                        "product_id_2": {"type": "integer"},
                    },
                    "required": ["product_id_1", "product_id_2"],
                },
            },
        ],
    },
    "recommendation": {
        "target_name": "pellier-curation-recommendation-target",
        "description": "Pellier curation, memory, policy, and evidence MCP server",
        "tools": [
            {
                "name": "get_customer_preferences",
                "description": "Read a safe customer preference, order, and memory snapshot.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["customer_id"],
                },
            },
            {
                "name": "get_audit_trail",
                "description": "Read recent ALLOW receipts from pellier.tool_audit.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "tool_name": {"type": "string"},
                        "caller": {"type": "string"},
                        "limit": {"type": "integer", "default": 3},
                    },
                    "required": ["customer_id"],
                },
            },
            {
                "name": "get_trending_products",
                "description": "Most popular products by rating and review volume.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 5},
                        "category": {"type": "string"},
                    },
                    "required": [],
                },
            },
            {
                "name": "get_return_policy",
                "description": "Look up the return and care policy for a category.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "default": "default"},
                    },
                    "required": [],
                },
            },
            {
                "name": "get_related_products",
                "description": (
                    "Find complementary products by vector similarity. "
                    "The source_product_name is resolved and verified before "
                    "any similarity query runs."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source_product_name": {
                            "type": "string",
                            "description": (
                                "Named source product from the shopper request"
                            ),
                        },
                        "product_id": {
                            "type": "integer",
                            "description": (
                                "Optional ID returned by search_products; must "
                                "match source_product_name"
                            ),
                        },
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["source_product_name"],
                },
            },
        ],
    },
    "experience": {
        "target_name": "pellier-concierge-experience-target",
        "description": "Pellier experience-guide MCP server (returns, credits, tickets, stylist handoff)",
        "tools": [
            {
                "name": "initiate_return",
                "description": (
                    "Process a return atomically: ownership check + INSERT into "
                    "pellier.returns + (if damaged) decrement product_catalog "
                    "quantity. Reason must be one of damaged, wrong_size, "
                    "not_as_described, changed_mind, other."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "product_id": {"type": "integer"},
                        "reason": {
                            "type": "string",
                            "enum": [
                                "changed_mind",
                                "damaged",
                                "not_as_described",
                                "other",
                                "wrong_size",
                            ],
                        },
                        "idempotency_key": {"type": "string"},
                    },
                    "required": [
                        "customer_id",
                        "product_id",
                        "reason",
                        "idempotency_key",
                    ],
                },
            },
            {
                "name": "issue_credit",
                "outputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                "description": (
                    "Issue a goodwill store credit for service recovery, up "
                    "to $500.00. Writes one durable row per idempotency key "
                    "into pellier.store_credits."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "amount_cents": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50000,
                        },
                        "reason": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": [
                        "customer_id",
                        "amount_cents",
                        "reason",
                        "idempotency_key",
                    ],
                },
            },
            {
                "name": "get_ticket_history",
                "description": (
                    "Read a customer's past support tickets, newest first, "
                    "for context before answering a service question."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                    },
                    "required": ["customer_id"],
                },
            },
            {
                "name": "escalate_to_human",
                "description": (
                    "Hand the conversation off to a human stylist. Honest "
                    "fallback when no catalog tool can answer (cultural "
                    "dressing norms, body-image fit, out-of-policy returns)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string"},
                        "customer_id": {"type": "string"},
                    },
                    "required": ["customer_id"],
                },
            },
        ],
    },
}

TOOL_SCHEMAS["experience"]["tools"].append(REPLACEMENT_TOOL)

# ``turn_id`` is a route-minted correlation value. It is optional in the
# Gateway schema so direct/instructor invocations remain valid, but the managed
# Runtime dispatcher requires it on every shopper tool call and each Lambda
# preserves it in ``tool_audit.args`` while stripping it before business logic.
for _target in TOOL_SCHEMAS.values():
    for _tool in _target["tools"]:
        _tool["inputSchema"]["properties"].setdefault(
            "turn_id",
            {
                "type": "string",
                "description": (
                    "Server-minted shopper-turn correlation ID for the "
                    "append-only governance receipt."
                ),
            },
        )


# ---------------------------------------------------------------------------
# What the CURRENT WORKSHOP ITERATION publishes
# ---------------------------------------------------------------------------
#
# `TOOL_SCHEMAS` above is the canonical catalogue of everything Pellier can serve
# through a Gateway target. It is deliberately the superset, because a schema
# is a description of a capability and publication is a separate decision.
#
# Publishing a tool gives it an MCP action id, a Cedar action, a capability-endpoint
# state and a place in participant-visible discovery. Two capabilities are DEFERRED at
# the start of this workshop iteration, and one is published for staff only:
#
#   issue_credit        moves money. PUBLISHED, because the operator desk executes an
#                       approved credit through the Gateway with the operator's own
#                       token, and the baseline permit for it requires the staff scope
#                       claim. No shopper permit names it, so a shopper token is denied
#                       by default, and no shopper-facing specialist binds it.
#
#   restock_inventory   moves stock. An operator capability behind the desk's own
#                       authorization; no shopper-facing specialist binds it, and a
#                       shopper token must not be able to reach it on the Gateway.
#
#   get_ticket_history  reads a customer's support history. The read is only safe under
#                       an ownership condition, and binding that condition is Lab 3b.
#
# Derived, never hand-copied. A second literal tool list would drift from this one the
# first time a tool is added, and the drift would be invisible until a fresh provision.
#
# === WORKSHOP · Gateway catalogue · published tools: START ===
# SOLUTION - publish the read, keep the money movement deferred.
#
# `get_ticket_history` is a customer-scoped read the support specialist needs
# for Theo's return. Lab 3b binds its `customer_id` to the authenticated
# caller, so the read cannot cross customers. `restock_inventory` stays
# deferred: it moves stock and belongs to the operator desk, not to any
# shopper-facing specialist.
WORKSHOP_DEFERRED_TOOLS: frozenset[str] = frozenset({
    "restock_inventory",
})
# === WORKSHOP · Gateway catalogue · published tools: END ===


# Publication is not visibility. AgentCore Gateway evaluates Cedar on MCP tool
# discovery, so `list_tools` returns the subset the calling token could actually be
# permitted to invoke, never the whole published catalogue. Live on 2026-09-10: a
# shopper token saw 14 of 15 published tools (no `issue_credit`), and a staff token
# with no customer mapping saw 13 (it gained `issue_credit` and lost the two
# owner-scoped reads).
#
# These two sets name why a tool can be missing from one caller's listing. They are
# claim shapes, not a second catalogue: every name here is published.
STAFF_ONLY_GATEWAY_TOOLS: frozenset[str] = frozenset({"issue_credit", "replace_damaged_item"})
OWNER_SCOPED_GATEWAY_TOOLS: frozenset[str] = frozenset({
    "get_customer_preferences",
    "get_audit_trail",
    "get_ticket_history",
})


def discoverable_tools_for_claims(
    *, has_staff_scope: bool, has_customer_claim: bool
) -> frozenset[str]:
    """Return the published tools a token carrying these claims can discover.

    A permit whose condition this token could satisfy keeps its tool visible; a
    permit that names a claim the token does not carry removes it. Comparing a
    live listing against the full published set instead of this one reports a
    working policy boundary as a deployment failure.
    """
    visible = set(workshop_published_tools())
    if not has_staff_scope:
        visible -= STAFF_ONLY_GATEWAY_TOOLS
    if not has_customer_claim:
        visible -= OWNER_SCOPED_GATEWAY_TOOLS
    return frozenset(visible)


def canonical_tool_names() -> frozenset[str]:
    """Every tool name in the canonical catalogue, published or not."""
    return frozenset(
        tool["name"] for config in TOOL_SCHEMAS.values() for tool in config["tools"]
    )


def workshop_published_tools() -> frozenset[str]:
    """The exact tool names this workshop iteration publishes on the Gateway."""
    return canonical_tool_names() - WORKSHOP_DEFERRED_TOOLS


def workshop_target_tools() -> dict[str, tuple[str, ...]]:
    """Published tool names per Gateway target, in declaration order.

    The single source both the renderer and the tests consume. A target whose every tool
    is deferred would appear here as an empty tuple rather than vanish, so a caller can
    tell "nothing published" from "no such target".
    """
    return {
        config["target_name"]: tuple(
            tool["name"] for tool in config["tools"]
            if tool["name"] not in WORKSHOP_DEFERRED_TOOLS
        )
        for config in TOOL_SCHEMAS.values()
    }


def schema_for(surface: str, *, workshop: bool) -> list[dict]:
    """Return the CLI-compatible tool schema for one Gateway target.

    `workshop` is REQUIRED, not defaulted, because the two answers differ and both are
    legitimate:

      * ``workshop=True`` drops the deferred tools, so a fresh provision cannot publish
        a capability whose governance is undecided. Every publication path wants this.
      * ``workshop=False`` is the full canonical vocabulary, which the Gateway vocabulary
        migration needs in order to compute what it is deliberately NOT publishing.

    It was briefly defaulted to ``True``, and that silently narrowed
    ``migrate_gateway_vocabulary.canonical_targets()`` from seventeen tools to fifteen,
    which emptied the migration's own deferred-tool list. A caller that has to name the
    answer cannot inherit the wrong one.
    """
    config = TOOL_SCHEMAS[surface]
    return [
        {**tool, "inputSchema": _sanitize_tool_schema(tool["inputSchema"])}
        for tool in config["tools"]
        if workshop is False or tool["name"] not in WORKSHOP_DEFERRED_TOOLS
    ]
