---
title: "Act I · Observe — Meet Marco"
weight: 11
---

:::alert{type="info"}
**Act I · Build + prove.** About six minutes. As **Marco**, click the
five **Try asking** hero pills **in order** — turns 1–3 land cleanly,
Turn 4 shows the Builder's Session gap, Turn 5 is a pairing beat that
already works. Strings and flows match **`marco-opening-demo`** (turns
1–4) plus the opening turn of **`marco-capstone`** for pill five.
:::

For the 60-minute session, treat this page as a checklist: click the pills,
confirm the routing/tool pattern, then move quickly to coding in lab 12.

## Meet Marco

Marco is a returning customer packing **linen for a long stretch in Goa**. The
agent recognizes him — taste from prior visits lives in **long-term memory**
(warm neutrals, natural fibers, travel-ready pieces).

## Anatomy of a Pellier agent

Before you wire a function, name the thing it plugs into. A Pellier specialist
agent is not just a prompt:

- **Model** — the reasoning and voice engine. Editorial specialists use Opus;
  reporting specialists use Haiku.
- **Instructions** — the system prompt that defines the specialist's job,
  tone, and boundaries.
- **Skills** — markdown playbooks loaded when a query needs domain judgment,
  such as `the-packing-list` for Marco or `the-gift-table` for Anna.
- **Tools** — Python functions decorated with `@tool`. They give the agent
  permission to read Aurora, compare products, check inventory, or file a
  return.
- **State** — memory and request context: who the shopper is, what they asked
  before, and what the current turn is trying to resolve.
- **Telemetry** — the trace you see in Boutique **Under the hood** and in the
  Atelier: which specialist answered, which skill loaded, which tool ran, how
  long it took, and what data came back.

The build exercise on the next page is deliberately small because the
agent already exists. You are wiring one missing tool body into that
anatomy.

In the Boutique (port **8000**), open the chat drawer (**Ask Pellier**, or
`⌘K` / `Ctrl+K`). With **Marco** selected in the header, you'll see five
suggestion pills. **Click them in order** below — each matches
`personaCurations` and the Sessions fixtures exactly.

---

## Turn 1 — *"What linen do you have for 10 days in Goa?"*

**Style Advisor** · **Opus 4.6 · 0.4** · `find_pieces`

You'll get editorial copy and a three-card grid. The fixture cites **Pellier
Linen Shirt in ecru**, **Linen Drawstring Trousers in oat**, and **Italian Linen
Camp Shirt in indigo** — cosine search + rerank, with memory/lived-in tone layered
on Marco's profile.

**Flow (Atelier shorthand):** `Dispatcher → Style Advisor → find_pieces`

Trace chips in the drawer align with **`find_pieces`** latency and tool evidence;
the same hops appear under **Sessions → `marco-opening-demo`**, turn 1.

---

## Turn 2 — *"What would go with the Hadley shirt?"*

*(Hadley is the storefront name for the **Pellier Linen Shirt in ecru**.)*

**Curator** · **`the-packing-list` skill loaded** · **Opus 4.6 · 0.4** · **`style_match`**

The curator answers with companions (drawstring trousers, washed cotton overshirt,
weekender bag in the replay). Telemetry reads **`style_match`** — product-to-product
pgvector similarity anchored on the Hadley / Pellier linen shirt embedding.

**Flow:** `Dispatcher → Curator (+ the-packing-list) → style_match`

---

## Turn 3 — *"What's the price range for linen shirts?"*

**Value Analyst** · **Haiku 4.5 · 0.1** · **`price_intelligence`**

A numeric band with median — fast, deterministic SQL aggregate. Fixture copy lands
near *"$88 to $285, median $148"* with a short contextual sentence.

**Flow:** `Dispatcher → Value Analyst → price_intelligence`

---

## Turn 4 — *"Is the Hadley shirt at the Brooklyn warehouse?"*

*(Same SKU: **Pellier Linen Shirt in ecru**.)*

This is **the Builder's Session seam**. You'll see an answer **like**:

> *I can help with style and recommendations, but I don't have real-time stock
> visibility for individual warehouses yet. I can tell you the Hadley shirt
> (Pellier Linen Shirt in ecru) is in the catalog and marked in-stock system-wide —
> but which warehouse holds it, and how many are on the floor, sits outside what I
> can answer right now.*

Opening-demo telemetry calls this a **dispatcher fall-through**: stock intent is
recognized, **`floor_check` is still stubbed**, and the storefront returns this
graceful voice-matched non-answer rather than hallucinating bins.

That's what you **wire closed** next (`BusinessLogic.floor_check()`).

::::expand{header="Confirm the warehouse data is real"}

```bash
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
```

Expect **about 120 rows** — **one row per (warehouse × product)** for the three
warehouses seeded against the **40-product** catalog (`BK-01`, `ATX-02`, `PDX-01`).
The gap is tooling, not empty tables.

```bash
psql -c "\
  SELECT w.id, w.display_name, count(*) AS items, sum(wi.quantity) AS units \
    FROM pellier.warehouses w \
    JOIN pellier.warehouse_inventory wi ON wi.warehouse_id = w.id \
   GROUP BY w.id, w.display_name \
   ORDER BY w.id;"
```

::::

---

## Turn 5 — *"What pairs with the Ecru overshirt?"*

Still as Marco — **Curator** · **`the-packing-list`** · **Opus 4.6 · 0.4** · **`style_match`**

This is **not** the opening-demo transcript (that's four user turns ending in *"I'll
come back when I'm ready to commit."*); it **is** the first user turn inside
**Sessions → `marco-capstone`**. Editorial pairing fires cleanly — proof the system
still sings after Turn 4's gap narrative.

---

## A quick visit to the Atelier

Under **OBSERVE → Sessions**, open **`marco-opening-demo`** — the four-turn spine
(lines up with pills **1–4** plus Marco's closing line in the replay). Optionally
peek at **`marco-capstone`** for the **Ecru overshirt** pairing you just drove on
pill 5.

You'll tour routing after the build; the AgentCore pages come next once
Marco's gap is nailed.

---

## What you noticed

| | |
| --- | --- |
| ✓ Turn 1 | `find_pieces` · Style Advisor |
| ✓ Turn 2 | `style_match` · Curator + packing-list skill |
| ✓ Turn 3 | `price_intelligence` · Value Analyst |
| ✗ Turn 4 | **`floor_check` stub** — graceful non-answer (**your build**) |
| ✓ Turn 5 | `style_match` · Curator — editorial pairing still works |

One wiring exercise ahead: **`floor_check`** in **`agent_tools.py`**.

:::alert{type="success" header="Act I · Build next"}
[Act I · Wire `floor_check` →](/12-wire-floor-check/)
:::
