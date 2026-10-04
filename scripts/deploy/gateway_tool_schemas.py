#!/usr/bin/env python3
"""Canonical AgentCore Gateway tool schemas: nine tools on one target."""

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


# One Lambda (scripts/deploy/pellier_store_tools.py) behind one target serves
# every tool. Cedar action ids are `pellier-store-tools___<tool>`.
TOOL_SCHEMAS = {
    "store": {
        "target_name": "pellier-store-tools",
        "description": "Pellier's nine store tools",
        "tools": [
            {
                "name": "search_products",
                "description": (
                    "Find products: the shopper's requirements as SQL filters, "
                    "then pgvector and Postgres full-text retrieval fused by RRF "
                    "and reranked by Cohere Rerank 3.5."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "What to find"},
                        "max_price": {"type": "number", "description": "Maximum price, a hard filter"},
                        "in_stock_only": {
                            "type": "boolean",
                            "description": "Only products with units in stock, a hard filter",
                        },
                        "exclusions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Tags or materials the shopper ruled out, such as "
                                "candle or wool, a hard filter"
                            ),
                        },
                        "min_rating": {"type": "number", "description": "Minimum star rating"},
                        "category": {"type": "string", "description": "A suggested department, recorded only"},
                        "limit": {"type": "integer", "description": "Max results"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "browse_department",
                "description": (
                    "The highest-rated products in one store department, within "
                    "the shopper's limits."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "department": {"type": "string"},
                        "max_price": {"type": "number", "description": "Maximum price, a hard filter"},
                        "in_stock_only": {
                            "type": "boolean",
                            "description": "Only products with units in stock, a hard filter",
                        },
                        "exclusions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Tags or materials the shopper ruled out, such as "
                                "candle or wool, a hard filter"
                            ),
                        },
                        "limit": {"type": "integer"},
                    },
                    "required": ["department"],
                },
            },
            {
                "name": "compare_products",
                "description": "Two products side by side by product id.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_id_1": {"type": "integer"},
                        "product_id_2": {"type": "integer"},
                    },
                    "required": ["product_id_1", "product_id_2"],
                },
            },
            {
                "name": "check_stock",
                "description": "Quantity and ship window at each warehouse for one named product.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"product_query": {"type": "string"}},
                    "required": ["product_query"],
                },
            },
            {
                "name": "get_orders",
                "description": "The customer's orders, newest first, with the amount paid.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["customer_id"],
                },
            },
            {
                "name": "get_return_policy",
                "description": "Return window, condition rules and refund method for a department.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"department": {"type": "string"}},
                    "required": [],
                },
            },
            {
                "name": "get_tickets",
                "description": "The customer's support tickets, newest first.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["customer_id"],
                },
            },
            {
                "name": "give_store_credit",
                "outputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                "description": (
                    "Give one store credit, up to $500.00, for a review a person "
                    "approved. One pellier.store_credits row per idempotency key."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "amount_cents": {"type": "integer", "minimum": 1, "maximum": 50000},
                        "reason": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["customer_id", "amount_cents", "reason", "idempotency_key"],
                },
            },
            {
                "name": "ask_a_person",
                "description": (
                    "Hand the conversation to a person at Pellier. A store credit "
                    "request opens a review for staff; nothing changes until a "
                    "person approves."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string"},
                        "customer_id": {"type": "string"},
                        "store_credit_cents": {"type": "integer"},
                    },
                    "required": ["reason"],
                },
            },
        ],
    },
}

# ``turn_id`` is a route-minted correlation value. It is optional in the
# Gateway schema so direct invocations remain valid, but the managed Runtime
# Router requires it on every shopper tool call and the Lambda preserves it in
# ``tool_audit.args`` while stripping it before the tool runs.
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
# `TOOL_SCHEMAS` above is the catalogue of everything Pellier can serve through
# the Gateway. Publication is a separate decision: publishing a tool gives it an
# MCP action id, a Cedar action and a place in participant-visible discovery.
#
#   give_store_credit   moves money. PUBLISHED for staff only: the Operator executes
#                       an approved credit through the Gateway with the operator's
#                       own token, and its one permit requires the staff scope claim.
#                       No shopper agent binds it.
#
#   get_tickets         reads a customer's support history. The read is only safe
#                       under an ownership condition, and binding that condition is
#                       Task 3A, so the starter withholds it.
#
# Derived, never hand-copied. A second literal tool list would drift from this one the
# first time a tool is added, and the drift would be invisible until a fresh provision.
#
# === WORKSHOP - Gateway catalogue - published tools: START ===
# WORKSHOP_EXERCISE_STUB
#
# Task 3A. Theo asks the Support agent for his ticket history. `get_tickets` has a
# schema in the catalogue above but is withheld from the Gateway, so the managed
# rail cannot serve it.
#
# Publishing makes a tool discoverable and adds it to the policy action set. It
# does not decide whose records a call may read: that is the caller binding in
# agentcore_gateway.py plus the owner-only permit rendered at deploy.
#
# Reconcile the Runtime list and caller binding in Task 3A, then deploy in
# Task 3B so the Runtime asks for the tools the Gateway now publishes:
#     python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" \
#         --mode participant
#
# Verify (live, the real check): an MCP tool listing made with your own token
# names `get_tickets`. Visible counts depend on the caller because the Gateway
# filters discovery by policy; a published staff-only tool is not visible to a
# shopper.
WORKSHOP_DEFERRED_TOOLS: frozenset[str] = frozenset({
    "get_tickets",
})
# === WORKSHOP - Gateway catalogue - published tools: END ===


# Publication is not visibility. AgentCore Gateway evaluates Cedar on MCP tool
# discovery, so `list_tools` returns the subset the calling token could actually be
# permitted to invoke, never the whole published catalogue. Expected counts: 8 tools
# published before Task 3A and 9 after. A shopper token with a customer claim
# discovers 7 and then 8 (never `give_store_credit`); a staff token with no customer
# claim discovers 7 both times (it gains `give_store_credit` and loses the
# owner-scoped reads).
#
# These two sets name why a tool can be missing from one caller's listing. They are
# claim shapes, not a second catalogue: every name here is published.
STAFF_ONLY_GATEWAY_TOOLS: frozenset[str] = frozenset({"give_store_credit"})
OWNER_SCOPED_GATEWAY_TOOLS: frozenset[str] = frozenset({
    "get_orders",
    "get_tickets",
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
    """Every tool name in the catalogue, published or not."""
    return frozenset(
        tool["name"] for config in TOOL_SCHEMAS.values() for tool in config["tools"]
    )


def workshop_published_tools() -> frozenset[str]:
    """The exact tool names this workshop iteration publishes on the Gateway."""
    return canonical_tool_names() - WORKSHOP_DEFERRED_TOOLS


def workshop_target_tools() -> dict[str, tuple[str, ...]]:
    """Published tool names per Gateway target, in declaration order.

    The single source both the renderer and the tests consume.
    """
    return {
        config["target_name"]: tuple(
            tool["name"] for tool in config["tools"]
            if tool["name"] not in WORKSHOP_DEFERRED_TOOLS
        )
        for config in TOOL_SCHEMAS.values()
    }


def schema_for(surface: str, *, workshop: bool) -> list[dict]:
    """Return the CLI-compatible schema of the tools one target serves.

    ``workshop`` is required, not defaulted, because the two answers differ and
    both are legitimate: ``True`` drops the deferred tools, so a fresh provision
    cannot publish a capability whose governance is undecided, and every
    publication path wants this; ``False`` is the full catalogue, which the
    Lambda's own ``list_tools`` probe and the schema tests read.
    """
    config = TOOL_SCHEMAS[surface]
    return [
        {**tool, "inputSchema": _sanitize_tool_schema(tool["inputSchema"])}
        for tool in config["tools"]
        if not workshop or tool["name"] not in WORKSHOP_DEFERRED_TOOLS
    ]
