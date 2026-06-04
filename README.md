# Pellier — Agentic AI-Powered Search with Amazon Aurora, Amazon RDS for PostgreSQL & Bedrock AgentCore

<div align="center">

_Agentic RAG on Aurora PostgreSQL · Bedrock AgentCore · Strands Agents · MCP_

<br/>

[![Aurora PostgreSQL 17.9](https://img.shields.io/badge/Aurora_PostgreSQL-17.9_·_pgvector-2D72D9?style=flat-square&logo=postgresql&logoColor=white)](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html)
[![Bedrock AgentCore](https://img.shields.io/badge/Bedrock-AgentCore-FF9900?style=flat-square&logo=amazonwebservices&logoColor=white)](https://aws.amazon.com/bedrock/agentcore/)
[![Strands Agents](https://img.shields.io/badge/Strands-Agents_SDK-232F3E?style=flat-square&logo=amazonwebservices&logoColor=white)](https://strandsagents.com)
[![MCP](https://img.shields.io/badge/MCP-postgres--mcp--server-4A154B?style=flat-square)](https://github.com/awslabs/mcp/tree/main/src/postgres-mcp-server)
[![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)

[![License: MIT-0](https://img.shields.io/github/license/aws-samples/sample-pellier-agentic-search-apg?style=flat-square&color=00b300&label=License)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/aws-samples/sample-pellier-agentic-search-apg?style=flat-square&color=informational)](https://github.com/aws-samples/sample-pellier-agentic-search-apg/commits/main)
[![Stars](https://img.shields.io/github/stars/aws-samples/sample-pellier-agentic-search-apg?style=flat-square&color=yellow)](https://github.com/aws-samples/sample-pellier-agentic-search-apg/stargazers)

</div>

> Educational reference implementation for the AWS Summit Builder's
> Session. Not intended for production deployment without security
> hardening.

---

## What this is

**Pellier** is a small editorial boutique with one quiet promise — a
shopper asks for something in their own words, and the search
understands what they mean. Behind the storefront sits an agentic Retrieval-Augmented
Generation (RAG) system that reads live inventory, remembers your
taste, cites every source, and hands off to a human stylist when it
should.

The application has two surfaces:

- **Boutique** (`/`) — the customer-facing storefront. Editorial
  photograph, AI search bar, persona-aware recommendations,
  conversational chat drawer.
- **Atelier** (`/atelier`) — the operator's observatory. Every agent
  decision, tool call, memory read, retrieval comparison, and
  routing hop in editorial detail. Same agent, different lens.

The two surfaces share design tokens, presence pill, trace chips, and
a typed agent vocabulary so an attendee crossing between them sees
the same atoms in both places.

### What it demonstrates

Every claim in the [Builder's Session abstract](lab-content/builders/index.en.md)
maps to something runnable in this repo:

| Claim | Where it lives |
|---|---|
| **RAG** with embeddings on **Aurora PostgreSQL & RDS for PostgreSQL** | `pellier.product_catalog.embedding vector(1024)` · pgvector 0.8.0 · HNSW index · `<=>` cosine operator |
| **Agentic AI — reasoning + tool use** | Strands Agents SDK · 5 specialists × 13 `@tool` functions · dispatcher routes intent → one specialist → cosine-discovered tools |
| **Model Context Protocol (MCP)** | [`awslabs.postgres-mcp-server`](https://github.com/awslabs/mcp/tree/main/src/postgres-mcp-server) installed via `uvx`, read-only against the Aurora cluster ARN · `pellier/config/mcp-server-config.json` is the literal contract · any MCP host (VS Code chat extension, Claude Code, Strands `MCPClient`, AgentCore Gateway) consumes the same JSON |
| **Managed tool catalog (AgentCore Gateway)** | `services/agentcore_gateway.py` discovers tools at runtime via `MCPClient.list_tools_sync()` over a Cognito-JWT-gated Gateway · the shopper's JWT is passed through (`Authorization: Bearer`) so tool calls carry the caller's identity · in-process tools stay the default; Gateway is the demonstrable side-path (Atelier Card 7) |
| **Personalization** | Long-term taste in `pellier.customers` + `pellier.customer_episodic_seed` · session-scoped working memory (AgentCore STM) via Bedrock AgentCore Memory |
| **Managed agent runtime** | `@app.entrypoint` in `pellier/backend/agentcore_runtime.py` · `bedrock-agentcore:InvokeRuntime` from `services/agentcore_runtime.py` · deploy path uses `npx -y @aws/agentcore@latest deploy -y --json` |

---

## Personas reshape everything

The signed-out state is the editorial baseline. Sign in as one of the
three returning customers and the entire storefront — hero
photograph, suggestion pills, featured product, weekend edit copy,
curated grid (10 exclusive products per persona, zero overlap),
editorial cards, chat greeting — reshapes immediately.

| Persona  | Profile                          | Signature piece              |
| -------- | -------------------------------- | ---------------------------- |
| *Marco*  | Natural fibers, travel, linen    | Italian Linen Camp Shirt     |
| *Anna*   | Gifts, milestones, candles       | Beeswax Taper Candles        |
| *Theo*   | Slow craft, ceramics, ritual     | Stoneware Pour-Over Set      |

The **signed-out state** is the editorial baseline — a 10-piece grid
anchored by the Nocturne Leather Weekender, no prior context, no
profile embedding. It is the hero state, not a fourth persona.

Each persona ships with 10 products carrying real Cohere Embed English v3
1024-dim embeddings, generated at seed time by
[`scripts/seed_boutique_catalog.py`](scripts/seed_boutique_catalog.py).
40 products total (10 signed-out baseline + 10 per persona);
HNSW-indexed vector column on the `pellier.product_catalog` table.

---

## Quick start (local dev)

The production flow is a single FastAPI process on `:8000` serving
both the built React SPA and the API. For interactive iteration, run
the backend with `--reload` and rebuild the frontend on save.

```bash
# 1. Aurora + Bedrock credentials
cp pellier/backend/.env.example pellier/backend/.env
# edit DB_HOST, DB_USER, DB_PASSWORD, AWS_REGION, BEDROCK_*
set -a; source pellier/backend/.env; set +a

# 2. Apply schema + seed 40-product catalog + required workshop tables (one-time)
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
  -U "$DB_USER" -d "$DB_NAME" \
  -v ON_ERROR_STOP=1 \
  -f scripts/migrations/001_schema.sql
python3 scripts/seed_boutique_catalog.py
for migration in \
  002_workshop_telemetry.sql \
  003_persona_seed.sql \
  004_anna_hybrid_search.sql \
  005_theo_returns.sql \
  006_warehouse_inventory.sql \
  007_chat_session_tables.sql \
  008_search_performance_indexes.sql
do
  PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
    -U "$DB_USER" -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 \
    -f "scripts/migrations/$migration"
done

# 3. Backend
cd pellier/backend
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# 4. Frontend (separate terminal)
cd pellier/frontend
npm install
npm run build      # production build → served by FastAPI on :8000
# or: npm run dev   for HMR on :5173 (still hits backend on :8000)
```

Open <http://localhost:8000> for the Boutique, or
<http://localhost:8000/atelier> for the Atelier.

### AgentCore CLI (latest)

Pellier uses the Node-based AgentCore CLI via `npx` so deploy commands
always resolve the latest published version:

```bash
npx -y @aws/agentcore@latest --version
npx -y @aws/agentcore@latest deploy -y --json
```

This replaces the older `agentcore configure` / `agentcore launch`
starter-toolkit flow.

### Facilitator note: `SPA_MOUNT_PATH`

By default the SPA is served at `/`. The nginx layer
([`scripts/bootstrap-environment.sh:173-182`](scripts/bootstrap-environment.sh#L173-L182))
rewrites `/app/*` → `/` before forwarding to FastAPI, so root-mount works
behind both Workshop Studio's `/ports/8000/*` proxy and the `/app/*`
shortcut. If you ever deploy behind a proxy that forwards `/app/*`
verbatim (no prefix-stripping), set:

```bash
SPA_MOUNT_PATH=/app
VITE_BASE_PATH=/app/   # bake the prefix into the bundle at build time
```

The app moves to `/app/`, `GET /app` 307-redirects to `/app/`, and the
real API stays at `/api/*`. Do not register new FastAPI routes below
the SPA catch-all — its `{full_path:path}` pattern shadows everything
under the mount.

---

## Builder's Session (60 min)

This repo is the source of truth for the **60-minute Builder's Session**
(AWS Summit). Two mandatory builds plus two optional fast-finishers:
`floor_check` tool body (Act I) and a `SELECT` from `pellier.tool_audit`
(Act II); the optional skill-edit and `logger.info` observability hook
round out tables that finish early. Everything else is observe / measure
/ read.

The session source of truth lives in
[`lab-content/builders/`](lab-content/builders/). It is structured as:

| Section | Time | What attendees do |
|---|---|---|
| [Introduction](lab-content/builders/00-introduction/) | 5 min | Open the workspace, land in Boutique + Atelier, and frame the architecture (the bootstrap pre-verifies backend, catalog, warehouse, memory, and audit ledger) |
| [Act I: The Boutique](lab-content/builders/10-act-1-the-boutique/) | 30 min | Observe Marco's broken Turn 4 → wire `floor_check` (Exercise 1) → measure vector / hybrid / hybrid+rerank / agentic for Anna's anchor query |
| [Act II: The Ledger](lab-content/builders/20-act-2-the-ledger/) | 12 min | Read memory substrates (AgentCore STM) via `/api/agent/session/{id}` + inspect long-term taste in Aurora → invoke managed Runtime, then `SELECT` from `pellier.tool_audit` (Exercise 2); optional `logger.info` observability hook |
| [Act III: The Concierge](lab-content/builders/30-act-3-the-concierge/) | 8 min | Read dispatcher + specialists pattern → read the `awslabs.postgres-mcp-server` config + verify from terminal, compare to Bedrock Knowledge Bases (read-only, take-home friendly) |
| [Close](lab-content/builders/40-close/) | 3 min | [What this maps to in your stack](lab-content/builders/90-appendix/03-your-stack/) + Q&A |

Make canonical edits in [`lab-content/builders/`](lab-content/builders/)
and `lab-content/builders/static/`.

---

## Architecture

### Agents

Five specialist agents + one orchestrator. Three orchestration
patterns shipped; the boutique runs the dispatcher pattern in
production and exposes the other two as Atelier toggles.

| Agent              | Role                                          | Model            |
| ------------------ | --------------------------------------------- | ---------------- |
| **Style Advisor**      | Interprets intent, runs semantic search        | Claude Opus 4.6 |
| **Curator**            | Pairing, palette, occasion, editorial picks    | Claude Opus 4.6 |
| **Value Analyst**      | Price intelligence, deals, percentile context  | Claude Haiku 4.5  |
| **Stock Keeper**       | Warehouse stock, restocks, low-inventory alerts | Claude Haiku 4.5  |
| **Experience Guide**   | Returns, care, post-purchase                   | Claude Opus 4.6 |

Per-agent model choice is an architectural decision — Stock Keeper's
terse warehouse answers run on Haiku; the Curator's editorial
prose earns Opus. Factories load **`BEDROCK_OPUS_MODEL`** for editorial
agents and **`BEDROCK_HAIKU_MODEL`** for reporting/routing —
see `pellier/backend/config.py`. The **`BEDROCK_SONNET_MODEL`** env name is
legacy only (same inference profile as Opus in defaults). The Atelier surfaces
the mix.

### Tools

13 `@tool` functions across the agent set:

`find_pieces` · `find_pieces_hybrid` · `style_match` · `whats_trending` ·
`price_intelligence` · `explore_collection` · `side_by_side` ·
`floor_check` · `restock_shelf` · `running_low` ·
`returns_and_care` · `process_return` · `escalate_to_stylist`

Tool registry is itself stored in Aurora pgvector; the orchestrator
uses cosine similarity to discover the right tool from a natural-
language query — the same primitive that powers product search,
applied to capabilities.

### Skills

Three persona-scoped skills loaded per-turn by the SkillRouter to
shape voice and handling without changing product selection:

[`skills/the-packing-list/`](skills/the-packing-list/) (Marco) ·
[`skills/the-gift-table/`](skills/the-gift-table/) (Anna) ·
[`skills/the-makers-shelf/`](skills/the-makers-shelf/) (Theo)

### Stack

| Layer            | Technology                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Database         | **Aurora PostgreSQL Serverless v2** (engine 17.9) in this lab; same pgvector primitives run unchanged on **Amazon RDS for PostgreSQL** — choose Aurora for elastic ACU scaling, RDS for predictable instance-class workloads |
| Vector retrieval | pgvector 0.8.0 · `vector(1024)` column · HNSW (m=16, ef_construction=64, `vector_cosine_ops`) · `<=>` cosine operator |
| Lexical retrieval | Postgres FTS — `tsvector` + GIN + `ts_rank_cd` (no native BM25; `pg_trgm` for fuzzy match) |
| Hybrid merge     | Reciprocal Rank Fusion (RRF) — fuses pgvector + FTS rank lists without normalizing raw scores |
| Models           | Claude Opus 4.6 (`global.anthropic.claude-opus-4-6-v1`, editorial · `T=0.2–0.4`) · Claude Haiku 4.5 (`global.anthropic.claude-haiku-4-5-20251001-v1:0`, reporting · `T=0.0–0.1`) · Cohere Embed English v3 (`cohere.embed-english-v3`, 1024-dim, on-demand) · Cohere Rerank v3.5 (`us.cohere.rerank-v3-5:0`, inference profile) |
| Agent framework  | Strands Agents SDK — `Agent`, `@tool`, `GraphBuilder`, `BeforeToolCallEvent` hooks                                       |
| Agent infra      | Bedrock AgentCore — Runtime (`@app.entrypoint` → `InvokeRuntime`) · Memory (STM, 30-day) · Gateway (MCP tool catalog, Cognito-JWT auth with shopper identity passthrough) · Identity     |
| MCP              | [`awslabs.postgres-mcp-server`](https://github.com/awslabs/mcp/tree/main/src/postgres-mcp-server) installed via `uvx`, registered against the Aurora cluster ARN with `--readonly True`; `pellier/config/mcp-server-config.json` is the literal contract; AgentCore Gateway is the managed-host counterpart |
| Backend          | FastAPI · Python 3.14 (3.13 fallback) · psycopg3 · boto3 · SSE streaming                                                  |
| Frontend         | React 18 · TypeScript 5 · Vite · Tailwind · Framer Motion 12                                                             |
| Editorial system | Fraunces Variable (display) · Inter (body) · JetBrains Mono (code) · cream / espresso / terracotta palette               |

---

## Repository layout

```
sample-pellier-agentic-search-apg/
├── pellier/
│   ├── backend/                           FastAPI server, agents, services
│   │   ├── agents/                          Style Advisor, Curator, Stock Keeper, ...
│   │   ├── services/                        agent_tools, chat, agentcore_*, db
│   │   ├── routes/                          FastAPI routers (transcribe, atelier, chat)
│   │   └── app.py
│   └── frontend/                          React 18 + TS + Vite SPA
│       └── src/
│           ├── components/                  BoutiqueHero, ChatDrawer, ProductCard, ...
│           ├── shared/                      Cross-surface atoms — TraceChip, PresencePill
│           ├── atelier/                     Operator's surface
│           └── data/                        showcaseProducts.ts (40), personaCurations.ts
│
├── skills/                                Per-persona Strands skills (3)
├── solutions/                             Reference implementations (drop-in escape hatches)
│   ├── the-quiet-search/                    Semantic search reference (observe-only)
│   ├── closing-marcos-gap/                  floor_check + Stock Keeper (Exercise 1)
│   └── the-ledger/                     AgentCore production + audit ledger (Exercise 2)
│
├── scripts/
│   ├── migrations/                         Ordered fresh-cluster SQL (001-008)
│   ├── seed_boutique_catalog.py             40 products with Cohere embeddings
│   ├── bootstrap-environment.sh             Code Editor + nginx + systemd
│   └── bootstrap-labs.sh                    DB seed + frontend build + service start
│
└── lab-content/                           Workshop Studio content + CFN
    └── builders/                            60-min Builder's Session bundle
        ├── index.en.md                        Landing · learning outcomes · module map
        ├── 00-introduction/                   Enter the environment · surfaces · architecture frame
        ├── 10-act-1-the-boutique/             Act I — observe Marco, wire floor_check, prove rerank
        │   ├── 01-meet-marco/
        │   ├── 02-wire-floor-check/             Exercise 1
        │   └── 03-prove-rerank/
        ├── 20-act-2-the-ledger/               Act II — Memory substrates (AgentCore STM) + managed Runtime + audit ledger
        │   ├── 01-memory-substrates/
        │   └── 02-agentcore-runtime/            Exercise 2 (SELECT from pellier.tool_audit; optional logger.info hook)
        ├── 30-act-3-the-concierge/            Act III (take-home) — routing + MCP + Knowledge Bases
        │   ├── 01-routing-patterns/
        │   └── 02-mcp-and-knowledge-bases/      reads pellier/config/mcp-server-config.json + uvx
        ├── 40-close/                          Summary · seams to carry back · expansion path
        ├── 90-appendix/                       Reference · runbook · your-stack · facilitator notes
        │   ├── 01-reference/                    Cast, memory substrates, pgvector primer, quick start
        │   ├── 02-when-things-misbehave/
        │   ├── 03-your-stack/
        │   └── 04-facilitator-notes/
        ├── assets/                            Builder CloudFormation source (CFN templates)
        └── static/                            Diagrams + prereq images
```

---

## Resources

- [Aurora PostgreSQL with pgvector](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html)
- [Amazon RDS for PostgreSQL with pgvector](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html#PostgreSQL.Concepts.General.FeatureSupport.Extensions)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [Amazon Bedrock Knowledge Bases (Aurora as vector store)](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup-rds.html)
- [Model Context Protocol (MCP) specification](https://modelcontextprotocol.io/)
- [Strands Agents SDK](https://strandsagents.com/latest/)
- [pgvector 0.8.0 performance on Aurora](https://aws.amazon.com/blogs/database/supercharging-vector-search-performance-and-relevance-with-pgvector-0-8-0-on-amazon-aurora-postgresql/)

---

## Credits

Built and curated by **Shayon Sanyal**.

## License

MIT-0. See [LICENSE](LICENSE).
