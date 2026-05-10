# Three personas, three Aurora capabilities, one ladder

*The workshop is titled "Agentic AI Search with Aurora PostgreSQL" — and yet it would be embarrassingly easy to write three personas that all use the same code path. They don't. Each persona anchors a distinct Aurora capability, and the next persona builds on top.*

---

## The ladder

| Persona | Aurora capability | What's new |
|---|---|---|
| **Marco** | pgvector semantic search · HNSW · iterative_scan | Foundation. Cosine similarity over 1024-dim Cohere Embed v4 vectors. The Module 1 teaching surface. |
| **Anna** | Hybrid (vector + tsvector BM25) → RRF → Cohere Rerank v3.5 | Vector wears thin when queries blend soft intent with literal constraints. Postgres' built-in full-text complements pgvector; RRF merges the two ranked lists; Cohere reorders the union. |
| **Theo** | Aurora as agent system-of-record · Cedar-gated writes · persistent audit trail | Agents don't just read — they write. Cedar gates *what* the agent can do; SQL gates *whose* state. Every ALLOW writes a row to `tool_audit` so a single SELECT replays the turn. |

Each row uses everything above it. Anna still uses HNSW for the vector branch. Theo still uses `find_pieces` to resolve a product mention before he can write a return for it. **The capabilities compound.**

---

## Why Marco anchors capability 1

Marco's queries are clean: *"What linen do you have for 10 days in Goa?"* The pgvector cosine over the catalog's embeddings finds the linen pieces by *meaning*. That's the demo where vector earns its name — no keyword in the catalog says "Goa," but the embedding captures "warm, breezy, beach-bar." HNSW makes it fast. iterative_scan keeps recall honest when the agent layers in a price filter on top.

This is the ground floor. Without it, none of the rest of the workshop teaches anything new.

## Why Anna anchors capability 2

Anna's queries are deliberately mixed: *"something beautiful under $100"*, *"wrap-ready gifts with no extra effort"*. The embedding sees "beautiful" as a vibe and "$100" as a fuzzy number; it doesn't read "wrap-ready" as a literal lookup against the catalog's product descriptions. **BM25 over a Postgres tsvector does.** Together — vector for meaning, BM25 for literal tokens, RRF to merge, Cohere to rerank — Anna's path returns the Gift Wrapping Kit at rank 1 with all the gift-coded pieces underneath.

The Atelier's *Search strategy comparison* card on `/atelier/performance` makes this concrete: type Anna's query, click "Run on Aurora," watch all three pipelines fire against the live catalog, see the ranking shift in real time.

## Why Theo anchors capability 3

A return is the moment Aurora becomes the source of truth, not an index. Theo's chipped Wabi-Sabi Bowl produces:

1. An `INSERT` into the `returns` table.
2. A `GREATEST(quantity - 1, 0)` decrement on `product_catalog` (only when `reason='damaged'`).
3. A `tool_audit` row capturing the agent's call with args + result + latency.

All three in one transaction. Two enforcement layers: **Cedar** rejects free-form return reasons before SQL runs; **SQL** rejects writes the customer doesn't have ownership for via a JOIN against `orders`. The Atelier's *Tools* page shows the WRITE badge on `process_return` and `restock_shelf` — and only those two — so the read/write split is visible at a glance.

---

## The compounding lesson

Every persona is a stage on the same database. The catalog they search is the catalog they write to. The audit trail they generate is queryable from the same psql prompt. **One source of truth, three teaching surfaces, one compounding ladder.**

That's the workshop. Not "agents can do RAG"; not "vectors work"; but *"here's what an agentic AI system looks like when Aurora is the operating substrate for everything — search, decision, action, memory."*

---

*Cross-links:*
- *Marco's narrative arc → [marco-arc-overview.en.md](./marco-arc-overview.en.md)*
- *Anna's hybrid arc → [anna-arc-overview.en.md](./anna-arc-overview.en.md)*
- *Theo's write-path arc → [theo-arc-overview.en.md](./theo-arc-overview.en.md)*
- *Per-agent model mix → [model-mix-sidebar.en.md](./model-mix-sidebar.en.md)*
