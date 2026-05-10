---
title: Module 1 · Observe
weight: 25
---

**Time budget: 5 minutes**
**Surfaces: Sessions → Observatory → Agents**

You've just watched Marco drive the opening demo. Module 1 is where you understand *why* each turn took the agent it did.

## Read the model-mix sidebar (2 minutes, solo)

Open: `lab-content/shared/model-mix-sidebar.en.md`

Read it. Come back.

## Atelier speed-tour (3 minutes, solo)

In the Atelier sidebar, work top to bottom. Spend 30 seconds each:

### `/atelier/sessions` → click `marco-opening-demo`
Replay the 4-turn you just saw. Notice **Turn 4's telemetry** shows a **routing fall-through** panel linking to "Open the Stock Keeper build."

### `/atelier/agents`
Five rows. **Stock Keeper has a burgundy "Your turn" pill.** Note the model tags — Sonnet 4.6 at 0.4 on two rows, Haiku 4.5 at 0.1 on one, Haiku 4.5 at 0.0 on one, Sonnet 4.6 at 0.2 on one. **No normalization.**

### `/atelier/tools`
Ten tools. Three are **dashed exercise** treatment: `floor_check`, `restock_shelf`, `running_low`. The discovery card surfaces `floor_check` as top match for "check stock at the Brooklyn warehouse" — "○ Pending implementation."

You'll build `floor_check` in Module 2. The other two are pre-applied for the Builder's Session (your Workshop Studio CFN template ran the `cp` command at boot) so you'll see them running but won't edit them.

### `/atelier/performance`
Per-agent latency bars. Sonnet agents at ~1200 ms. Haiku agents at ~150 ms. **Order of magnitude apart.** Stock Keeper's row shows "—" with a "pending" tag.

Scroll down to the **Search strategy comparison** card. This is Anna's anchor capability — vector + BM25 + Cohere Rerank. Type *"wrap-ready gifts"* in the input, click **Run on Aurora**, watch all three pipelines fire against the live catalog. The top-5 product mix differs per strategy — that's the rerank lift made visible.

The card includes a "Postgres FTS gotcha" callout: **`plainto_tsquery` AND-joins every stem** for plain-text input, so a 6-stem query matches zero products. The fix is OR-joining content tokens manually — see `HybridSearch._build_or_tsquery` in `services/hybrid_search.py`. One of those Postgres footguns worth knowing about.

Marco's `find_pieces` stays on plain pgvector — his queries are clean and the rerank cost ($1/1k) doesn't earn its keep. The architectural lesson: **pick the right tool for the query class.**

## Ready to build

Next: [Module 2 · Understand](20-module2-understand.en.md)

*Cross-links: [Anna's full arc](../shared/anna-arc-overview.en.md) · [Theo's write-path arc](../shared/theo-arc-overview.en.md) · [Aurora capabilities ladder](../shared/aurora-capabilities-arc.en.md)*
