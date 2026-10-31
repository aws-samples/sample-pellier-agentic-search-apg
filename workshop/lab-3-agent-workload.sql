\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off \pset border 1 \pset linestyle ascii \pset expanded off

-- Lab 3: what did the agent do to your database?
--
-- To Aurora an agent is an application user. Every tool call is a SQL statement
-- run by a role, and pg_stat_statements has been counting them since the cluster
-- started: how often each statement ran, how many rows it returned and how long
-- it took. This file reads that record role by role, then shows one plan.
--
--   pellier_agent          the customer-scoped tools (orders, tickets). The app
--                          and the Gateway Lambda switch into it for each call.
--   pellier_credit_writer  the credit path, once a credit has run (Lab 4)
--   your login             the app's own login: catalog search, the audit ledger,
--                          and the statements you ran in psql
--
-- Supplied and read-only: it runs in one transaction and rolls back.
--   psql -f workshop/lab-3-agent-workload.sql

SET client_min_messages TO warning;
BEGIN;

-- Is pg_stat_statements there to read? The workshop's cluster preloads it; a
-- database without the library loaded cannot answer, and says so below.
DO $available$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements') THEN
        PERFORM set_config('lab3.workload', 'not installed in this database', true);
        RETURN;
    END IF;
    BEGIN
        PERFORM 1 FROM pg_stat_statements LIMIT 1;
        PERFORM set_config('lab3.workload', 'ok', true);
    EXCEPTION WHEN object_not_in_prerequisite_state THEN
        PERFORM set_config('lab3.workload', 'installed but not loaded (shared_preload_libraries)',
                           true);
    END;
END
$available$;
SELECT current_setting('lab3.workload') = 'ok' AS ready,
       current_setting('lab3.workload') AS state,
       session_user AS login,
       (SELECT oid FROM pg_database WHERE datname = current_database()) AS db
\gset lab_3_

\echo 'Lab 3: what the agent did to your database, role by role'
\if :lab_3_ready
\else
  \echo 'Observed  pg_stat_statements is' :lab_3_state
  \echo 'Next      the workshop cluster loads it; run this on the workshop database (check PGHOST).'
  \echo 'Lab 3 workload check unchecked'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 3 workload check unchecked; see the lines above'; END $fail$;
\endif

-- Each role reads its own statements: pg_stat_statements shows a statement's
-- text to the role that ran it, so the query switches role for each one.
-- Transaction control, SET and SHOW are left out; the caller's binding,
-- set_config, stays in, because every customer-scoped call starts with it.

\echo ''
\echo 'pellier_agent: the customer-scoped tools, under row-level security, on both paths'
SET LOCAL ROLE pellier_agent;
SELECT format('distinct statements %s, calls %s, rows %s', count(*), coalesce(sum(calls), 0),
              coalesce(sum(rows), 0)) AS summary,
       count(*) FILTER (WHERE tool) AS tool_reads,
       count(*) FILTER (WHERE tool) > 0 AS tool_seen
  FROM (SELECT calls, rows, query,
               regexp_replace(query, '\s+', ' ', 'g') ~ ANY (ARRAY[
                   'FROM pellier\.orders o JOIN pellier\.product_catalog p',   -- get_orders
                   'SELECT ticket_id, subject, status, channel, last_note'        -- get_tickets
               ]) AS tool
          FROM pg_stat_statements
         WHERE dbid = :lab_3_db AND userid = current_user::regrole) statements
 WHERE (query ~ 'pellier\.' OR query ~* '^\s*select set_config')
   AND query !~ 'lab_3_probe'
\gset lab_3_agent_
\echo '          ' :lab_3_agent_summary
SELECT sum(calls) AS calls, sum(rows) AS rows,
       round((sum(total_exec_time) / sum(calls))::numeric, 2) AS mean_ms, statement
  FROM (SELECT calls, rows, total_exec_time,
               left(regexp_replace(query, '\s+', ' ', 'g'), 80) AS statement
          FROM pg_stat_statements
         WHERE dbid = :lab_3_db AND userid = current_user::regrole
           AND (query ~ 'pellier\.' OR query ~* '^\s*select set_config')
           AND query !~ 'lab_3_probe') recorded
 GROUP BY statement
 ORDER BY calls DESC, statement
 LIMIT 5;
RESET ROLE;

\echo ''
\echo 'pellier_credit_writer: the credit path, which can only call give_store_credit'
SET LOCAL ROLE pellier_credit_writer;
SELECT format('distinct statements %s, calls %s', count(*), coalesce(sum(calls), 0)) AS summary,
       count(*) > 0 AS seen
  FROM pg_stat_statements
 WHERE dbid = :lab_3_db AND userid = current_user::regrole AND query ~ 'pellier\.'
   AND query !~ 'lab_3_probe'
\gset lab_3_writer_
\if :lab_3_writer_seen
  \echo '          ' :lab_3_writer_summary
  SELECT sum(calls) AS calls,
         round((sum(total_exec_time) / sum(calls))::numeric, 2) AS mean_ms, statement
    FROM (SELECT calls, total_exec_time,
                 left(regexp_replace(query, '\s+', ' ', 'g'), 80) AS statement
            FROM pg_stat_statements
           WHERE dbid = :lab_3_db AND userid = current_user::regrole
             AND query ~ 'pellier\.' AND query !~ 'lab_3_probe') recorded
   GROUP BY statement
   ORDER BY calls DESC, statement
   LIMIT 3;
\else
  \echo '           none yet: no credit has run. Lab 4 writes the first one.'
\endif
RESET ROLE;

\echo ''
\echo 'Your login:' :lab_3_login '(the app, the audit ledger, and your own psql)'
SELECT format('distinct statements %s, calls %s, rows %s', count(*), coalesce(sum(calls), 0),
              coalesce(sum(rows), 0)) AS summary
  FROM pg_stat_statements
 WHERE dbid = :lab_3_db AND userid = session_user::regrole AND query ~ 'pellier\.'
   AND query !~ 'lab_3_probe'
\gset lab_3_login_
\echo '          ' :lab_3_login_summary
SELECT sum(calls) AS calls, sum(rows) AS rows,
       round((sum(total_exec_time) / sum(calls))::numeric, 2) AS mean_ms, statement
  FROM (SELECT calls, rows, total_exec_time,
               left(regexp_replace(query, '\s+', ' ', 'g'), 80) AS statement
          FROM pg_stat_statements
         WHERE dbid = :lab_3_db AND userid = session_user::regrole
           AND query ~ 'pellier\.' AND query !~ 'lab_3_probe') recorded
 GROUP BY statement
 ORDER BY calls DESC, statement
 LIMIT 5;

-- One plan: Theo is bound, and the query asks for Jessica's orders. The policy
-- is part of the plan: an InitPlan reads the bound name, and a one-time filter
-- compares the customer it maps to with the one the query asked for. ANALYZE
-- runs it, so the plan shows what was read: on PostgreSQL 18 the buffers by
-- default, the InitPlan's lookup of the bound name, and an orders scan that was
-- never executed.
\echo ''
\echo 'One plan: as pellier_agent, Theo bound, a query for Jessica''s orders'
SET LOCAL ROLE pellier_agent;
SELECT set_config('pellier.principal_username', 'theo', true) AS lab_3_probe \gset lab_3_bound_
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF)
  SELECT o.id AS lab_3_probe FROM pellier.orders o
                     WHERE o.customer_id = 'CUST-JESSICA';
SELECT count(*) AS lab_3_probe, count(*) = 0 AS lab_3_none
  FROM pellier.orders o WHERE o.customer_id = 'CUST-JESSICA'
\gset lab_3_wrong_
RESET ROLE;
\echo 'Observed ' :lab_3_wrong_lab_3_probe 'rows: the row policy runs inside the plan, before any row is read'

ROLLBACK;

\echo ''
\echo 'Expected  at least one get_orders or get_tickets call recorded under pellier_agent, and'
\echo '          0 of Jessica''s orders visible to a session bound to Theo'
\if :lab_3_wrong_lab_3_none
\if :lab_3_agent_tool_seen
  \echo 'Observed ' :lab_3_agent_tool_reads 'tool statement(s): the agent is a role with a workload and plans'
  \echo 'Lab 3 workload check passed'
\else
  \echo 'Observed  none yet: no get_orders or get_tickets statement under pellier_agent'
  \echo 'Next      send Theo''s requests with uv run scripts/lab_run.py send --lab 3, then run this again.'
  \echo 'Lab 3 workload check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 3 workload check failed; see the lines above'; END $fail$;
\endif
\else
  \echo 'Observed ' :lab_3_wrong_lab_3_probe 'of Jessica''s orders were visible to Theo''s session'
  \echo 'Next      the row policy did not hold; run workshop/lab-3-row-ownership.sql until it passes.'
  \echo 'Lab 3 workload check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 3 workload check failed; see the lines above'; END $fail$;
\endif
