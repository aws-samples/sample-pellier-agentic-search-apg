# Pellier — Agentic AI-Powered Search with Amazon Aurora & Bedrock AgentCore

<div align="center">

[![AWS Workshop](https://img.shields.io/badge/AWS-Workshop-FF9900?style=for-the-badge&logo=amazon-aws&logoColor=white)](https://github.com/aws-samples/sample-pellier-agentic-search-apg)
[![Level 400](https://img.shields.io/badge/Level-400%20Expert-red?style=for-the-badge)](https://github.com/aws-samples/sample-pellier-agentic-search-apg)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT--0-00b300?style=for-the-badge)](LICENSE)

</div>

> Educational reference implementation for AWS re:Invent and Summit
> sessions. Not intended for production deployment without security
> hardening.

---

## What this is

**Pellier** is a small editorial boutique with one quiet promise — a
shopper asks for something in their own words, and the right pieces
find them. Behind the storefront sits a multi-agent system that reads
live inventory, remembers your taste, cites every source, and hands
off to a human stylist when it should.

The application has two surfaces:

- **Boutique** (`/`) — the customer-facing storefront. Editorial
  photograph, AI search bar, voice input, persona-aware
  recommendations, conversational chat drawer.
- **Atelier** (`/atelier`) — the operator's observatory. Every agent
  decision, tool call, memory read, and routing hop in editorial
  detail. Same agent, different lens.

The two surfaces share design tokens, presence pill, trace chips, and
a typed agent vocabulary so an attendee crossing between them sees
the same atoms in both places.

---

## Personas reshape everything

The signed-out state is the editorial baseline. Sign in as one of the
three returning customers and the entire storefront — hero
photograph, suggestion pills, featured product, weekend edit copy,
curated grid (10 exclusive products per persona, zero overlap),
editorial cards, chat greeting, voice search hints — reshapes
immediately.

| Persona  | Profile                          | Signature piece              |
| -------- | -------------------------------- | ---------------------------- |
| *Marco*  | Natural fibers, travel, linen    | Italian Linen Camp Shirt     |
| *Anna*   | Gifts, milestones, candles       | Beeswax Taper Candles        |
| *Theo*   | Slow craft, ceramics, ritual     | Stoneware Pour-Over Set      |
| *Fresh*  | Editorial baseline (signed out)  | Nocturne Leather Weekender   |

Each persona ships with 10 products carrying real Cohere Embed v4
1024-dim embeddings, generated at seed time by
[`scripts/seed_boutique_catalog.py`](scripts/seed_boutique_catalog.py).
40 products total; HNSW-indexed vector column on the
`pellier.product_catalog` table.

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
  007_chat_session_tables.sql
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

---

## Workshop formats

This repo is the source of truth. Two Workshop Studio bundles
package it for live events:

| Format                          | Duration | Coding modules | What participants build                                       |
| ------------------------------- | -------- | -------------- | ------------------------------------------------------------- |
| **Builder's Session** (DC Summit)   | 60 min (45 hands-on) | 1 exercise | `floor_check` tool + AgentCore STM verify + Runtime invoke (pre-launched) |
| **Workshop** (re:Invent)        | 120 min  | 9 challenges   | Full stack — semantic search, agents, AgentCore production patterns         |

The 60-min Builder's Session source of truth lives in
`lab-content/builders/`. The 120-min Workshop bundle lives in
`lab-content/workshop/`. The `lab-content/builders/ws-repo/` folder is
kept only as a reference snapshot of the Workshop Studio repo shape;
make canonical edits in `lab-content/builders/` and
`lab-content/builders/static/`.

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

12 `@tool` functions across the agent set:

`find_pieces` · `style_match` · `whats_trending` ·
`price_intelligence` · `explore_collection` · `side_by_side` ·
`floor_check` · `restock_shelf` · `running_low` ·
`returns_and_care` · `process_return` · `cart.holds`

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
| Database         | Aurora PostgreSQL Serverless v2 (engine 17.7) · pgvector 0.8.0 · HNSW index · 1024-dim Cohere Embed v4 vectors          |
| Models           | Claude Opus 4.6 · Claude Haiku 4.5 (Bedrock inference profiles) · Cohere Embed v4 · Cohere Rerank v3.5                               |
| Voice            | Amazon Transcribe Streaming over WebSocket — interim + final transcripts                                                |
| Agent infra      | Bedrock AgentCore — Runtime · Memory (STM + LTM) · Gateway (MCP) · Identity                                              |
| Agent framework  | Strands Agents SDK — `Agent`, `@tool`, `GraphBuilder`, `BeforeToolCallEvent` hooks                                       |
| Backend          | FastAPI · Python 3.13 · psycopg3 · boto3 · SSE streaming                                                                 |
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
├── solutions/                             Reference implementations
│   ├── the-quiet-search/                    Module 1 (semantic search)
│   ├── closing-marcos-gap/                  Module 2 (Stock Keeper)
│   └── the-paper-trail/                     Module 3 (AgentCore production)
│
├── scripts/
│   ├── migrations/                         Ordered fresh-cluster SQL (001-007)
│   ├── seed_boutique_catalog.py             40 products with Cohere embeddings
│   ├── bootstrap-environment.sh             Code Editor + nginx + systemd
│   └── bootstrap-labs.sh                    DB seed + frontend build + service start
│
└── lab-content/                           Workshop Studio content + CFN
    ├── workshop/                            120-min re:Invent bundle
    │   └── static/                          Workshop CloudFormation source
    └── builders/                            60-min DC Summit bundle
        ├── static/                          Builder CloudFormation source
        └── ws-repo/                         Reference snapshot only
```

---

## Resources

- [Aurora PostgreSQL with pgvector](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [Amazon Transcribe Streaming](https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html)
- [Strands Agents SDK](https://strandsagents.com/latest/)
- [pgvector 0.8.0 performance on Aurora](https://aws.amazon.com/blogs/database/supercharging-vector-search-performance-and-relevance-with-pgvector-0-8-0-on-amazon-aurora-postgresql/)

---

## Credits

Built and curated by **Shayon Sanyal**.

## License

MIT-0. See [LICENSE](LICENSE).
