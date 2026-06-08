-- tool_audit_recap.sql — Act II: Exercise 2 (Aurora SQL proof)
--
-- Drops in for the in-room SQL proof when a participant runs out of
-- time. Pulls the most recent ALLOWed process_return session in
-- pellier.tool_audit, then prints three proof surfaces:
--
--   1) raw rows           — tool, caller, args, result, latency_ms
--   2) JSONB extraction   — args->>'reason', result->>'return_id', etc.
--   3) DENY absence check — optional -v denied_session=...
--
-- Every ALLOWed tool call writes a row, reads and writes alike.
-- DENY decisions skip the ledger because the tool never ran; the
-- denial belongs in the policy decision surface, not tool_audit.
--
-- Run:
--   psql "$PG_URL" -f solutions/the-ledger/sql/tool_audit_recap.sql
--
-- Optional DENY check:
--   psql "$PG_URL" -v denied_session=builders-denied-... \
--     -f solutions/the-ledger/sql/tool_audit_recap.sql

\echo ''
\echo '== Most recent allowed process_return session ==================='
\echo ''

-- Stash the latest session_id with an allowed process_return row in a
-- temp table so the rest of the script can reference it cleanly.
DROP TABLE IF EXISTS _latest_session;

CREATE TEMP TABLE _latest_session ON COMMIT DROP AS
SELECT session_id, MAX(created_at) AS last_seen
  FROM pellier.tool_audit
 WHERE tool = 'process_return'
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
   AND tool = 'process_return'
 ORDER BY created_at;

\echo ''
\echo '== Optional DENY absence check =================================='
\echo ''

\if :{?denied_session}
SELECT :'denied_session' AS denied_session,
       count(*)          AS denied_rows
  FROM pellier.tool_audit
 WHERE session_id = :'denied_session'
   AND tool = 'process_return';
\else
\echo 'Skipped: pass -v denied_session=builders-denied-... after firing'
\echo 'a denied return turn. Expected result: denied_rows = 0 because'
\echo 'the process_return tool never executed.'
\endif

\echo ''
\echo 'Notes:'
\echo '  - args / result are JSONB. The ->> operator returns text;'
\echo '    -> returns JSONB.'
\echo '  - ALLOW means the tool ran and wrote tool_audit evidence.'
\echo '    DENY means the tool did not run, so tool_audit has no'
\echo '    process_return row for that denied session.'
\echo '  - latency_ms is BeforeToolCallEvent → AfterToolCallEvent'
\echo '    wall-clock — the real tool round-trip, not the LLM call.'
\echo '  - If result IS NULL, the tool started but did not finish.'
\echo '    That row is itself a real signal you would page on.'
