# Requirements Document

## Introduction

Pellier is a multi-agent e-commerce shopping assistant built with the Strands SDK. The system currently has an Orchestrator Agent that routes user queries to three specialist agents: Product Recommendation, Price Optimization, and Inventory Restock. This feature adds two new specialists — the Customer Support Agent and the Search Agent — and refactors the Recommendation Agent. The Customer Support Agent handles return policy inquiries and general troubleshooting questions. The Search Agent promotes the existing frontend-only "Search Agent" identity to a real backend agent backed by `search_products`, `get_product_by_category`, and `compare_products` tools. As part of this promotion, the Recommendation Agent is refactored to remove `search_products` from its tools, focusing it purely on trending and personalized recommendations. The Customer Support Agent integrates a new `get_return_policy` tool (backed by the `pellier.return_policies` Aurora PostgreSQL table), reuses the existing `search_products` tool (renamed from `semantic_product_search` for naming consistency) for product lookups, and optionally integrates Exa MCP tools for web-based troubleshooting. Beyond the agents themselves, this feature requires updates to the backend routing (intent classification with new SUPPORT_KEYWORDS and SEARCH_KEYWORDS, FastAPI endpoint, AgentType enum, prompt registry), the frontend agent identity system, the graph orchestrator visualization (now five specialist nodes), a codebase-wide rename of `semantic_product_search` to `search_products`, and registration of the new tools with the AgentCore Gateway for dynamic MCP-based tool discovery.

## Glossary

- **Orchestrator**: The top-level Strands Agent (Claude Haiku 4.5, model ID `global.anthropic.claude-haiku-4-5-20251001-v1:0`) that classifies user intent and routes queries to one specialist agent.
- **Customer_Support_Agent**: A new Strands specialist agent (using `settings.BEDROCK_CHAT_MODEL`, currently `global.anthropic.claude-opus-4-6-v1`) defined as a `@tool` function named `customer_support_agent` in `agents/customer_support_agent.py`. Handles return policies, product search for support contexts, and troubleshooting queries.
- **get_return_policy**: A `@tool` decorated function in `services/agent_tools.py` that returns return policy details for a given product category by querying the `pellier.return_policies` Aurora PostgreSQL table.
- **return_policies table**: An Aurora PostgreSQL table (`pellier.return_policies`) seeded by the bootstrap script with 21 rows (20 product categories + a default). Columns: `category_name`, `return_window_days`, `conditions`, `refund_method`.
- **search_products**: The `@tool` decorated function in `services/agent_tools.py` that performs hybrid AI search (semantic + keyword + reranking). Renamed from `semantic_product_search` for naming consistency — every other data tool follows a `get_*` or `verb_noun` pattern, and `search_products` matches that convention.
- **Exa_MCP_Tools**: External web search tools provided via the Exa MCP server, used optionally by the Customer_Support_Agent for troubleshooting questions beyond the product catalog. Requires an Exa API key and network egress.
- **Agent_Tools_Module**: The `services/agent_tools.py` file containing all `@tool` decorated functions shared across agents.
- **Product_Catalog**: The Aurora PostgreSQL database table (`pellier.product_catalog`) storing product data.
- **SUPPORT_KEYWORDS**: A set of keywords in `services/chat.py` used by the `classify_intent` function to detect customer support intent (e.g., "return", "refund", "policy", "support", "warranty", "troubleshoot").
- **AgentType_Enum**: The `AgentType` enum in `services/context_manager.py` that lists all agent types for context management and prompt routing.
- **Frontend_AgentIdentity**: The agent identity system in `frontend/src/utils/agentIdentity.ts` that defines agent types, colors, icons, and display names for the chat UI.
- **Search_Agent**: A new Strands specialist agent (using `settings.BEDROCK_CHAT_MODEL`, currently `global.anthropic.claude-opus-4-6-v1`) defined as a `@tool` function named `search_agent` in `agents/search_agent.py`. Handles explicit product search queries using `search_products`, `get_product_by_category`, and `compare_products` tools. Promotes the existing frontend-only "Search Agent" identity to a real backend agent.
- **SEARCH_KEYWORDS**: A set of keywords in `services/chat.py` used by the `classify_intent` function to detect product search intent (e.g., "search for", "looking for", "where can I", "compare", "browse"). Checked with the LOWEST priority (after pricing, inventory, and support keywords), with unmatched queries defaulting to "recommendation".
- **AgentCore_Gateway**: The Bedrock AgentCore Gateway MCP server that exposes registered tools via streamable HTTP transport. The existing `services/agentcore_gateway.py` module provides `create_gateway_orchestrator()` (discovers all tools via MCP), `create_gateway_orchestrator_with_semantic_search()` (uses `x_amz_bedrock_agentcore_search` for query-time tool discovery), and `list_gateway_tools()`. Configured via `AGENTCORE_GATEWAY_URL` and `AGENTCORE_GATEWAY_API_KEY` in `config.py`.

## Requirements

### Requirement 1: Return Policy Lookup Tool

**User Story:** As a customer, I want to ask about return policies for different product categories, so that I understand the return terms before making a purchase.

#### Acceptance Criteria

1. THE bootstrap seed script SHALL create a `pellier.return_policies` table with columns `category_name`, `return_window_days`, `conditions`, and `refund_method`, seeded with 21 rows (20 product categories + a default row).
2. WHEN a product category is provided, THE get_return_policy tool SHALL query the `pellier.return_policies` table and return the matching policy details as a JSON string.
3. WHEN the provided category does not match any row in the return_policies table, THE get_return_policy tool SHALL fall back to the row with `category_name = 'default'` and return that policy.
4. IF an exception occurs during policy retrieval, THEN THE get_return_policy tool SHALL return a JSON object containing the error description.
5. THE get_return_policy tool SHALL follow the existing `@tool` decorator pattern used by other tools in the Agent_Tools_Module.
6. THE get_return_policy tool SHALL accept a `category` string parameter to filter return policies by product category.

### Requirement 2: Customer Support Agent Definition

**User Story:** As a developer, I want a new Customer Support Agent module, so that customer support queries are handled by a dedicated specialist with appropriate tools and system prompt.

#### Acceptance Criteria

1. THE Customer_Support_Agent SHALL be defined as a `@tool` decorated function named `customer_support_agent` in `agents/customer_support_agent.py`, following the same pattern as the existing specialist agents (`product_recommendation_agent` in `agents/recommendation_agent.py`, `price_optimization_agent` in `agents/pricing_agent.py`, `inventory_restock_agent` in `agents/inventory_agent.py`).
2. THE Customer_Support_Agent SHALL use the model ID referenced by `settings.BEDROCK_CHAT_MODEL` (currently `global.anthropic.claude-opus-4-6-v1`), consistent with the other specialist agents.
3. THE Customer_Support_Agent SHALL have access to the get_return_policy tool and the search_products tool from the Agent_Tools_Module.
4. THE Customer_Support_Agent SHALL accept a `query` string parameter and return a string response.
5. THE Customer_Support_Agent SHALL include a system prompt that instructs the model to act as a customer support specialist for Pellier, using get_return_policy for return/refund questions and search_products for product-related support queries.
6. IF an exception occurs during agent execution, THEN THE Customer_Support_Agent SHALL return a JSON object containing the error description.
7. THE Customer_Support_Agent SHALL capture inner tool results and append product JSON to the output when the LLM response lacks a JSON products block, following the `_ensure_products_in_output` pattern used by the other specialist agents.

### Requirement 3: Orchestrator Integration

**User Story:** As a customer, I want my support questions to be automatically routed to the Customer Support Agent, so that I receive relevant help without manually selecting an agent.

#### Acceptance Criteria

1. THE Orchestrator in `agents/orchestrator.py` SHALL include the `customer_support_agent` and `search_agent` tools alongside the existing three specialist agents (`product_recommendation_agent`, `price_optimization_agent`, `inventory_restock_agent`) in both `create_orchestrator` and `create_guarded_orchestrator` functions, bringing the total to five specialist agent tools.
2. THE Orchestrator system prompt (ORCHESTRATOR_PROMPT) SHALL be updated to describe the Customer_Support_Agent's capabilities (return policies, troubleshooting, general support) and the Search_Agent's capabilities (product search, category browsing, product comparison) so the routing model can correctly classify queries.
3. THE Orchestrator system prompt SHALL include example queries that route to the Customer_Support_Agent, such as: "what's the return policy for electronics", "my headphones stopped working", and "how do I return a product".
4. WHEN a user query relates to return policies, product troubleshooting, or customer support topics, THE Orchestrator SHALL route the query to the Customer_Support_Agent.
5. THE Orchestrator SHALL continue to route product recommendation, pricing, and inventory queries to their respective existing agents without disruption.
6. WHEN a user query contains explicit product search intent (e.g., "find me X", "show me X", descriptive product queries), THE Orchestrator SHALL route the query to the Search_Agent.
7. WHEN a user query relates to trending, popular, or best-selling products, THE Orchestrator SHALL route the query to the product_recommendation_agent rather than the Search_Agent.

### Requirement 4: Graph Orchestrator Visualization Update

**User Story:** As a developer, I want the graph orchestrator visualization to include the Customer Support Agent node, so that the frontend accurately reflects the multi-agent architecture.

#### Acceptance Criteria

1. THE `get_graph_structure` function in `agents/graph_orchestrator.py` SHALL include a new node for the Customer_Support_Agent with id "support", label "Customer Support", type "agent", a description referencing return policies and troubleshooting, and model "Claude Opus 4.6".
2. THE `get_graph_structure` function SHALL include a new edge from the "router" node to the "support" node with a descriptive label such as "support queries".
3. THE `get_graph_structure` description text SHALL be updated to mention the Customer_Support_Agent and Search_Agent alongside the existing agents.
4. THE `get_graph_structure` function SHALL include a new node for the Search_Agent with id "search", label "Product Search", type "agent", a description referencing product search, category browsing, and product comparison, and model "Claude Opus 4.6".
5. THE `get_graph_structure` function SHALL include a new edge from the "router" node to the "search" node with a descriptive label such as "search queries".

### ~~Requirement 5: Exa MCP Tool Integration (Optional / Stretch)~~

> **Removed · 2026-04-27 · three-pattern refactor.** Exa MCP integration for live web search in the support agent was cut from the workshop codebase. Workshop scope is agentic search over Aurora pgvector; live web retrieval was out of scope, unconfigured in every workshop environment (`EXA_API_KEY` unset), and it was the only thing forcing the specialist-factory pattern to be inconsistent across the five specialists. The support agent now runs purely against the local tool set (`return_policy`, `search_products`). See `docs/PATTERNS_NOTES.md` for the broader refactor context. Requirement retained here (struck through) as spec history, not spec drift.

~~**User Story:** As a customer, I want the support agent to optionally search the web for troubleshooting answers, so that I can get help with issues not covered by the product catalog.~~

#### ~~Acceptance Criteria~~

1. ~~WHERE the Exa MCP server is configured with a valid API key and network egress is available, THE Customer_Support_Agent SHALL load Exa MCP tools using the Strands SDK MCP client configuration.~~
2. ~~WHEN a troubleshooting query cannot be answered using the local tools alone, THE Customer_Support_Agent system prompt SHALL instruct the model to use Exa_MCP_Tools for web search.~~
3. ~~IF the Exa MCP server is unavailable, the API key is not configured, or the MCP client fails to initialize, THEN THE Customer_Support_Agent SHALL continue to function using only the local data tools (get_return_policy, search_products) and log a warning.~~
4. ~~THE Customer_Support_Agent module SHALL document that Exa MCP integration requires an `EXA_API_KEY` environment variable and outbound network access, neither of which are provisioned by the default workshop bootstrap scripts.~~

### Requirement 6: Intent Classification Update

**User Story:** As a developer, I want the deterministic intent classifier to recognize customer support queries, so that the orchestrator receives the correct routing hint for support-related messages.

#### Acceptance Criteria

1. THE `services/chat.py` module SHALL define a new `SUPPORT_KEYWORDS` set containing keywords such as "return", "refund", "policy", "help", "support", "troubleshoot", "issue", "problem", "warranty", "broken", and "defective".
2. THE `classify_intent` function in `services/chat.py` SHALL check for SUPPORT_KEYWORDS and return "customer_support" when a match is found.
3. THE intent-to-agent hint mapping in the `_strands_enhanced_chat` method SHALL include a "customer_support" entry that maps to "customer_support_agent".
4. THE SUPPORT_KEYWORDS check SHALL have lower priority than PRICING_KEYWORDS and INVENTORY_KEYWORDS to avoid misclassifying price or stock queries that happen to contain support-adjacent words.
5. THE `services/chat.py` module SHALL define a new `SEARCH_KEYWORDS` set containing keywords such as "search for", "looking for", "where can I", "compare", and "browse".
6. THE `classify_intent` function in `services/chat.py` SHALL check for SEARCH_KEYWORDS and return "search" when a match is found.
7. THE SEARCH_KEYWORDS check SHALL have the LOWEST priority, checked last after PRICING_KEYWORDS, INVENTORY_KEYWORDS, and SUPPORT_KEYWORDS, with unmatched queries defaulting to "recommendation" as they do today.
8. THE intent-to-agent hint mapping in the `_strands_enhanced_chat` method SHALL include a "search" entry that maps to "search_agent".

### Requirement 7: FastAPI Endpoint and Agent Name Mapping Update

**User Story:** As a developer, I want the FastAPI agent query endpoint and the tool-to-agent-name mapping to support the new agent type, so that the backend can route and label support agent queries correctly.

#### Acceptance Criteria

1. THE `agent_query` function in `app.py` SHALL accept `"customer_support"` as a valid `agent_type` value and invoke the `customer_support_agent` tool function when selected.
2. THE `_tool_to_agent_name` static method in `services/chat.py` SHALL include a `'customer_support_agent': 'Support Agent'` entry in its mapping dictionary.
3. THE `agent_query` function in `app.py` SHALL accept `"search"` as a valid `agent_type` value and invoke the `search_agent` tool function when selected.
4. THE `_tool_to_agent_name` static method in `services/chat.py` SHALL include a `'search_agent': 'Search Agent'` entry in its mapping dictionary.

### Requirement 8: AgentType Enum and Prompt Registry Update

**User Story:** As a developer, I want the AgentType enum and PromptRegistry to include the Customer Support agent, so that context management and prompt templates work correctly for the new agent.

#### Acceptance Criteria

1. THE `AgentType` enum in `services/context_manager.py` SHALL include a `CUSTOMER_SUPPORT = "customer_support_agent"` value.
2. THE `PromptRegistry.TEMPLATES` dictionary in `services/context_manager.py` SHALL include an entry for `AgentType.CUSTOMER_SUPPORT` with a version string, a system prompt describing the customer support specialist role, and performance metrics.
3. THE `agent_contexts` dictionary initialized in the `ContextManager.__init__` method SHALL automatically include the new `CUSTOMER_SUPPORT` agent type since it iterates over all `AgentType` enum values.
4. THE `AgentType` enum in `services/context_manager.py` SHALL include a `SEARCH = "search_agent"` value.
5. THE `PromptRegistry.TEMPLATES` dictionary in `services/context_manager.py` SHALL include an entry for `AgentType.SEARCH` with a version string, a system prompt describing the product search specialist role, and performance metrics.

### Requirement 9: Frontend Agent Identity Update

**User Story:** As a user, I want the chat UI to display a distinct identity (name, icon, color) for the Customer Support Agent, so that I can visually distinguish support responses from other agent responses.

#### Acceptance Criteria

1. THE `AgentType` type in `frontend/src/utils/agentIdentity.ts` SHALL include `'support'` as a valid union member.
2. THE `AGENT_IDENTITIES` record in `frontend/src/utils/agentIdentity.ts` SHALL include a `support` entry with a name of "Support Agent", a unique icon letter, gradient, bgColor, borderColor, textColor, and accentHex distinct from the existing agents.
3. THE `resolveAgentType` function in `frontend/src/utils/agentIdentity.ts` SHALL return `'support'` when the agent name string contains "support" or "customer_support".
4. THE `resolveAgentType` function SHALL map agent names containing "search" to the `'search'` type, ensuring the frontend `'search'` identity is intentionally connected to the renamed backend tool `search_products` via the `_tool_to_agent_name` mapping (`'search_products': 'Search Agent'`).
5. THE `AIAssistant.tsx` component's keyword-based agent type detection for Lab 2 single-agent mode SHALL include support-related keywords (e.g., "return", "refund", "policy", "support", "warranty", "help") that set the `agentType` to `'support'`.
6. THE agent badge color mappings in `AIAssistant.tsx` SHALL include entries for "Support Agent" and "Customer Support" with colors matching the `support` identity defined in `agentIdentity.ts`.
7. THE existing `'search'` AgentType in `agentIdentity.ts` SHALL remain unchanged since it already defines the frontend identity for the Search Agent; the promotion to a real backend agent requires no frontend identity changes.

### Requirement 10: Rename semantic_product_search to search_products

**User Story:** As a developer, I want the `semantic_product_search` tool renamed to `search_products` across the entire codebase, so that the tool naming is consistent with the `verb_noun` pattern used by all other data tools (e.g., `get_trending_products`, `get_price_analysis`, `restock_product`).

#### Acceptance Criteria

1. THE `@tool` function `semantic_product_search` in `services/agent_tools.py` SHALL be renamed to `search_products`, with the docstring and behavior remaining unchanged.
2. THE import statement and all references to `semantic_product_search` in `agents/recommendation_agent.py` SHALL be updated to `search_products`.
3. THE import statement and all references to `semantic_product_search` in `agents/pricing_agent.py` SHALL be updated to `search_products`.
4. THE `agents/customer_support_agent.py` module SHALL import and use `search_products` (the renamed function) from the Agent_Tools_Module.
5. THE `_tool_to_agent_name` mapping in `services/chat.py` SHALL be updated from `'semantic_product_search': 'Search Agent'` to `'search_products': 'Search Agent'`.
6. THE SINGLE_AGENT_PROMPT text in `services/chat.py` SHALL reference `search_products` instead of `semantic_product_search` in the tool selection instructions.
7. THE import statements referencing `semantic_product_search` in `services/chat.py` (used by `_single_agent_chat` and `_single_agent_stream`) SHALL be updated to `search_products`, and the corresponding `tools=` lists SHALL use `search_products`.

### Requirement 11: Search Agent Definition and Recommendation Agent Refactor

**User Story:** As a customer, I want a dedicated Search Agent that handles explicit product search queries, so that search functionality is backed by a real specialist agent rather than being a frontend-only label, and the Recommendation Agent can focus on trending and personalized recommendations.

#### Acceptance Criteria

1. THE Search_Agent SHALL be defined as a `@tool` decorated function named `search_agent` in `agents/search_agent.py`, following the same pattern as the existing specialist agents (`product_recommendation_agent`, `price_optimization_agent`, `inventory_restock_agent`).
2. THE Search_Agent SHALL use the Strands SDK `Agent` class with `BedrockModel` configured with `settings.BEDROCK_CHAT_MODEL` (currently `global.anthropic.claude-opus-4-6-v1`), max_tokens=4096, and temperature=0.2, consistent with the other specialist agents.
3. THE Search_Agent SHALL have access to the `search_products`, `get_product_by_category`, and `compare_products` tools from the Agent_Tools_Module.
4. THE Search_Agent SHALL include a system prompt instructing the model to act as Pellier's Product Search Specialist, using `search_products` for natural language and intent-based queries, `get_product_by_category` for category browsing, and `compare_products` for side-by-side product comparisons.
5. THE Search_Agent SHALL accept a `query` string parameter and return a string response.
6. THE Search_Agent SHALL capture inner tool results and append product JSON to the output when the LLM response lacks a JSON products block, following the `_ensure_products_in_output` pattern and `AfterToolCallEvent` hook capture used by the other specialist agents.
7. IF an exception occurs during Search_Agent execution, THEN THE Search_Agent SHALL return a JSON object containing the error description, following the existing error pattern used by the other specialist agents.
8. THE `product_recommendation_agent` in `agents/recommendation_agent.py` SHALL be updated to REMOVE `search_products` (renamed from `semantic_product_search`) from its tools list.
9. AFTER the refactor, THE `product_recommendation_agent` SHALL have ONLY `get_trending_products` and `get_product_by_category` as its tools.
10. THE `product_recommendation_agent` system prompt SHALL be updated to focus on trending, popular, and personalized product recommendations, removing references to descriptive or intent-based product search.
11. THE import of `semantic_product_search` (or `search_products`) SHALL be removed from `agents/recommendation_agent.py`.

### Requirement 12: AgentCore Gateway Integration for New Tools

**User Story:** As a developer, I want the new customer support and search tools to be discoverable through the AgentCore Gateway, so that the gateway orchestrator can dynamically find and invoke them without hardcoded imports.

#### Acceptance Criteria

1. THE `get_return_policy` tool SHALL be registered with the AgentCore Gateway with a clear, distinct tool description that enables semantic search discovery for return/refund policy queries.
2. THE `search_products` tool (renamed from `semantic_product_search`) SHALL have its AgentCore Gateway registration updated to reflect the new name and an optimized tool description.
3. THE `create_gateway_orchestrator()` function in `services/agentcore_gateway.py` SHALL continue to work with the expanded tool catalog (9 data tools + 5 agent tools) without modification, since it discovers tools dynamically via MCP.
4. THE `create_gateway_orchestrator_with_semantic_search()` function's system prompt SHALL be updated to include guidance for support-related queries (e.g., "For return policies and support, search for 'return policy' or 'customer support' tools").
5. ALL tool descriptions in `services/agent_tools.py` SHALL be reviewed and optimized to be concise, distinct, and semantically searchable — avoiding overlap that could cause the gateway's semantic search to return the wrong tool.
6. THE tool descriptions SHALL follow the pattern: one clear sentence describing what the tool does, followed by when to use it. No implementation details in the description.
