-- Proof queries for the four contracts. Adapt table and column names.
-- Each proves one claim from rows, not from logs or UI state.

-- ---------------------------------------------------------------------------
-- Start here: what did the agent do to the database?
-- ---------------------------------------------------------------------------

-- 0. The agent's workload by role, from pg_stat_statements (preloaded through
--    shared_preload_libraries; CREATE EXTENSION pg_stat_statements once). A
--    statement is recorded under the role in force when it ran, so a tool that
--    switches with SET LOCAL ROLE shows up under that role. Each role sees its
--    own statements' text, so read each role's while switched to it (the
--    application login sees its own; pg_read_all_stats sees everyone's).
--    Expect the agent's reads under app_agent, its writes under credit_writer,
--    and nothing wide or unbounded under either.
BEGIN;
SET LOCAL ROLE app_agent;
SELECT userid::regrole AS role, calls, rows, round(mean_exec_time::numeric, 2) AS mean_ms,
       left(regexp_replace(query, '\s+', ' ', 'g'), 80) AS statement
  FROM pg_stat_statements
 WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
   AND userid = current_user::regrole
 ORDER BY calls DESC
 LIMIT 10;
ROLLBACK;

-- ---------------------------------------------------------------------------
-- Contract 1: filter before ranking
-- ---------------------------------------------------------------------------

-- 1a. Recompute a recorded fused ranking from its two ranks (RRF, k = 60).
--     Every row must read 'matches'. A row that differs names a product whose
--     recorded score cannot be derived from its ranks.
WITH receipt AS (
  SELECT receipt_id, vector_ranks, lexical_ranks, rrf_scores
    FROM retrieval_receipts
   ORDER BY receipt_id DESC
   LIMIT 1
),
ranks AS (
  SELECT r.receipt_id, k.product_id,
         (r.vector_ranks->>k.product_id)::int      AS vector_rank,
         (r.lexical_ranks->>k.product_id)::int     AS full_text_rank,
         (r.rrf_scores->>k.product_id)::numeric    AS recorded_rrf
    FROM receipt r
   CROSS JOIN LATERAL jsonb_object_keys(r.rrf_scores) AS k(product_id)
)
SELECT product_id, vector_rank, full_text_rank, recorded_rrf,
       coalesce(1.0 / (60 + vector_rank), 0)
         + coalesce(1.0 / (60 + full_text_rank), 0) AS recomputed_rrf,
       CASE WHEN abs(recorded_rrf - (coalesce(1.0 / (60 + vector_rank), 0)
                                   + coalesce(1.0 / (60 + full_text_rank), 0))) <= 1e-6
            THEN 'matches' ELSE 'differs' END AS check
  FROM ranks
 ORDER BY recorded_rrf DESC;

-- 1a2. The vector branch orders by meaning. Search with a product's own stored
--      embedding: that product is at distance 0 from itself, so it must come
--      back first, the rest in rising distance, similarity = 1 - distance.
WITH q AS (SELECT embedding AS emb FROM catalog WHERE product_id = 'P-1')
SELECT product_id,
       1 - (embedding <=> (SELECT emb FROM q)) AS similarity
  FROM catalog
 WHERE price <= 100                          -- the same hard predicates as the search
 ORDER BY embedding <=> (SELECT emb FROM q)
 LIMIT 20;
-- expect: P-1 first with similarity 1.000, then similarity falling

-- 1b. Every returned product meets the hard constraints the search recorded.
--     Expect zero violations. (Pellier's receipt keeps search_plan,
--     hard_constraints and exclusions as JSONB; adapt the names.)
WITH receipt AS (
  SELECT receipt_id, returned_product_ids, plan
    FROM retrieval_receipts ORDER BY receipt_id DESC LIMIT 1
)
SELECT p.product_id, p.price, p.quantity, p.category
  FROM receipt r
  JOIN catalog p ON p.product_id = ANY (r.returned_product_ids)
 WHERE (r.plan->>'max_price') IS NOT NULL AND p.price > (r.plan->>'max_price')::numeric
    OR (r.plan->>'in_stock_only')::boolean AND p.quantity <= 0
    OR p.category = ANY (ARRAY(SELECT jsonb_array_elements_text(r.plan->'exclude')));

-- 1c. Does a filtered HNSW scan come back short? Compare an exact scan with
--     the index forced, with and without iterative scan. Read-only; roll back.
BEGIN;
SET LOCAL enable_seqscan = on;
-- exact: expect 20 of 20
SELECT count(*) FROM (SELECT 1 FROM catalog WHERE price <= 35 AND category <> 'candles'
                      ORDER BY embedding <=> '[...]'::vector LIMIT 20) s;
SET LOCAL enable_seqscan = off;
SET LOCAL hnsw.iterative_scan = off;
-- forced index, no iterative scan: may be fewer than 20
SELECT count(*) FROM (SELECT 1 FROM catalog WHERE price <= 35 AND category <> 'candles'
                      ORDER BY embedding <=> '[...]'::vector LIMIT 20) s;
SET LOCAL hnsw.iterative_scan = strict_order;
-- iterative, strict order: 20 of 20 again
SELECT count(*) FROM (SELECT 1 FROM catalog WHERE price <= 35 AND category <> 'candles'
                      ORDER BY embedding <=> '[...]'::vector LIMIT 20) s;
ROLLBACK;

-- ---------------------------------------------------------------------------
-- Contract 2: return bounded facts
-- ---------------------------------------------------------------------------

-- 2a. The agent's answer equals the rows. Compare the counts a tool returned
--     (from its audit row) with one SELECT on the source table.
WITH last_call AS (
  SELECT result FROM tool_audit
   WHERE tool = 'check_stock' ORDER BY audit_id DESC LIMIT 1
)
SELECT w.warehouse_name, w.quantity AS in_table,
       (elem->>'quantity')::int     AS in_answer,
       CASE WHEN w.quantity = (elem->>'quantity')::int THEN 'matches' ELSE 'differs' END AS check
  FROM last_call, jsonb_array_elements(result->'warehouses') AS elem
  JOIN warehouse_inventory w ON w.warehouse_name = elem->>'warehouse_name'
   AND w.product_id = (SELECT result->'product'->>'productId' FROM last_call);

-- 2b. The grant the answering agent held, from its audit row. Expect only the
--     tool it needs. (Pellier writes the agent's name and tool list into args.)
SELECT session_id, args->>'agent' AS agent, args->'grant' AS tools_granted
  FROM tool_audit WHERE args->>'agent' = 'stock' ORDER BY audit_id DESC LIMIT 5;

-- ---------------------------------------------------------------------------
-- Contract 3: bind identity, enforce ownership
-- ---------------------------------------------------------------------------

-- 3a. Preconditions for a denial to mean anything.
SELECT rolname, rolbypassrls, rolsuper FROM pg_roles WHERE rolname = 'app_agent';
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner) AS owner
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relname IN ('orders', 'support_tickets');
SELECT tablename, policyname, permissive, roles
  FROM pg_policies WHERE tablename IN ('orders', 'support_tickets');
-- expect: no bypass, not superuser, RLS on, not owned by app_agent (or forced),
-- exactly one PERMISSIVE policy per table, TO app_agent.

-- 3b. Probe as the agent role, bound as one customer, in a transaction that
--     rolls back. Own rows: counts > 0. Another customer's rows: 0. A write in
--     another customer's name: SQLSTATE 42501.
BEGIN;
SET LOCAL ROLE app_agent;
SELECT set_config('app.principal_username', 'theo', true);
SELECT (SELECT count(*) FROM orders WHERE customer_id = 'CUST-THEO')    AS own_orders,
       (SELECT count(*) FROM orders WHERE customer_id = 'CUST-JESSICA') AS others_orders;
DO $$ BEGIN
  INSERT INTO support_tickets (ticket_id, customer_id, subject, status)
  VALUES ('PROBE-1', 'CUST-JESSICA', 'probe', 'open');
  RAISE EXCEPTION 'write in another name was accepted';
EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'refused with %', SQLSTATE;   -- 42501
END $$;
ROLLBACK;

-- 3c. The binding is proved by a forged call, not by reading history: a model
--     rarely asks for someone else's rows, so past rows prove little. While a
--     shopper is signed in, send a call for another customer through the
--     binding, then read the row it left. Expect the shopper's id, not the
--     forged one. (Pellier's Lab 3 check, scripts/lab3_check.py, sends Theo's
--     forged ticket read through the server's binding.)
SELECT audit_id, session_id, args->>'customer_id' AS read_customer
  FROM tool_audit
 WHERE tool = 'get_tickets'
 ORDER BY audit_id DESC
 LIMIT 1;

-- 3d. The policy decides before the read. As the agent role, bound as one
--     customer, explain a query for another customer's rows. Expect an
--     InitPlan that reads the bound name once, a One-Time Filter comparing it
--     with the customer asked for, and the table scan '(never executed)'.
--     PostgreSQL 18 prints buffers by default: only the InitPlan's lookup
--     touches pages. If the scan executes and filters rows instead, the
--     predicate is evaluated row by row: still correct, but every row is read
--     before it is discarded.
BEGIN;
SET LOCAL ROLE app_agent;
SELECT set_config('app.principal_username', 'theo', true);
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF)
  SELECT * FROM orders WHERE customer_id = 'CUST-JESSICA';
ROLLBACK;

-- ---------------------------------------------------------------------------
-- Contract 4: approve and deduplicate writes
-- ---------------------------------------------------------------------------

-- 4a. The absence proof with its positive control. For the denied key both
--     counts are 0; for the allowed key store_credits holds exactly 1. The
--     1 is what makes the two 0s an absence rather than a query that looked
--     in the wrong place.
SELECT (SELECT count(*) FROM tool_audit    WHERE args->>'idempotency_key' = :'deny_key')  AS denied_audit_rows,
       (SELECT count(*) FROM store_credits WHERE idempotency_key = :'deny_key')           AS denied_credit_rows,
       (SELECT count(*) FROM store_credits WHERE idempotency_key = :'allow_key')          AS allowed_credit_rows;

-- 4b. What ran and what was written agree, key by key. A retry adds no audit
--     row and no credit; the join returns one row per allowed key.
SELECT a.audit_id, a.caller, a.args->>'idempotency_key' AS idempotency_key,
       a.latency_ms, c.credit_id, c.amount_cents
  FROM tool_audit a
  LEFT JOIN store_credits c ON c.idempotency_key = a.args->>'idempotency_key'
 WHERE a.tool = 'give_store_credit'
 ORDER BY a.audit_id;

-- 4c. Every credit references an approved review whose arguments it matches.
SELECT c.credit_id
  FROM store_credits c
  JOIN approvals r ON r.id = c.approval_id
 WHERE r.status <> 'approved'
    OR r.args->>'customer_id' <> c.customer_id
    OR (r.args->>'amount_cents')::int <> c.amount_cents;
-- expect zero rows

-- 4d. The audit table is append-only for application roles.
SELECT grantee, privilege_type FROM information_schema.role_table_grants
 WHERE table_name = 'tool_audit' AND privilege_type IN ('UPDATE', 'DELETE');
-- expect zero rows for application roles

-- 4e. The money role can write only through the function. It holds EXECUTE
--     and no table privilege; the function runs as its owner with a pinned
--     search_path; PUBLIC cannot execute it.
SELECT p.prosecdef AS security_definer, p.proconfig AS settings,
       has_function_privilege('credit_writer', p.oid, 'EXECUTE') AS writer_executes,
       has_function_privilege('public', p.oid, 'EXECUTE')        AS public_executes,
       (SELECT count(*) FROM information_schema.role_table_grants
         WHERE grantee = 'credit_writer')                         AS writer_table_grants
  FROM pg_proc p
 WHERE p.oid = 'apply_store_credit(text, text, integer, text, text)'::regprocedure;
-- expect: t, {"search_path=pg_catalog, pg_temp"}, t, f, 0

-- 4f. Probe it: as the money role, a direct UPDATE of a credit is refused with
--     42501 before it touches a row. Rolls back.
BEGIN;
SET LOCAL ROLE credit_writer;
DO $$ BEGIN
  UPDATE store_credits SET amount_cents = 50000 WHERE false;
  RAISE EXCEPTION 'a direct update was allowed';
EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'refused with %', SQLSTATE;   -- 42501
END $$;
ROLLBACK;

-- 4g. Rebuild one write from the request to the row with joins alone. Each
--     link names the next: the request names the review that answered it, the
--     review's id and hash make the key, the key is on the audit row and the
--     written row, and the written row's id is on the rows it changed. Expect
--     one audit row and one credit for the key; a missing link is the finding.
WITH credit AS (
  SELECT * FROM store_credits WHERE customer_id = :'customer' ORDER BY credit_id DESC LIMIT 1
), review AS (
  SELECT a.*, 'operator-review:' || a.id || ':' || left(a.action_hash, 32) AS write_key
    FROM approvals a JOIN credit c ON c.approval_id = a.id
)
SELECT q.source_turn_id                 AS asked_in_turn,
       r.id                             AS review, r.decided_by_name AS approved_by,
       r.write_key,
       (SELECT count(*) FROM tool_audit t
         WHERE t.tool = 'give_store_credit'
           AND t.args->>'idempotency_key' = r.write_key) AS audit_rows,   -- expect 1
       c.credit_id, c.amount_cents,
       (SELECT array_agg(o.id ORDER BY o.id) FROM orders o
         WHERE o.store_credit_id = c.credit_id)         AS orders_credited
  FROM credit c
  JOIN review r ON true
  LEFT JOIN approvals q ON q.answered_by_review_id = r.id;

-- 4h. Two sessions race one approved write. This needs two connections, so it
--     is a procedure, not one query; run it on a copy, never on live money.
--     Session A: BEGIN; call the write function for an approved review; do not
--     commit. Session B, at READ COMMITTED: call it with the same key. B waits
--     on A's lock. Commit A. Expect B to return the first row as a replay and
--     the written table to hold exactly one row for the key. Repeat with B at
--     REPEATABLE READ or SERIALIZABLE: expect SQLSTATE 40001 and still one row.
--     From a third session, a waiting B shows as:
SELECT pid, wait_event_type, wait_event, pg_blocking_pids(pid) AS blocked_by
  FROM pg_stat_activity
 WHERE cardinality(pg_blocking_pids(pid)) > 0;
--     expect: Lock / transactionid, blocked by A's pid. Pellier runs this race
--     as a test on a fresh PostgreSQL 18 cluster:
--     pellier/backend/tests/test_credit_race_postgres.py
