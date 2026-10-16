-- Read-only checks for examples/setup.sql, NOT drop-in Pellier queries.
-- Select a named query and supply its psql variables, or run the whole file:
-- psql -X -v ON_ERROR_STOP=1 -v request_id=search-1 -v case_id=stock-1
--      -v write_key=approval:1 -f references/proof-queries.sql <disposable-db>
-- Run after setup as its administrator; ownership probes switch roles locally.
-- "passed" applies only to the named fixture claim. Missing evidence is
-- "not tested". A failure is not proof of its cause until you inspect it.

-- query: retrieval
WITH request AS (
    SELECT * FROM review_example.search_requests WHERE request_id = :'request_id'
), receipt AS (
    SELECT r.* FROM review_example.retrieval_receipts r
    JOIN request q USING (request_id)
), products AS (
    SELECT id, p.*, q.original_constraints AS limits
    FROM request q JOIN receipt r USING (request_id)
    CROSS JOIN LATERAL unnest(r.returned_product_ids) AS ids(id)
    LEFT JOIN review_example.catalog p ON p.product_id = ids.id
), violations AS (
    SELECT * FROM products
    WHERE product_id IS NULL
       OR CASE WHEN jsonb_typeof(limits->'max_price') = 'number'
               THEN price > (limits->>'max_price')::numeric ELSE true END
       OR CASE WHEN jsonb_typeof(limits->'in_stock_only') = 'boolean'
               THEN (limits->>'in_stock_only')::boolean AND quantity <= 0 ELSE true END
       OR CASE WHEN jsonb_typeof(limits->'exclude') = 'array'
               THEN (limits->'exclude') ? category ELSE true END
)
SELECT CASE
    WHEN (SELECT count(*) FROM request) <> 1
      OR (SELECT count(*) FROM receipt) <> 1 THEN 'not tested'
    WHEN EXISTS (SELECT 1 FROM request q JOIN receipt r USING (request_id)
                 WHERE NOT (q.original_constraints <@ r.final_plan)) THEN 'failed'
    WHEN NOT EXISTS (SELECT 1 FROM products) THEN 'not tested'
    WHEN EXISTS (SELECT 1 FROM violations) THEN 'failed'
    ELSE 'passed' END AS result,
    (SELECT count(*) FROM products) AS tested_products,
    (SELECT count(*) FROM violations) AS violations;
-- end
-- Fixture: passed | 1 | 0. A dropped plan with the candle returns failed | 1 | 1.
-- A missing returned product also fails. An empty receipt is not a positive test.

-- query: stock
SELECT CASE
    WHEN NOT EXISTS (SELECT 1 FROM review_example.expected_stock WHERE case_id = :'case_id')
      OR NOT EXISTS (SELECT 1 FROM review_example.stock_receipts WHERE case_id = :'case_id')
        THEN 'not tested'
    WHEN (SELECT result FROM review_example.expected_stock WHERE case_id = :'case_id')
         IS DISTINCT FROM
         (SELECT result FROM review_example.stock_receipts WHERE case_id = :'case_id')
        THEN 'failed'
    ELSE 'passed' END AS result,
    (SELECT count(*) FROM review_example.stock_receipts WHERE case_id = :'case_id') AS tested_calls;
-- end
-- Fixture: passed | 1. Omitted/duplicate warehouses, changed counts or status fail.
-- This compares a tool result with an independent expectation, not the final prose.

-- query: ownership
BEGIN;
SET LOCAL ROLE review_support;
SELECT set_config('review_example.customer_id', 'customer-a', true);
SELECT CASE WHEN
    (SELECT count(*) FROM review_example.tickets WHERE customer_id = 'customer-a') = 1
    AND (SELECT count(*) FROM review_example.tickets WHERE customer_id = 'customer-b') = 0
    THEN 'passed' ELSE 'failed' END AS result;
ROLLBACK;
-- end
-- Positive control and wrong-customer query use the same role and transaction.
-- These counts are fixture-specific. Inspect the policy and role before adapting.

-- query: unbound
BEGIN;
SET LOCAL ROLE review_support;
SELECT set_config('review_example.customer_id', '', true);
SELECT CASE WHEN count(*) = 0 THEN 'passed' ELSE 'failed' END AS result
FROM review_example.tickets;
ROLLBACK;
-- end
-- This checks unbound access only. It does not prove authentication or Gateway policy.

-- query: approval
WITH credits AS (
    SELECT * FROM review_example.credits WHERE write_key = :'write_key'
), violations AS (
    SELECT c.credit_id
    FROM credits c LEFT JOIN review_example.approvals a ON a.id = c.approval_id
    WHERE a.id IS NULL OR a.status IS DISTINCT FROM 'approved'
       OR nullif(a.approved_by, '') IS NULL
       OR a.customer_id IS DISTINCT FROM c.customer_id
       OR a.expense_id IS DISTINCT FROM c.expense_id
       OR c.write_key IS DISTINCT FROM ('approval:' || a.id::text)
       OR a.args IS DISTINCT FROM jsonb_build_object(
           'customer_id', c.customer_id, 'amount_cents', c.amount_cents, 'reason', c.reason)
)
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM credits) THEN 'not tested'
            WHEN EXISTS (SELECT 1 FROM violations) THEN 'failed'
            ELSE 'passed' END AS result,
       (SELECT count(*) FROM credits) AS tested_credits,
       (SELECT count(*) FROM violations) AS violations;
-- end
-- After the example write: passed | 1 | 0. Missing amount/reason and changed terms fail.

-- query: privileges
WITH access AS (
    SELECT c.relname,
           has_table_privilege('review_writer', c.oid,
               'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS table_access
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'review_example' AND c.relkind = 'r'
), fn AS (
    SELECT p.* FROM pg_proc p
    WHERE p.oid = 'review_example.apply_credit(text,text,integer,text)'::regprocedure
)
SELECT CASE WHEN p.prosecdef
    AND p.proconfig @> ARRAY['search_path=pg_catalog, pg_temp']
    AND has_function_privilege('review_writer', p.oid, 'EXECUTE')
    AND NOT has_function_privilege('public', p.oid, 'EXECUTE')
    AND NOT EXISTS (SELECT 1 FROM access WHERE table_access)
    AND NOT pg_has_role('review_writer', p.proowner, 'MEMBER')
    AND NOT has_schema_privilege('review_writer', 'review_example', 'CREATE')
    AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'review_writer' AND NOT rolsuper)
    THEN 'passed' ELSE 'failed' END AS result,
    (SELECT count(*) FROM access WHERE table_access) AS tables_with_effective_access
FROM fn p;
-- end
-- Fixture: passed | 0. PUBLIC or inherited table access changes this to failed.
-- Review additional callable functions and role-switch paths separately.

-- query: committed_write
SELECT CASE WHEN
    NOT EXISTS (SELECT 1 FROM review_example.credits WHERE write_key = :'write_key')
    THEN 'not tested'
    WHEN (SELECT count(*) FROM review_example.credits WHERE write_key = :'write_key') = 1
    AND (SELECT count(*) FROM review_example.write_audit a
         JOIN review_example.credits c ON c.credit_id = a.credit_id AND c.write_key = a.write_key
         WHERE c.write_key = :'write_key') = 1
    THEN 'passed' ELSE 'failed' END AS result,
    (SELECT count(*) FROM review_example.credits WHERE write_key = :'write_key') AS credit_rows,
    (SELECT count(*) FROM review_example.write_audit WHERE write_key = :'write_key') AS audit_rows;
-- end
-- After one write and its replay: passed | 1 | 1. This is a first-write ledger.
-- A missing credit leaves the commit unestablished. A credit without its matching
-- first-write audit record fails this example's atomic recording contract.
-- Permission and exact terms are separate claims; run their checks too.

-- Optional workload inspection on YOUR application, not this example schema:
-- pg_stat_statements aggregates normalized statements by database, user and
-- query id. Snapshot before and after an isolated test, account for concurrent
-- activity and resets, and correlate application receipts separately. Do not
-- label its cumulative rows as the trace of one request. No extension is
-- needed for the checks above.
