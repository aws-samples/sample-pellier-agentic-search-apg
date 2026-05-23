---
title: "Measure · Prove rerank earns its cost"
weight: 30
---

:::alert{type="info"}
**Time:** ~9 min  ·  **Page:** 3 of 3 in Act I  ·  **Exercises on this page:** 0 (analytical)

You'll run Anna's exact Boutique turn through three retrieval strategies
and decide per-query-class whether the reranker paid for itself. No
new code is required — this is the *analyst's call* that closes Act I.
A short optional skill-edit lives at the bottom for tables with time
to spare.
:::

**You'll learn to:**

1. Read the **`vector` vs `hybrid (RRF)` vs `hybrid + rerank`** delta
   in the Atelier's Performance card against the live Aurora catalog.
2. Decide **per-query-class** whether Cohere Rerank v3.5 earns its
   latency and cost — soft taste vs literal-constraint queries behave
   differently.
3. Name the production pgvector knobs (`hnsw.iterative_scan`,
   `halfvec`, `binary_quantize(...)`) without yet exercising them.

---

## *Why this is a proof step*

Marco's build task proved the agent can reach live warehouse data.
Anna's exercise asks a different question: **did the more expensive
retrieval path actually improve the answer?** This is the *retrieval*
half of RAG, instrumented — the Curator's editorial reply is the
*generation* half, grounded in whichever ordered list of rows you
choose to ship.

Anna's Curator uses `find_pieces_hybrid`:

1. **Vector branch** — pgvector cosine over the catalog embeddings.
2. **Postgres FTS branch** — `tsvector` + GIN + `to_tsquery`, ranked with
   `ts_rank_cd`.
3. **RRF merge** — fuses both ranked lists without comparing raw scores.
4. **Cohere Rerank v3.5** — reads the merged candidate pool and reorders
   for the exact user phrasing.

Postgres does **not** ship a native BM25 operator. In this workshop, the
lexical branch is built from Postgres full-text search primitives:
`tsvector`, `to_tsquery`, and `ts_rank_cd`. That's the right built-in
choice for this catalog. Reach for `pg_trgm` when you need typo tolerance
or fuzzy name matching; use FTS when you need ranked lexical recall over
descriptions, tags, brands, and categories.

---

## 1 · Run Anna's Boutique turn

In the Boutique:

1. Switch the persona to **Anna**.
2. Click:

```text
A milestone gift for a new homeowner
```

Open **Under the hood** under Pellier's reply (the expandable trace panel
below the assistant response). You should see:

```text
skill.the-gift-table
tool.find_pieces_hybrid
```

Click **Compare retrieval strategies in Atelier**.

---

## 2 · Run the same query in Atelier

The link lands on **Atelier → Performance**. In the
**Search strategy comparison · Anna's anchor capability** card, run:

```text
A milestone gift for a new homeowner
```

The card calls:

```text
GET /api/atelier/search-strategies/compare?query=A%20milestone%20gift%20for%20a%20new%20homeowner
```

and measures three paths against the live Aurora catalog:

| Strategy | What it proves |
|---|---|
| `vector only` | What Marco's foundation search would have surfaced |
| `hybrid (RRF)` | What pgvector + Postgres FTS agree on before rerank |
| `hybrid + rerank` | What Anna actually ships to the shopper |

Just above it, the **Advanced pgvector tuning** card names the production
knobs you would tune once the catalog is large enough for those choices to
matter: `hnsw.iterative_scan` for filtered recall, `halfvec` for storage
footprint, and `binary_quantize(...)` for compact coarse retrieval. This is
not a fourth exercise — the live catalog is intentionally small — but it is
the performance conversation you have before taking the pattern to production.

::::expand{header="Run one production tuning knob yourself (60 sec, optional)"}

Even on 40 rows, the EXPLAIN plan shows the index path. Paste this in
`psql`:

```sql
-- 1. Baseline plan with the HNSW index
EXPLAIN (ANALYZE, BUFFERS)
SELECT name
  FROM pellier.product_catalog
 ORDER BY embedding <=> (
     SELECT embedding FROM pellier.product_catalog
      WHERE name = 'Pellier Linen Shirt'
   )
 LIMIT 5;

-- 2. Turn on iterative scan — protects recall when you ALSO filter
--    on metadata (e.g. category = 'shirts' AND price < 200).
SET hnsw.iterative_scan = strict_order;

EXPLAIN (ANALYZE, BUFFERS)
SELECT name, price
  FROM pellier.product_catalog
 WHERE price < 200
 ORDER BY embedding <=> (
     SELECT embedding FROM pellier.product_catalog
      WHERE name = 'Pellier Linen Shirt'
   )
 LIMIT 5;

RESET hnsw.iterative_scan;
```

Plan #1 should show `Index Scan using product_catalog_embedding_hnsw`.
Plan #2 with the `WHERE price < 200` filter is where `iterative_scan`
earns its keep at scale: it keeps walking the HNSW graph until it
finds enough rows that satisfy your filter, instead of cutting the
recall short. **At 40 rows it's invisible; at 4M rows it's the
difference between empty result sets and correct ones.**

`halfvec(1024)` (16-bit storage, ~50% smaller index) and
`binary_quantize(embedding)` (1-bit, used as a coarse first pass)
are the next two knobs — read them in the [pgvector
README](https://github.com/pgvector/pgvector#performance), not in
the room.

::::

---

## 3 · Decide if rerank earned it

Look at the **Top 5** row under each strategy.

Ask:

- Did the reranked row put the product Pellier named first near the top?
  For this anchor query, that should be **Olive Branch Vessel** — a lasting
  object for a new-home milestone.
- Did literal signals like *homeowner*, *gift*, *wrap-ready*, or budget
  language improve versus vector-only?
- Did the result quality justify the extra latency and the Cohere Rerank
  cost?

There is no universal answer. That's the point. Hybrid + rerank is not a
default; it is a per-query-class tradeoff.

---

## 4 · Optional: change the query

Run one of Anna's other turns:

```text
Something beautiful under $100
```

```text
Wrap-ready gifts with no extra effort
```

If vector-only already gives a tight result set, rerank may not earn its
cost. If the query mixes soft taste with literal constraints, the reranker
usually pays for itself.

---

## 5 · Stretch · customize Anna's skill, prove with SQL

:::alert{type="info" header="Stretch · only if your table has time"}
This is **not Exercise 2** — Exercise 2 is in Act II (one
`logger.info(...)` line on the managed Runtime path). If you finished
the analyst's call early, this 5–6 min stretch lets you edit one rule
in `skills/the-gift-table/SKILL.md`, re-run Anna's anchor query, and
prove with a `SELECT` against `pellier.tool_uses` that your edit landed
on the real retrieval path.
:::

### Edit one skill rule

Open:

```text
skills/the-gift-table/SKILL.md
```

Change one guidance line under **Voice and curation rules** (for example:
"Offer one strong primary recommendation before alternates").

Save, then run Anna again:

```text
A milestone gift for a new homeowner
```

### Prove the retrieval path with SQL

From your terminal, inspect the latest hybrid tool call:

```sql
SELECT tool_name,
       tool_input ->> 'query' AS query,
       "timestamp"
  FROM pellier.tool_uses
 WHERE tool_name = 'find_pieces_hybrid'
 ORDER BY "timestamp" DESC
 LIMIT 3;
```

You should see your Anna query in the latest rows. This proves the turn hit
the real retrieval tool path, not a canned fixture.

### Verify in Under the hood

In Boutique, expand **Under the hood** for the same reply and confirm:

```text
skill.the-gift-table
tool.find_pieces_hybrid
```

If those chips are present and SQL confirms the latest call, your skill edit is
live and grounded in the same retrieval pipeline.

---

## What you've learned

- The Boutique's `tool.find_pieces_hybrid` chip is not decoration — it
  maps to a measurable backend path you can reproduce with SQL.
- **Postgres FTS complements pgvector, but it is not native BM25.** The
  workshop uses `ts_rank_cd` because it is built in, indexable, and
  good enough for a product catalog. Reach for `pg_trgm` when you need
  fuzzy matching.
- **Cohere Rerank is a per-query-class decision, not a default.** The
  Atelier comparison is how you decide whether the change was worth
  the latency and cost.
- **pgvector has production knobs you'll reach for at catalog scale.**
  `hnsw.iterative_scan` protects filtered recall; `halfvec` and
  `binary_quantize(...)` trade precision for storage and speed.
- **A skill rule is live the moment you save it** — and SQL against
  `pellier.tool_uses` is how you prove the edit landed on the real
  retrieval path, not a fixture.

:::alert{type="success" header="Act II · The Ledger"}
You've wired Marco's live tool and measured Anna's retrieval tradeoff.
Next, switch from in-process Strands to the **managed AgentCore
Runtime** — and add **Exercise 2**: a one-line `logger.info(...)`
observability hook so every `InvokeRuntime` call shows up in
`uvicorn.log`.

[Act II · AgentCore Memory (STM) →](/20-act-2-the-ledger/01-agentcore-memory-stm/)
:::
