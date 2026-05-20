---
title: "Act I · The Boutique"
weight: 10
---

*Build + prove. ~30 minutes — the only coding block of the session.*

:::alert{type="info" header="Act I · The Boutique"}
**Time:** ~30 min  ·  **Exercises:** 2 (one tool body, one skill rule)  ·  **Code surface:** `pellier/backend/services/agent_tools.py` + `skills/the-gift-table/SKILL.md`

This is where your hands get on the keys. Five Strands specialists are
already wired into a single FastAPI process on `:8000`. **One tool
body — `floor_check` — is left for you. One skill rule for Anna is
left unfinished.** Everything else is production-shaped: the same
orchestrator, the same Aurora pgvector index, the same Cohere reranker
your laptop would run.

By the end of the act, **Marco's Turn 4 lands against live warehouse
data** and **Anna's `the-gift-table` skill speaks the way you tell it to.**
:::

The Boutique is the storefront a shopper sees. Behind the cream paper
and the editorial photograph, five specialists are listening, a
1024-dim Cohere v4 vector index is warm, and a tool registry is
waiting to be asked.

Marco walks in first. Three of his five turns land cleanly; **Turn 4
breaks** because the warehouse tool he needs is a stub. You wire it.
Then **Anna** asks something messier — and you measure whether
hybrid + rerank earned its cost while editing the skill that shapes
her answer.

---

## The arc · ~30 minutes

```text
   Observe         Build              Measure
   ~6 min          ~15 min            ~9 min
   meet Marco      wire floor_check   prove rerank
   (5 pills)                          + edit Anna's skill
                   ▲                  ▲
                   Exercise 1         Exercise 2
```

---

## Learning objectives

By the end of Act I you will be able to:

1. **Read the anatomy of a Strands specialist** — model, instructions,
   skills, tools, state, telemetry — and know which lever to pull when
   an answer goes wrong.
2. **Wire a Strands `@tool` body** that bridges agent intent to a real
   Aurora source of truth, using `BusinessLogic.floor_check()` against
   `pellier.warehouse_inventory`.
3. **Decide per-query-class** whether `vector` vs `hybrid (RRF)` vs
   `hybrid + rerank` earns its latency, using the Atelier's three-way
   comparison against the live catalog.
4. **Edit one skill rule and prove it landed** with SQL against
   `pellier.tool_uses` — no fixture, no restart, no guesswork.

---

## Core concepts ladder

A taste of the technical territory underneath the build, in the order
you'll meet it:

| Concept | What you'll see |
|---|---|
| **Strands SDK anatomy** | `Agent`, `@tool`, system instructions, skills as markdown playbooks, telemetry on every turn |
| **Aurora pgvector retrieval** | HNSW index, 1024-dim Cohere Embed v4, cosine similarity, sub-100 ms vector recall |
| **Hybrid retrieval with RRF** | pgvector cosine + Postgres FTS (`tsvector` + GIN + `ts_rank_cd`), merged via Reciprocal Rank Fusion *without* normalizing raw scores |
| **Cohere Rerank v3.5** | Cross-encoder reordering of the merged candidate pool for the exact user phrasing |
| **Production tuning knobs** | `hnsw.iterative_scan` for filtered recall, `halfvec` for storage footprint, `binary_quantize(...)` for compact coarse retrieval — named, not exercised |

---

## What you'll do

| Page | Activity | Time | Exercise |
|---|---|---|---|
| 01 · [Observe — Meet Marco](01-meet-marco/) | Click 5 hero pills; spot the broken one | ~6 min | — |
| 02 · [Build — Wire `floor_check`](02-wire-floor-check/) | Replace one stub body so Stock Keeper reads Aurora | ~15 min | **Exercise 1** |
| 03 · [Measure — Prove rerank earns its cost](03-prove-rerank/) | Compare 3 retrieval strategies; edit Anna's skill | ~9 min | **Exercise 2** |

---

:::alert{type="warning" header="Two exercises in this act — don't miss either"}

**Exercise 1 · `floor_check` tool body**  *(in 02-wire-floor-check)*
Replace the stub between the `START` / `END` markers in
`pellier/backend/services/agent_tools.py`. Marco's Turn 4 lands
against live warehouse data after you save.
**⏩ Out of time?** A one-line `cp` from `solutions/closing-marcos-gap/`
swaps in the reference implementation — the act still completes.

**Exercise 2 · Anna's `the-gift-table` skill**  *(in 03-prove-rerank)*
Edit one guidance line under **Voice and curation rules** in
`skills/the-gift-table/SKILL.md`. Run Anna's anchor query, then prove
with a `SELECT` against `pellier.tool_uses` that the live retrieval
path picked up your edit. No fixtures, no restart.

:::

---

## What you'll have shipped

```text
   12/12 tools shipped       → floor_check has a sage "Shipped" pill
   Marco Turn 4 lands         → Brooklyn (BK-01), real quantity, real ship window
   Anna's anchor measured     → vector vs hybrid vs hybrid+rerank, side by side
   one skill rule, live       → SELECT proves it on the latest tool_uses row
```

::::expand{header="Who's on the floor (the cast)"}

If you need a quick reminder of which specialist answers what, the
Appendix has a one-page reference: [The Cast](/90-appendix/01-the-cast/).

::::

:::alert{type="success" header="Begin Act I"}
[Observe · Meet Marco →](01-meet-marco/)
:::
