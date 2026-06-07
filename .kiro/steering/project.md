---
inclusion: always
---

# Pellier — Project Context

## What This Is

Pellier is a hands-on workshop application that teaches developers how to build agentic AI-powered search using Amazon Aurora PostgreSQL, pgvector, Amazon Bedrock, Strands SDK, and Amazon Bedrock AgentCore. It's a real e-commerce storefront (React + FastAPI) where participants progressively build features by editing the actual application code.

## Delivery Format

- **60-min Builder's Session (AWS Summit)** — the storefront ships fully wired except one tool body. Participants do two mandatory builds and two optional fast-finishers; everything else is observe / measure / read.

Lab guide content lives in `lab-content/builders/`.

## Session Structure

Three Acts. Two mandatory builds, two optional fast-finishers.

- **Act I: The Boutique** (~28 min)
  - Observe Marco's broken Turn 4
  - **Exercise 1 (mandatory):** wire the `floor_check` tool body against `pellier.warehouse_inventory`
  - Measure vector / hybrid / hybrid+rerank for Anna's anchor query
  - *Optional fast-finisher:* edit Anna's skill rule and prove it via SQL
- **Act II: The Ledger** (~11 min)
  - Read memory substrates (AgentCore STM) + long-term taste in Aurora
  - Invoke the managed AgentCore Runtime
  - **Exercise 2 (mandatory):** `SELECT` from `pellier.tool_audit` to reconstruct the agent's actions
  - *Optional fast-finisher:* add a `logger.info` observability hook on the Runtime path
- **Act III: The Concierge** (~7 min, read-only)
  - Dispatcher + specialists routing (production default for curated intents)
  - MCP contract + AgentCore Gateway (managed tool catalog, JWT identity passthrough)
  - Bedrock Knowledge Bases comparison

## Key Directories

- `pellier/backend/` — FastAPI Python backend with Strands SDK agents
- `pellier/frontend/` — React + Vite + Tailwind storefront
- `solutions/` — Drop-in reference files / escape hatches (cp and restart)
  - `solutions/the-quiet-search/` (semantic search), `solutions/closing-marcos-gap/` (floor_check + specialists), `solutions/the-ledger/` (AgentCore production)
- `scripts/` — Bootstrap and seed scripts for the session environment
- `lab-content/builders/` — 60-min Builder's Session Workshop Studio content
- `data/` — Product catalog CSV with pre-generated Cohere Embed v4 embeddings
- `.kiro/specs/` — Feature specs (requirements, design, tasks)
- `.claude/prompts/` — Claude Code prompt playbooks

## Database

- Amazon Aurora PostgreSQL (latest available at session time; currently 17.9) Serverless v2 (0–16 ACU, scale-to-zero)
- Schema: `pellier` (product_catalog, warehouse_inventory, customers, customer_episodic_seed, tool_audit, and supporting tables)
- pgvector 0.8.0 with HNSW indexes for 1024-dim Cohere Embed v4 vectors
- 40 curated products (10 signed-out baseline + 10 per persona) with pre-generated embeddings
- Session management: AgentCore Memory (STM) via `agentcore_memory.py`
- User preferences stored in AgentCore Memory keyed by verified Cognito user_id

## Authentication

Real Amazon Cognito + AgentCore Identity (not simulated). Cognito User Pool with hosted UI federated to Google + Apple + email/password. JWT validated via Cognito JWKS. AgentCore Identity wraps verified user context for agents and scopes AgentCore Memory keys by user_id. The shopper's JWT is also passed through to the AgentCore Gateway so MCP tool calls carry the caller's identity.

The Builder's Session runs in demo auth mode by default (`AUTH_MODE=demo`); the Cognito/JWT path is fully wired and used for the signed-in Gateway demo.
