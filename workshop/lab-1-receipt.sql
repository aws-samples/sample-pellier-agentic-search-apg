\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off \pset border 2 \pset linestyle unicode \pset expanded off \pset format wrapped
SET client_min_messages = warning;

-- Lab 1B: what Anna's latest search was asked to keep, and what it kept.
--
-- Every catalog search writes one row to pellier.retrieval_receipts. Its
-- retrieval_config holds the request as the Catalog agent asked for it; its
-- hard_constraints and exclusions columns hold what the search actually applied;
-- relaxations records a retry and the soft tags it dropped. This prints her
-- latest turn's receipt, the retry's when one ran, as a small table: one row per
-- requirement, what she asked for beside what the retry kept, and the words the
-- retry dropped. When her latest turn records no retry, there is nothing to
-- compare, so it says so and names the send that makes one. No model is called and
-- nothing changes; the view below lives only in this session.
--
-- Supplied and read-only. Run:
--   psql -f workshop/lab-1-receipt.sql

-- The checker reads the terminal's turn record and the Lab 1 reset time. Share those
-- two inputs with psql. PostgreSQL does the receipt lookup and all the comparisons.
\set lab_1_context `python3 -c 'from scripts.lab1_retry import receipt_context; print(receipt_context())'`
\if :SHELL_ERROR
  DO $$ BEGIN RAISE EXCEPTION 'Run the receipt command from the workshop repository root.'; END $$;
\endif
SELECT (context->>'unfinished')::boolean AS lab_1_unfinished,
       coalesce(context->>'turn', '') AS lab_1_turn,
       coalesce(context->>'since', '-infinity') AS lab_1_since
  FROM (SELECT :'lab_1_context'::jsonb AS context) state \gset

CREATE TEMP VIEW lab_1_receipt AS
WITH eligible AS NOT MATERIALIZED (
    SELECT * FROM pellier.retrieval_receipts
     WHERE NOT :'lab_1_unfinished'::boolean
       AND session_id LIKE 'persona-anna-%'
       AND created_at >= :'lab_1_since'::timestamptz
), newest AS (
    SELECT receipt_id, turn_id FROM eligible
     ORDER BY receipt_id DESC
     LIMIT 1
)
SELECT jsonb_typeof(r.retrieval_config->'requested') = 'object' AS requested_recorded,
       r.retrieval_config->'requested'->'hard_constraints' AS asked,
       r.hard_constraints AS kept,
       r.retrieval_config->'requested'->'exclusions' AS asked_out,
       r.exclusions AS kept_out,
       r.relaxations->0->'dropped' AS dropped,
       jsonb_array_length(coalesce(r.relaxations, '[]'::jsonb)) > 0 AS retried
  FROM eligible r, newest
 WHERE CASE WHEN :'lab_1_turn' = ''
            THEN r.receipt_id = newest.receipt_id OR r.turn_id = newest.turn_id
            ELSE r.turn_id = :'lab_1_turn' END
 ORDER BY jsonb_array_length(r.relaxations) > 0 DESC, r.receipt_id DESC
 LIMIT 1;

SELECT coalesce(bool_or(requested_recorded AND retried), false) AS lab_1_compare,
       count(*) > 0 AS lab_1_found,
       count(*) > 0 AND NOT coalesce(bool_or(requested_recorded), false) AS lab_1_unknown,
       :'lab_1_turn' <> '' AS lab_1_by_turn,
       count(*) = 0 AND :'lab_1_turn' = '' AND NOT :'lab_1_unfinished'::boolean AS lab_1_first
  FROM lab_1_receipt \gset
\if :lab_1_compare
  \echo 'Lab 1B: the retry must keep Anna''s requirements and her exclusion'
  \echo ''
  SELECT "Requirement", "Anna asked for", "The retry kept" FROM (
  SELECT 1 AS ord, 'In stock only' AS "Requirement",
         CASE WHEN (asked->>'in_stock_only')::boolean THEN 'yes' ELSE 'no' END AS "Anna asked for",
         CASE WHEN (kept->>'in_stock_only')::boolean THEN 'yes' ELSE 'no' END AS "The retry kept"
    FROM lab_1_receipt
  UNION ALL
  SELECT 2, 'Price limit',
         coalesce(regexp_replace(to_char((asked->>'price_max_usd')::numeric, 'FM$999990.00'),
                                 '\.00$', ''), 'none'),
         coalesce(regexp_replace(to_char((kept->>'price_max_usd')::numeric, 'FM$999990.00'),
                                 '\.00$', ''), 'none')
    FROM lab_1_receipt
  UNION ALL
  SELECT 3, 'Excluded',
         coalesce((SELECT string_agg(e, ', ') FROM jsonb_array_elements_text(asked_out) e),
                  'nothing'),
         coalesce((SELECT string_agg(e, ', ') FROM jsonb_array_elements_text(kept_out) e),
                  'nothing')
    FROM lab_1_receipt
  UNION ALL
  SELECT 4, 'Category',
         coalesce((SELECT string_agg(e, ', ') FROM jsonb_array_elements_text(asked->'categories') e),
                  'any'),
         coalesce((SELECT string_agg(e, ', ') FROM jsonb_array_elements_text(kept->'categories') e),
                  'any')
    FROM lab_1_receipt
   WHERE jsonb_array_length(coalesce(asked->'categories', '[]')) > 0
      OR jsonb_array_length(coalesce(kept->'categories', '[]')) > 0
  ) rows ORDER BY ord;
  SELECT coalesce(string_agg(e, ', '), '') AS lab_1_dropped, count(e) > 0 AS lab_1_words_dropped
    FROM lab_1_receipt LEFT JOIN LATERAL jsonb_array_elements_text(dropped) e ON true
  \gset
  \if :lab_1_words_dropped
    \echo 'The retry dropped the words:' :lab_1_dropped
  \else
    \echo 'The retry dropped no words.'
  \endif
\else
  \if :lab_1_unfinished
    \echo 'There is no completed turn recorded for Anna''s latest send.'
  \elif :lab_1_unknown
    \echo 'This receipt did not record Anna''s original requirements.'
  \elif :lab_1_found
    \echo 'No retry ran for this request.'
  \elif :lab_1_by_turn
    \echo 'There is no search receipt for Anna''s latest request.'
  \else
    \echo 'No receipt for Anna yet.'
  \endif
  \if :lab_1_first
    \echo 'Next: send her full request, then read this receipt.'
  \else
    \echo 'Next: send her full request again, then read this receipt.'
  \endif
  \echo '      uv run scripts/lab_run.py send --lab 1 --task 1B'
\endif
