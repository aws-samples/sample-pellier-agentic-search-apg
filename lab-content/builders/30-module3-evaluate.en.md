---
title: Module 3 · Evaluate
weight: 40
---

**Time budget: 10 minutes**
**Surfaces: Performance → Evaluations → Experience Guide code**

Build is done. 10 minutes to read what the system tells you about itself.

## Part 1 · Performance (3 min, solo)

Open `/atelier/performance`.

| Agent | Model | p50 warm |
|---|---|---|
| Style Advisor | Sonnet 4.6 · 0.4 | ~1200–1400 ms |
| Curator | Sonnet 4.6 · 0.4 | ~1300–1500 ms |
| Value Analyst | Haiku 4.5 · 0.1 | ~140–180 ms |
| **Stock Keeper** (yours) | Haiku 4.5 · 0.0 | ~150–200 ms |
| Experience Guide (pre-applied) | Sonnet 4.6 · 0.2 | ~900–1100 ms |
| Dispatcher | *(no LLM)* | 60–120 ms |

**Dispatcher is fastest** because it's pure pattern matching — no model call. That's why Pattern III is the active storefront routing: classification wants determinism and speed.

**Sonnet ~10× slower than Haiku.** If Value Analyst ran on Sonnet, every price question would feel slow for no added quality. If Style Advisor ran on Haiku, the voice would flatten. Different trades per agent.

### Bonus 90 seconds — Search Strategy comparison

Scroll down to **Search strategy comparison · Anna's anchor capability**. Type *"wrap-ready gifts with no extra effort"* in the input, click **Run on Aurora**. The card runs all three pipelines (vector / hybrid / hybrid+rerank) against the live catalog and shows the top-5 product names per row. **Watch the ranking shift between rows** — that's the rerank lift made visible.

The columns name the trade: **+20 points recall@5, ~2× p50, 6× cost.** No universally right answer; pick per query class.

---

## Part 2 · Walk through Experience Guide (5 min, instructor-led, no typing)

In Code Editor, open `blaize-bazaar/backend/agents/customer_support_agent.py`.

This is the agent you *would* have built in the 2-hour Workshop. In the Builder's Session it was pre-applied — but it's readable code, and the chaining pattern is worth 5 minutes.

Presenter walks through:

1. **Model choice** — Sonnet 4.6 at 0.2. Why? Empathy + policy. "Your return arrived and we're sorry" needs warmth; "30 days, prepaid label" is policy that doesn't wander.
2. **Chaining in the system prompt** — the interesting part. When a customer says *"can I return my Camp Shirt?"*, the agent first calls `find_pieces` to identify the product's category, **then** calls `returns_and_care` with that category. Two tool calls in sequence, orchestrated by the system prompt.
3. **Open `/atelier/sessions/theo-ceramics-return`** — Theo's session that was broken in the Workshop format (Experience Guide stub) but resolves in the Builder's Session because the agent is pre-applied. Read the brief.

---

## Part 3 · Capstone (5 min, whole class)

Click through Marco's **5 capstone pills** in order. Presenter narrates each turn's agent / tool / model:

| Turn | Pill | Narrate |
|---|---|---|
| 1 | "What pairs with the Ecru overshirt?" | Curator on Sonnet, `the-packing-list` loaded, `style_match` |
| 2 | "What's the cheapest piece that goes with it?" | Value Analyst on Haiku, `price_intelligence`, sub-200ms |
| 3 | "Is it in stock at Brooklyn?" | **Stock Keeper on Haiku 0.0 — the agent you wrote**, `floor_check` |
| 4 | "What's the return window?" | Experience Guide on Sonnet (pre-applied), `returns_and_care` |
| 5 | "Show me one more linen piece under $100." | Style Advisor on Sonnet, `find_pieces` |

Atelier Performance page lights up per turn. Sonnet bars at ~1200 ms. Haiku bars at ~150 ms. Order of magnitude. Five specialists, three models, two temperatures, one shopper — no one doing anything it doesn't need to do.

You built one of them.

Next: [Wrap-up](99-wrap-up.en.md)
