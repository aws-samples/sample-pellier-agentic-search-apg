\set ON_ERROR_STOP on

-- Lab 2 task artifact (Task 2A): RECONSTRUCT AND VERIFY RRF.
--
-- Complete the fusion expression between the markers, then check your
-- arithmetic against the score the application already recorded for this
-- turn. This reads a retrieval receipt; it does not change the ranking the
-- live application performs. That is the point: you are proving you can
-- derive the recorded score from the two ranks beside it, which is what
-- makes the receipt auditable rather than something to take on faith.
--
-- Run with:
--   psql -X -v ON_ERROR_STOP=1 -P pager=off \
--     -v receipt_high_water="$RECEIPT_HIGH_WATER" \
--     -v comparison_id="$COMPARISON_ID" \
--     -f workshop/lab-2-rrf.sql

DROP TABLE IF EXISTS pg_temp.lab_2_fusion;

-- The exact comparison ID selects the request you captured. The high-water
-- mark excludes earlier runs, and the source tag excludes Storefront receipts.
-- A newer comparison must not replace this request while you read the guide.
CREATE TEMP TABLE lab_2_fusion AS
WITH receipt AS (
  SELECT *
    FROM pellier.retrieval_receipts
   WHERE receipt_id > :'receipt_high_water'::bigint
     AND turn_id = :'comparison_id'
     AND retrieval_config->>'source' = 'observatory-compare'
   ORDER BY receipt_id DESC
   LIMIT 1
)
SELECT keys.product_id,
       r.receipt_id,
       r.query_preview,
       (r.vector_ranks->>keys.product_id)::int AS vector_rank,
       (r.lexical_ranks->>keys.product_id)::int AS lexical_rank,
       -- === WORKSHOP · PostgreSQL RRF · fusion expression: START ===
       coalesce(
         1.0 / (60 + (r.vector_ranks->>keys.product_id)::int),
         0
       ) + coalesce(
         1.0 / (60 + (r.lexical_ranks->>keys.product_id)::int),
         0
       ) AS recomputed_rrf,
       -- === WORKSHOP · PostgreSQL RRF · fusion expression: END ===
       (r.rrf_scores->>keys.product_id)::numeric AS recorded_rrf
  FROM receipt r
 CROSS JOIN LATERAL jsonb_object_keys(
   r.vector_ranks || r.lexical_ranks
 ) AS keys(product_id);

SELECT coalesce(max(receipt_id)::text, '(none)') AS lab_2_receipt_id,
       coalesce(
         max(query_preview),
         '(no comparison receipt written since the high-water mark)'
       ) AS lab_2_query
  FROM lab_2_fusion
\gset

\echo 'Lab 2 fusion source: receipt' :lab_2_receipt_id
\echo 'Lab 2 fusion source query:' :lab_2_query

SELECT product_id,
       vector_rank,
       lexical_rank,
       round(recomputed_rrf, 6) AS recomputed_rrf,
       round(recorded_rrf, 6) AS recorded_rrf,
       abs(recorded_rrf - recomputed_rrf) <= 0.000001 AS matches_receipt
  FROM lab_2_fusion
 ORDER BY recorded_rrf DESC NULLS LAST;

SELECT coalesce(
         count(*) > 0
         AND bool_and(
           recorded_rrf IS NOT NULL
           AND recomputed_rrf IS NOT NULL
           AND abs(recorded_rrf - recomputed_rrf) <= 0.000001
         ),
         false
       ) AS fusion_matches
  FROM lab_2_fusion
\gset

\if :fusion_matches
  \echo 'Lab 2 RRF build passed'
\else
  \echo 'Lab 2 RRF build failed: complete the fusion expression'
  DO $fail$ BEGIN RAISE EXCEPTION 'lab worksheet failed; see the line above'; END $fail$;
\endif
