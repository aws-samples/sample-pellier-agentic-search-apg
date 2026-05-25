---
title: "The Cast · agents, tools, skills, personas"
weight: 10
---

*A one-page reference. Skim before the session, return mid-flight when
you can't remember which specialist owns which tool.*

Pellier is **five specialists, twelve tools, three skills, and three
personas.** The signed-out state is the editorial baseline — a hero
state, not a fourth persona. The names are intentional — they're not
a generic "inventory agent" or "pricing agent" — and the cast list
below is the canonical mapping.

---

## The five specialists

Each specialist is a Strands `Agent` with its own model, temperature,
system prompt, and tool set. The dispatcher reads intent and routes
one specialist per turn.

| Specialist | Model | Temp | Owns | Answers when… |
|---|---|---|---|---|
| **Style Advisor** | Opus 4.6 | 0.4 | `find_pieces`, `explore_collection`, `side_by_side`, `style_match` | The shopper describes what they want in their own words ("linen for Goa"). Editorial copy + product cards. |
| **Curator** | Opus 4.6 | 0.4 | `find_pieces_hybrid`, `whats_trending`, `side_by_side`, `explore_collection` | The query needs pairing, palette, occasion, or editorial framing. Loads a persona-scoped skill. |
| **Value Analyst** | Haiku 4.5 | 0.1 | `price_intelligence`, `explore_collection`, `find_pieces` | The shopper asks about price, range, or value. Fast, deterministic. |
| **Stock Keeper** | Haiku 4.5 | 0.0 | `floor_check`, `restock_shelf`, `running_low` | The shopper asks about warehouses, stock, restocks. Terse warehouse answers. |
| **Experience Guide** | Opus 4.6 | 0.2 | `returns_and_care`, `find_pieces`, `process_return` | Returns, care, post-purchase. Opus for tone; steady temperature. |

::::expand{header="Why per-agent model + temperature is an architectural choice"}

The Curator's editorial prose earns Opus. Stock Keeper's terse
warehouse answers run on Haiku at temperature 0 — there's no creative
range to add to "12 in Brooklyn, ships next-day." Value Analyst is
Haiku at 0.1 because price language tolerates almost no creativity.
Experience Guide is Opus at 0.2 because a return needs warmth without
drift.

`pellier/backend/config.py` reads these Bedrock inference profiles:

- `BEDROCK_OPUS_MODEL=global.anthropic.claude-opus-4-6-v1`
- `BEDROCK_HAIKU_MODEL=global.anthropic.claude-haiku-4-5-20251001-v1:0`

The legacy `BEDROCK_SONNET_MODEL` env name still resolves to Opus by
default — you may see it in older code paths. **The model names will
shift over time; the temperature-vs-task pattern is the architectural
choice that survives.**

::::

---

## The twelve tools

Tools are Python functions decorated with `@tool` in
`pellier/backend/services/agent_tools.py`. The orchestrator
discovers them via cosine similarity over their docstrings — the
same pgvector primitive that powers product search, applied to
capabilities.

| Tool | Owner | Reads | What it does |
|---|---|---|---|
| `find_pieces` | Style Advisor | `pellier.product_catalog` | pgvector cosine + Cohere Rerank over the catalog |
| `find_pieces_hybrid` | Curator | catalog + `tsvector` | Hybrid: pgvector + Postgres FTS, RRF merge, then Rerank |
| `style_match` | Style Advisor | catalog | Product-to-product pgvector similarity from one anchor |
| `whats_trending` | Curator | catalog + sales | Returns recent + popular pieces, persona-aware |
| `price_intelligence` | Value Analyst | catalog | Min/max/median + percentile context |
| `explore_collection` | Style Advisor, Curator, Value Analyst | catalog | Browse a category or theme |
| `side_by_side` | Style Advisor, Curator | catalog | Compare two pieces directly |
| `floor_check` | Stock Keeper | `pellier.warehouse_inventory` | Inventory across three warehouses (**the Builder's exercise**) |
| `restock_shelf` | Stock Keeper | warehouse | Top-up helper for low-inventory rows |
| `running_low` | Stock Keeper | warehouse | Aggregate alert: which SKUs need attention |
| `returns_and_care` | Experience Guide | care policy | Care + return policy lookup |
| `process_return` | Experience Guide | returns | Files a return for a customer |

There's also an internal `cart.holds` capability used for cart
bookkeeping. It is not a customer-callable tool, so it doesn't appear
in the discovery registry.

---

## The three skills

Skills are persona-scoped markdown playbooks loaded by the
`SkillRouter` per turn. They shape **voice and handling** without
changing product selection.

| Skill | Persona | Loads when… | Lives in |
|---|---|---|---|
| `the-packing-list` | Marco | The query is about travel, layering, or natural fibers | `skills/the-packing-list/` |
| `the-gift-table` | Anna | The query is a gift, milestone, or wrap-ready ask | `skills/the-gift-table/` |
| `the-makers-shelf` | Theo | The query is about ceramics, ritual, or slow craft | `skills/the-makers-shelf/` |

Skills are **read-only context the Curator pulls in** — not separate
agents. They're how the same Curator delivers a voice that fits Marco
versus Anna versus Theo without you maintaining three Curators.

---

## The three personas

| Persona | Profile | Signature piece | Anchor query |
|---|---|---|---|
| **Marco** | Natural fibers, travel, linen | Italian Linen Camp Shirt | *"What linen do you have for 10 days in Goa?"* |
| **Anna** | Gifts, milestones, candles | Beeswax Taper Candles | *"A thoughtful gift for someone who loves morning rituals"* |
| **Theo** | Slow craft, ceramics, ritual | Stoneware Pour-Over Set | *"Something to slow my morning ritual"* |

The **signed-out state** is the editorial baseline — a 10-piece grid
anchored by the Nocturne Leather Weekender, no prior context, no
profile embedding. It is the hero state, not a fourth persona.

Each persona ships with **10 products** carrying real Cohere Embed
v4 1024-dim embeddings — 40 products total in
`pellier.product_catalog` (10 signed-out baseline + 10 per persona),
HNSW-indexed. The same column shape and HNSW index work unchanged on
**Amazon RDS for PostgreSQL** — pgvector behaves identically on both
engines.

---

## How they fit together

```text
Customer turn (Marco / Anna / Theo, or signed-out baseline)
        ↓
   Dispatcher (services/chat.py — keyword + intent classification)
        ↓
   One specialist (Style Advisor / Curator / Value Analyst / Stock Keeper / Experience Guide)
        ↓ (Curator path also loads one of the three skills)
   One or more @tool calls (cosine-discovered from the registry)
        ↓
   pgvector retrieve (Aurora or RDS for PostgreSQL) + Postgres FTS + Cohere Rerank
        ↓
   Claude Opus / Haiku grounds the reply on those rows
        ↓
   Editorial reply + product cards + trace chips
```

Same five atoms in every turn. The personas reshape what the agent
*sees*; the dispatcher decides who *answers*; the skill decides
*how it sounds*; the tool decides *what's true*.
