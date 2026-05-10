---
inclusion: fileMatch
fileMatchPattern: "**/*.sql,**/seed-database*,**/business_logic*,**/database*,**/hybrid_search*"
---

# Database Conventions

## Connection

- Cluster: `pellier-cluster` (Aurora Serverless v2)
- Secret: `pellier-db-secret` in Secrets Manager
- Schema: `pellier` (product_catalog, return_policies)
- Legacy schema: `bedrock_integration` (used by some existing queries)

## Tables

- `pellier.product_catalog` — ~1000 products with 1024-dim embeddings (Cohere Embed v4)
- `pellier.return_policies` — 21 rows (20 categories + default), seeded by bootstrap

## pgvector

- Extension: pgvector 0.8.0
- Index type: HNSW with `vector_cosine_ops`
- Operator: `<=>` (cosine distance) — lower is more similar
- Similarity: `1 - (embedding <=> query_embedding)`
- Iterative scan: `SET LOCAL hnsw.iterative_scan = 'relaxed_order'` for filtered queries

## Query Patterns

- Always use parameterized queries (`%s` placeholders, never f-strings for values)
- Use CTE for embedding: `WITH query_embedding AS (SELECT %s::vector as emb)`
- Filter on `quantity > 0` for in-stock products
- Use `ILIKE` with `%` wildcards for category matching
