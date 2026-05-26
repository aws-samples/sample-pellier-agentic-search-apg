---
title: "01: Meet Marco"
weight: 10
---

:::alert{type="info"}
**Time:** ~6 min  
**Exercises:** 0  
**Surface:** Boutique (`/`) chat drawer · Atelier trace chips
:::

Click Marco's five hero pills in order. Three land cleanly. **Turn 4 breaks** – that's the gap you close in Exercise 1.

## The stack under Pellier

Pellier is the editorial face of the demo. The system underneath is **Aurora PostgreSQL with pgvector** for retrieval, **Amazon Bedrock** for inference (Claude Opus 4.6 for editorial voice, Haiku 4.5 for terse reports), **MCP** for tool federation across specialist agents, and the **Strands Agents SDK** orchestrating the dispatch. Every chat turn on this page exercises that stack end-to-end.

Act I is observational. You read the trace chips, identify the seams between memory tiers and routing layers, and locate the one tool that's stubbed. You don't write code on this page – you map the system so the build that follows lands in context.

**You'll learn to:**

1. Name the **six components of a specialist agent** (model, instructions, skills, tools, state, telemetry) and recognize them in the trace.
2. Read the **trace chips** under each reply (specialist · model · tool) and connect them to the orchestration layer.
3. Distinguish the **four memory substrates** Pellier wires together: *working* (this turn's session timeline), *semantic* (Marco's stable preferences), *episodic* (his prior browsing and orders), and *procedural* (which tools win for which intents). You verify the working substrate hands-on in Act II.
4. Locate **why Turn 4 fails gracefully** – and identify the specific wiring needed to close the gap.

For the 60-minute session, treat this page as a checklist: click the pills, confirm the routing pattern, then move to [Wire `floor_check`](../02-wire-floor-check/).

## Customer context

Marco is a returning customer packing **linen for a long stretch in Goa**. The agent recognizes him because the system separates memory into four substrates – *working*, *semantic*, *episodic*, and *procedural*. His **semantic** preferences (warm neutrals, natural fibers, travel-ready pieces) live in AgentCore Memory under a customer-scoped key; his **episodic** browsing rows live in Aurora; his **working** memory is the live conversation; **procedural** signal accumulates as tools fire. You verify the working substrate hands-on in Act II.

**Pattern:** memory in an agent system is not a single bucket. Pellier separates session continuity, durable preferences, customer events, and tool-choice evidence into four substrates. In another stack, that same separation might cover a current care encounter versus a longitudinal member profile, a support chat versus account history, or a troubleshooting session versus asset maintenance records.

::::expand{header="Anatomy of a Pellier specialist (read once, reuse all session)"}

A specialist agent is not a prompt. It's six concrete components, each independently versioned and observable:

| Component | What it is | Example in this demo |
| --- | --- | --- |
| **Model** | Foundation model selected per role | Opus 4.6 for editorial voice; Haiku 4.5 for terse reports |
| **Instructions** | System prompt defining job, tone, boundaries | *"You are the Curator. Recommend companion pieces…"* |
| **Skills** | Markdown playbooks loaded per turn | `the-packing-list` for Marco; `the-gift-table` for Anna |
| **Tools** | Python functions decorated with `@tool` | `find_pieces`, `style_match`, `price_intelligence`, `floor_check` |
| **State** | Memory plus request context | Four substrates: working (session), semantic (preferences), episodic (Aurora rows), procedural (`tool_audit`) |
| **Telemetry** | Per-turn trace exposed in the UI | Specialist · model · tool · latency chips |

The build on the next page is small because the agent already exists. You are wiring one missing tool body into that anatomy – not assembling the anatomy itself.

::::

## 1. Open Marco's chat drawer

In the Boutique (port **8000**), confirm **Marco** is selected in the header. Open the chat drawer with **Ask Pellier** or `⌘K` / `Ctrl+K`. Five suggestion pills appear. **Click them in order.**

## 2. Turn 1 – *"What linen do you have for 10 days in Goa?"*

**Style Advisor** · Opus 4.6 · `find_pieces`

Returns editorial copy and a three-card grid: **Pellier Linen Shirt in ecru**, **Linen Drawstring Trousers in oat**, **Italian Linen Camp Shirt in indigo**. Under the hood, `find_pieces` runs a pgvector cosine search with rerank, layered on Marco's profile embedding.

The trace chips align with `find_pieces` latency and tool evidence.

**Pattern:** `find_pieces` is semantic retrieval plus rerank over a domain corpus. In Pellier, that corpus is curated product copy. In your stack, the same retrieval shape could search support tickets, policy documents, clinical protocols, service manuals, contracts, or internal knowledge articles.

## 3. Turn 2 – *"What would go with the Hadley shirt?"*

*(Hadley is the storefront name for the Pellier Linen Shirt in ecru.)*

**Curator** + `the-packing-list` skill · Opus 4.6 · `style_match`

The Curator returns companion pieces – drawstring trousers, washed cotton overshirt, weekender. Telemetry reads `style_match`: product-to-product pgvector similarity anchored on the Hadley embedding.

## 4. Turn 3 – *"What's the price range for linen shirts?"*

**Value Analyst** · Haiku 4.5 · `price_intelligence`

A numeric band with median – a deterministic SQL aggregate, no embedding involved. Result lands near *"$88 to $285, median $148."*

## 5. Turn 4 – *"Is the Hadley shirt at the Brooklyn warehouse?"*

This is the **Builder's Session seam.** You'll see something like:

> *I can help with style and recommendations, but I don't have real-time stock visibility for individual warehouses yet…*

The dispatcher recognized stock intent and routed correctly to Stock Keeper. The failure is **inside the tool** – `floor_check` is stubbed, so it returns a graceful, voice-matched non-answer rather than hallucinating bin numbers.

That non-answer is the gap you close next.

**Pattern:** this is a missing tool body between an agent contract and a system of record. The router chose the right specialist; the tool contract existed; only the implementation was missing. In a regulated or operational workflow, that is exactly where you want failure to be visible and non-fabricated.

::::expand{header="Confirm the warehouse data is real (optional)"}

```bash
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
```

Expect ~120 rows – three warehouses (`BK-01`, `ATX-02`, `PDX-01`) × 40 products. **The gap is tooling, not data.**

::::

## 6. Turn 5 – *"What pairs with the Ecru overshirt?"*

**Curator** · `the-packing-list` · Opus 4.6 · `style_match`

The editorial pairing returns cleanly. Turn 5 routes through `style_match` rather than `floor_check`, so the gap from Turn 4 doesn't propagate. This isolation is by design: a stubbed tool degrades one capability, not the system.

## What the traces showed you

| Turn | Specialist | Tool | Status |
| :---: | --- | --- | :---: |
| 1 | Style Advisor | `find_pieces` | ✓ |
| 2 | Curator + `the-packing-list` | `style_match` | ✓ |
| 3 | Value Analyst | `price_intelligence` | ✓ |
| **4** | **Stock Keeper** | **`floor_check`** *(stub)* | **✗** |
| 5 | Curator | `style_match` | ✓ |

## Takeaways

- A specialist is **six components, not one prompt**: model, instructions, skills, tools, state, telemetry. Each is independently observable and replaceable.
- The orchestrator **routed Turn 4 correctly** – the failure is at the tool body, not the dispatcher. That's the diagnostic skill you'll lean on throughout the workshop.
- A graceful non-answer is a **design choice**. Stub tools should refuse to fabricate; that's why Marco received a voice-matched apology rather than invented bin numbers.
- Turn 5 still works because it routes through a different tool. **Capability isolation** is what lets you ship an agent system with partial tool coverage – and it's the reason the next exercise is one focused wiring task, not a system rebuild.

:::alert{type="success" header="Build next – Exercise 1"}
[Wire `floor_check` →](../02-wire-floor-check/)
:::
