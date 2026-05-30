-- tool_audit_recap.sql — Act II: Exercise 2 (Aurora read path)
--
-- Drops in for the in-room SELECT when a participant runs out of
-- time. Pulls the most recent session with at least one row in
-- pellier.tool_audit, then prints two views:
--
--   1) raw rows  — tool, caller, args, result, latency_ms, created_at
--   2) JSONB extraction — args->>'reason', result->>'return_id', etc.
--
-- Every ALLOWed tool call writes a row — reads and writes alike —
-- so a typical browse session shows find_pieces, find_pieces_hybrid,
-- floor_check etc. alongside any process_return / restock_shelf
-- mutations. DENY decisions skip the ledger (the tool never ran)
-- and live in policy_hook's per-session decision deque instead.
--
-- Run:
--   psql "$PG_URL" -f solutions/the-ledger/sql/tool_audit_recap.sql

\echo ''
\echo '== Most recent audited session =================================='
\echo ''

-- Stash the latest session_id with at least one tool_audit row in a
-- temp table so the rest of the script can reference it cleanly.
CREATE TEMP TABLE IF NOT EXISTS _latest_session ON COMMIT DROP AS
SELECT session_id, MAX(created_at) AS last_seen
  FROM pellier.tool_audit
 GROUP BY session_id
 ORDER BY last_seen DESC
 LIMIT 1;

SELECT session_id, last_seen FROM _latest_session;

\echo ''
\echo '== Raw rows ===================================================='
\echo ''

SELECT tool,
       caller,
       args,
       result,
       latency_ms,
       created_at
  FROM pellier.tool_audit
 WHERE session_id = (SELECT session_id FROM _latest_session)
 ORDER BY created_at;

\echo ''
\echo '== JSONB-extracted view ========================================'
\echo ''

SELECT tool,
       args->>'customer_id'  AS customer,
       args->>'product_id'   AS product_id,
       args->>'reason'       AS reason,
       args->>'quantity'     AS quantity,
       result->>'return_id'  AS return_id,
       result->>'status'     AS status,
       latency_ms
  FROM pellier.tool_audit
 WHERE session_id = (SELECT session_id FROM _latest_session)
 ORDER BY created_at;

\echo ''
\echo 'Notes:'
\echo '  - args / result are JSONB. The ->> operator returns text;'
\echo '    -> returns JSONB.'
\echo '  - latency_ms is BeforeToolCallEvent → AfterToolCallEvent'
\echo '    wall-clock — the real tool round-trip, not the LLM call.'
\echo '  - If result IS NULL, the tool started but did not finish.'
\echo '    That row is itself a real signal you would page on.'
