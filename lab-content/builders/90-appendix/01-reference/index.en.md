---
title: "01: Reference"
weight: 10
---

:::alert{type="info"}
**Audience:** all builders  
**Use:** skim before the session; return mid-flight when you need the canonical map of specialists, tools, skills, personas, pgvector, or commands  
**Surfaces covered:** cast, memory substrates, pgvector, hybrid retrieval, quick start
:::

This page is the workshop map in reference form. It is not required reading during the live path, but it is the fastest way to answer, *"Which specialist owns that tool?"*, *"Where does that data live?"*, or *"What command gets me unstuck?"*

- [The cast](#the-cast): specialists, tools, skills, personas
- [Memory substrates](#memory-substrates): working, semantic, episodic, procedural
- [pgvector primer](#pgvector-primer): column types, distance operators, HNSW, hybrid retrieval
- [Quick start](#quick-start): URLs, commands, layout, and exercise workflow

---

## The cast

Pellier is five specialists, thirteen customer-callable tools, three skills, three named personas, and one signed-out baseline called **Fresh**. The dispatcher routes one customer turn to one specialist; the specialist may call one or more tools; the reply returns with trace evidence.

### The five specialists

| Specialist | Model | Temp | Owns | Answers when… |
|---|---:|---:|---|---|
| **Style Advisor** | Opus 4.6 | 0.4 | `find_pieces`, `explore_collection`, `side_by_side`, `style_match` | The shopper describes what they want in natural language. |
| **Curator** | Opus 4.6 | 0.4 | `find_pieces_hybrid`, `whats_trending`, `side_by_side`, `explore_collection` | The query needs pairing, palette, occasion, gift framing, or persona-aware curation. |
| **Value Analyst** | Haiku 4.5 | 0.1 | `price_intelligence`, `explore_collection`, `find_pieces` | The shopper asks about price, value, range, or comparison. |
| **Stock Keeper** | Haiku 4.5 | 0.0 | `floor_check`, `restock_shelf`, `running_low` | The shopper asks about warehouses, inventory, stock, or restock state. |
| **Experience Guide** | Opus 4.6 | 0.2 | `returns_and_care`, `find_pieces`, `process_return` | The shopper asks about care, returns, post-purchase support, or escalation. |

:::alert{type="info" header="Why model and temperature differ by specialist"}
Editorial recommendation benefits from a richer model and some expressive range. Warehouse answers and price summaries should be terse and stable. Pellier makes that tradeoff explicit: Opus for voice-heavy specialists, Haiku for deterministic reports, and low temperature where creativity would be noise.
:::

### The thirteen tools

Tools are Python functions decorated with `@tool` in `pellier/backend/services/agent_tools.py`. The orchestrator discovers capabilities from their contracts and docstrings; the bodies decide which source of truth to read or write.

| Tool | Owner | Data source | Pattern |
|---|---|---|---|
| `find_pieces` | Style Advisor | `pellier.product_catalog` | pgvector cosine + rerank over a domain corpus |
| `find_pieces_hybrid` | Curator | `pellier.product_catalog` + `tsvector` | Vector + full-text search, RRF merge, then rerank |
| `style_match` | Style Advisor | `pellier.product_catalog` | Product-to-product vector similarity |
| `whats_trending` | Curator | `product_catalog`, `orders` | Popularity and recency signal over structured data |
| `price_intelligence` | Value Analyst | `product_catalog` | Deterministic aggregate over price fields |
| `explore_collection` | Style Advisor, Curator, Value Analyst | `product_catalog` | Browse by category, theme, or collection |
| `side_by_side` | Style Advisor, Curator | `product_catalog` | Compare two pieces directly |
| `floor_check` | Stock Keeper | `warehouse_inventory`, `warehouses` | Deterministic operational read; the Act I build exercise |
| `restock_shelf` | Stock Keeper | `warehouse_inventory` | Policy-gated write; audited in `tool_audit` |
| `running_low` | Stock Keeper | `warehouse_inventory` | Inventory-health aggregate |
| `returns_and_care` | Experience Guide | `return_policies` | Policy lookup before mutation or escalation |
| `process_return` | Experience Guide | `returns`, `customers` | Policy-gated write; audited in `tool_audit` |
| `escalate_to_stylist` | Style Advisor, Curator, Experience Guide | session context | Human handoff when a tool or model answer would be unsafe or incomplete |

`cart.holds` exists internally for cart bookkeeping. It is not customer-callable, so it does not appear in the discovery registry.

:::alert{type="info" header="Audit rule"}
Every Cedar-allowed tool call that actually runs writes a row to `pellier.tool_audit`, reads and writes alike. DENY decisions do not appear in the table because the tool never executes.
:::

### The three skills

Skills are persona-scoped markdown playbooks loaded by the `SkillRouter` per turn. They shape voice and handling without changing product selection or SQL.

| Skill | Persona | Loads when… | Lives in |
|---|---|---|---|
| `the-packing-list` | Marco | Travel, layering, natural fibers | `skills/the-packing-list/` |
| `the-gift-table` | Anna | Gift, milestone, wrap-ready ask | `skills/the-gift-table/` |
| `the-makers-shelf` | Theo | Ceramics, ritual, slow craft | `skills/the-makers-shelf/` |

### The personas, plus Fresh

| Persona | Profile | Signature piece | Anchor query |
|---|---|---|---|
| **Marco** | Natural fibers, travel, linen | Italian Linen Camp Shirt | `What linen do you have for 10 days in Goa?` |
| **Anna** | Gifts, milestones, candles | Beeswax Taper Candles | `A milestone gift for a new homeowner` |
| **Theo** | Slow craft, ceramics, ritual | Stoneware Pour-Over Set | `Something to slow my morning ritual` |
| **Fresh** | Signed-out editorial baseline | Nocturne Leather Weekender | Default hero state with no prior context |

Each persona ships with ten products, for forty products total in `pellier.product_catalog`.

### How a turn fits together

```text
Customer turn
  ↓
Dispatcher in services/chat.py
  ↓
One specialist
  ↓
Optional skill overlay + one or more @tool calls
  ↓
Aurora PostgreSQL, pgvector, warehouse data, memory, and rerank
  ↓
Reply + product cards + trace chips + audit evidence
```

The personas reshape what the agent sees. The dispatcher decides who answers. The skill decides how it sounds. The tool decides what is true.

---

## Memory substrates

Pellier uses four memory substrates with different lifetimes and write cadences. Avoid treating them as one generic "memory" bucket.

| Substrate | What it answers | Primary store | Workshop proof |
|---|---|---|---|
| **Working** | What happened in this session, in order? | AgentCore Memory session events | `/api/agent/session/{session_id}` readback |
| **Semantic** | What stable preference do we know about this customer? | AgentCore Memory KV | Atelier Memory panel |
| **Episodic** | What events has this customer produced over time? | Aurora tables such as `customer_episodic_seed`, `orders`, `returns` | Atelier Memory panel and SQL references |
| **Procedural** | Which tools ran, how often, and at what latency? | Aurora `pellier.tool_audit` aggregate | Act II ledger query and Atelier Memory panel |

---

## pgvector primer

`pgvector` adds a vector column type, distance operators, and approximate-nearest-neighbor indexes to PostgreSQL. Pellier uses it for product retrieval and capability discovery.

### The column

```sql
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE pellier.product_catalog
  ADD COLUMN embedding vector(1024);
```

`vector(1024)` stores a 1024-dimensional embedding per row. Pellier uses Cohere Embed English v3, so the column dimension must match the embedder output.

### The distance operator you see most

```sql
SELECT id, name, 1 - (embedding <=> $1::vector) AS similarity
FROM pellier.product_catalog
ORDER BY embedding <=> $1::vector
LIMIT 5;
```

`<=>` is cosine distance. Lower distance sorts first; `1 - distance` is useful when you want a similarity-like display value.

### Hybrid retrieval

Pellier's hybrid path runs two retrieval signals and merges them:

1. pgvector cosine search for soft taste and semantic match.
2. PostgreSQL full-text search for literal tokens, exact phrases, and category language.
3. Reciprocal Rank Fusion (RRF) to merge rankings without normalizing raw scores.
4. Rerank over the candidate pool for the final user phrasing.

```text
RRF score = sum over each ranking list of 1 / (k + rank)
```

`k=60` is the conventional constant. Vector handles soft taste; full-text search handles literal tokens; rerank decides the final ordering.

### Recall-safe filtered vector search

```sql
SET LOCAL hnsw.iterative_scan = 'relaxed_order';

SELECT id, name
FROM pellier.product_catalog
WHERE category = 'shirts' AND price <= 100
ORDER BY embedding <=> $1::vector
LIMIT 5;
```

This is the production conversation you started in Act I: filters can reduce recall if the index stops too early, so pgvector tuning matters once the corpus grows.

---

## Quick start

### Your URLs

| Surface | URL |
|---|---|
| **Boutique** | `https://<your-cloudfront>/ports/8000/` |
| **Atelier** | `https://<your-cloudfront>/ports/8000/atelier` |
| **Code Editor** | Workshop Studio Code Editor tab |

Find your CloudFront domain in Workshop Studio **Event Outputs**.

### Terminal commands

```bash
start-backend                         # Restart uvicorn with reload
rebuild-frontend                      # Build the SPA and restart app serving
psql                                  # Connect to Aurora PostgreSQL
python3 scripts/check_model_access.py # Verify Bedrock model access
```

Python changes are picked up by uvicorn reload. Use `rebuild-frontend` only after editing `pellier/frontend/src/`.

### Project layout

```text
pellier/
├── backend/           # FastAPI + Strands agents
│   ├── agents/        # one specialist module per role
│   ├── services/      # tools, search, embeddings, AgentCore, policy hooks
│   ├── routes/        # API endpoints
│   ├── skills/        # SKILL.md prompt overlays
│   └── app.py         # FastAPI app entry point
├── frontend/          # React + Vite + Tailwind
│   ├── src/
│   └── dist/
└── config/            # MCP server config

solutions/             # drop-in reference files
scripts/               # bootstrap, migrations, seed, utility scripts
data/                  # product catalog CSV and seed data
```

### Build exercise workflow

1. Read the `floor_check` challenge page.
2. Open `pellier/backend/services/agent_tools.py`.
3. Replace the stub between the challenge markers.
4. Save; uvicorn reloads.
5. Verify in Atelier and replay Marco's warehouse turn in Boutique.

Short on time:

```bash
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
   pellier/backend/services/agent_tools.py
```

:::alert{type="info" header="See also"}
[When things misbehave](/90-appendix/02-when-things-misbehave/) for the runbook, and [What this maps to in your stack](/90-appendix/03-your-stack/) for industry and service mapping.
:::
