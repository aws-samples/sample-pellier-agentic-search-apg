\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off

-- Wrap-up: rebuild Jessica's store credit, from her request to the row.
--
-- The model's account of a conversation can drift; the database's cannot. Every
-- step of Lab 4 left a row, and each row names the next one:
--   her request (approvals, store_credit_request)  names the review that answered it
--   the review (approvals, give_store_credit)     its id and hash make the write key
--   the write key                                  is on the audit row and the credit
--   the credit (store_credits)                     is the id her returned orders carry
-- This worksheet follows those links with joins only, prints the story in time
-- order, and checks that every link finds the row it should.
--
-- Supplied and read-only; it never writes:
--   psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/wrap-up-reconstruct.sql

SET client_min_messages TO warning;

-- Start from Jessica's newest credit and walk back. The key is derived from the
-- review exactly as the Operator derives it, so a key that drifted would find
-- no audit row and no credit, and the check below would say so.
WITH credit AS (
    SELECT * FROM pellier.store_credits
     WHERE customer_id = 'CUST-JESSICA'
     ORDER BY credit_id DESC
     LIMIT 1
), review AS (
    SELECT a.*, 'operator-review:' || a.id || ':' || left(a.action_hash, 32) AS write_key
      FROM pellier.approvals a JOIN credit c ON c.approval_id = a.id
     WHERE a.tool = 'give_store_credit'
), request AS (
    SELECT q.* FROM pellier.approvals q JOIN review r ON q.answered_by_review_id = r.id
     WHERE q.tool = 'store_credit_request'
     ORDER BY q.id
     LIMIT 1
)
SELECT (SELECT count(*) FROM credit) = 1 AS has_credit,
       coalesce((SELECT credit_id::text FROM credit), '') AS credit_id,
       coalesce((SELECT id::text FROM review), '') AS review_id,
       coalesce((SELECT id::text FROM request), '') AS request_id,
       coalesce((SELECT source_turn_id FROM request), '') AS request_turn,
       coalesce((SELECT write_key FROM review), '') AS write_key,
       coalesce((SELECT write_key = c.idempotency_key FROM review, credit c), false) AS key_matches,
       (SELECT count(*) FROM pellier.approvals q JOIN review r ON q.answered_by_review_id = r.id
         WHERE q.tool = 'store_credit_request') AS requests,
       (SELECT count(*) FROM pellier.tool_audit t JOIN request q ON t.session_id = q.source_turn_id
         WHERE t.tool = 'ask_a_person') AS handoff_rows,
       (SELECT count(*) FROM pellier.tool_audit t JOIN review r
            ON t.args->>'idempotency_key' = r.write_key
         WHERE t.tool = 'give_store_credit') AS credit_audit_rows,
       (SELECT count(*) FROM pellier.store_credits s JOIN review r
            ON s.idempotency_key = r.write_key) AS credit_rows,
       (SELECT count(*) FROM pellier.orders o JOIN credit c ON o.store_credit_id = c.credit_id)
         AS credited_orders,
       coalesce((SELECT array_length(order_ids, 1) FROM review), 0) AS reviewed_orders,
       coalesce((SELECT (SELECT array_agg(o.id ORDER BY o.id) FROM pellier.orders o
                          WHERE o.store_credit_id = c.credit_id) = (SELECT array_agg(x ORDER BY x)
                          FROM unnest(r.order_ids) x)
                   FROM credit c, review r), false) AS orders_match
\gset wrap_

\echo 'Wrap-up: Jessica''s store credit, rebuilt from her request to the row'
\if :wrap_has_credit
\else
  \echo 'Observed  NOT YET: Jessica has no store credit'
  \echo 'Next      finish Lab 4 (Nadia approves and executes her review), then run this again.'
  \echo 'Wrap-up reconstruction failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Wrap-up reconstruction failed; see the lines above'; END $fail$;
\endif

-- The story, step by step. Each line names the row it comes from. The audit row
-- is written as the call returns, so its time can trail the credit it records.
WITH credit AS (
    SELECT * FROM pellier.store_credits WHERE credit_id = :'wrap_credit_id'::bigint
), review AS (
    SELECT * FROM pellier.approvals WHERE id = :'wrap_review_id'::bigint
), request AS (
    SELECT * FROM pellier.approvals WHERE id = nullif(:'wrap_request_id', '')::bigint
), story (step, at, what, evidence) AS (
    SELECT 1, requested_at, 'Jessica asked for a person about a store credit',
           'request ' || id || ', turn ' || left(coalesce(source_turn_id, '?'), 18)
      FROM request
    UNION ALL
    SELECT 2, t.created_at, 'ask_a_person ran in her turn (' || t.caller || ')',
           'tool_audit ' || t.audit_id
      FROM pellier.tool_audit t JOIN request q ON t.session_id = q.source_turn_id
     WHERE t.tool = 'ask_a_person'
    UNION ALL
    SELECT 3, requested_at, 'The investigation proposed ' || to_char((args->>'amount_cents')::int / 100.0,
           'FM$999990.00') || ' for orders ' || array_to_string(order_ids, ', '),
           'review ' || id || ', turn ' || left(coalesce(source_turn_id, '?'), 18)
      FROM review
    UNION ALL
    SELECT 4, decided_at, coalesce(decided_by_name, 'a person') || ' approved the review',
           'approvals ' || id
      FROM review
    UNION ALL
    SELECT 5, t.created_at, 'give_store_credit ran with the review''s key (' || t.caller || ')',
           'tool_audit ' || t.audit_id
      FROM pellier.tool_audit t
     WHERE t.tool = 'give_store_credit' AND t.args->>'idempotency_key' = :'wrap_write_key'
    UNION ALL
    SELECT 6, created_at, 'Aurora wrote credit ' || credit_id || ', '
           || to_char(amount_cents / 100.0, 'FM$999990.00'), 'store_credits ' || credit_id
      FROM credit
    UNION ALL
    SELECT 7, NULL, 'Orders ' || string_agg(o.id::text, ', ' ORDER BY o.id) || ' now carry credit '
           || c.credit_id, 'orders.store_credit_id'
      FROM pellier.orders o JOIN credit c ON o.store_credit_id = c.credit_id
     GROUP BY c.credit_id
)
SELECT to_char(at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS') AS "when (UTC)", what, evidence
  FROM story
 ORDER BY step, at;

\echo 'Key      ' :wrap_write_key
\echo ''
SELECT * FROM (VALUES
    ('a request from her chat answered by the review', 'at least 1', :'wrap_requests'),
    ('an ask_a_person row in her turn', 'at least 1', :'wrap_handoff_rows'),
    ('the write key derived from the review', 'the credit''s key',
        CASE WHEN :'wrap_key_matches'::boolean THEN 'the credit''s key' ELSE 'differs' END),
    ('give_store_credit audit rows for the key', '1', :'wrap_credit_audit_rows'),
    ('store_credits rows for the key', '1', :'wrap_credit_rows'),
    ('orders carrying the credit', :'wrap_reviewed_orders' || ', the review''s orders',
        :'wrap_credited_orders' || CASE WHEN :'wrap_orders_match'::boolean
                                        THEN ', the review''s orders' ELSE ', other orders' END)
) AS links(link, expected, observed);

SELECT CASE
         WHEN :wrap_requests = 0 THEN 'no request from Jessica''s chat is answered by review '
              || :'wrap_review_id' || ': send her request (python3 scripts/lab_run.py send --lab 4)'
         WHEN :wrap_handoff_rows = 0 THEN 'her request''s turn left no ask_a_person row in tool_audit'
         WHEN NOT :'wrap_key_matches'::boolean THEN 'the key derived from the review is not the credit''s'
         WHEN :wrap_credit_audit_rows <> 1 THEN :'wrap_credit_audit_rows'
              || ' give_store_credit audit rows carry the key; one applied write leaves one'
         WHEN :wrap_credit_rows <> 1 THEN :'wrap_credit_rows' || ' credits carry the key'
         WHEN NOT :'wrap_orders_match'::boolean THEN 'the credited orders are not the review''s orders'
         ELSE ''
       END AS missing,
       :wrap_requests > 0 AND :wrap_handoff_rows > 0 AND :'wrap_key_matches'::boolean
         AND :wrap_credit_audit_rows = 1 AND :wrap_credit_rows = 1
         AND :'wrap_orders_match'::boolean AS whole
\gset wrap_

\echo 'Expected  every link finds its row: request, turn, review, key, audit row, credit, orders'
\if :wrap_whole
  \echo 'Observed  the request, the approval, the write and the credit join into one story'
  \echo 'Wrap-up reconstruction passed'
\else
  \echo 'Observed  NOT YET:' :wrap_missing
  \echo 'Wrap-up reconstruction failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Wrap-up reconstruction failed; see the lines above'; END $fail$;
\endif
