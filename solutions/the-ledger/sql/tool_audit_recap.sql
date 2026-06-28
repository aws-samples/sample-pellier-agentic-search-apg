-- tool_audit_recap.sql — Act II: Exercise 2 (Aurora ledger proof)
--
-- Drops in for the in-room SQL proof when a participant runs out of time.
-- The required workshop path uses the in-process storefront rail:
-- /api/chat/stream, no bearer token, caller='agent'. The same table can also
-- receive caller='gateway' rows from the optional managed Gateway rail when
-- Policy permits a Lambda-backed MCP tool call. This script pulls the most
-- recent executed process_return for 'theo' and prints:
--
--   1) raw row            — tool, caller, args, result, latency_ms
--   2) JSONB extraction   — args->>'reason', result->>'return_id', etc.
--   3) rail grouping      — caller + reason counts, then the boundary note:
--                            Gateway DENY happens before a tool row exists.
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
\echo '== Most recent executed process_return (customer-keyed) ========='
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
\echo '== Rail grouping ==============================================='
\echo ''

SELECT caller,
       args->>'reason' AS reason,
       count(*)        AS calls
  FROM pellier.tool_audit
 WHERE tool = 'process_return'
   AND args->>'customer_id' = :'customer'
 GROUP BY caller, args->>'reason'
 ORDER BY caller, calls DESC;

\echo ''
\echo 'Notes:'
\echo '  - args / result are JSONB. ->> returns text; -> returns JSONB.'
\echo '  - Required path: /api/chat/stream uses in-process tools, so caller=agent.'
\echo '  - Optional Gateway path: allowed Lambda-backed calls write caller=gateway.'
\echo '  - Gateway DENY: managed Policy blocks before Lambda execution, so no'
\echo '    tool_audit row exists. In-process changed_mind is valid and would log.'
\echo '  - latency_ms is the tool round-trip measured by the active rail, not'
\echo '    the LLM call.'
