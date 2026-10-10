# Contract 1: filter before ranking

Hard constraints are SQL predicates on every candidate branch, before `LIMIT`.
Ranking orders eligible rows; it never decides eligibility.

## Template: two branches, same predicates

Both branches take the same `extra_clauses` (price cap, in-stock, exclusions,
tenant) and apply them inside the query. Parameters are bound, never
interpolated. From Pellier's `services/store_tools.py`:

```sql
-- Vector branch: nearest by meaning, among eligible rows only.
WITH query_embedding AS (SELECT %s::vector AS emb)
SELECT product_id, name, price, quantity,
       1 - (embedding <=> (SELECT emb FROM query_embedding)) AS similarity
  FROM catalog
 WHERE image_url IS NOT NULL
   AND price <= %s              -- hard limit
   AND quantity > 0             -- hard limit
   AND category <> %s           -- exclusion
 ORDER BY embedding <=> (SELECT emb FROM query_embedding)
 LIMIT %s;

-- Full-text branch: cover-density rank, among the same eligible rows.
WITH q AS (SELECT to_tsquery('english', %s) AS ts_q)
SELECT product_id, name, price, quantity,
       ts_rank_cd(description_tsv, q.ts_q) AS fts_rank_score
  FROM catalog CROSS JOIN q
 WHERE image_url IS NOT NULL
   AND description_tsv @@ q.ts_q
   AND price <= %s
   AND quantity > 0
   AND category <> %s
 ORDER BY fts_rank_score DESC
 LIMIT %s;
```

If a predicate exists on one branch and not the other, the fused list can
contain an ineligible row. That is the most common defect in hybrid search.

## Template: reciprocal rank fusion you can recompute

Fuse by rank, not by score. Scores from different rankers are not comparable;
ranks are. A product present in both lists outscores one ranked first in only
one, which is the point.

```sql
-- k = 60. A rank is NULL when the product was not in that list, and a
-- missing rank adds nothing: apply the default to the term, not the rank.
coalesce(1.0 / (60 + vector_rank), 0)
  + coalesce(1.0 / (60 + full_text_rank), 0) AS rrf_score
```

Record the two ranks and the fused score per result (Pellier writes a
`retrieval_receipts` row per search with `vector_ranks`, `lexical_ranks`
and `rrf_scores` as JSONB). Then anyone can recompute the ranking later and
compare it with what was recorded. The check is in `proof-queries.sql`.

Rerank only the top of the fused list (Pellier: Cohere Rerank 3.5 on the top
15). The reranker reorders; it still cannot admit a row the SQL excluded.

## Template: a fallback that keeps the constraints

When the strict plan returns too little, relax a *preference*, never a
*constraint*. Copy the plan and change only the soft fields:

```python
@dataclass(frozen=True)
class SearchPlan:
    query: str
    max_price: float | None        # hard
    in_stock_only: bool            # hard
    exclude: tuple[str, ...]       # hard
    soft_tags: tuple[str, ...]     # soft: may be dropped on retry

def relaxed(plan: SearchPlan) -> SearchPlan:
    # dataclasses.replace keeps every field you do not name.
    return dataclasses.replace(plan, soft_tags=())
```

The defect to look for: `SearchPlan(query=plan.query, soft_tags=())`, which
takes the default for every field not passed, including the hard ones. Record
which relaxation was applied (`drop_tags`) alongside the receipt so the retry
is explainable.

## pgvector under a filter

With a small table the planner may skip the HNSW index and scan exactly; that
is correct, not a defect. At scale, a filtered HNSW scan can return fewer than
`LIMIT` rows because the index returns a fixed candidate set before the filter
applies. With pgvector 0.8 and later:

```sql
SET hnsw.iterative_scan = strict_order;   -- keep scanning until LIMIT is met, in distance order
```

Use `strict_order` when downstream fusion depends on ranks (it does here).
`relaxed_order` is faster and acceptable when only the set matters.

## Review questions

- Can a retry or a fallback ever return a row the user's constraints exclude?
- Can you recompute why this row ranked here from recorded values?
- Does any branch have a predicate the other branches lack?
