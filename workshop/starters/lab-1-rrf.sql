\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off

-- Lab 1, Task 1A: recompute Anna's recorded ranking.
--
-- Anna's latest search wrote a retrieval receipt. For every product it ranked,
-- the receipt holds the product's place in the vector (meaning) list, its
-- place in the full-text (words) list, and the fused score the application
-- recorded. Write the fusion expression between the markers, then run this
-- file. It recomputes each product's score from its two ranks and compares it
-- with the recorded one. Nothing here changes how the application ranks: you
-- are proving the recorded score can be derived from the ranks beside it.
--
-- Run with:
--   psql -X -P pager=off -f workshop/lab-1-rrf.sql
--
-- The receipt is the newest one written in Anna's session. Choosing Anna on
-- the home page starts that session, named persona-anna-...

SET client_min_messages TO warning;
DROP TABLE IF EXISTS pg_temp.lab_1_ranks;
DROP TABLE IF EXISTS pg_temp.lab_1_fusion;

-- Anna's newest search receipt, one row per product it fused. A rank is NULL
-- when the product was not in that list.
CREATE TEMP TABLE lab_1_ranks AS
WITH receipt AS (
  SELECT receipt_id, session_id, query_preview, vector_ranks, lexical_ranks, rrf_scores
    FROM pellier.retrieval_receipts
   WHERE session_id LIKE 'persona-anna-%'
     AND rrf_scores <> '{}'::jsonb
   ORDER BY receipt_id DESC
   LIMIT 1
)
SELECT r.receipt_id,
       r.session_id,
       r.query_preview,
       keys.product_id,
       (r.vector_ranks->>keys.product_id)::int AS vector_rank,
       (r.lexical_ranks->>keys.product_id)::int AS full_text_rank,
       (r.rrf_scores->>keys.product_id)::numeric AS recorded_rrf
  FROM receipt r
 CROSS JOIN LATERAL jsonb_object_keys(r.rrf_scores) AS keys(product_id);

-- Your build: each product's fused score, from its two ranks and k = 60.
CREATE TEMP TABLE lab_1_fusion AS
SELECT product_id,
       vector_rank,
       full_text_rank,
       -- === WORKSHOP - PostgreSQL RRF - fusion expression: START ===
       1.0 / (60 + coalesce(vector_rank, 0))
         + 1.0 / (60 + coalesce(full_text_rank, 0)) AS recomputed_rrf,
       -- === WORKSHOP - PostgreSQL RRF - fusion expression: END ===
       recorded_rrf
  FROM lab_1_ranks;

SELECT coalesce(max(receipt_id)::text, 'none') AS lab_1_receipt,
       coalesce(max(session_id), 'none') AS lab_1_session,
       coalesce(max(query_preview), '') AS lab_1_query,
       count(*) > 0 AS lab_1_has_receipt
  FROM lab_1_ranks
\gset

SELECT count(*) AS lab_1_products,
       count(*) FILTER (
         WHERE recomputed_rrf IS NOT NULL
           AND abs(recorded_rrf - recomputed_rrf) <= 0.000001
       ) AS lab_1_matched,
       count(*) FILTER (WHERE vector_rank IS NULL OR full_text_rank IS NULL)
         AS lab_1_one_list
  FROM lab_1_fusion
\gset

\echo 'Lab 1A: recompute Anna''s recorded ranking from its two ranks'

\if :lab_1_has_receipt
  \echo 'Evidence  pellier.retrieval_receipts receipt' :lab_1_receipt 'in session' :lab_1_session
  \echo '          query:' :'lab_1_query'
  \echo '          products in one list only:' :lab_1_one_list 'of' :lab_1_products
  \echo ''
  SELECT product_id AS product,
         coalesce(vector_rank::text, '-') AS vector_rank,
         coalesce(full_text_rank::text, '-') AS full_text_rank,
         round(recorded_rrf, 6) AS expected_recorded,
         round(recomputed_rrf, 6) AS observed_yours,
         CASE
           WHEN recomputed_rrf IS NULL THEN 'differs: no score'
           WHEN abs(recorded_rrf - recomputed_rrf) <= 0.000001 THEN 'matches'
           ELSE 'differs'
         END AS verdict
    FROM lab_1_fusion
   ORDER BY recorded_rrf DESC, product_id;
  \echo 'Expected  every recomputed score equals the score receipt' :lab_1_receipt 'recorded'
  \echo 'Observed ' :lab_1_matched 'of' :lab_1_products 'scores match'
  SELECT :lab_1_matched = :lab_1_products AS lab_1_passed \gset
  \if :lab_1_passed
    \echo 'Lab 1A check passed'
  \else
    \echo 'Next      pick a row marked differs and compute it by hand from its two ranks.'
    \echo '          A rank shown as - means the product was not in that list.'
    \echo 'Lab 1A check failed'
    DO $fail$ BEGIN RAISE EXCEPTION 'Lab 1A check failed; see the lines above'; END $fail$;
  \endif
\else
  \echo 'Expected  a search receipt written in a session of Anna''s'
  \echo 'Observed  none yet: no pellier.retrieval_receipts row has a session starting persona-anna-'
  \echo 'Next      choose Anna on the home page, send her request in Ask Pellier,'
  \echo '          then run this again.'
  \echo 'Lab 1A check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 1A check failed; see the lines above'; END $fail$;
\endif
