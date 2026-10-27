\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off
\x on
SET client_min_messages = warning;

-- Lab 1B: what Anna's latest search was asked to keep, and what it kept.
--
-- Every catalog search writes one row to pellier.retrieval_receipts. Its
-- retrieval_config holds the request as the Catalog agent asked for it; its
-- hard_constraints and exclusions columns hold what the search actually applied;
-- relaxations records a retry and the soft tags it dropped. This prints her
-- latest turn's receipt, the retry's when one ran, as one record.
-- No model is called and nothing changes.
--
-- Supplied and read-only. Run:
--   psql -f workshop/lab-1-receipt.sql

WITH newest AS (
    SELECT receipt_id, turn_id
      FROM pellier.retrieval_receipts
     WHERE session_id LIKE 'persona-anna-%'
     ORDER BY receipt_id DESC
     LIMIT 1
)
SELECT r.receipt_id,
       r.retrieval_config->'requested'->'hard_constraints' AS asked_limits,
       r.retrieval_config->'requested'->'exclusions' AS asked_exclusions,
       r.hard_constraints AS kept_limits,
       r.exclusions AS kept_exclusions,
       r.relaxations->0->>'step' AS relaxation,
       r.relaxations->0->'dropped' AS dropped
  FROM pellier.retrieval_receipts r, newest
 WHERE r.session_id LIKE 'persona-anna-%'
   AND (r.receipt_id = newest.receipt_id OR r.turn_id = newest.turn_id)
 ORDER BY jsonb_array_length(r.relaxations) > 0 DESC, r.receipt_id DESC
 LIMIT 1;
