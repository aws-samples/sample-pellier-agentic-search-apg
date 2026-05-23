---
title: "Shipment SQL · The shipment that just arrived"
weight: 20
---

:::alert{type="info"}
*Optional follow-on (~10 minutes), best after the main session. Not part
of the 50-minute hands-on block.*
:::

Anna's Beeswax Tapers story: one `UPDATE` to refresh catalog quantity, then
the agent notices on the next search turn.

```bash
psql -c "SELECT \"productId\", name, quantity FROM pellier.product_catalog WHERE name ILIKE '%beeswax%';"
```

Use the exact product name returned by your `SELECT` to avoid updating
multiple rows accidentally:

```sql
UPDATE pellier.product_catalog
   SET quantity = 24
 WHERE name = 'Beeswax Taper Candles';
```

Switch to **Anna** in the Boutique and re-run the beeswax pill — in-stock
language should return without a redeploy.

---

## The production gotcha — content edits ≠ embedding refresh

The pattern above worked because **only the `quantity` column changed**.
Quantity does not influence retrieval — the embedding is over `name`,
`brand`, `description`, `tags`, etc. But if you edit any of *those*
columns, the row's `embedding` is now stale: the agent's cosine search
will still match the old description.

**The real production loop** when content changes:

```sql
-- 1. Edit the content
UPDATE pellier.product_catalog
   SET description = 'Hand-poured beeswax tapers; warm honey scent; pair burns 8 hours.'
 WHERE name = 'Beeswax Taper Candles';

-- 2. Mark the row for re-embedding (cheap NULL signal)
UPDATE pellier.product_catalog
   SET embedding = NULL
 WHERE name = 'Beeswax Taper Candles';
```

Then re-embed from your terminal:

```bash
python3 scripts/seed_boutique_catalog.py --refresh-empty-embeddings
```

The script picks up only rows where `embedding IS NULL`, calls
**Cohere Embed v4** for each, and writes the 1024-dim vector back.
Re-run Anna's pill — the new description is reachable by retrieval.

::::expand{header="Why a NULL signal beats a 'dirty' boolean"}

Three reasons that matter at scale:

1. **No schema migration** — pgvector lets `vector` columns be NULL.
2. **The HNSW index ignores NULL rows** automatically; no special filter.
3. The seeder's idempotency check is already `WHERE embedding IS NULL` —
   you're using the same primitive for re-embed that bootstrap uses.

In a larger system you'd schedule this on `AFTER UPDATE` triggers
plus a small worker, but the SQL surface is identical.

::::
