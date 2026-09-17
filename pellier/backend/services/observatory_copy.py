"""Observatory-specific reference copy.

The Observatory teaches technical architecture and therefore intentionally
uses vocabulary that is inappropriate for the shopper-facing copy scanner.
Keeping these strings here still gives route payloads one source of truth
without weakening shopper copy rules.
"""

OBSERVATORY_COPY = {
    "SESSION_EVIDENCE_UNAVAILABLE": "Aurora session evidence is unavailable.",
    "MEMORY_SHOWCASE_UNAVAILABLE": "Memory showcase is temporarily unavailable.",
    "IDENTITY_BOUNDARY_UNAVAILABLE": (
        "Aurora governed receipts are unavailable, so the identity boundary "
        "cannot be reconstructed."
    ),
    "IDENTITY_BOUNDARY_EMPTY": (
        "No governed identity attempt has been recorded yet. Run "
        "scripts/prove_identity_boundary.py to produce the evidence."
    ),
    "SESSION_EVIDENCE_NOT_FOUND": "Session evidence not found.",
    "EVIDENCE_RECORDED": "Evidence recorded.",
    "AGENT_TOPOLOGY_UNAVAILABLE": (
        "The running agent topology could not be inspected."
    ),
    "TOOL_REGISTRY_UNAVAILABLE": "Aurora tool registry is unavailable.",
    "TOOL_DISCOVERY_UNAVAILABLE": "Aurora tool discovery is unavailable.",
    "SCENARIOS_UNAVAILABLE": "Aurora workshop scenarios are unavailable.",
    "PERFORMANCE_UNAVAILABLE": "Aurora performance evidence is unavailable.",
    "EVALUATION_UNAVAILABLE": "Evaluation configuration is unavailable.",
    "BUILD_STATE_UNAVAILABLE": "Live build-state is unavailable.",
    "ROUTING": (
        {
            "name": "Storefront Dispatcher",
            "slug": "dispatcher",
            "description": (
                "One shopper turn is classified and routed to one specialist; "
                "the streamed response exposes its actual route and tool events."
            ),
            "isActive": True,
            "activeIn": "Storefront",
            "agents": (
                "Search Agent",
                "Personalization Agent",
                "Pricing Agent",
                "Inventory Agent",
                "Customer Service Agent",
            ),
            "codeSnippet": (
                "POST /api/chat/stream -> classify_intent -> specialist -> "
                "Aurora evidence"
            ),
        },
        {
            "name": "Operator Concierge graph",
            "slug": "operator-graph",
            "description": (
                "A bounded Strands graph investigates a client case and plans "
                "a resolution. Aurora stores the review checkpoint between turns."
            ),
            "isActive": True,
            "activeIn": "Operator",
            "agents": ("Case Investigator", "Resolution Planner"),
            "codeSnippet": (
                "investigator -> resolution planner -> persisted review -> "
                "governed execution"
            ),
        },
    ),
    "ARCHITECTURE": (
        {
            "numeral": "I",
            "category": "live",
            "title": "Grounding",
            "role": "Aurora PostgreSQL system of record",
            "description": (
                "Catalog, inventory, orders, returns, and tool evidence are "
                "read from Aurora."
            ),
            "codeSnippet": (
                "SELECT * FROM pellier.product_catalog;  -- live catalog rows"
            ),
            "slug": "grounding",
        },
        {
            "numeral": "II",
            "category": "live",
            "title": "Memory",
            "role": "AgentCore Memory plus Aurora evidence",
            "description": (
                "Conversation memory is separate from the Aurora records that "
                "prove what ran."
            ),
            "codeSnippet": "GET /api/observatory/memory/{persona}",
            "slug": "memory",
        },
        {
            "numeral": "III",
            "category": "live",
            "title": "Skills",
            "role": "Reviewed prompt guidance",
            "description": "Specialist turns can select skill guidance after intent routing; a skill does not grant permission.",
            "codeSnippet": "intent classification -> skill selection -> specialist; inspect skill_routing for the actual decision",
            "slug": "skills",
        },
        {
            "numeral": "IV",
            "category": "live",
            "title": "Routing and state",
            "role": "Storefront dispatcher and Operator graph",
            "description": (
                "The shopper and operator surfaces use separate, explicit "
                "orchestration paths."
            ),
            "codeSnippet": "dispatcher -> specialist; investigator -> planner -> review",
            "slug": "state-management",
        },
        {
            "numeral": "V",
            "category": "live",
            "title": "Governed execution",
            "role": "Human decision, policy, database, receipts",
            "description": (
                "Aurora receipts distinguish an attempted action from a "
                "committed effect."
            ),
            "codeSnippet": "human decision -> Policy -> Aurora -> receipt",
            "slug": "runtime",
        },
        {
            "numeral": "VI",
            "category": "quality",
            "title": "Evaluations",
            "role": "Measured outcomes and explicit proof limits",
            "description": "Compare retrieval candidates and governed outcomes using retained run evidence. Configuration alone is not an evaluation result.",
            "codeSnippet": "hypothesis -> controlled change -> retained result -> decision",
            "slug": "evaluations",
        },
        {
            "numeral": "VII",
            "category": "workshop",
            "title": "Tool Registry",
            "role": "Discovery is separate from permission",
            "description": "Aurora ranks tool descriptions; Gateway publication and caller policy determine the managed tool boundary.",
            "codeSnippet": "description similarity != publication != authorization",
            "slug": "tool-registry",
        },
        {
            "numeral": "VIII",
            "category": "workshop",
            "title": "MCP Gateway",
            "role": "Managed discovery and invocation",
            "description": "Labs 1 and 2 establish the in-process baseline. Lab 3 moves the tools behind Runtime, Gateway, and caller-bound policy.",
            "codeSnippet": "verified caller -> Runtime -> Gateway / Cedar -> target -> Aurora",
            "slug": "mcp",
        },
    ),
}
