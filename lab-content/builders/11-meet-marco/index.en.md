---
title: "Part I · Observe — Meet Marco"
weight: 11
---

:::alert{type="info"}
**Part I of III · Marco's arc · Sublab 11.** About six minutes. Click five
pills, watch three land cleanly, see Turn 4 miss — then you'll fix it in
sublab 12.*
:::

## Meet Marco

Marco is a returning customer planning a long weekend in Lisbon. The
agent recognizes him because his taste from prior visits is in
long-term memory — linen, leather, terracotta, soft tailoring,
nothing fussy.

In the Boutique tab (port 8000), open the chat drawer (bottom-right
**Ask Pellier** pill, or press `⌘K` / `Ctrl+K`). The drawer slides
in from the right. The agent greets Marco by name and offers a short
list of suggested prompts — five pills, drawn from a curation that
Pellier maintains for returning shoppers.

Click them in order. Each one is a turn in Marco's afternoon.

---

## Turn 1 — *"Linen pieces that travel well."*

Click the first pill.

The agent calls `find_pieces` (semantic vector search over the
catalog), reranks the candidates, and answers in a few sentences. A
small grid of three pieces lands under the answer: the Linen Camp
Shirt, the Wide-Leg Trouser, the Chambray Shirt-Jacket.

Look at the trace chips just under each card — small mono pills that
read `find_pieces · 240 ms`, `palette.match · 0.92`, `memory.recall`.
Those are not decoration. They are the agent citing the tools it
used, and they appear identically in the Atelier.

::::expand{header="Why it works"}

`find_pieces` runs cosine similarity against the 1024-dim Cohere
Embed v4 column on `pellier.product_catalog`, with an HNSW index.
The top thirty hits get reranked by Cohere Rerank v3.5, then the
top five are returned. Memory recall layers Marco's persona on top.

The Atelier's *Architecture · Tools* page explains the full pipeline.
::::

---

## Turn 2 — *"What pairs with the Camp Shirt?"*

Click the second pill.

This time the orchestrator routes to the **Recommendation** agent, a
specialist that knows pairing. It calls `pairing.score`, weighs
fabric weight, palette, and occasion, and returns three pieces that
go with the Camp Shirt — the Wide-Leg Trouser tops the list.

The trace chips now read `pairing.score · 0.88`, `inventory.live`.
Note `inventory.live` — the agent confirmed stock before recommending.

---

## Turn 3 — *"Show me what just arrived."*

Click the third pill.

The agent surfaces a small "this week" edit — three pieces that
landed in the catalog this morning. The trace cites `inventory.live`
and `trend.signal`. A small "**Bestseller**" badge shows on the
Cashmere-Blend Cardigan card.

So far the agent looks like it can do anything. Let's find the
seam.

---

## Turn 4 — *"Is the Hadley shirt at the Brooklyn warehouse?"*

Click the fourth pill.

The agent pauses — and answers something like:

> *I can't see the warehouse floor from here. I'd ask Stock Keeper,
> but they aren't on shift yet. Would you like me to surface what's
> in stock from the boutique catalog instead?*

That's the gap. There **is** a Stock Keeper agent — you'll see it
listed in the Atelier in a moment — wired up with a finished system
prompt, ready to answer warehouse questions. The orchestrator
already routes turn 4 to it. Stock Keeper already calls
`floor_check`. The seam is one layer deeper: the *body* of
`floor_check` is stubbed, so when Stock Keeper invokes the tool, it
gets back a graceful `"floor_check is in stub state"` error and
relays that as the polite non-answer above.

This is the only thing wrong with the system right now. You'll fix
it in sublab 12.

::::expand{header="Confirm the agent isn't hiding the warehouse"}

Open a terminal in Code Editor and run:

```bash
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
```

You'll see ~120 rows — three warehouses (`BK-01`, `ATX-02`, `PDX-01`)
each holding a slice of the 40-product catalog. The data exists.
Stock Keeper's `floor_check` tool just isn't connected to it yet.

```bash
psql -c "\
  SELECT w.id, w.display_name, count(*) AS items, sum(wi.quantity) AS units \
    FROM pellier.warehouses w \
    JOIN pellier.warehouse_inventory wi ON wi.warehouse_id = w.id \
   GROUP BY w.id, w.display_name \
   ORDER BY w.id;"
```

That's the table you'll teach the agent to read.

::::

---

## Turn 5 — *"Hold those two pieces for me."*

Click the fifth pill.

This one already works. The Experience Guide agent runs `cart.holds`
and writes a row into Aurora. Marco's bag now has the two pieces
the Recommendation agent surfaced in turn 2. The trace chips read
`cart.holds`, `memory.write` — that's the agent persisting the hold
into long-term memory so the next visit picks up where this one
left off.

---

## A quick visit to the Atelier

Switch to your Atelier tab. In the left sidebar, under **OBSERVE**,
click **Sessions**. The five turns Marco just took are listed in
order, each with timing, agent, tools called, and the full
reasoning trace. Click any turn to drill in.

This is the same agent. Different lens.

You'll tour the Atelier in Part III (routing patterns).

---

## What you noticed

| | |
| --- | --- |
| ✓ Turn 1 | `find_pieces` works |
| ✓ Turn 2 | `pairing.score` works |
| ✓ Turn 3 | `inventory.live` + `trend.signal` work |
| ✗ Turn 4 | Stock Keeper not wired — agent falls back gracefully |
| ✓ Turn 5 | `cart.holds` works |

Four of five. One gap. That gap is the only code exercise in Part I.

:::alert{type="success" header="Part I · Build next"}
[Part I · Wire `floor_check` →](/12-wire-floor-check/)
:::
