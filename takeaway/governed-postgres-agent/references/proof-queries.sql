-- Proof queries for the four contracts. Adapt table and column names.
-- Each proves one claim from rows, not from logs or UI state.

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

-- 1b. Every returned product meets the hard constraints the search recorded.
--     Expect zero violations. (Pellier records the applied plan with the receipt.)
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
--     tool it needs.
SELECT session_id, result->>'grant' AS tools_granted
  FROM tool_audit WHERE caller = 'stock_agent' ORDER BY audit_id DESC LIMIT 5;

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

-- 3c. Every executed customer-scoped call in a shopper's turns read that
--     shopper. Expect zero rows.
SELECT audit_id, session_id, args->>'customer_id' AS read_customer
  FROM tool_audit
 WHERE tool IN ('get_orders', 'get_tickets')
   AND caller = 'support_agent'
   AND args->>'customer_id' <> result->>'bound_customer_id';

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
