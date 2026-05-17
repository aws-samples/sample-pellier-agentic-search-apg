# Implementation Plan: Customer Support Agent

## Overview

Add two new specialist agents (Customer Support and Search) to the Pellier multi-agent system, refactor the Recommendation Agent, rename `semantic_product_search` to `search_products`, and update all supporting infrastructure (routing, enums, frontend, graph viz, gateway). Implementation follows dependency order: rename first, then new agents, then integration, then frontend, then gateway.

## Tasks

- [x] 1. Rename `semantic_product_search` to `search_products` across the codebase
  - [x] 1.1 Rename the `@tool` function in `pellier/backend/services/agent_tools.py` from `semantic_product_search` to `search_products`, keeping docstring and behavior unchanged
    - _Requirements: 10.1_
  - [x] 1.2 Update import and all references in `pellier/backend/agents/curator.py` from `semantic_product_search` to `search_products`
    - _Requirements: 10.2_
  - [x] 1.3 Update import and all references in `pellier/backend/agents/pricing_agent.py` from `semantic_product_search` to `search_products`
    - _Requirements: 10.3_
  - [x] 1.4 Update `_tool_to_agent_name` mapping in `pellier/backend/services/chat.py` from `'semantic_product_search': 'Search Agent'` to `'search_products': 'Search Agent'`
    - _Requirements: 10.5_
  - [x] 1.5 Update `SINGLE_AGENT_PROMPT` in `pellier/backend/services/chat.py` to reference `search_products` instead of `semantic_product_search`
    - _Requirements: 10.6_
  - [x] 1.6 Update import statements in `pellier/backend/services/chat.py` (used by `_single_agent_chat` and `_single_agent_stream`) to import `search_products`, and update the `tools=` lists
    - _Requirements: 10.7_

- [x] 2. Refactor Recommendation Agent and create Search Agent
  - [x] 2.1 Refactor `product_recommendation_agent` in `pellier/backend/agents/curator.py`: remove `search_products` from tools list (keep only `get_trending_products` and `get_product_by_category`), remove the import, and update system prompt to focus on trending/popular/personalized recommendations
    - _Requirements: 11.8, 11.9, 11.10, 11.11_
  - [x] 2.2 Create `pellier/backend/agents/search_agent.py` with a `@tool` decorated `search_agent` function using `BedrockModel(model_id=settings.BEDROCK_CHAT_MODEL, max_tokens=4096, temperature=0.2)`, tools `[search_products, get_product_by_category, compare_products]`, system prompt for product search specialist, `_ensure_products_in_output` pattern with `AfterToolCallEvent` hook, error handling returning JSON error object
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_
  - [ ]\* 2.3 Write property test for `_ensure_products_in_output` (shared by all agents)
    - **Property 4: Product JSON appended when missing from agent output**
    - **Validates: Requirements 2.7, 11.6**

- [x] 3. Create Return Policy Tool and Customer Support Agent
  - [x] 3.1 Add DB-backed `get_return_policy` `@tool` function to `pellier/backend/services/agent_tools.py` that queries `pellier.return_policies` table with category lookup, default fallback, error handling, and `category` string parameter (table seeded by bootstrap script)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - [ ]\* 3.2 Write property test for `get_return_policy`
    - **Property 1: Return policy lookup correctness**
    - **Validates: Requirements 1.2, 1.3**
  - [x] 3.3 Create `pellier/backend/agents/experience_guide.py` with a `@tool` decorated `customer_support_agent` function using `BedrockModel(model_id=settings.BEDROCK_CHAT_MODEL, max_tokens=4096, temperature=0.2)`, tools `[get_return_policy, search_products]`, system prompt for support specialist, `_ensure_products_in_output` pattern with `AfterToolCallEvent` hook, error handling, and optional Exa MCP integration (try/except with warning log if unavailable)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 5.1, 5.2, 5.3, 5.4_

- [x] 4. Checkpoint - Ensure new agents and tools are correct
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Orchestrator and intent classification updates
  - [x] 5.1 Update `pellier/backend/agents/orchestrator.py`: import `customer_support_agent` and `search_agent`, add both to `tools=` list in `create_orchestrator()` and `create_guarded_orchestrator()`, update `ORCHESTRATOR_PROMPT` to describe all 5 specialist agents with example queries for support and search routing
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
  - [x] 5.2 Add `SUPPORT_KEYWORDS` and `SEARCH_KEYWORDS` sets to `pellier/backend/services/chat.py`, update `classify_intent` to check in priority order: pricing → inventory → support → search → recommendation (default)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
  - [x] 5.3 Update intent-to-agent hint mapping in `_strands_enhanced_chat` to include `"customer_support": "customer_support_agent"` and `"search": "search_agent"`
    - _Requirements: 6.3, 6.8_
  - [ ]\* 5.4 Write property test for intent classification keyword matching
    - **Property 2: Intent classification keyword matching**
    - **Validates: Requirements 3.4, 3.6, 6.2, 6.6**
  - [ ]\* 5.5 Write property test for intent classification priority ordering
    - **Property 3: Intent classification priority ordering**
    - **Validates: Requirements 3.5, 6.4, 6.7**

- [x] 6. Backend routing, enum, and prompt registry updates
  - [x] 6.1 Update `agent_query` in `pellier/backend/app.py` to accept `"customer_support"` and `"search"` as valid `agent_type` values, importing and invoking `customer_support_agent` and `search_agent` respectively
    - _Requirements: 7.1, 7.3_
  - [x] 6.2 Update `_tool_to_agent_name` in `pellier/backend/services/chat.py` to add `'customer_support_agent': 'Support Agent'` and `'search_agent': 'Search Agent'`
    - _Requirements: 7.2, 7.4_
  - [x] 6.3 Add `CUSTOMER_SUPPORT = "customer_support_agent"` and `SEARCH = "search_agent"` to `AgentType` enum in `pellier/backend/services/context_manager.py`
    - _Requirements: 8.1, 8.4_
  - [x] 6.4 Add `PromptRegistry.TEMPLATES` entries for `AgentType.CUSTOMER_SUPPORT` and `AgentType.SEARCH` with version, system prompt, and performance metrics
    - _Requirements: 8.2, 8.5_
  - [ ]\* 6.5 Write property test for ContextManager agent_contexts coverage
    - **Property 6: ContextManager agent_contexts covers all AgentType values**
    - **Validates: Requirements 8.3**

- [x] 7. Graph orchestrator visualization update
  - [x] 7.1 Update `get_graph_structure` in `pellier/backend/agents/graph_orchestrator.py`: add "support" node (label "Customer Support", type "agent", model "Claude Opus 4.6"), "search" node (label "Product Search", type "agent", model "Claude Opus 4.6"), edges from "router" to both, and update description text
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 8. Checkpoint - Ensure all backend changes are correct
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Frontend agent identity and UI updates
  - [x] 9.1 Update `pellier/frontend/src/utils/agentIdentity.ts`: add `'support'` to `AgentType` union, add `support` entry to `AGENT_IDENTITIES` with unique teal colors/gradient, reorder `resolveAgentType` to check support first (priority: support > search > inventory > pricing > recommendation > orchestrator default)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.7_
  - [ ]\* 9.2 Write property test (fast-check) for `resolveAgentType` mapping
    - **Property 5: Agent type resolution mapping**
    - **Validates: Requirements 9.3, 9.4**
  - [x] 9.3 Update `pellier/frontend/src/components/AIAssistant.tsx`: add support-related keywords ("return", "refund", "policy", "support", "warranty", "help") to Lab 2 single-agent mode agent type detection setting `agentType` to `'support'`, and add badge color mappings for "Support Agent" and "Customer Support"
    - _Requirements: 9.5, 9.6_

- [x] 10. AgentCore Gateway integration and tool description optimization
  - [x] 10.1 Review and optimize all `@tool` docstrings in `pellier/backend/services/agent_tools.py` to be concise, distinct, and semantically searchable following the pattern from the design doc's optimized tool descriptions table. Remove implementation details (no "hybrid search", "pgvector", "reranking", etc.)
    - _Requirements: 12.1, 12.2, 12.5, 12.6_
  - [x] 10.2 Update `create_gateway_orchestrator_with_semantic_search()` system prompt in `pellier/backend/services/agentcore_gateway.py` to include routing hints for support and search queries
    - _Requirements: 12.4_
  - [ ]\* 10.3 Write property test for tool description distinctness and no implementation details
    - **Property 7: Tool descriptions are distinct and free of implementation details**
    - **Validates: Requirements 12.5, 12.6**

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests use Hypothesis (Python) for backend and fast-check (TypeScript) for frontend
- Task 1 (rename) must be completed first as many subsequent tasks depend on `search_products`
- Task 2 (search agent + recommendation refactor) depends on the rename
- Tasks 5-7 (orchestrator, routing, graph viz) can be done in parallel after agents exist
- Task 9 (frontend) depends on backend being complete
- Task 10 (gateway) should be last as it's the MCPify step
- Requirement 5 (Exa MCP) is optional/stretch and handled within task 3.3
