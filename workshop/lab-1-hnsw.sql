\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off

-- Lab 1, optional: does Aurora use the HNSW index, and what does a filter do to it?
--
-- pellier.product_catalog carries an HNSW index on its embeddings
-- (product_catalog_embedding_hnsw, scripts/migrations/001_schema.sql). An index
-- is a scale decision. At a hundred products the planner usually reads every
-- row and computes each distance exactly: cheaper than walking the graph, and
-- the exact answer.
--
-- When the index is used, pgvector applies the WHERE clause to the rows the
-- graph returns, nearest first. With hnsw.iterative_scan off it stops after one
-- pass of hnsw.ef_search candidates (40), so a selective filter can leave fewer
-- rows than the LIMIT asked for. An iterative scan keeps walking the graph until
-- the LIMIT is met. Pellier uses strict_order, so the rows also come back in
-- exact distance order: the vector branch's ranks feed RRF.
--
-- The search, in Anna's terms: gifts like the Linen Photo Album, $35 or less,
-- no candles, top 20. The album's own embedding is the query vector, so nothing
-- calls Bedrock. The count without iterative scan depends on the graph pgvector
-- built, so it can differ from one deployment to the next; it stays below 20.
--
-- This check is supplied and read-only. Everything runs in one transaction that
-- is rolled back, and enable_seqscan is turned off inside it only to force the
-- index for the demonstration; an application should never do that. Run:
--   psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-1-hnsw.sql

SET client_min_messages TO warning;
BEGIN READ ONLY;

SELECT (SELECT count(*) FROM pellier.product_catalog
          WHERE price <= 35 AND NOT tags ? 'candle') AS eligible,
       EXISTS (SELECT 1 FROM pellier.product_catalog
                WHERE name = 'Linen Photo Album' AND embedding IS NOT NULL) AS has_query
\gset lab_1_

\echo 'Lab 1, optional: does Aurora use the HNSW index?'
\echo 'Search    gifts like the Linen Photo Album, $35 or less, no candles, top 20'
\if :lab_1_has_query
\else
  \echo 'Observed  no Linen Photo Album with an embedding in pellier.product_catalog'
  \echo 'Next      this is not Pellier''s seeded catalog; the check is optional, so skip it.'
  \echo 'Lab 1 index check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 1 index check failed; see the lines above'; END $fail$;
\endif

\echo ''
\echo '1. The planner''s own choice'
\pset tuples_only on
EXPLAIN (COSTS OFF)
SELECT "productId" FROM pellier.product_catalog
 WHERE price <= 35 AND NOT tags ? 'candle'
 ORDER BY embedding <=> (SELECT embedding FROM pellier.product_catalog
                          WHERE name = 'Linen Photo Album')
 LIMIT 20;
\pset tuples_only off

-- The exact top 20: an ORDER BY the index cannot serve, so every row is scored.
SELECT count(*) AS exact_rows, array_agg("productId" ORDER BY d) AS exact_ids
  FROM (SELECT "productId",
               embedding <=> (SELECT embedding FROM pellier.product_catalog
                               WHERE name = 'Linen Photo Album') AS d
          FROM pellier.product_catalog
         WHERE price <= 35 AND NOT tags ? 'candle'
         ORDER BY (embedding <=> (SELECT embedding FROM pellier.product_catalog
                                   WHERE name = 'Linen Photo Album')) + 0
         LIMIT 20) exact
\gset lab_1_

SET LOCAL enable_seqscan = off;
SET LOCAL hnsw.ef_search = 40;
SET LOCAL hnsw.iterative_scan = off;

\echo ''
\echo '2. Forced onto the HNSW index, iterative scan off'
\pset tuples_only on
EXPLAIN (COSTS OFF)
SELECT "productId" FROM pellier.product_catalog
 WHERE price <= 35 AND NOT tags ? 'candle'
 ORDER BY embedding <=> (SELECT embedding FROM pellier.product_catalog
                          WHERE name = 'Linen Photo Album')
 LIMIT 20;
\pset tuples_only off

SELECT count(*) AS off_rows
  FROM (SELECT "productId" FROM pellier.product_catalog
         WHERE price <= 35 AND NOT tags ? 'candle'
         ORDER BY embedding <=> (SELECT embedding FROM pellier.product_catalog
                                  WHERE name = 'Linen Photo Album')
         LIMIT 20) hnsw_off
\gset lab_1_

SET LOCAL hnsw.iterative_scan = strict_order;

SELECT count(*) AS strict_rows, array_agg("productId") AS strict_ids
  FROM (SELECT "productId" FROM pellier.product_catalog
         WHERE price <= 35 AND NOT tags ? 'candle'
         ORDER BY embedding <=> (SELECT embedding FROM pellier.product_catalog
                                  WHERE name = 'Linen Photo Album')
         LIMIT 20) hnsw_strict
\gset lab_1_

SELECT :lab_1_eligible >= 20 AS enough,
       :lab_1_off_rows < 20 AS short_list,
       :lab_1_strict_rows = 20 AS filled,
       format('1. exact scan: %s of 20 (%s products are $35 or less and not candles)',
              :lab_1_exact_rows, :lab_1_eligible) AS line_1,
       format('2. HNSW, iterative scan off: %s of 20', :lab_1_off_rows) AS line_2,
       format('3. HNSW, strict_order: %s of 20, %s', :lab_1_strict_rows,
              CASE WHEN :'lab_1_strict_ids' = :'lab_1_exact_ids'
                   THEN 'the exact 20 in the same order'
                   ELSE 'not the exact 20 in order' END) AS line_3
\gset lab_1_

ROLLBACK;

\echo ''
\echo 'Expected  1. no index at this size: every row scored exactly'
\echo '          2. the HNSW index with iterative scan off returns fewer than 20'
\echo '          3. with strict_order the same index returns all 20'
\echo 'Observed ' :lab_1_line_1
\echo '         ' :lab_1_line_2
\echo '         ' :lab_1_line_3
\if :lab_1_short_list
\else
  \echo 'Note      the graph found every match in one pass this time; the filter is still why'
  \echo '          a single pass can come back short.'
\endif
\if :lab_1_enough
\else
  \echo 'Observed  fewer than 20 products are $35 or less and not candles, so no plan can return 20'
  \echo 'Next      this is not Pellier''s seeded catalog; the check is optional, so skip it.'
  \echo 'Lab 1 index check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 1 index check failed; see the lines above'; END $fail$;
\endif
\if :lab_1_filled
  \echo 'Lab 1 index check passed'
\else
  \echo 'Next      this cluster''s pgvector does not support iterative scans (0.8.0 or later).'
  \echo 'Lab 1 index check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 1 index check failed; see the lines above'; END $fail$;
\endif
