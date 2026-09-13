#!/usr/bin/env python3
"""Canonical AgentCore Gateway tool schemas for Pellier's four MCP targets."""


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
                "name": "find_pieces",
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
                "name": "find_pieces_hybrid",
                "description": (
                    "Hybrid retrieval: pgvector cosine + Postgres FTS merged via "
                    "RRF, then reranked by Cohere Rerank v3.5. Higher quality "
                    "than find_pieces at the cost of one extra Bedrock call."
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
                "name": "explore_collection",
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
                "name": "floor_check",
                "description": "Check aggregate inventory or one product across all warehouses.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_query": {
                            "type": "string",
                            "description": (
                                "Product-name words only, for example 'Hadley shirt'. "
                                "Exclude warehouse names, locations, and question phrasing. "
                                "The result includes every warehouse for the matching product. "
                                "Leave empty only for aggregate inventory."
                            ),
                        }
                    },
                    "required": [],
                },
            },
            {
                "name": "running_low",
                "description": "Get products with critically low stock.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 5}},
                    "required": [],
                },
            },
            {
                "name": "restock_shelf",
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
                "name": "price_intelligence",
                "description": "Price statistics by category.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"category": {"type": "string"}},
                    "required": [],
                },
            },
            {
                "name": "side_by_side",
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
                "name": "preference_snapshot",
                "description": "Read a safe customer preference, order, and memory snapshot.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "persona": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": [],
                },
            },
            {
                "name": "trace_receipt",
                "description": "Read recent ALLOW receipts from pellier.tool_audit.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "tool_name": {"type": "string"},
                        "caller": {"type": "string"},
                        "limit": {"type": "integer", "default": 3},
                    },
                    "required": [],
                },
            },
            {
                "name": "whats_trending",
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
                "name": "returns_and_care",
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
                "name": "style_match",
                "description": "Find complementary products by vector similarity.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["product_id"],
                },
            },
        ],
    },
    "experience": {
        "target_name": "pellier-concierge-experience-target",
        "description": "Pellier experience-guide MCP server (returns + stylist handoff)",
        "tools": [
            {
                "name": "process_return",
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
                "name": "escalate_to_stylist",
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
                    "required": [],
                },
            },
        ],
    },
}


def schema_for(surface: str) -> list[dict]:
    """Return the CLI-compatible tool schema for one Gateway target."""
    config = TOOL_SCHEMAS[surface]
    return [
        {**tool, "inputSchema": _sanitize_tool_schema(tool["inputSchema"])}
        for tool in config["tools"]
    ]
