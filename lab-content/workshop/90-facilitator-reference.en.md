---
title: Facilitator Reference · Narrative Spine
weight: 90
---

# Facilitator Reference

This appendix consolidates the workshop's narrative notes into one
place. It is not a participant checkpoint; use it as the facilitator
reference for the 120-minute workshop.

---

## Marco's Arc — The Spine

Marco is the protagonist of the Pellier workshop. He's a returning
customer with clear signals: natural fabrics, linen, travel-ready
pieces, warm tones. Anna and Theo show range, but Marco drives the
instructional checkpoints in both delivery formats.

Participants drive the opening demo by clicking Marco's hero pills in
fixture order. The Boutique pills are
`personaCurations · PERSONA_HERO_PILLS.marco`, and they must stay aligned
with `session-marco-opening-demo.json` plus the opening turn of
`marco-capstone`.

Where the guide says **Hadley shirt**, that is the storefront line for
**Pellier Linen Shirt in ecru**.

| Turn | Marco clicks | Route | Agent | Tool | Outcome |
|---|---|---|---|---|---|
| 1 | "What linen do you have for 10 days in Goa?" | Style Advisor | Opus 4.6 · 0.4 | `find_pieces` | Three linen pieces; editorial voice |
| 2 | "What would go with the Hadley shirt?" | Curator + `the-packing-list` | Opus 4.6 · 0.4 | `style_match` | Companion pieces from product-to-product similarity |
| 3 | "What's the price range for linen shirts?" | Value Analyst | Haiku 4.5 · 0.1 | `price_intelligence` | Numeric band, fast |
| 4 | "Is the Hadley shirt at the Brooklyn warehouse?" | Fall-through | — | — | `floor_check` is stubbed; graceful non-answer |

After participants wire `floor_check`, they re-click Turn 4. The payoff
line should name Brooklyn stock for Hadley / Pellier Linen Shirt in ecru.
The Atelier Routing page connects the dotted line, Agents drops the
exercise pill, and Performance shows the Haiku stock turn around the
sub-250 ms class.

The capstone is `marco-capstone`: every specialist fires once, each on
its own model and temperature. Narrate Opus editorial turns versus Haiku
reporting turns as an architectural decision participants can hear and
measure.

---

## Why These Agents Use Different Models

Five specialists use different model configurations on purpose.

**Style Advisor** and **Curator** run on **Claude Opus 4.6 at 0.4**
because their job is editorial: describe linen, suggest pairings, and
carry Pellier's boutique voice.

**Value Analyst** and **Stock Keeper** run on **Claude Haiku 4.5 at 0.1
and 0.0** because their job is to report: prices, ranges, warehouse
counts. The only thing worse than a slow stock check is a wrong one.

**Experience Guide** sits in the middle: **Opus at 0.2** for warmth
without wandering when policy language matters.

**Orchestrator** and **SkillRouter** use **Haiku 4.5 at 0.0** because
classification wants determinism.

The Atelier makes this visible:

- `/atelier/agents` shows the model tag and temperature per specialist.
- `/atelier/performance` shows latency spread by roughly an order of
  magnitude: Opus editorial turns often ~800-1500 ms warm; Haiku turns
  ~100-250 ms; routing ~60-120 ms.

There is no global `DEFAULT_MODEL`. Model selection is an architectural
decision: ask whether the agent describes or reports.

---

## Three Personas, Three Aurora Capabilities

Pellier teaches a ladder of Aurora capabilities. Each persona uses
everything above it.

| Persona | Aurora capability | What's new |
|---|---|---|
| **Marco** | pgvector semantic search · HNSW · iterative scan | Foundation: cosine similarity over Cohere Embed v4 vectors |
| **Anna** | Hybrid vector + Postgres FTS → RRF → Cohere Rerank | Literal constraints and soft intent are combined before rerank |
| **Theo** | Aurora as agent system of record · Cedar-gated writes · audit trail | Agents mutate durable state, not just retrieve context |

Marco's clean linen query is where vector search earns its name: no
catalog row says "Goa," but embeddings capture warm, breezy,
travel-ready context.

Anna's queries mix taste and constraints: "something beautiful under
$100", "wrap-ready gifts with no extra effort". Vector sees the vibe;
Postgres FTS sees literal terms; RRF merges ranked lists; Cohere Rerank
reads the candidate pool and reorders for the exact phrasing.

Theo's return is where Aurora becomes the operating substrate. A return
inserts into `returns`, decrements `product_catalog.quantity` when the
reason is `damaged`, and writes `tool_audit` rows so the turn is
reconstructible from SQL.

---

## Anna's Arc — When Pure Vector Wears Thin

Anna is a gift-giver. Her hero pills blend editorial intent with hard
constraints:

| Pill | Soft signal | Literal token |
|---|---|---|
| thoughtful gift for someone who loves morning rituals | thoughtful, ritual | morning |
| something beautiful under $100 | beautiful | under $100 |
| help me pair a candle with something else | pair | candle |
| wrap-ready gifts with no extra effort | gifts, no effort | wrap-ready |
| a milestone gift for a new homeowner | milestone | homeowner |

Anna's Curator uses `find_pieces_hybrid`:

1. Vector branch: pgvector cosine, k=20.
2. Postgres FTS branch: generated `tsvector`, weighted fields, ranked
   with `ts_rank_cd`.
3. RRF merge: fuses the vector and FTS ranks without comparing raw
   scores.
4. Cohere Rerank v3.5: reorders the merged pool for the exact user
   phrasing.

The teaching beat is the ranking shift, not "rerank is always better."
The Atelier Performance page lets participants run vector-only, hybrid,
and hybrid + rerank against the same query and argue whether the added
latency and cost paid off.

---

## Theo's Arc — Aurora as System of Record

Theo anchors the write path. His canonical turn:

> "My Wabi-Sabi Bowl arrived chipped. Please file a damaged return — my
> customer id is 'theo'."

Experience Guide chains:

1. `find_pieces` resolves "Wabi-Sabi Bowl" to a product and category.
2. `returns_and_care` confirms the return window.
3. `process_return` performs the write.

Two enforcement layers matter:

- **Cedar** runs in `BeforeToolCallEvent` and gates what the agent can do,
  such as allowed return reasons.
- **SQL** gates whose state the agent can mutate by checking ownership in
  `orders`.

If both pass, the transaction inserts a return row and updates inventory.
The policy hook also writes `tool_audit`, so every mutation is
reconstructible.

In the Builder's Session, Experience Guide ships pre-applied. In the
120-minute Workshop, it is the second specialist build.
