---
title: Module 3 · Evaluate
weight: 40
---

**Time budget: 20 minutes**
**Surfaces: Performance → Evaluations**

The build is done. Module 3 is where you read what the system tells you about itself — and where you try one stretch experiment that lets you feel the difference between a Level 400 decision and a Level 200 guess.

---

## Part 1 · Performance deep-dive (6 minutes, solo)

Open `/atelier/performance` in the Atelier.

You're looking at per-agent latency bars for the session data the Atelier has logged. Because every agent runs on its own model at its own temperature, the bars vary by an order of magnitude:

| Agent | Model | p50 warm |
|---|---|---|
| Style Advisor | Sonnet 4.6 · 0.4 | ~1200–1400 ms |
| Curator | Sonnet 4.6 · 0.4 | ~1300–1500 ms |
| Value Analyst | Haiku 4.5 · 0.1 | ~140–180 ms |
| **Stock Keeper** (yours) | Haiku 4.5 · 0.0 | ~150–200 ms |
| Experience Guide (yours) | Sonnet 4.6 · 0.2 | ~900–1100 ms |
| Dispatcher | *(no LLM)* | 60–120 ms |

Notice the Dispatcher is **fastest** — it's pure pattern matching, no model call. That's why Pattern III is the active storefront pattern: classification wants determinism and speed, not capability.

### Why this matters in production

Sonnet costs more per token and runs ~10× slower than Haiku. If Value Analyst ran on Sonnet, every price question would feel slow and rack up cost for no added quality (the answer is a number). If Style Advisor ran on Haiku, the editorial voice would flatten. The system makes a different trade for each agent based on what that agent's job actually is.

### The Search Strategy comparison card

Scroll down on `/atelier/performance`. Below the pgvector index card you'll find **Search strategy comparison · Anna's anchor capability**. This card runs Anna's three retrieval pipelines — vector only, hybrid (RRF), hybrid + rerank — against the live catalog.

Type a query in the input. Try Anna's pill 4 — *"wrap-ready gifts with no extra effort"*. Click **Run on Aurora**. The card refreshes with measured latency per pipeline + the actual top-5 product names per row.

Read the recall vs latency vs cost columns:

- **vector only**: ~74% recall@5, ~340 ms, $0.18/1k queries
- **hybrid (RRF)**: ~86% recall@5, ~425 ms, $0.18/1k queries
- **hybrid + rerank**: ~94% recall@5, ~720 ms, $1.18/1k queries

**Recall@5 jumps 20 points; p50 doubles; cost goes 6×.** The card lets you decide. There's no universally right answer — pick per query class. Anna's editorial-with-constraints queries earn the rerank cost; Marco's clean product-mention queries don't.

The "Postgres FTS gotcha" callout under the table flags the lesson behind `_build_or_tsquery`: **`plainto_tsquery` AND-joins all stems**, so a 6-stem conversational query matches zero products. Worth committing to memory before your first Postgres-FTS production app.

### Theo's write-path numbers

Switch to **Theo** in the persona dropdown. Send the chipped-ceramics turn (or re-send if you ran it in Module 2). Then run from psql:

```sql
SELECT audit_id, tool, latency_ms,
       jsonb_pretty(args) AS args
  FROM tool_audit
 WHERE tool = 'process_return'
 ORDER BY audit_id DESC
 LIMIT 1;
```

The `latency_ms` column is the wall-clock measured between `BeforeToolCallEvent` (placeholder INSERT) and `AfterToolCallEvent` (UPDATE with result). Ours typically lands at ~180–250 ms — Sonnet 4.6 at 0.2 plus a single 3-statement transaction. **The same psql query replays Theo's whole turn from one row.** That's the third capability surfacing as a measurement, not just a claim.

---

## Part 2 · Evaluations (6 minutes, solo)

Open `/atelier/evaluations`.

Three evaluation scorecards ship. Each one picks a subset of agents and runs a test suite against them:

- **Routing correctness** — does the Dispatcher route intent to the right specialist? (Tested across 50 varied queries; current pass rate shown live.)
- **Retrieval relevance** — does `find_pieces` return products whose embeddings make sense? (Tested against hand-labeled ground truth.)
- **Voice discipline** — does each agent honor its output rules? (Checks for markdown tables, emojis, forbidden words in responses.)

Read through each scorecard's pass/fail breakdown. **The evaluations that cover Stock Keeper + Experience Guide started life red** when you opened the lab. After C1–C5 they should be green (or close to it — if a case is flaky, the Atelier will tell you which one).

### Why this matters

In a production agent stack, behavior drift is inevitable — model updates, prompt tweaks, new tools. Evaluations are how you catch regressions before they ship. The scorecard pattern you see here isn't bespoke; it's the same shape you'd wire against your own stack.

---

## Part 3 · Optional stretch — try Opus on Style Advisor (5 min)

**Only if you're ahead.** This is the decision framework every team makes: *is the most capable model always right?*

Open `pellier/backend/agents/search_agent.py`. Swap the model:

```python
model_id=settings.BEDROCK_OPUS_MODEL,  # was BEDROCK_SONNET_MODEL
temperature=0.4,                       # same
```

Save. Uvicorn reloads. Click Marco's Turn 1 pill: *"What linen do you have for 10 days in Goa?"*

Now open `/atelier/performance`. Style Advisor's p50 bar just doubled. Read the response carefully in the Boutique. Did the quality jump match the latency + cost jump? Probably not — Opus's extra capability doesn't show up on a 10-item semantic-search-plus-prose task. **This is the Level 400 decision point**: the most capable model is rarely the right one. You pick it for the jobs that actually need it (long-form reasoning, complex multi-step planning).

**Swap back to Sonnet when you're done.**

---

## Part 4 · Capstone — Marco's full journey (5 minutes, whole class)

Click through the 5 Marco capstone pills in order. The presenter narrates each turn's agent / tool / model live.

| Turn | Pill | Listen for |
|---|---|---|
| 1 | "What pairs with the Ecru overshirt?" | Curator on Sonnet, `the-packing-list` loaded, `style_match` |
| 2 | "What's the cheapest piece that goes with it?" | Value Analyst on Haiku, `price_intelligence`, sub-200ms |
| 3 | "Is it in stock at Brooklyn?" | **Stock Keeper on Haiku 0.0 — the agent you wrote**, `floor_check` |
| 4 | "What's the return window?" | **Experience Guide on Sonnet — the agent you wrote**, `returns_and_care` |
| 5 | "Show me one more linen piece under $100." | Style Advisor on Sonnet, `find_pieces` |

Watch the Atelier's `/atelier/performance` bars light up per turn. Sonnet bars at ~1200 ms. Haiku bars at ~150 ms. **Order of magnitude.**

This is what "agentic composition" looks like in practice. Five specialists, three models, two temperatures, one shopper — no one specialist doing anything it doesn't need to do. You built two of them.

---

## Q&A (5 min)

Flag a question. Compare notes. Tell us what broke.

Next: [Wrap-up](99-wrap-up.en.md)
