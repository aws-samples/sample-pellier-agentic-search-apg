-- tool_audit_recap.sql — Act II: Exercise 2 (managed Policy + Aurora proof)
--
-- Drops in for the in-room SQL proof when a participant runs out of time.
-- On the managed Gateway rail, process_return runs in the experience Lambda
-- ONLY after managed AgentCore Policy (Cedar, ENFORCE) permits it. The Lambda
-- receives the tool arguments but NOT a session_id, so the ledger row is keyed
-- by the customer the agent acted for (args->>'customer_id'). This script
-- pulls the most recent ALLOWed process_return for 'theo' and prints:
--
--   1) raw row            — tool, caller (= 'gateway'), args, result, latency_ms
--   2) JSONB extraction   — args->>'reason', result->>'return_id', etc.
--   3) DENY absence note   — a managed-Policy DENY blocks the call at the
--                            Gateway, so no row is written; the decision lives
--                            in CloudWatch, not tool_audit.
--
-- Run (bare psql picks up the PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE
-- vars bootstrap exports — no connection string needed):
--   psql -f solutions/the-ledger/sql/tool_audit_recap.sql
--
-- Optional: override the customer (defaults to 'theo'):
--   psql -v customer=theo -f solutions/the-ledger/sql/tool_audit_recap.sql

\if :{?customer}
\else
\set customer theo
\endif

\echo ''
\echo '== Most recent ALLOWed process_return (customer-keyed) =========='
\echo ''

SELECT :'customer' AS customer, MAX(created_at) AS last_seen
  FROM pellier.tool_audit
 WHERE tool = 'process_return'
   AND args->>'customer_id' = :'customer';

\echo ''
\echo '== Raw row ====================================================='
\echo ''

SELECT tool,
       caller,
       args,
       result,
       latency_ms,
       created_at
  FROM pellier.tool_audit
 WHERE tool = 'process_return'
   AND args->>'customer_id' = :'customer'
 ORDER BY created_at DESC
 LIMIT 1;

\echo ''
\echo '== JSONB-extracted view ========================================'
\echo ''

SELECT tool,
       args->>'customer_id'  AS customer,
       args->>'product_id'   AS product_id,
       args->>'reason'       AS reason,
       result->>'return_id'  AS return_id,
       result->>'status'     AS status,
       latency_ms
  FROM pellier.tool_audit
 WHERE tool = 'process_return'
   AND args->>'customer_id' = :'customer'
 ORDER BY created_at DESC
 LIMIT 1;

\echo ''
\echo '== DENY absence check =========================================='
\echo ''

-- A managed-Policy DENY never writes a row. Run this count BEFORE and AFTER
-- firing a non-damaged return: it does NOT increase, because the Gateway
-- blocked process_return before the Lambda ran.
SELECT :'customer' AS customer,
       count(*)    AS process_return_rows
  FROM pellier.tool_audit
 WHERE tool = 'process_return'
   AND args->>'customer_id' = :'customer';

\echo ''
\echo 'Notes:'
\echo '  - args / result are JSONB. ->> returns text; -> returns JSONB.'
\echo '  - ALLOW: managed Policy permitted the call at the Gateway, the'
\echo '    experience Lambda ran and wrote this tool_audit row (caller=gateway).'
\echo '  - DENY: managed Policy blocked it at the Gateway; no row is written.'
\echo '    The deny decision is in CloudWatch (managed control plane), not here.'
\echo '  - latency_ms is the tool round-trip measured in the Lambda, not the'
\echo '    LLM call.'
