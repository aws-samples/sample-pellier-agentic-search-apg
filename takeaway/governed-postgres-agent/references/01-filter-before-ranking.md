# Contract 1: preserve requirements through retrieval

**Question:** Can a search or retry return something the caller ruled out?

**Takeaway:** Ranking chooses among eligible records. A fallback can relax a
preference only when the application's contract permits it.

## Trace the requirements

Find where the request becomes structured constraints, where each candidate
branch uses them, and what changes on retry. In Pellier, Anna's budget,
availability and exclusions remain hard requirements while gift tags may be
relaxed. Preserve the original requirements separately from the executed
plan; comparing results only with the retry's plan would miss dropped limits.

For SQL retrieval, place eligibility predicates before the candidate limit:

```sql
SELECT product_id, name, price
  FROM catalog
 WHERE price <= $1 AND quantity > 0 AND category <> ALL ($2::text[])
 ORDER BY embedding <=> $3::vector
 LIMIT $4;
```

This is an adaptation pattern, not a statement for the supplied fixture,
which has no vectors. Parameter values and table names belong to the target
application. Check every candidate branch and every fallback. If an
application filters later, inspect replenishment and result-count behavior
as well as eligibility; the position of a filter alone is not a verdict.

A copied plan that changes only permitted soft fields is easier to review:

```python
return dataclasses.replace(plan, soft_tags=())
```

Test the behavior, not just this implementation choice. A newly constructed
plan can also be correct if it explicitly preserves every requirement.

## Test both the result and the evidence

Use a request with known eligible and ineligible records. Force the fallback
rather than hoping the model chooses it. Record the request id, original
requirements, executed plan, returned ids and the catalog snapshot used for
verification. Check that:

- the expected request and receipt exist;
- the positive fixture returns at least one eligible record;
- every returned id resolves to a record and obeys the original requirements;
- missing constraint fields, missing products and missing receipts cannot pass.

Query `retrieval` in [proof-queries.sql](proof-queries.sql) demonstrates this
on the supplied fixture. Live stock or prices may change after a search;
reconstruct the search-time facts or identify that limitation explicitly.

## Ranking and approximate search are separate questions

Pellier uses reciprocal rank fusion, with `k = 60`, then reranking. If the
application uses RRF, reconstruct its scores from the actual configured `k`
and recorded ranks. Appearing in two lists helps a result; it does not always
outscore the first result from one list. Other ranking methods need their own
checks. Correct arithmetic does not establish relevance or eligibility.

With pgvector, `LIMIT` requests an output count. `hnsw.ef_search` controls the
initial search candidate list. Filtering an approximate scan can leave fewer
results. Iterative scanning can search further, but stops at configured scan
or resource limits. `strict_order` orders the results by distance; it does
not guarantee exact recall or a full result count.

For a representative data set, compare an exact baseline with HNSW with and
without iterative scanning. For the baseline, disable index and bitmap scans
inside a transaction and verify the actual plan with `EXPLAIN`. Merely setting
`enable_seqscan = on` does not force a sequential scan. For HNSW, inspect the
plan rather than assuming `enable_seqscan = off` selected that index. Compare
eligible counts, returned ids, recall and latency. Roll back the settings.

See [pgvector's iterative scan documentation](https://github.com/pgvector/pgvector#iterative-index-scans)
and [PostgreSQL planner controls](https://www.postgresql.org/docs/current/runtime-config-query.html).
