# Anna's arc — when pure vector wears thin

*Anna is a gift-giver. Her queries blend editorial intent with hard constraints — "something beautiful under $100", "wrap-ready gifts with no extra effort". Her path through the system anchors the workshop's second Aurora capability: hybrid retrieval with reranking.*

---

## Who is Anna?

Anna buys for other people — partner, sister, friend, never for herself. Her recent searches lean *milestone* (housewarming, birthday) and her budget framing is explicit. She doesn't say "find me a candle"; she says "something thoughtful that arrives ready to give." Her hero pills in the Boutique reflect that: five queries that all blend a soft signal with a literal one.

| Pill | Soft signal | Literal token |
|---|---|---|
| 1. *a thoughtful gift for someone who loves morning rituals* | thoughtful, ritual | morning |
| 2. *something beautiful under $100* | beautiful | under $100 |
| 3. *help me pair a candle with something else* | pair, with something else | candle |
| 4. *wrap-ready gifts with no extra effort* | gifts, no extra effort | wrap-ready |
| 5. *a milestone gift for a new homeowner* | milestone | homeowner |

Pure cosine similarity finds *some* answer for each, but the answer drifts. The literal token is the constraint that reranks the soft one into a coherent gift band. **That's where hybrid earns its keep.**

## What Anna's Curator does differently

Marco's Style Advisor runs on plain `find_pieces` — pgvector cosine, top 5. Anna's Curator runs on `find_pieces_hybrid`, which is a four-stage pipeline:

1. **Vector branch** — `find_pieces` would have been this. pgvector cosine over the 1024-dim Cohere Embed v4 vectors, k=20.
2. **BM25 branch** — `to_tsquery` against a `tsvector` column generated from `name + brand + category + color + tags + description` with weighted contributions. The query is OR-joined from content tokens; we return k=20 by `ts_rank_cd` cover-density score.
3. **RRF merge** — Reciprocal Rank Fusion with k=60 produces a ~30-candidate union pool. A document at rank 1 in both branches scores ~0.0328; rank 1 in only one scores ~0.0164. Sort descending.
4. **Cohere Rerank v3.5** — Bedrock invokes `cohere.rerank-v3-5:0` with the query + a per-document text rendering of the 30 candidates. Top 5 returns.

The whole pipeline runs in roughly 1 second wall-clock, and each stage is logged separately so the Atelier session view shows the ranking lift between stages, not just the final top 5.

## The teaching beat — pill 4

*"Wrap-ready gifts with no extra effort"* is the demo turn that earns the rerank fee.

- **Pure cosine** finds Gift Wrapping Kit (it's in the literal text), then drifts to Linen Napkins, Leather Journal, Soap Set, Beeswax Candles. Coherent but generic.
- **Hybrid (RRF)** keeps Gift Wrapping Kit at #1, swaps in Botanical Print Scarf at #3 (BM25 caught "wrap" in the description).
- **Hybrid + rerank** keeps Gift Wrapping Kit at #1 again, but reorders the rest meaningfully: Handmade Soap Set climbs from #4 to #2 (Cohere reads "no extra effort"), Straw Panama Hat surfaces at #5 (Cohere reads "ready to give" and pulls in a piece neither retrieval branch ranked highly).

The Atelier's *Search strategy comparison* card runs all three pipelines against the live catalog and shows the top-5 mix per row. Workshop participants watch the ranking shift live — that's the demo.

## The cost question

Vector + hybrid run entirely against Aurora and are effectively free per query (already-paid-for compute). Rerank adds a Bedrock invoke at ~$1 per 1000 queries. The card surfaces this honestly: **6× cost increase, +20 points of recall@5, ~2× latency.** The workshop's "is it worth it?" question has a real answer for participants to argue with — there isn't a universally right call.

## Replay any of Anna's turns

- `/atelier/sessions/anna-housewarming` — *"something considered under $100 for a new homeowner"* — the hybrid pipeline catches "considered" via BM25 + reranks for budget coherence.
- `/atelier/sessions/anna-birthday-gift` — *"birthday gift for my sister — no idea where to start"* — the rerank lift surfaces gift-wrapping pieces over generic-recommendation pieces.

The Atelier session brief tab walks through the four pipeline stages with realistic latencies measured from the live audit (vector ~970ms, BM25 ~1000ms because both run in parallel, RRF ~3ms, rerank ~280ms — total ~1.3s wall-clock).

---

*Where to next: [theo-arc-overview.en.md](./theo-arc-overview.en.md) — Theo's chipped ceramics arrive and Aurora becomes the system of record.*
