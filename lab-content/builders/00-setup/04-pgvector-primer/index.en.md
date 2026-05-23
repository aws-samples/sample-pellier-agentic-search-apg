---
title: "pgvector primer (optional)"
weight: 40
---

:::alert{type="info"}
**Time:** ~2 min  ·  **Optional** — skip if you've shipped pgvector
before. New to embeddings? This is the 60-second SQL you'll be glad
you saw before Marco walks in.
:::

The whole stack rides on three primitives: a **column** that stores a
1024-dim vector, an **operator** that returns cosine distance, and an
**HNSW index** that makes the operator fast at scale. Run each block
once so you've seen them with your own eyes.

> **Aurora and RDS use the same primitives.** This page runs against
> Aurora in the lab, but every statement is identical on Amazon RDS
> for PostgreSQL once you've installed the `vector` extension.

---

## 1 · The column

```bash
psql -c "\d pellier.product_catalog" | grep -E "embedding|vector"
```

Expect:

```text
 embedding | vector(1024) |
```

That `vector(1024)` matches **Cohere Embed v4**'s output dimension. If
you swapped to a 1536-dim model (e.g. Titan Text v2), you'd alter the
column **and** drop+rebuild the HNSW index — pgvector cannot reshape
an index in place.

---

## 2 · The operator

`<=>` is cosine distance. Smaller is closer. Run a real query against
Marco's signature piece:

```bash
psql <<'SQL'
SELECT name,
       round((embedding <=> (
         SELECT embedding
           FROM pellier.product_catalog
          WHERE name = 'Pellier Linen Shirt'
       ))::numeric, 4) AS cosine_distance
  FROM pellier.product_catalog
 ORDER BY cosine_distance
 LIMIT 5;
SQL
```

The Linen Shirt itself returns `0.0000`; the next four are the
catalog's nearest neighbours by editorial taste — typically other
linen pieces and travel-ready shirts. **That ranking is the literal
shape of `style_match`** — the tool you'll see Marco's Curator call
on Turn 2.

---

## 3 · The index

```bash
psql -c "\d+ pellier.product_catalog" | grep -A1 hnsw
```

Expect:

```text
"product_catalog_embedding_hnsw" hnsw (embedding vector_cosine_ops)
                                  WITH (m='16', ef_construction='64')
```

`m=16, ef_construction=64` are the workshop defaults — fine for 40
rows, fine for 40,000. At 4M+ rows you'd reach for the production
knobs Act I names: `hnsw.iterative_scan` (filtered recall),
`halfvec` (16-bit storage), `binary_quantize(...)` (compact coarse
retrieval). Those land in the [Prove rerank](/10-act-1-the-boutique/03-prove-rerank/) page.

---

## What you've seen

- A **vector column** is just a typed Postgres column. No magic.
- The **`<=>` operator** is the single primitive every retrieval tool
  in this lab eventually calls.
- The **HNSW index** is what makes it sub-millisecond at catalog
  scale. The Aurora vs. RDS choice does not change any of these
  three statements — the extension behaves identically on both.

:::alert{type="success"}
Next: meet Marco and watch where the stub breaks.

[Act I · Meet Marco →](/10-act-1-the-boutique/01-meet-marco/)
:::
