---
title: Module 1 · Observe
weight: 20
---

**Time budget: 20 minutes**
**Surfaces: Sessions → Observatory**

Module 1 is orientation. Before you change anything, you observe what Pellier already does — which specialists the Dispatcher routes to, which tools each agent reaches for, what the model mix looks like, and where the gap is that you'll be closing.

---

## Part 1 · Marco's opening demo (5 minutes, whole class)

Open the Boutique tab. Make sure the **Marco** persona is active in the header.

**Click the four Marco pills in order.** The presenter will narrate each beat live — you're driving the clicks.

| Click | Listen for |
|---|---|
| Pill 1 — "What linen do you have for 10 days in Goa?" | **Style Advisor on Sonnet 4.6 at 0.4.** Editorial voice. 3 pieces. ~1.3 seconds. |
| Pill 2 — "What would go with the Pellier shirt?" | **Curator on Sonnet 4.6 at 0.4, with `the-packing-list` skill loaded.** Voice mentions packability. ~1.4 seconds. |
| Pill 3 — "What's the price range for linen shirts?" | **Value Analyst on Haiku 4.5 at 0.1.** No narrative, just a number. Sub-200ms. |
| Pill 4 — "Is the Pellier shirt at the Brooklyn warehouse?" | **Stock Keeper — in stub state.** Voice-matched non-answer. That's your build. |

Marco closes: *"I'll come back when I'm ready to commit."*

Flip to the Atelier tab. In the sidebar, click **Sessions**, then `marco-opening-demo`. The full 4-turn replay appears — chat transcript, per-turn telemetry, curator's brief. Turn 4 shows a **routing fall-through** panel (telemetry index 11) linking to "Open the Stock Keeper build." That panel is honest about the gap.

---

## Part 2 · Read the model-mix sidebar (2 minutes, solo)

The most important 2 minutes of the day. Open:

`lab-content/shared/model-mix-sidebar.en.md`

Read it through once. Come back.

Back? Now open `pellier/backend/config.py` and find the three constants:

```python
BEDROCK_SONNET_MODEL: str = "global.anthropic.claude-sonnet-4-6"
BEDROCK_HAIKU_MODEL:  str = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
BEDROCK_OPUS_MODEL:   str = "global.anthropic.claude-opus-4-7"
```

There's **no `DEFAULT_MODEL`**. Every agent picks its own.

---

## Part 3 · Tour the Atelier (8 minutes, solo)

In the Atelier's left sidebar, work top to bottom. The arc is
*zoom out → zoom in → understand → measure*.

### `/atelier/observatory`
Wide-angle dashboard — your starting point. Look at the **Agent Status** card — five rows, model tags per row, live/idle indicators. Then the **Performance headlines** at the bottom. Note the P50 numbers for Sonnet vs Haiku agents. *This is the system at a glance; everything below explains a piece of what's on this screen.*

### `/atelier/sessions`
The replay store. Seven sessions shipped: 3 Marco (opening / midpoint / capstone), 2 Anna (birthday / housewarming), 2 Theo (pour-over / return). You just watched `marco-opening-demo`. Keep it bookmarked — every later module references specific session turns.

### `/atelier/agents` (under UNDERSTAND)
Five specialist cards. **Stock Keeper has a "Your turn" pill** — that's the build. Note every card's model + temperature badge. No row is normalized.

### `/atelier/tools`
Ten tool cards. Three are in dashed **exercise** treatment: `floor_check`, `restock_shelf`, `running_low`. The discovery card at the bottom surfaces `floor_check` as the top match for *"check stock at the Brooklyn warehouse"* — but tagged "○ Pending implementation."

### `/atelier/routing`
Three routing patterns. **Dispatcher** (Pattern III) is the active one in the Boutique — pattern-matched, deterministic, no LLM call. Agents-as-Tools (Pattern II) and Graph (Pattern I) are documented for reference.

### `/atelier/memory`
STM + LTM orbit. Marco's LTM preferences are visible (minimal, warm tones, linen). This is what makes Turn 1 return Marco-shaped results.

### `/atelier/performance`
Per-agent latency bars. Sonnet agents sit at ~1000-1500 ms. Haiku agents sit at ~100-250 ms. **An order of magnitude apart.** Stock Keeper's bar shows "—" with a "pending" tag.

---

## Part 4 · Swap a model (5 minutes, solo hands-on)

Before you start the real build, a quick experiment to make the model-mix lesson tactile.

Open `pellier/backend/agents/pricing_agent.py`. Find the `build_pricing_agent()` factory:

```python
return Agent(
    model=BedrockModel(
        model_id=settings.BEDROCK_HAIKU_MODEL,  # ← this
        max_tokens=2048,
        temperature=0.1,
    ),
    ...
)
```

**Change `BEDROCK_HAIKU_MODEL` to `BEDROCK_SONNET_MODEL`. Save.** Uvicorn will reload.

Click Marco's Turn 3 pill again in the Boutique: *"What's the price range for linen shirts?"*

Open the Atelier Performance page. Value Analyst's latency bar just jumped from ~150 ms to ~1200 ms. **Almost 10× slower** for a question that wanted a number.

**Now swap it back.** Save. Latency drops back. You've just made the architectural argument for Haiku on a reporting agent tangible — you felt the cost of the wrong choice.

---

## Part 5 · Anna's hybrid pipeline (5 minutes, solo)

Marco's Style Advisor runs on **plain pgvector cosine** — meaning-based search, top 5. That's the workshop's first Aurora capability. The next persona, **Anna**, anchors a different one: **hybrid retrieval with reranking**.

Why? Because Anna's queries aren't clean. She doesn't say "find me a candle"; she says *"something thoughtful that arrives ready to give"* or *"wrap-ready gifts with no extra effort"*. The embedding catches "thoughtful" as a vibe; it doesn't catch "wrap-ready" as a literal lookup against the catalog's product descriptions. **Postgres' BM25 over a tsvector does.**

Anna's Curator runs on `find_pieces_hybrid`:

1. **Vector branch** — pgvector cosine, k=20.
2. **BM25 branch** — `to_tsquery` against a `tsvector` column generated from `name + brand + category + color + tags + description` with weighted contributions. Query is OR-joined from content tokens (see `_build_or_tsquery` in `services/hybrid_search.py`).
3. **RRF merge** — Reciprocal Rank Fusion with k=60 produces a 30-candidate union pool.
4. **Cohere Rerank v3.5** — Bedrock invokes `cohere.rerank-v3-5:0` with the query + 30 documents, returns top 5.

### See it run live

Switch to **Anna** in the persona dropdown. Click her hero pill *"wrap-ready gifts with no extra effort"*. Read the response — Gift Wrapping Kit will be at rank 1, then a tight gift-band of 4 more pieces.

Now flip to `/atelier/performance`. Scroll to the **Search strategy comparison** card. Type the same query in the input and click **Run on Aurora**. The card runs all three strategies — vector only, hybrid (RRF), hybrid + rerank — against the live catalog and shows you the top-5 mix per row. Watch the ranking shift between rows: vector-only puts certain pieces first; hybrid+rerank reorders meaningfully (Cohere reads "no extra effort" and pulls in pieces neither retrieval branch ranked highly).

That's the second-capability teaching moment: **vector finds meaning, BM25 finds literals, Cohere reads intent shape, RRF merges them honestly**.

### The Postgres FTS gotcha

Worth flagging: **Postgres' obvious primitives don't do what their names suggest.** Both `plainto_tsquery` and `websearch_to_tsquery` AND-join every stem for plain-text input. A 6-stem query like *"thoughtful gift for someone who loves morning rituals"* compiles to `'thought' & 'gift' & 'someon' & 'love' & 'morn' & 'ritual'` — and matches **zero** products in a real catalog. The fix is OR-joining content tokens manually before passing to `to_tsquery`. That's what `HybridSearch._build_or_tsquery` does. The Atelier card surfaces this as a teaching callout — one of those gotchas worth knowing about before your first Postgres-FTS production app.

### Why Marco still uses plain `find_pieces`

The workshop deliberately **doesn't** swap Marco onto hybrid. Why?

- Marco's queries are clean — clear product mentions, clear product context. Vector wins them all.
- The 6× cost increase + ~120ms extra latency from rerank doesn't earn its keep on every query.
- The pipeline tradeoff is the architectural lesson: **pick the right tool for the query class**.

---

## What's next

You've observed the whole system. You've felt the model-mix lesson in your hands. You've watched the hybrid pipeline rerank a query in real time. Time to close Marco's gap.

Next: [Module 2 · Understand](20-module2-understand.en.md)

*Cross-links: [Anna's full arc](../shared/anna-arc-overview.en.md) · [Aurora capabilities ladder](../shared/aurora-capabilities-arc.en.md)*
