---
inclusion: always
---

# Pellier — Project Context

## What This Is

Pellier is a hands-on workshop application that teaches developers how to build agentic AI-powered search using Amazon Aurora PostgreSQL, pgvector, Amazon Bedrock, Strands SDK, and Amazon Bedrock AgentCore. It's a real e-commerce storefront (React + FastAPI) where participants progressively build features by editing the actual application code.

## Two Delivery Formats

- **2-hour Workshop** — participants delete challenge blocks and reimplement using hints
- **1-hour Builders Session** — participants build C1 only; C2 through C9 are read-and-test

Both formats share one codebase, one solutions directory, and one infrastructure stack. Lab guides live in `lab-content/workshop/` and `lab-content/builders/` respectively.

## Workshop Structure

Three modules, nine challenges total. Infrastructure-out ordering in Module 3.

- **Module 1: Smart Search** (Workshop 30 min / Builders 15 min) — 1 challenge
  - C1: `_vector_search()` with pgvector + Cohere Embed v4 + HNSW
- **Module 2: Agentic AI** (Workshop 40 min / Builders 20 min) — 3 challenges
  - C2: `get_trending_products()` as a `@tool`
  - C3: `product_recommendation_agent` specialist
  - C4: Multi-agent orchestrator routing 5 specialists
- **Module 3: Production Patterns** (Workshop 40 min / Builders 15 min) — 5 challenges, infrastructure-out
  - C5: AgentCore Runtime
  - C6: AgentCore STM Memory (session history + user preferences)
  - C7: AgentCore MCP Gateway
  - C8: OpenTelemetry observability
  - C9 (capstone): Agent Identity — Cognito + AgentCore Identity (four files)

## Key Directories

- `pellier/backend/` — FastAPI Python backend with Strands SDK agents
- `pellier/frontend/` — React + Vite + Tailwind storefront
- `solutions/` — Drop-in solution files for each module (cp and restart)
  - `solutions/the-quiet-search/`, `solutions/closing-marcos-gap/`, `solutions/the-paper-trail/`
- `scripts/` — Bootstrap and seed scripts for the workshop environment
- `lab-content/workshop/` — 2-hour Workshop Studio content
- `lab-content/builders/` — 1-hour Builders Session content
- `data/` — Product catalog CSV with pre-generated Cohere Embed v4 embeddings
- `.kiro/specs/` — Feature specs (requirements, design, tasks)
- `.claude/prompts/` — Claude Code prompt playbooks (infrastructure, workshop content, builders content)

## Database

- Amazon Aurora PostgreSQL (latest available at workshop time; currently 17.7) Serverless v2 (0–16 ACU, scale-to-zero)
- Schema: `pellier` (product_catalog, return_policies)
- pgvector 0.8.0 with HNSW indexes for 1024-dim Cohere Embed v4 vectors
- ~444 products with pre-generated embeddings
- Session management: AgentCore Memory (STM) via `agentcore_memory.py`
- User preferences stored in AgentCore Memory keyed by verified Cognito user_id (Module 3 C9)

## Authentication

Real Amazon Cognito + AgentCore Identity (not simulated). Cognito User Pool with hosted UI federated to Google + Apple + email/password. JWT validated via Cognito JWKS. AgentCore Identity wraps verified user context for agents and scopes AgentCore Memory keys by user_id.

Wired in Module 3 Challenge 9 (capstone).
