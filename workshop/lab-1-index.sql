\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off \pset border 1 \pset linestyle ascii \pset expanded off

-- Lab 1, Go deeper: does Aurora use the HNSW index, and what does a filter do to it?
--
-- pellier.product_catalog carries two HNSW indexes on its embeddings
-- (scripts/migrations/001_schema.sql): product_catalog_embedding_hnsw over all
-- 50,000 rows, and product_catalog_visible_hnsw over the 1,000 photographed
-- products the storefront shows. An index is a scale decision: inspect the actual
-- plan, whose choice depends on selectivity, table statistics and planner costs,
-- and compare approximate retrieval with an exact scan on the same data.
--
-- When an HNSW index is used, pgvector applies the WHERE clause to the rows the
-- graph returns, nearest first. With hnsw.iterative_scan off it stops after one
-- pass of hnsw.ef_search candidates (40), so a selective filter can leave fewer
-- rows than the LIMIT asked for. An iterative scan keeps walking the graph until
-- the LIMIT or a scan limit is reached. Pellier uses strict_order, so returned
-- candidates come back in exact distance order: the vector branch's ranks feed RRF.
--
-- The search, in Anna's terms: gifts like the Linen Photo Album, $35 or less,
-- no candles, top 20. The album's own embedding is the query vector, so nothing
-- calls Bedrock. The count without iterative scan depends on the graph pgvector
-- built, so counts and recall can differ from one deployment to the next.
--
-- The second run keeps only photographed products. Steps 1 to 4 write that rule as
-- "imgUrl" <> '', which the planner cannot match to the partial index, so they
-- measure the 50,000-row graph. Step 5 writes it exactly as the storefront does,
-- NULLIF(btrim("imgUrl"), '') IS NOT NULL: the partial index's own predicate.
--
-- This file is supplied and read-only. Everything runs in one transaction that
-- is rolled back, and enable_seqscan is turned off inside it only to force an
-- index for the demonstration; an application should never do that. Run:
--   psql -f workshop/lab-1-index.sql
--   psql -v storefront_only=on -f workshop/lab-1-index.sql

-- Default: measure the full scale dataset. The second run uses the storefront filter.
\if :{?storefront_only}
\else
  \set storefront_only off
\endif

SET client_min_messages TO warning;
BEGIN READ ONLY;
SET LOCAL hnsw.ef_search = 40;
SET LOCAL hnsw.iterative_scan = off;

SELECT count(*) AS total_products,
       count(*) FILTER (WHERE NULLIF(btrim("imgUrl"), '') IS NOT NULL) AS photographed_products,
       CASE WHEN :'storefront_only'::boolean THEN 'Photographed storefront subset'
            ELSE 'Full scale dataset' END AS scope
  FROM pellier.product_catalog
\gset lab_1_

SELECT (SELECT count(*) FROM pellier.product_catalog
          WHERE price <= 35 AND NOT tags ? 'candle'
            AND (NOT :'storefront_only'::boolean OR "imgUrl" <> '')) AS eligible,
       (SELECT count(*) FROM pellier.product_catalog
          WHERE price <= 35 AND NOT tags ? 'candle'
            AND (NOT :'storefront_only'::boolean
                 OR NULLIF(btrim("imgUrl"), '') IS NOT NULL)) AS eligible_storefront,
       EXISTS (SELECT 1 FROM pellier.product_catalog
                WHERE name = 'Linen Photo Album' AND embedding IS NOT NULL) AS has_query
\gset lab_1_

\echo 'Lab 1, Go deeper: measure search on the 50,000-product catalog'
\echo 'Dataset  ' :lab_1_total_products 'real vectors;' :lab_1_photographed_products 'photographed products'
\echo 'Scope    ' :lab_1_scope
\echo 'Eligible ' :lab_1_eligible 'products after this run''s filters'
\echo 'Search    gifts like the Linen Photo Album, $35 or less, no candles, top 20'
\if :lab_1_has_query
\else
  \echo 'Observed  no Linen Photo Album with an embedding in pellier.product_catalog'
  \echo 'Next      this is not Pellier''s seeded catalog; this file is optional, so skip it.'
  \echo 'Lab 1 index check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 1 index check failed; see the lines above'; END $fail$;
\endif

\echo ''
\echo '1. The planner''s own choice'
\pset tuples_only on
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, COSTS OFF)
SELECT "productId" FROM pellier.product_catalog
 WHERE price <= 35 AND NOT tags ? 'candle'
   AND (NOT :'storefront_only'::boolean OR "imgUrl" <> '')
 ORDER BY embedding <=> (SELECT embedding FROM pellier.product_catalog
                          WHERE name = 'Linen Photo Album')
 LIMIT 20;
\pset tuples_only off

-- The exact top 20: an ORDER BY the index cannot serve, so every eligible row is scored.
\echo ''
\echo '2. Exact scan baseline: score every eligible vector'
\pset tuples_only on
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, COSTS OFF)
SELECT "productId" FROM pellier.product_catalog
 WHERE price <= 35 AND NOT tags ? 'candle'
   AND (NOT :'storefront_only'::boolean OR "imgUrl" <> '')
 ORDER BY (embedding <=> (SELECT embedding FROM pellier.product_catalog
                           WHERE name = 'Linen Photo Album')) + 0
 LIMIT 20;
\pset tuples_only off
SELECT count(*) AS exact_rows, array_agg("productId" ORDER BY d) AS exact_ids
  FROM (SELECT "productId",
               embedding <=> (SELECT embedding FROM pellier.product_catalog
                               WHERE name = 'Linen Photo Album') AS d
          FROM pellier.product_catalog
         WHERE price <= 35 AND NOT tags ? 'candle'
           AND (NOT :'storefront_only'::boolean OR "imgUrl" <> '')
         ORDER BY (embedding <=> (SELECT embedding FROM pellier.product_catalog
                                   WHERE name = 'Linen Photo Album')) + 0
         LIMIT 20) exact
\gset lab_1_

SET LOCAL enable_seqscan = off;
SET LOCAL hnsw.ef_search = 40;
SET LOCAL hnsw.iterative_scan = off;

\echo ''
\echo '3. Forced onto the HNSW index, iterative scan off'
\pset tuples_only on
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, COSTS OFF)
SELECT "productId" FROM pellier.product_catalog
 WHERE price <= 35 AND NOT tags ? 'candle'
   AND (NOT :'storefront_only'::boolean OR "imgUrl" <> '')
 ORDER BY embedding <=> (SELECT embedding FROM pellier.product_catalog
                          WHERE name = 'Linen Photo Album')
 LIMIT 20;
\pset tuples_only off

SELECT count(*) AS off_rows, coalesce(array_agg("productId"), ARRAY[]::text[]) AS off_ids
  FROM (SELECT "productId" FROM pellier.product_catalog
         WHERE price <= 35 AND NOT tags ? 'candle'
           AND (NOT :'storefront_only'::boolean OR "imgUrl" <> '')
         ORDER BY embedding <=> (SELECT embedding FROM pellier.product_catalog
                                  WHERE name = 'Linen Photo Album')
         LIMIT 20) hnsw_off
\gset lab_1_

SET LOCAL hnsw.iterative_scan = strict_order;

\echo ''
\echo '4. Same HNSW index and filters, strict_order'
\pset tuples_only on
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, COSTS OFF)
SELECT "productId" FROM pellier.product_catalog
 WHERE price <= 35 AND NOT tags ? 'candle'
   AND (NOT :'storefront_only'::boolean OR "imgUrl" <> '')
 ORDER BY embedding <=> (SELECT embedding FROM pellier.product_catalog
                          WHERE name = 'Linen Photo Album')
 LIMIT 20;
\pset tuples_only off

SELECT count(*) AS strict_rows, coalesce(array_agg("productId"), ARRAY[]::text[]) AS strict_ids
  FROM (SELECT "productId" FROM pellier.product_catalog
         WHERE price <= 35 AND NOT tags ? 'candle'
           AND (NOT :'storefront_only'::boolean OR "imgUrl" <> '')
         ORDER BY embedding <=> (SELECT embedding FROM pellier.product_catalog
                                  WHERE name = 'Linen Photo Album')
         LIMIT 20) hnsw_strict
\gset lab_1_

-- Step 5 runs only with storefront_only: the storefront's own predicate, so the
-- planner can prove the partial index covers every row the query may return.
\set lab_1_partial_rows 0
\set lab_1_partial_ids '{}'
\if :storefront_only
SET LOCAL hnsw.iterative_scan = off;

\echo ''
\echo '5. The storefront''s own predicate: the photographed-only index, iterative scan off'
\pset tuples_only on
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, COSTS OFF)
SELECT "productId" FROM pellier.product_catalog
 WHERE price <= 35 AND NOT tags ? 'candle'
   AND NULLIF(btrim("imgUrl"), '') IS NOT NULL
 ORDER BY embedding <=> (SELECT embedding FROM pellier.product_catalog
                          WHERE name = 'Linen Photo Album')
 LIMIT 20;
\pset tuples_only off

SELECT count(*) AS partial_rows,
       coalesce(array_agg("productId"), ARRAY[]::text[]) AS partial_ids
  FROM (SELECT "productId" FROM pellier.product_catalog
         WHERE price <= 35 AND NOT tags ? 'candle'
           AND NULLIF(btrim("imgUrl"), '') IS NOT NULL
         ORDER BY embedding <=> (SELECT embedding FROM pellier.product_catalog
                                  WHERE name = 'Linen Photo Album')
         LIMIT 20) hnsw_partial
\gset lab_1_
\endif

SELECT :lab_1_eligible >= 20 AS enough,
       :lab_1_off_rows < 20 AS short_list,
       :lab_1_strict_rows = 20 AS filled,
       :lab_1_eligible = :lab_1_eligible_storefront AS same_rows,
       format('2. exact scan: %s of 20 (%s products are $35 or less and not candles)',
              :lab_1_exact_rows, :lab_1_eligible) AS line_1,
       format('3. HNSW, iterative scan off: %s of 20; recall@20 %s%%', :lab_1_off_rows,
              round(100.0 * (SELECT count(*) FROM unnest(:'lab_1_off_ids'::text[]) AS ids(id)
                             WHERE id = ANY(:'lab_1_exact_ids'::text[]))
                    / nullif(:lab_1_exact_rows, 0), 1)) AS line_2,
       format('4. HNSW, strict_order: %s of 20; recall@20 %s%%; %s', :lab_1_strict_rows,
              round(100.0 * (SELECT count(*) FROM unnest(:'lab_1_strict_ids'::text[]) AS ids(id)
                             WHERE id = ANY(:'lab_1_exact_ids'::text[]))
                    / nullif(:lab_1_exact_rows, 0), 1),
              CASE WHEN :'lab_1_strict_ids' = :'lab_1_exact_ids'
                   THEN 'the exact 20 in the same order'
                   ELSE 'not the exact 20 in order' END) AS line_3,
       format('5. photographed-only index, iterative scan off: %s of 20; recall@20 %s%%',
              :lab_1_partial_rows,
              round(100.0 * (SELECT count(*) FROM unnest(:'lab_1_partial_ids'::text[]) AS ids(id)
                             WHERE id = ANY(:'lab_1_exact_ids'::text[]))
                    / nullif(:lab_1_exact_rows, 0), 1)) AS line_4
\gset lab_1_

ROLLBACK;

\echo ''
\echo 'Expected  1. the planner''s own choice; compare it with 2, the exact scan'
\echo '          3. HNSW with iterative scan off may return fewer than 20'
\echo '          4. with strict_order the same index returns all 20'
\if :storefront_only
  \echo '          5. the photographed-only index returns all 20 in one pass'
\endif
\echo 'Read      Execution Time, Buffers and Rows Removed by Filter in each plan above.'
\echo 'Recall    overlap with this run''s exact top 20; not recommendation quality.'
\echo 'Observed ' :lab_1_line_1
\echo '         ' :lab_1_line_2
\echo '         ' :lab_1_line_3
\if :storefront_only
  \echo '         ' :lab_1_line_4
\endif
\if :lab_1_short_list
\else
  \echo 'Note      the graph found every match in one pass this time; the filter is still why'
  \echo '          a single pass can come back short.'
\endif
\if :lab_1_same_rows
\else
  \echo 'Note      the two spellings of the photo rule select different rows here, so step 5'
  \echo '          measures a different set; this is not Pellier''s seeded catalog.'
\endif
\if :lab_1_enough
\else
  \echo 'Observed  fewer than 20 products are $35 or less and not candles, so no plan can return 20'
  \echo 'Next      this is not Pellier''s seeded catalog; this file is optional, so skip it.'
  \echo 'Lab 1 index check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 1 index check failed; see the lines above'; END $fail$;
\endif
\if :lab_1_filled
  \echo 'Lab 1 index check passed'
\else
  \echo 'Next      inspect pgvector version (0.8.0+), filter selectivity and hnsw scan limits.'
  \echo 'Lab 1 index check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 1 index check failed; see the lines above'; END $fail$;
\endif
