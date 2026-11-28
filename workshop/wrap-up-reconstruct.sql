\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off \pset border 2 \pset linestyle unicode \pset expanded off \pset format wrapped

-- Wrap-up: rebuild Jessica's store credit, from her request to the row.
--
-- The model's account of a conversation can drift; the database's cannot. Every
-- step of Lab 4 left a row, and each row names the next one:
--   her request (approvals, store_credit_request)  names the review that answered it
--   the review (approvals, give_store_credit)     its id and hash make the write key
--   the write key                                  is on the audit row and the credit
--   the credit (store_credits)                     is the id her returned orders carry
-- This file follows those links with joins only, prints the story in time
-- order, and checks that every link finds the row it should.
--
-- Supplied and read-only; it never writes:
--   psql -f workshop/wrap-up-reconstruct.sql

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
         WHERE t.tool = 'ask_a_person' AND t.result->>'request_id' = q.id::text) AS handoff_rows,
       -- The row that applied the credit. A call that failed or was refused
       -- before it leaves its own row with the key: an attempt, kept apart.
       (SELECT count(*) FROM pellier.tool_audit t JOIN review r
            ON t.args->>'idempotency_key' = r.write_key
         WHERE t.tool = 'give_store_credit'
           AND (t.result->>'status' = 'success'
                AND coalesce(t.result->>'idempotent_replay', 'false') <> 'true')) AS credit_audit_rows,
       (SELECT count(*) FROM pellier.tool_audit t JOIN review r
            ON t.args->>'idempotency_key' = r.write_key
         WHERE t.tool = 'give_store_credit'
           AND (t.result->>'status' = 'success'
                AND coalesce(t.result->>'idempotent_replay', 'false') <> 'true') IS NOT TRUE)
         AS credit_attempt_rows,
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

\echo 'Wrap-up: the whole story of Jessica''s credit, rebuilt from rows'
\if :wrap_has_credit
\else
  \echo 'Jessica has no store credit yet.'
  \echo ''
  \echo 'Next  In the guide, read "Execute again and replay as Nadia".'
  \echo '      Approve and execute her review in the Operator, then run this file again.'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[31m' || true`
  \echo 'Wrap-up reconstruction failed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  DO $fail$ BEGIN RAISE EXCEPTION 'stopped on purpose; see Next'; END $fail$;
\endif

-- The story in three rows, each from its own table: who asked, who approved, what Aurora wrote.
-- The credit's time can trail the approval; each row shows the time its own row was written.
WITH credit AS (
    SELECT * FROM pellier.store_credits WHERE credit_id = :'wrap_credit_id'::bigint
), review AS (
    SELECT * FROM pellier.approvals WHERE id = :'wrap_review_id'::bigint
), request AS (
    SELECT * FROM pellier.approvals WHERE id = nullif(:'wrap_request_id', '')::bigint
)
SELECT label AS "Step", who AS "Who", what AS "What", "when (UTC)" FROM (
    SELECT 1 AS ord, 'Request' AS label,
           (SELECT c.name FROM pellier.customers c WHERE c.id = q.customer_id) AS who,
           'asked for a person about a store credit' AS what,
           to_char(q.requested_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS') AS "when (UTC)"
      FROM request q
    UNION ALL
    SELECT 2, 'Approval', coalesce(r.decided_by_name, 'a person'),
           'approved ' || to_char((r.args->>'amount_cents')::int / 100.0, 'FM$999990.00'),
           to_char(r.decided_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
      FROM review r
    UNION ALL
    SELECT 3, 'Credit', 'Aurora',
           'wrote credit ' || c.credit_id || ', ' || to_char(c.amount_cents / 100.0, 'FM$999990.00')
           || CASE WHEN :wrap_credit_rows = 1 THEN ', paid once' ELSE '' END,
           to_char(c.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
      FROM credit c
) story ORDER BY ord;

\echo 'Write key' :wrap_write_key
SELECT format('%s credit%s for this key, %s audit row%s that applied it',
              :wrap_credit_rows, CASE WHEN :wrap_credit_rows = 1 THEN '' ELSE 's' END,
              :wrap_credit_audit_rows, CASE WHEN :wrap_credit_audit_rows = 1 THEN '' ELSE 's' END)
       AS wrap_counts
\gset
\echo :wrap_counts
\echo ''
SELECT CASE
         WHEN :wrap_requests = 0 THEN 'no shopper request links to this paid review'
         WHEN :wrap_handoff_rows = 0 THEN 'no ask_a_person row in her turn names her request'
         WHEN NOT :'wrap_key_matches'::boolean THEN 'the key derived from the review is not the credit''s'
         WHEN :wrap_credit_audit_rows <> 1 THEN :'wrap_credit_audit_rows'
              || ' give_store_credit audit rows applied the key; expected one'
         WHEN :wrap_credit_rows <> 1 THEN :'wrap_credit_rows' || ' credits carry the key'
         WHEN NOT :'wrap_orders_match'::boolean THEN 'the credited orders are not the review''s orders'
         ELSE ''
       END AS missing,
       :wrap_requests > 0 AND :wrap_handoff_rows > 0 AND :'wrap_key_matches'::boolean
         AND :wrap_credit_audit_rows = 1 AND :wrap_credit_rows = 1
         AND :'wrap_orders_match'::boolean AS whole
\gset wrap_

SELECT :wrap_credit_attempt_rows > 0 AS has_attempts,
       format('%s other attempt%s with the key did not apply; the audit keeps %s.',
              :wrap_credit_attempt_rows,
              CASE WHEN :wrap_credit_attempt_rows = 1 THEN '' ELSE 's' END,
              CASE WHEN :wrap_credit_attempt_rows = 1 THEN 'it' ELSE 'them' END) AS attempts
\gset wrap_
\if :wrap_has_attempts
  \echo :wrap_attempts
\endif
\if :wrap_whole
  \echo 'The request, the approval, the write and the credit join into one story.'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[32m' || true`
  \echo 'Wrap-up reconstruction passed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
\else
  \echo :wrap_missing
  \echo ''
  \echo 'Next  In the guide, read "Follow one credit end to end".'
  \echo '      Keep the existing credit. Show the review and its key to a facilitator.'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[31m' || true`
  \echo 'Wrap-up reconstruction failed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  DO $fail$ BEGIN RAISE EXCEPTION 'stopped on purpose; see Next'; END $fail$;
\endif
