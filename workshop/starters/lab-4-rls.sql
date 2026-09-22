\set ON_ERROR_STOP on

-- Lab 4 proof artifact: exercise the same customer boundary through PostgreSQL
-- RLS. The script fails closed if the mapping, positive control, denial, or
-- runtime role is wrong. Every write is enclosed by an explicit ROLLBACK.
--
-- Run with:
--   psql -X -v ON_ERROR_STOP=1 -P pager=off \
--     -f workshop/lab-4-rls.sql

DO $mapping$
DECLARE
    mapped_shoppers INTEGER;
    marco_mappings INTEGER;
    jessica_mappings INTEGER;
BEGIN
    SELECT count(*) INTO mapped_shoppers
      FROM pellier.principal_customers;
    SELECT count(*) INTO marco_mappings
      FROM pellier.principal_customers
     WHERE customer_id = 'CUST-MARCO';
    SELECT count(*) INTO jessica_mappings
      FROM pellier.principal_customers
     WHERE customer_id = 'CUST-JESSICA';

    IF mapped_shoppers <> 4 THEN
        RAISE EXCEPTION
            'Lab 4 needs exactly four workshop principal mappings; found %',
            mapped_shoppers;
    END IF;
    IF marco_mappings <> 1 OR jessica_mappings <> 1 THEN
        RAISE EXCEPTION
            'Lab 4 needs one Marco and one Jessica principal mapping';
    END IF;
END;
$mapping$;

SELECT principal_sub AS marco_sub
  FROM pellier.principal_customers
 WHERE customer_id = 'CUST-MARCO'
\gset

SELECT principal_sub AS jessica_sub
  FROM pellier.principal_customers
 WHERE customer_id = 'CUST-JESSICA'
\gset

WITH ordered AS (
    SELECT product_id, sum(quantity)::INTEGER AS ordered_quantity
      FROM pellier.orders
     WHERE customer_id = 'CUST-JESSICA'
     GROUP BY product_id
),
returned AS (
    SELECT product_id, sum(quantity)::INTEGER AS returned_quantity
      FROM pellier.returns
     WHERE customer_id = 'CUST-JESSICA'
       AND status <> 'rejected'
     GROUP BY product_id
)
SELECT o.product_id AS jessica_product_id
  FROM ordered o
  LEFT JOIN returned r USING (product_id)
 WHERE o.ordered_quantity > coalesce(r.returned_quantity, 0)
 ORDER BY o.product_id
 LIMIT 1
\gset

\if :{?jessica_product_id}
\else
  \warn 'Lab 4 needs one returnable Jessica product for the positive write control'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4 RLS proof failed; see the line above'; END $fail$;
\endif

BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '15s';

-- Task 4B. Author one ownership predicate used by both USING and WITH CHECK.
-- RLS trusts the principal context established by the application. It does not
-- independently validate a Cognito token. These direct SQL probes set test context.
-- === WORKSHOP · Row ownership · predicate: START ===
\set ownership_predicate 'false'
-- === WORKSHOP · Row ownership · predicate: END ===

ALTER POLICY orders_principal_scope ON pellier.orders
    USING (:ownership_predicate) WITH CHECK (:ownership_predicate);
ALTER POLICY returns_principal_scope ON pellier.returns
    USING (:ownership_predicate) WITH CHECK (:ownership_predicate);

RESET ROLE;
SET LOCAL ROLE pellier_query;
SELECT set_config('pellier.principal_sub', :'jessica_sub', true);
SELECT current_setting('pellier.principal_sub', true) = :'jessica_sub'
       AS jessica_principal_bound
\gset
\if :jessica_principal_bound
\else
  \warn 'Jessica principal was not bound to the RLS transaction'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4 RLS proof failed; see the line above'; END $fail$;
\endif

SELECT count(*) AS jessica_jessica_rows
  FROM pellier.orders
 WHERE customer_id = 'CUST-JESSICA'
\gset

SELECT 'RLS_READ_JESSICA_JESSICA_ROWS:' || :'jessica_jessica_rows';
SELECT :'jessica_jessica_rows'::INTEGER = 0 AS jessica_read_failed
\gset
\if :jessica_read_failed
  \warn 'Jessica could not read any Jessica rows; the positive control failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4 RLS proof failed; see the line above'; END $fail$;
\endif
RESET ROLE;

RESET ROLE;
SET LOCAL ROLE pellier_query;
SELECT set_config('pellier.principal_sub', :'marco_sub', true);
SELECT current_setting('pellier.principal_sub', true) = :'marco_sub'
       AS marco_principal_bound
\gset
\if :marco_principal_bound
\else
  \warn 'Marco principal was not bound to the RLS transaction'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4 RLS proof failed; see the line above'; END $fail$;
\endif

SELECT count(*) AS marco_jessica_rows
  FROM pellier.orders
 WHERE customer_id = 'CUST-JESSICA'
\gset

SELECT 'RLS_READ_MARCO_JESSICA_ROWS:' || :'marco_jessica_rows';
SELECT :'marco_jessica_rows'::INTEGER <> 0 AS marco_read_failed
\gset
\if :marco_read_failed
  \warn 'Marco could read Jessica rows; the RLS read boundary failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4 RLS proof failed; see the line above'; END $fail$;
\endif
RESET ROLE;

RESET ROLE;
SET LOCAL ROLE pellier_agent;

-- ---------------------------------------------------------------------------
-- Production edge case: the conditions under which the denial below is proof
-- ---------------------------------------------------------------------------
-- A policy you author only decides anything if the role it is tested against
-- is actually subject to it. Three ways that silently stops being true, none
-- of which change your policy text:
--
--   1. BYPASSRLS or SUPERUSER on the runtime role. Row-level security is
--      skipped outright. Migration 016 creates both runtime roles NOBYPASSRLS,
--      but that is a creation-time fact, not a standing guarantee -- a later
--      ALTER ROLE re-grants it, and nothing in the policy would look different.
--
--   2. Table ownership. `ENABLE ROW LEVEL SECURITY` does not apply to the
--      table's owner; only `FORCE ROW LEVEL SECURITY` does. pellier.returns is
--      ENABLE, so running this proof as the owning role would produce a
--      successful write and no denial -- an outcome that looks like a broken
--      policy but is a correctly-skipped one.
--
--   3. Permissive policies combine with OR. Adding a second PERMISSIVE policy
--      to this table widens access; it cannot narrow it. A denial that holds
--      today stops holding the moment anyone adds a broader permissive rule,
--      and the rule you wrote is still there, still correct, still quoted in
--      your evidence.
--
-- Asserting these here turns each one from a confusing "out-of-scope write
-- succeeded" into a named diagnosis.
DO $rls_preconditions$
DECLARE
    bypasses BOOLEAN;
    is_super BOOLEAN;
    rls_enabled BOOLEAN;
    rls_forced BOOLEAN;
    table_owner NAME;
    permissive_policies INTEGER;
BEGIN
    SELECT rolbypassrls, rolsuper INTO bypasses, is_super
      FROM pg_roles WHERE rolname = current_user;
    IF bypasses THEN
        RAISE EXCEPTION
            'Role % holds BYPASSRLS, so row-level security is skipped and the '
            'denial below would prove nothing. Revoke it: ALTER ROLE % NOBYPASSRLS;',
            current_user, current_user;
    END IF;
    IF is_super THEN
        RAISE EXCEPTION
            'Role % is a superuser, which is exempt from row-level security. '
            'Run this proof as the pellier_agent runtime role.',
            current_user;
    END IF;

    SELECT relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner)
      INTO rls_enabled, rls_forced, table_owner
      FROM pg_class WHERE oid = 'pellier.returns'::regclass;
    IF NOT rls_enabled THEN
        RAISE EXCEPTION
            'pellier.returns has no row-level security enabled; apply '
            'scripts/migrations/016_runtime_roles_rls.sql before proving a boundary.';
    END IF;
    IF table_owner = current_user AND NOT rls_forced THEN
        RAISE EXCEPTION
            'This proof is running as %, which owns pellier.returns. An owner '
            'is exempt from ENABLE ROW LEVEL SECURITY, so the write below would '
            'succeed no matter what your policy says. Either run as a '
            'non-owning runtime role, or set FORCE ROW LEVEL SECURITY.',
            current_user;
    END IF;

    SELECT count(*) INTO permissive_policies
      FROM pg_policies
     WHERE schemaname = 'pellier' AND tablename = 'returns'
       AND permissive = 'PERMISSIVE';
    IF permissive_policies <> 1 THEN
        RAISE EXCEPTION
            'pellier.returns carries % permissive policies; this proof expects '
            'exactly one (returns_principal_scope). Permissive policies are '
            'OR-ed together, so an extra one widens access and the denial below '
            'stops being attributable to the rule you wrote.',
            permissive_policies;
    END IF;

    RAISE NOTICE 'RLS_PRECONDITIONS_OK: role=% owner=% forced=% permissive=%',
        current_user, table_owner, rls_forced, permissive_policies;
END;
$rls_preconditions$;

SELECT CASE
         WHEN current_user = 'pellier_agent' THEN 'RLS_PROBE_ROLE_OK'
         ELSE 'RLS_PROBE_ROLE_WRONG'
       END;
SELECT current_user <> 'pellier_agent' AS role_probe_failed
\gset
\if :role_probe_failed
  \warn 'The write proof is not running as pellier_agent'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4 RLS proof failed; see the line above'; END $fail$;
\endif

SELECT set_config('pellier.principal_sub', '', true);
DO $missing$ BEGIN
    IF EXISTS (SELECT 1 FROM pellier.orders) THEN
        RAISE EXCEPTION 'RLS missing-principal check failed';
    END IF;
END $missing$;
SELECT set_config('pellier.principal_sub', 'workshop-unmapped-principal', true);
DO $unmapped$ BEGIN
    IF EXISTS (SELECT 1 FROM pellier.orders) THEN
        RAISE EXCEPTION 'RLS unmapped-principal check failed';
    END IF;
END $unmapped$;

SELECT set_config('pellier.lab4_product_id', :'jessica_product_id', true);
SELECT set_config('pellier.principal_sub', :'marco_sub', true);

DO $marco_write$
DECLARE
    error_message TEXT;
BEGIN
    BEGIN
        INSERT INTO pellier.returns
            (customer_id, product_id, reason, status, quantity)
        VALUES
            (
                'CUST-JESSICA',
                current_setting('pellier.lab4_product_id'),
                'other',
                'pending',
                1
            );
        RAISE EXCEPTION
            'RLS_PROBE_MARCO_SQLSTATE:00000: out-of-scope write succeeded';
    EXCEPTION
        WHEN insufficient_privilege THEN
            GET STACKED DIAGNOSTICS error_message = MESSAGE_TEXT;
            IF position('row-level security policy' IN error_message) = 0 THEN
                RAISE EXCEPTION
                    'Marco received 42501 for a non-RLS reason: %',
                    error_message;
            END IF;
            RAISE NOTICE 'RLS_PROBE_MARCO_SQLSTATE:42501';
    END;
END;
$marco_write$;

SELECT set_config('pellier.principal_sub', :'jessica_sub', true);
INSERT INTO pellier.returns
    (customer_id, product_id, reason, status, quantity)
VALUES
    ('CUST-JESSICA', :'jessica_product_id', 'other', 'pending', 1);
DO $jessica_write$
BEGIN
    RAISE NOTICE 'RLS_PROBE_JESSICA_SQLSTATE:00000';
END;
$jessica_write$;

RESET ROLE;
ROLLBACK;
\echo 'Lab 4 RLS contract passed; policy edits and test writes rolled back'
