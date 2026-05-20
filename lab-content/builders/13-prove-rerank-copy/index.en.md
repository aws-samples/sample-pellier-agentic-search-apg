---
title: "Act I · Measure — Prove Rerank Earns Its Cost"
weight: 13
---

*Proof step — no code. You run Anna's exact Boutique turn through three
retrieval strategies and decide whether the reranker paid for itself.*

---

## *Why this is a proof step*

Marco's build task proved the agent can reach live warehouse data.
Anna's exercise asks a different question: **did the more expensive
retrieval path actually improve the answer?**

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

Open **Under the hood** under Pellier's reply. You should see:

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
religion; it is a per-query-class tradeoff.

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

## 5 · Code extension (recommended in 60-minute format): customize a skill, prove with SQL

This is a fast builder extension (about 6-8 minutes). In the one-hour
Builder's Session, treat this as the **second coding moment** after
`floor_check`.

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

## *What you proved*

- The Boutique's `tool.find_pieces_hybrid` chip is not decoration — it
  maps to a measurable backend path.
- Postgres FTS complements pgvector, but it is not native BM25. The
  workshop uses `ts_rank_cd` because it is built in, indexable, and good
  enough for a product catalog.
- Cohere Rerank changes ranking after retrieval; the Atelier comparison
  is how you decide whether the change was worth it.
- pgvector performance has its own knobs. Iterative index scans protect
  filtered recall; `halfvec` and `binary_quantize(...)` trade precision for
  storage and speed.

:::alert{type="success" header="Act II · Platform tour"}
You've wired Marco's live tool and measured Anna's retrieval tradeoff.
Next, switch from building to reading the platform around that build:
short-term memory, Runtime, and routing.

[Act II · AgentCore Memory (STM) →](/20-agentcore-memory-stm/)
:::
