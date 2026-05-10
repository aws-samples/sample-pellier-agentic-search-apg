# Pellier — Agentic AI-Powered Search with Amazon Aurora & Bedrock AgentCore

<div align="center">

[![AWS Workshop](https://img.shields.io/badge/AWS-Workshop-FF9900?style=for-the-badge&logo=amazon-aws&logoColor=white)](https://github.com/aws-samples/sample-pellier-agentic-search-apg)
[![Level 400](https://img.shields.io/badge/Level-400%20Expert-red?style=for-the-badge)](https://github.com/aws-samples/sample-pellier-agentic-search-apg)
[![License](https://img.shields.io/badge/License-MIT-00b300?style=for-the-badge)](LICENSE)

</div>

> **Educational Workshop**: Demonstration code for re:Invent / AWS Summit sessions. Not intended for production deployment without proper security hardening.

---

## What Is This?

**Pellier** is a boutique e-commerce storefront powered by a multi-agent AI system. It demonstrates how to build agentic search using **Amazon Aurora PostgreSQL** (pgvector for semantic search), **Amazon Bedrock** (Claude for reasoning), **Bedrock AgentCore** (managed agent infrastructure), and **Amazon Transcribe** (voice-to-text).

The application has two surfaces:

- **Boutique** (`/`) — the customer-facing editorial storefront with AI-powered search, voice input, personalized recommendations, and a conversational shopping concierge
- **Atelier** (`/atelier`) — the operator-facing observatory that shows every agent decision, tool call, memory read, and reasoning step in real time

### Three Personas

The demo ships with three personas that reshape the entire experience. The signed-out state serves as the editorial baseline.

| Persona | Profile | Boutique Effect |
|---------|---------|-----------------|
| **Marco** | Natural fibers, travel, linen | Italian Linen Camp Shirt hero, "The Travel Edit", linen/leather grid |
| **Anna** | Gifts, milestones, candles | Beeswax Taper Candles hero, "The Gift Edit", gift-forward grid |
| **Theo** | Slow craft, ceramics, home | Stoneware Pour-Over Set hero, "The Slow Edit", artisanal grid |
| *(signed out)* | Editorial baseline | Nocturne Leather Weekender hero, generic editorial, warm welcome |

Switching personas in the header immediately reshapes: hero image, suggestion pills, featured product, Weekend Edit copy, curated grid (exclusive 9 products per persona), "Because you asked..." editorial cards, chat concierge greeting, and voice search suggestions.

### 40-Product Curated Catalog

Each persona has 10 exclusive products (zero overlap) with real Cohere Embed v4 embeddings:

| Persona | Products | Price Range | Signature Piece |
|---------|----------|-------------|-----------------|
| Fresh | 9 editorial bestsellers | $78–$425 | Nocturne Leather Weekender |
| Marco | 9 travel/linen pieces | $38–$485 | Italian Linen Camp Shirt |
| Anna | 9 gift-ready pieces | $28–$128 | Beeswax Taper Candles |
| Theo | 9 slow-craft pieces | $24–$195 | Stoneware Pour-Over Set |

---

## Two Formats, One Codebase

| Format | Duration | Challenges | What Participants Build |
|--------|----------|------------|------------------------|
| **Workshop** | 2 hours | 9 challenges (all edit) | Full stack: search → agents → production |
| **Builder's Session** | 1 hour | 2 edit + 7 test/read | Search + tools hands-on, rest pre-completed |

### Three Modules

| Module | Name | Challenges | Outcome |
|--------|------|------------|---------|
| 1 | Smart Search | C1: `_vector_search()` | "Your database understands what customers mean." |
| 2 | Agentic AI | C2: `@tool`, C3: agent, C4: orchestrator | "A multi-agent team handles customer queries." |
| 3 | Production Patterns | C5–C9: runtime, memory, gateway, observability, identity | "Your agent system runs on managed infrastructure." |

---

## Quick Start

```bash
# Terminal 1: Backend (auto-reloads on .py changes)
cd pellier/backend
cp .env.example .env  # Edit with your Aurora + Bedrock credentials
pip install amazon-transcribe  # For voice search
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend (HMR on .ts/.tsx changes)
cd pellier/frontend
npm install && npm run dev

# Seed the 40-product catalog with real embeddings
python scripts/seed_boutique_catalog.py
```

Open [http://localhost:5173](http://localhost:5173) for the Boutique, or [http://localhost:5173/atelier](http://localhost:5173/atelier) for the Atelier.

---

## Architecture

### Voice → Agent → Database Pipeline

```
Browser Mic (Web Audio API)
  ↓ PCM audio (16kHz, WebSocket)
Amazon Transcribe Streaming
  ↓ interim + final transcripts
Bedrock Agent (Claude Opus 4.6)
  ↓ tool calls (find_pieces, style_match, etc.)
Aurora PostgreSQL + pgvector
  ↓ cosine similarity search (HNSW)
SSE streamed response
  ↓ product cards + prose
Boutique Chat Drawer
```

### Multi-Agent System

5 boutique-branded specialist agents + 1 orchestrator, running three orchestration patterns:

| Pattern | Surface | How It Works |
|---------|---------|-------------|
| **Dispatcher** (Pattern III) | Boutique production | Deterministic classifier picks one specialist; one LLM call |
| **Agents as Tools** (Pattern I) | Atelier toggle | Haiku orchestrator + five `@tool` specialists; two LLM calls |
| **Graph** (Pattern II) | Atelier toggle | Real Strands `GraphBuilder` DAG: Haiku router → 5 specialist nodes |

### Specialist Agents

| Agent | Role | Tools |
|-------|------|-------|
| **Style Advisor** | Interprets intent, searches catalog | `find_pieces`, `explore_collection`, `side_by_side`, `style_match` |
| **Curator** | Personalized recommendations, trending | `find_pieces`, `whats_trending`, `side_by_side`, `explore_collection` |
| **Value Analyst** | Price intelligence, deals | `price_intelligence`, `explore_collection`, `find_pieces` |
| **Stock Keeper** | Inventory, restocking | `floor_check`, `restock_shelf`, `running_low` |
| **Experience Guide** | Returns, care instructions | `returns_and_care`, `find_pieces` |

### 10 Tools

| Tool | What It Does |
|------|-------------|
| `find_pieces` | Semantic search via pgvector cosine similarity |
| `explore_collection` | Browse by category with filters |
| `side_by_side` | Compare two products |
| `style_match` | Product-to-product pgvector similarity (complementary pieces) |
| `whats_trending` | Trending by review velocity × rating |
| `price_intelligence` | Price distribution — percentiles, averages, value picks |
| `floor_check` | Warehouse health snapshot |
| `restock_shelf` | Add inventory (Cedar policy enforces 500-unit ceiling) |
| `running_low` | Products with ≤5 units |
| `returns_and_care` | Return window + care instructions |

### 3 Skills

| Skill | Persona | What It Teaches |
|-------|---------|-----------------|
| **The Packing List** | Marco | Travel wardrobe curation — packable, natural, layer-friendly |
| **The Gift Table** | Anna | Gift guidance — wrapping, milestones, price-band pairing |
| **The Maker's Shelf** | Theo | Craft provenance — patina, kiln-fired, slow ritual |

### Infrastructure Stack

| Layer | Technologies |
|-------|-------------|
| **Database** | Aurora PostgreSQL Serverless v2, pgvector 0.8.0 (HNSW), 40 products with 1024-dim embeddings |
| **AI/ML** | Amazon Bedrock — Claude Opus 4.6 (specialists), Claude Haiku 4.5 (router), Cohere Embed v4 |
| **Voice** | Amazon Transcribe Streaming — real-time speech-to-text via WebSocket |
| **Agent Infra** | Bedrock AgentCore — Gateway (MCP), Memory (STM/LTM), Policy (Cedar), Runtime |
| **Agent Framework** | Strands Agents SDK (Agent, @tool, GraphBuilder, BeforeToolCallEvent hooks) |
| **Backend** | FastAPI, Python 3.13, SSE streaming, WebSocket, psycopg3, boto3 |
| **Frontend** | React 18, TypeScript 5, Tailwind CSS, Vite, Framer Motion |
| **Design System** | Fraunces Variable (editorial), Inter (body), JetBrains Mono (code) |

---

## Boutique Features

- **Voice search** — click Mic → speak naturally → Amazon Transcribe streams interim transcripts into the search bar → auto-submit → chat drawer opens with agent response
- **BoutiqueHero** — full-bleed editorial photograph (per-persona), Sparkles + Mic/Send button, persona-specific suggestion pills, trust strip
- **Per-persona storefront** — hero image, featured product, Weekend Edit headline, exclusive product grid, editorial cards all reshape by persona
- **Chat drawer** — opens from hero search or ⌘K. Persona-aware welcome greeting with personal touch. AgentCore STM hydration on refresh. Real-time SSE streaming.
- **Cart** — session-scoped, wired to "Add to bag" on every product card
- **Editorial Brief** — workshop credit section with tech stack chips

## Atelier Features

- **Espresso sidebar** (300px) — Observatory, Sessions, Memory, Inventory, Agents, Tools, Evaluations, Settings with real persona headshot photos
- **Sessions list** — timestamped session cards with opening query, elapsed time, agent count, routing pattern
- **Session detail** — Chat / Telemetry / Brief tabs with numbered timeline, tool call expansion, SQL highlighting, product recommendation cards
- **Architecture index** — 8 concept cards with sticky category legend rail (Both / Managed / Owned / Teaching)
- **Architecture detail pages** — deep-dive with two-tier hero, sequence diagrams, cheat sheets, live state callouts, back navigation
- **Observatory** — wide-angle dashboard with metric numerals, agent status, tool invocations, memory state
- **Live telemetry** — per-turn runtime timing, DB query log, guardrail decisions, Cedar policy enforcement, performance p50/p95

---

## Repository Structure

```
pellier/
├── backend/
│   ├── agents/
│   │   ├── orchestrator.py              Maître d' (Agents-as-Tools pattern)
│   │   ├── graph_pattern.py             GraphBuilder DAG adapter (Pattern II)
│   │   ├── search_agent.py              Style Advisor
│   │   ├── recommendation_agent.py      Curator
│   │   ├── pricing_agent.py             Value Analyst
│   │   ├── inventory_agent.py           Stock Keeper
│   │   └── customer_support_agent.py    Experience Guide
│   ├── services/
│   │   ├── chat.py                      SSE streaming chat (3 patterns)
│   │   ├── agent_tools.py               10 @tool functions (boutique-branded)
│   │   ├── policy_hook.py               Cedar enforcement via BeforeToolCallEvent
│   │   ├── agentcore_memory.py          AgentCore Memory (STM + LTM)
│   │   └── database.py                  Aurora connection pool
│   ├── routes/
│   │   └── transcribe.py               Amazon Transcribe WebSocket endpoint
│   ├── skills/
│   │   ├── the-packing-list/SKILL.md   Marco's travel wardrobe skill
│   │   ├── the-gift-table/SKILL.md     Anna's gifting skill
│   │   └── the-makers-shelf/SKILL.md   Theo's slow-craft skill
│   └── app.py                          FastAPI server (60+ endpoints)
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── BoutiqueHero.tsx         Editorial hero with voice search
│   │   │   ├── BecauseYouAsked.tsx      Persona-aware editorial cards
│   │   │   ├── EditorialBrief.tsx       Workshop credit section
│   │   │   ├── ChatDrawer.tsx           Conversational drawer with SSE + STM
│   │   │   └── ProductCard.tsx          Product card with scroll-reveal
│   │   ├── hooks/
│   │   │   ├── useAgentChat.ts          SSE event loop + STM hydration
│   │   │   └── useVoiceSearch.ts        Amazon Transcribe mic capture
│   │   ├── data/
│   │   │   ├── showcaseProducts.ts      40 products (10 per persona)
│   │   │   ├── personaCurations.ts      Per-persona: pills, featured, editorial
│   │   │   └── personaPhotos.ts         Unsplash headshot URLs
│   │   └── design/                      Tokens, typography, primitives
│   └── tailwind.config.js              Design tokens (cream, sand, espresso)
├── scripts/
│   └── seed_boutique_catalog.py        Seed 40 products + Cohere embeddings
└── solutions/                           Drop-in solution files per challenge
```

---

## Design System

Three typefaces, shared across Boutique and Atelier via CSS variables:

| Token | Family | Usage |
|-------|--------|-------|
| `--serif` / `font-display` | Fraunces Variable | Editorial headlines, product names |
| `--sans` / `font-sans` | Inter | Body text, UI, navigation |
| `--mono` / `font-mono` | JetBrains Mono | Code, timestamps, metadata |

Color palette: cream (`#F7F3EE`), sand (`#E8DFD4`), espresso (`#3B2F2F`), accent/burgundy (`#C44536`), ink variants (1–5)

Preview: [http://localhost:5173/dev/design-system](http://localhost:5173/dev/design-system) (dev only)

---

## Resources

- [Aurora PostgreSQL with pgvector](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [Amazon Transcribe Streaming](https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html)
- [Strands Agents SDK](https://strandsagents.com/latest/)
- [pgvector 0.8.0 Performance](https://aws.amazon.com/blogs/database/supercharging-vector-search-performance-and-relevance-with-pgvector-0-8-0-on-amazon-aurora-postgresql/)
- [AWS Labs MCP Servers](https://awslabs.github.io/mcp/)

---

## Credits

Workshop built and curated by **Shayon Sanyal**.

---

## License

MIT-0 License. See [LICENSE](./LICENSE).
