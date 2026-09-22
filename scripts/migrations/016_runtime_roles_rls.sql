-- ---------------------------------------------------------------------
-- 016_runtime_roles_rls.sql — runtime database roles and Row-Level Security
--
-- Agent policy answers "what may the agent attempt?". This migration adds the
-- second, independent answer: "what may the database session actually read or
-- change?" Cedar can be in LOG_ONLY and the database still refuses.
--
-- Three roles (spec section 10.1):
--
--   owner (postgres)  bootstrap, migrations, DDL. Owns the tables, so it
--                     bypasses RLS unless FORCE ROW LEVEL SECURITY is set.
--                     That bypass is the point of the exercise, not a bug:
--                     participants see that RLS binds the *effective* role.
--   pellier_agent     normal application and deterministic tools. Business
--                     tables, INSERT-only on the evidence ledger. RLS-bound.
--   pellier_query     model-generated read-only SQL. SELECT on a scoped set.
--                     NO tool_audit access of any kind — not read, not write.
--                     Generated SQL must never inspect the evidence ledger,
--                     modify it, or manufacture evidence.
--
-- Neither runtime role has BYPASSRLS or SUPERUSER.
--
-- WHY A MAPPING TABLE
--
-- `principal_sub` is a Cognito subject; `customer_id` is a catalog key like
-- 'CUST-MARCO'. They are different namespaces, so a policy cannot compare
-- them directly. `pellier.principal_customers` is the authorization mapping,
-- and the direction matters: the *database* resolves principal -> customer.
-- If the policy trusted an app-supplied customer id instead, an application
-- bug could read another shopper's orders while still passing a policy check.
--
-- FAIL CLOSED
--
-- Policies read `current_setting('pellier.principal_sub', true)`, which
-- returns NULL when the setting is absent. NULL matches no mapping row, so a
-- missing principal denies access. A missing principal must never widen it.
--
-- This migration is additive and idempotent. It changes no existing row, and
-- it does not alter behavior for connections that keep using the owner role.
-- ---------------------------------------------------------------------

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Runtime roles
--
-- Created NOLOGIN: the workshop binds them with `SET LOCAL ROLE` inside a
-- transaction rather than opening a second authenticated connection, so no
-- new secret is introduced. A production deployment gives each role its own
-- credential (or IAM database authentication) and connects directly; the
-- grants and policies below are identical either way.
--
-- NOINHERIT so that holding the role does not silently confer it: the
-- effective role changes only on an explicit SET ROLE.
-- ---------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pellier_agent') THEN
        CREATE ROLE pellier_agent NOLOGIN NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pellier_query') THEN
        CREATE ROLE pellier_query NOLOGIN NOINHERIT NOBYPASSRLS;
    END IF;
END
$$;

-- Verify the safety attributes rather than re-asserting them.
--
-- `ALTER ROLE ... NOSUPERUSER` / `NOBYPASSRLS` requires a true superuser, and
-- on Aurora and RDS the `postgres` login is `rds_superuser`, not a superuser.
-- Asserting them therefore fails the migration outright. Both are the CREATE
-- ROLE defaults, so the correct move is to confirm nothing granted them
-- elsewhere: a runtime role holding BYPASSRLS would silently void every
-- policy below while leaving the schema looking correct.
DO $$
DECLARE
    offending TEXT;
BEGIN
    SELECT string_agg(rolname, ', ') INTO offending
      FROM pg_roles
     WHERE rolname IN ('pellier_agent', 'pellier_query')
       AND (rolbypassrls OR rolsuper);
    IF offending IS NOT NULL THEN
        RAISE EXCEPTION
            'Runtime roles must not hold BYPASSRLS or SUPERUSER: %', offending;
    END IF;
END
$$;

-- The owner must be able to SET ROLE into them.
GRANT pellier_agent TO CURRENT_USER;
GRANT pellier_query TO CURRENT_USER;

-- ---------------------------------------------------------------------
-- 2. Authorization mapping: verified principal -> customer scope
--
-- Seeded by provisioning once the Cognito subjects exist. An unmapped
-- principal — including every anonymous or simulated-persona turn — resolves
-- to no customer and therefore sees no protected rows.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pellier.principal_customers (
    principal_sub   TEXT NOT NULL,
    customer_id     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (principal_sub, customer_id)
);

COMMENT ON TABLE pellier.principal_customers IS
    'Authorization mapping from verified Cognito subject to customer scope. '
    'Read by RLS policies; never written by the application at request time.';

CREATE INDEX IF NOT EXISTS principal_customers_customer_idx
    ON pellier.principal_customers (customer_id);

-- ---------------------------------------------------------------------
-- 3. Resolver
--
-- One function so every policy asks the question identically. STABLE (not
-- IMMUTABLE): it reads a table and a session setting, both of which can
-- change between statements.
--
-- SECURITY DEFINER, deliberately, and this is a reversal worth explaining.
-- The obvious choice is INVOKER, so the function cannot become a way to read
-- the mapping table without a grant. But INVOKER means every runtime role
-- needs SELECT on `pellier.principal_customers` — including `pellier_query`,
-- which runs model-generated SQL. That role could then enumerate the entire
-- principal-to-customer mapping, which is precisely the sort of thing
-- generated SQL must not see.
--
-- DEFINER is tighter here because the function is not a general reader: its
-- WHERE clause is pinned to the session's own `pellier.principal_sub`, so it
-- can only ever return the current principal's scopes. It cannot be coaxed
-- into returning someone else's. `search_path` is fixed on the function so a
-- caller cannot shadow `pellier` with their own schema — the standard
-- precaution that makes DEFINER safe.
--
-- Consequence: no runtime role reads the authorization table directly.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION pellier.current_principal_customers()
RETURNS TABLE (customer_id TEXT)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pellier
AS $$
    SELECT pc.customer_id
      FROM pellier.principal_customers pc
     WHERE pc.principal_sub = NULLIF(
               current_setting('pellier.principal_sub', true), ''
           );
$$;

COMMENT ON FUNCTION pellier.current_principal_customers() IS
    'Customer scopes the current transaction principal may touch. Empty when '
    'pellier.principal_sub is unset, which denies access rather than widening it.';

-- ---------------------------------------------------------------------
-- 4. Grants
--
-- pellier_agent: business access plus INSERT-only on the evidence ledger.
-- It may append a receipt and may not rewrite or delete one.
-- ---------------------------------------------------------------------

GRANT USAGE ON SCHEMA pellier TO pellier_agent, pellier_query;

GRANT SELECT ON pellier.product_catalog, pellier.warehouses,
                pellier.warehouse_inventory, pellier.customers,
                pellier.return_policies
    TO pellier_agent;

GRANT SELECT, INSERT, UPDATE ON pellier.orders, pellier.returns
    TO pellier_agent;

-- Sequence access for the tables it may INSERT into.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA pellier TO pellier_agent;

-- Evidence ledger: as close to append-only as the shipped writer allows.
--
-- A literal INSERT-only grant does not work, and finding out why is worth
-- recording. `services/tool_audit_writer.py` writes each row in two phases:
--
--   1. INSERT ... RETURNING audit_id      (before the tool body runs)
--   2. UPDATE ... SET result, latency_ms  (after it returns)
--
-- `RETURNING` requires SELECT on the returned column, and phase 2 requires
-- UPDATE. Under INSERT-only both fail with "permission denied for table
-- tool_audit" — and the writer swallows its exceptions at debug level, so
-- every tool call would quietly lose its evidence while the application
-- looked healthy. Verified against the live cluster.
--
-- So the grants are column-scoped instead of table-scoped, which keeps the
-- property that actually matters: the agent may complete its own receipt and
-- cannot falsify anyone's. It has no access to `tool`, `caller`, `args`, or
-- `session_id` after insert, and no DELETE at all.
REVOKE ALL ON pellier.tool_audit FROM pellier_agent;
GRANT INSERT ON pellier.tool_audit TO pellier_agent;
-- Read back only the surrogate key of the row it just wrote (for RETURNING
-- and for the phase-2 WHERE clause). Not args, not result, not session.
GRANT SELECT (audit_id) ON pellier.tool_audit TO pellier_agent;
-- Complete its own receipt, and only these two columns. What was called and
-- on whose behalf is immutable once written.
GRANT UPDATE (result, latency_ms) ON pellier.tool_audit TO pellier_agent;

-- The mapping table itself stays unreadable by both runtime roles; the
-- resolver above is the only way in, and it only ever returns the caller's
-- own scopes.
REVOKE ALL ON pellier.principal_customers FROM pellier_agent;
GRANT EXECUTE ON FUNCTION pellier.current_principal_customers() TO pellier_agent;

-- Governed write path.
--
-- `process_return_idempotent` and `restock_shelf_idempotent` are SECURITY
-- INVOKER, which is what makes this layer work at all: they run as the
-- caller's effective role, so RLS binds inside the function body. A SECURITY
-- DEFINER function would execute as the owner and silently bypass every
-- policy above while appearing to be governed.
--
-- Granted explicitly rather than relying on the default EXECUTE-to-PUBLIC, so
-- revoking PUBLIC later does not quietly break the agent.
GRANT EXECUTE ON FUNCTION pellier.process_return_idempotent(text, text, text, text, text)
    TO pellier_agent;
GRANT EXECUTE ON FUNCTION pellier.restock_shelf_idempotent(text, text, text, integer, text)
    TO pellier_agent;

-- The idempotency ledger the write functions claim and complete. Not
-- customer-scoped, so no RLS: it records that an operation was attempted,
-- which is the property that makes a retry safe.
GRANT SELECT, INSERT, UPDATE ON pellier.write_operations TO pellier_agent;

-- `restock_inventory` adjusts warehouse counts; `initiate_return` reads them.
GRANT UPDATE ON pellier.warehouse_inventory TO pellier_agent;

-- Both write functions recompute `product_catalog.quantity` and take
-- `SELECT ... FOR UPDATE` row locks on the catalog to serialize concurrent
-- writes. A row lock requires UPDATE privilege, not merely SELECT — with
-- SELECT alone the governed rail fails at the lock with "permission denied
-- for table product_catalog" before reaching any policy decision, which reads
-- as a broken tool rather than as an authorization boundary.
GRANT UPDATE ON pellier.product_catalog TO pellier_agent;

-- Trigger-written table. `record_inventory_movement` (migration 015) fires on
-- every `warehouse_inventory` change and appends to the ledger, so a role that
-- may adjust stock must also be able to append the movement. Triggers run as
-- the invoking role here, so a missing grant surfaces from inside the trigger
-- as "permission denied for table inventory_ledger" — several frames away from
-- the statement the agent actually issued.
GRANT INSERT ON pellier.inventory_ledger TO pellier_agent;

-- pellier_query: read-only, and deliberately blind to the ledger.
GRANT SELECT ON pellier.product_catalog, pellier.warehouses,
                pellier.warehouse_inventory, pellier.return_policies
    TO pellier_query;

-- Customer-sensitive reads, which is where this gets interesting: generated
-- SQL may reach `orders` and `returns`, and Row-Level Security scopes it to
-- the same principal a curated tool would see. Withholding the grant entirely
-- would be simpler but would teach the wrong lesson — that generated SQL is
-- safe because it cannot see customer data, rather than because the database
-- decides which rows it sees.
GRANT SELECT ON pellier.orders, pellier.returns, pellier.customers
    TO pellier_query;
GRANT EXECUTE ON FUNCTION pellier.current_principal_customers() TO pellier_query;

REVOKE ALL ON pellier.tool_audit FROM pellier_query;
REVOKE ALL ON pellier.governed_receipts FROM pellier_query;
REVOKE ALL ON pellier.principal_customers FROM pellier_query;

-- ---------------------------------------------------------------------
-- 5. Row-Level Security on the customer-sensitive tables
--
-- Both runtime roles are named. `pellier_query` holds only SELECT, so the
-- policy governs its reads; omitting it would leave RLS enabled with no policy
-- for that role, which denies every generated read regardless of principal and
-- makes the scoping lesson unobservable.
--
-- Both USING and WITH CHECK are specified per command rather than relying on
-- a SELECT-shaped policy. USING governs which existing rows are visible;
-- WITH CHECK governs which new or modified rows may be written. A policy with
-- FOR ALL policy can reuse USING as WITH CHECK when the latter is omitted.
-- Keep both explicit here to distinguish visibility from proposed-row checks.
-- ---------------------------------------------------------------------

ALTER TABLE pellier.orders  ENABLE ROW LEVEL SECURITY;
ALTER TABLE pellier.returns ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS orders_principal_scope ON pellier.orders;
CREATE POLICY orders_principal_scope ON pellier.orders
    FOR ALL
    TO pellier_agent, pellier_query
    USING (customer_id IN (SELECT customer_id FROM pellier.current_principal_customers()))
    WITH CHECK (customer_id IN (SELECT customer_id FROM pellier.current_principal_customers()));

DROP POLICY IF EXISTS returns_principal_scope ON pellier.returns;
CREATE POLICY returns_principal_scope ON pellier.returns
    FOR ALL
    TO pellier_agent, pellier_query
    USING (customer_id IN (SELECT customer_id FROM pellier.current_principal_customers()))
    WITH CHECK (customer_id IN (SELECT customer_id FROM pellier.current_principal_customers()));

COMMIT;
