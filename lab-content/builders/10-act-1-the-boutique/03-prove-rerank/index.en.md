---
title: "03: Prove rerank earns its cost"
weight: 30
---

:::alert{type="info"}
**Time:** ~9 min  
**Exercises:** 0 (analytical)  
**Surface:** Atelier → Performance · Boutique chat (Anna persona)
:::

You'll run Anna's exact Boutique turn through three retrieval strategies and decide per-query-class whether the reranker paid for itself. No new code is required – this is the *analyst's call* that closes Act I. A short optional skill-edit lives at the bottom for tables with time to spare.

**You'll learn to:**

1. Read the **four-strategy comparison** – `vector only`, `hybrid (RRF)`,
   `hybrid + rerank`, and `agentic (Haiku → filter → vector → rerank)` –
   in the Atelier's Performance card against the live Aurora catalog.
2. Decide **per-query-class** which path earns its latency and cost.
   Soft taste, literal constraints, and budget ceilings each have a
   different winner.
3. See how **Haiku 4.5 at T=0** turns a conversational query into a
   structured WHERE clause + a residual taste phrase the reranker
   scores against – and how `hnsw.iterative_scan = 'relaxed_order'`
   keeps recall safe under strict filters.
4. Name the production pgvector knobs (`hnsw.iterative_scan`,
   `halfvec`, `binary_quantize(...)`) without yet exercising them.

---

## *Why this is a proof step*

Marco's build task proved the agent can reach live warehouse data.
Anna's exercise asks a different question: **does the more expensive
retrieval path actually improve the answer – and does it respect the
shopper's constraints?**

Anna's Curator now uses an agentic retrieval pipeline:

1. **Haiku extract** – Claude Haiku 4.5 at T=0 reads the query and
   emits `{categories, tags, price_max_usd, in_stock_only, soft_signal}`
   as structured JSON. Hallucinated values are dropped against an
   allow-list of 6 categories and 28 tags.
2. **Filtered vector search** – pgvector cosine over rows that pass the
   structured WHERE clause, with `hnsw.iterative_scan = 'relaxed_order'`
   so a strict filter doesn't silently drop recall below `LIMIT`.
3. **Cohere Rerank v3.5** – reads the filtered pool and reorders for
   the *residual taste phrase* (not the raw query – the price
   ceiling and category names have already done their work).

The Performance card runs all four strategies side-by-side so you can
see, query by query, when the agentic path wins (budget ceilings,
explicit categories, "in stock") and when plain `hybrid + rerank` is
already enough (pure soft-taste queries).

Postgres does **not** ship a native BM25 operator. The hybrid (RRF)
strategy is kept as a teaching foil – it shows you what plain FTS gets
right and where it breaks down on conversational shopper phrasing
(see the FTS gotcha on the Performance card). The `pg_trgm` extension
is also installed: not as a fuzzy-search reach-for, but as a GIN
trigram index on `lower(name)` and `lower(category)` that accelerates
the `ILIKE` lookups `floor_check` does inside `business_logic.py`.
Same extension, different job – fast prefix/substring matching, not
ranked lexical recall.

**Pattern:** hybrid + rerank is the path for conversational queries that mix soft intent with hard constraints. In Pellier that means gift intent plus budget, category, and in-stock language. In your stack the same shape covers benefits language plus procedure codes, policy documents plus account type, service manuals plus machine model, or product reviews plus exact SKU.

---

## 1. Run Anna's Boutique turn

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

## 2. Run the same query in Atelier

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
not a fourth exercise – the live catalog is intentionally small – but it is
the performance conversation you have before taking the pattern to production.

---

## 3. Decide if rerank earned it

Look at the **Top 5** row under each strategy.

Ask:

- Did the reranked row put the product Pellier named first near the top?
  For this anchor query, that should be **Olive Branch Vessel** – a lasting
  object for a new-home milestone.
- Did literal signals like *homeowner*, *gift*, *wrap-ready*, or budget
  language improve versus vector-only?
- Did the result quality justify the extra latency and the Cohere Rerank
  cost?

There is no universal answer. That's the point. Hybrid + rerank is not a
default; it is a per-query-class tradeoff.

---

## 4. Optional: change the query

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

## 5. Optional builder extension – edit Anna's skill, see the voice change

:::alert{type="info" header="Optional · only if your table has time"}
This is **not a required exercise** – Act II's mandatory build is the
Aurora SQL ledger query against `pellier.tool_audit`. If you finished
the analyst's call early, this 5-min extension lets you edit one
rule in `skills/the-gift-table/SKILL.md`, re-run Anna's anchor query,
and watch Pellier's voice change to match. The skill is *prose
guidance*, so the proof is in the reply text and the **Under the
hood** chips – the retrieval pipeline itself doesn't change.
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

### Read the new reply

Pellier's reply should now lead with one decisive recommendation
before listing alternates. The retrieval set is identical to the
pre-edit run – only the *voice* shifts, because the skill changes
the agent's prompt, not the SQL.

### Verify in Under the hood

In Boutique, expand **Under the hood** for the same reply and confirm:

```text
skill.the-gift-table
tool.find_pieces_hybrid
```

If those chips are present and the reply prose reflects your new
rule, the edit is live. The retrieval-side proof – that Aurora is
actually hosting this turn – comes in Act II's
`pellier.tool_audit` exercise, where you'll fire a *write* turn
(Theo's damaged return) and read the row back.

---

## What you've learned

- The Boutique's `tool.find_pieces_hybrid` chip is not decoration –
  it names the retrieval pipeline you can compare against three
  alternates in Atelier → Performance.
- **Postgres FTS complements pgvector, but it is not native BM25.**
  `ts_rank_cd` is built in, indexable, and good enough for a product
  catalog. `pg_trgm`, despite the name, is *not* the fuzzy-match
  reach in this workshop – it backs the GIN trigram index that
  accelerates `floor_check`'s `ILIKE` lookups.
- **Cohere Rerank is a per-query-class decision, not a default.** The
  Atelier comparison is how you decide whether the change was worth
  the latency and cost.
- **pgvector has production knobs you'll reach for at catalog scale.**
  `hnsw.iterative_scan` protects filtered recall under strict
  WHERE clauses; `halfvec` and `binary_quantize(...)` trade
  precision for storage and speed.
- **A skill rule is live the moment you save it** – the change shows
  up in the next reply's voice, while the retrieval set stays the
  same. Skills change the agent's prompt, not the SQL.

:::alert{type="success" header="Act II: The Ledger"}
You've wired Marco's live tool and measured Anna's retrieval
tradeoff. Next, switch from in-process Strands to the **managed
AgentCore Runtime**, then run **Exercise 2**: one SELECT against
`pellier.tool_audit` to recover the Cedar-allowed mutation Theo's
damaged-return turn just made – args, result, and latency from a
single Aurora query.

[Act II: Memory: four substrates →](/20-act-2-the-ledger/01-memory-substrates/)
:::
