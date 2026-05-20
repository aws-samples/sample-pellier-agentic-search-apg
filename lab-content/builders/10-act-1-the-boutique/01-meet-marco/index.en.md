---
title: "Observe · Meet Marco"
weight: 10
---

:::alert{type="info"}
**Time:** ~6 min  ·  **Page:** 1 of 3 in Act I  ·  **Exercises on this page:** 0

Click Marco's five hero pills in order. Three land cleanly. **Turn 4
breaks** — that's the gap you'll close in Exercise 1 on the next page.
:::

**You'll learn to:**

1. Recognize the **anatomy of a Pellier specialist** — model,
   instructions, skills, tools, state, telemetry — by watching one
   answer customer turns.
2. Read the **trace chips** (specialist · model · tool) under each
   reply and connect them back to the orchestration layer.
3. Spot **the seam between long-term taste memory** (Marco's
   profile in Aurora pgvector) and **session-scoped STM** (the
   turn-by-turn record you'll verify in Act II).
4. Identify **why Turn 4 fails gracefully** instead of hallucinating
   bins — and what wiring is needed to close the gap.

For the 60-minute session, treat this page as a checklist: click the pills,
confirm the routing/tool pattern, then move quickly to coding in
[Wire `floor_check`](../02-wire-floor-check/).

Marco is a returning customer packing **linen for a long stretch in
Goa**. The agent recognizes him — taste from prior visits lives in
**long-term memory** (warm neutrals, natural fibers, travel-ready
pieces), which is separate from the turn-by-turn STM you verify in Act II.

::::expand{header="Anatomy of a Pellier agent (read once, reuse all session)"}

Before you wire a function, name the thing it plugs into. A Pellier
specialist agent is **not** just a prompt:

- **Model** — Opus for editorial voice, Haiku for terse reports.
- **Instructions** — system prompt; defines job, tone, boundaries.
- **Skills** — markdown playbooks loaded per turn (e.g. `the-packing-list`
  for Marco, `the-gift-table` for Anna).
- **Tools** — Python functions decorated with `@tool`. Permission to
  read Aurora, compare products, check inventory, or file a return.
- **State** — memory + request context.
- **Telemetry** — the trace you see in *Under the hood* and the Atelier.

The build on the next page is small because the agent already exists.
You're wiring one missing tool body into that anatomy.

::::

## 1 · Open Marco's chat drawer

In the Boutique (port **8000**), confirm **Marco** is selected in the
header. Open the chat drawer with **Ask Pellier** or `⌘K` / `Ctrl+K`.
You'll see five suggestion pills. **Click them in order.**

## 2 · Turn 1 — *"What linen do you have for 10 days in Goa?"*

**Style Advisor** · Opus 4.6 · `find_pieces`

Editorial copy + a three-card grid: **Pellier Linen Shirt in ecru**,
**Linen Drawstring Trousers in oat**, **Italian Linen Camp Shirt in
indigo**. Cosine search + rerank, layered on Marco's profile.

Trace chips align with `find_pieces` latency and tool evidence.

## 3 · Turn 2 — *"What would go with the Hadley shirt?"*

*(Hadley = the storefront name for the Pellier Linen Shirt in ecru.)*

**Curator** + `the-packing-list` skill · Opus 4.6 · `style_match`

The curator returns companions — drawstring trousers, washed cotton
overshirt, weekender. Telemetry reads `style_match` (product-to-product
pgvector similarity anchored on the Hadley embedding).

## 4 · Turn 3 — *"What's the price range for linen shirts?"*

**Value Analyst** · Haiku 4.5 · `price_intelligence`

A numeric band with median — fast, deterministic SQL aggregate. Lands
near *"$88 to $285, median $148"*.

## 5 · Turn 4 — *"Is the Hadley shirt at the Brooklyn warehouse?"*

This is **the Builder's Session seam**. You'll see something like:

> *I can help with style and recommendations, but I don't have
> real-time stock visibility for individual warehouses yet…*

The dispatcher recognized stock intent and routed correctly, but
`floor_check` is still stubbed — so Stock Keeper returns this
graceful, voice-matched non-answer instead of hallucinating bins.

That's what you **wire closed** next.

::::expand{header="Confirm the warehouse data is real (optional)"}

```bash
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
```

Expect ~120 rows — three warehouses (`BK-01`, `ATX-02`, `PDX-01`) ×
40 products. **The gap is tooling, not empty tables.**

::::

## 6 · Turn 5 — *"What pairs with the Ecru overshirt?"*

**Curator** · `the-packing-list` · Opus 4.6 · `style_match`

Editorial pairing fires cleanly — proof the system still sings after
Turn 4's gap. Turn 5 works because it routes through `style_match`,
not `floor_check`.

## What you noticed

| | |
| --- | --- |
| ✓ Turn 1 | `find_pieces` · Style Advisor |
| ✓ Turn 2 | `style_match` · Curator + packing-list skill |
| ✓ Turn 3 | `price_intelligence` · Value Analyst |
| ✗ **Turn 4** | **`floor_check` stub** — graceful non-answer (your build) |
| ✓ Turn 5 | `style_match` · Curator |

## What you've learned

- A Pellier specialist is **six things, not one prompt**: model,
  instructions, skills, tools, state, telemetry. Each is a separate
  lever.
- The orchestrator already **routed Turn 4 correctly** to Stock
  Keeper — the failure is at the *tool body*, not the dispatcher.
- A graceful non-answer is a design choice. Stub tools should refuse
  to hallucinate; that's why Marco saw a voice-matched apology, not
  invented bin numbers.
- Turn 5 still works because it routes through `style_match`, not
  `floor_check` — proof that the rest of the agent is healthy and
  one wiring exercise will close the gap.

:::alert{type="success" header="Build next — Exercise 1"}
[Wire `floor_check` →](../02-wire-floor-check/)
:::
