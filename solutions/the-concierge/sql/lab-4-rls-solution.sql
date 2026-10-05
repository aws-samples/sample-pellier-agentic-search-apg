\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off

-- Lab 4, Task 4B: the row-ownership predicate.
--
-- Ask Pellier and the Operator's Investigator read orders and support tickets
-- as the pellier_agent role, with one customer's sign-in name bound on the
-- session as pellier.principal_username. In process, that customer comes from
-- the signed token; on the Gateway, it is the customer Cedar's owner-only
-- permit admitted. Row-level security then returns only that customer's rows,
-- even if a tool's own SQL asks for someone else's: it contains a wrong query.
--
-- Write one expression between the markers. It decides which rows a session
-- may see (USING) and which rows it may write (WITH CHECK), on pellier.orders
-- and pellier.support_tickets. A row has a customer_id (CUST-THEO);
-- pellier.customers maps each id to its cognito_username (theo).
--
-- Run with:
--   psql -X -P pager=off -f workshop/lab-4-rls.sql
--
-- Everything below runs in one transaction that ends in ROLLBACK: your policy
-- edit and the test writes are never kept, and the live policies stay as
-- they were.

SET client_min_messages TO warning;
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '15s';

-- Your build: the one ownership expression.
-- === WORKSHOP - Row ownership - predicate: START ===
SELECT $predicate$
  customer_id = (SELECT c.id
                   FROM pellier.customers c
                  WHERE c.cognito_username = current_setting('pellier.principal_username', true))
$predicate$ AS ownership_predicate
\gset
-- === WORKSHOP - Row ownership - predicate: END ===

ALTER POLICY orders_owner ON pellier.orders
    USING (:ownership_predicate) WITH CHECK (:ownership_predicate);
ALTER POLICY support_tickets_owner ON pellier.support_tickets
    USING (:ownership_predicate) WITH CHECK (:ownership_predicate);

-- What the tables hold, read as the owner, which row-level security does not
-- apply to: the numbers each probe below must reproduce under your policy.
SELECT (SELECT count(*) FROM pellier.orders WHERE customer_id = 'CUST-THEO') AS theo_orders,
       (SELECT count(*) FROM pellier.support_tickets WHERE customer_id = 'CUST-THEO')
         AS theo_tickets,
       (SELECT count(*) FROM pellier.orders WHERE customer_id = 'CUST-JESSICA') AS jessica_orders,
       (SELECT count(*) FROM pellier.support_tickets WHERE customer_id = 'CUST-JESSICA')
         AS jessica_tickets,
       (SELECT string_agg(cognito_username || ' -> ' || id, ', ' ORDER BY id)
          FROM pellier.customers WHERE id IN ('CUST-THEO', 'CUST-JESSICA')) AS names
\gset owner_

-- A denial below proves something only if the role is subject to the policy:
-- no BYPASSRLS, no superuser, not the tables' owner, and exactly one
-- permissive policy per table (permissive policies combine with OR, so a
-- second one would widen access whatever your expression says).
SET LOCAL ROLE pellier_agent;
DO $preconditions$
DECLARE
    bypasses boolean;
    is_super boolean;
    misowned text;
    permissive_count integer;
BEGIN
    SELECT rolbypassrls, rolsuper INTO bypasses, is_super
      FROM pg_roles WHERE rolname = current_user;
    IF bypasses OR is_super THEN
        RAISE EXCEPTION 'pellier_agent bypasses row-level security (BYPASSRLS or superuser), '
                        'so a denial would prove nothing';
    END IF;
    SELECT string_agg(c.relname, ', ') INTO misowned
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'pellier' AND c.relname IN ('orders', 'support_tickets')
       AND (NOT c.relrowsecurity
            OR (pg_get_userbyid(c.relowner) = current_user AND NOT c.relforcerowsecurity));
    IF misowned IS NOT NULL THEN
        RAISE EXCEPTION 'row-level security does not bind pellier_agent on %', misowned;
    END IF;
    SELECT count(*) INTO permissive_count FROM pg_policies
     WHERE schemaname = 'pellier' AND tablename IN ('orders', 'support_tickets')
       AND permissive = 'PERMISSIVE';
    IF permissive_count <> 2 THEN
        RAISE EXCEPTION '% permissive policies on orders and support_tickets; expected one each',
                        permissive_count;
    END IF;
END
$preconditions$;

-- Theo signed in: his own rows, then Jessica's.
SELECT set_config('pellier.principal_username', 'theo', true) AS bound \gset
SELECT (SELECT count(*) FROM pellier.orders WHERE customer_id = 'CUST-THEO') AS theo_orders,
       (SELECT count(*) FROM pellier.support_tickets WHERE customer_id = 'CUST-THEO')
         AS theo_tickets,
       (SELECT count(*) FROM pellier.orders WHERE customer_id = 'CUST-JESSICA') AS jessica_orders,
       (SELECT count(*) FROM pellier.support_tickets WHERE customer_id = 'CUST-JESSICA')
         AS jessica_tickets
\gset as_theo_

-- Theo writes a ticket in Jessica's name, then in his own. Each answer is the
-- SQLSTATE the database gave: 42501 is a row-level security refusal.
DO $writes$
DECLARE
    state text;
BEGIN
    FOREACH state IN ARRAY ARRAY['CUST-JESSICA', 'CUST-THEO'] LOOP
        BEGIN
            INSERT INTO pellier.support_tickets (ticket_id, customer_id, subject, status, channel)
            VALUES ('TKT-LAB4-' || state, state, 'Lab 4 row-level security probe', 'open', 'chat');
            PERFORM set_config('lab4.write_' || lower(replace(state, 'CUST-', '')), '00000', true);
        EXCEPTION WHEN insufficient_privilege THEN
            PERFORM set_config('lab4.write_' || lower(replace(state, 'CUST-', '')), SQLSTATE, true);
        END;
    END LOOP;
END
$writes$;
SELECT current_setting('lab4.write_jessica') AS write_jessica,
       current_setting('lab4.write_theo') AS write_theo
\gset as_theo_

-- No one signed in: the role must see nothing.
SELECT set_config('pellier.principal_username', '', true) AS bound \gset
SELECT count(*) AS orders FROM pellier.orders \gset as_nobody_

-- The Investigator, working Jessica's case, binds her name and must see her rows.
SELECT set_config('pellier.principal_username', 'jessica', true) AS bound \gset
SELECT (SELECT count(*) FROM pellier.orders) AS orders,
       (SELECT count(*) FROM pellier.support_tickets) AS tickets
\gset as_jessica_

-- Back to the owner, to tabulate the probes.
RESET ROLE;

-- A temporary table inside the transaction: the ROLLBACK below drops it too.
CREATE TEMP TABLE lab_4_probes (probe text, bound_as text, expected text, observed text);
INSERT INTO lab_4_probes VALUES
    ('Theo reads his own orders', 'theo', :'owner_theo_orders', :'as_theo_theo_orders'),
    ('Theo reads his own tickets', 'theo', :'owner_theo_tickets', :'as_theo_theo_tickets'),
    ('Theo reads Jessica''s orders', 'theo', '0', :'as_theo_jessica_orders'),
    ('Theo reads Jessica''s tickets', 'theo', '0', :'as_theo_jessica_tickets'),
    ('Theo writes a ticket in Jessica''s name', 'theo', '42501', :'as_theo_write_jessica'),
    ('Theo writes a ticket in his own name', 'theo', '00000', :'as_theo_write_theo'),
    ('No one signed in reads orders', '(none)', '0', :'as_nobody_orders'),
    ('The Investigator reads Jessica''s orders', 'jessica', :'owner_jessica_orders',
     :'as_jessica_orders'),
    ('The Investigator reads Jessica''s tickets', 'jessica', :'owner_jessica_tickets',
     :'as_jessica_tickets');

\echo 'Lab 4B: your ownership predicate, as pellier_agent, rolled back'
\echo 'Evidence  policies orders_owner and support_tickets_owner, rewritten inside this transaction'
\echo '          sign-in names in pellier.customers:' :owner_names
\echo ''
SELECT probe, bound_as,
       expected,
       observed,
       CASE WHEN expected = observed THEN 'matches' ELSE 'differs' END AS verdict
  FROM lab_4_probes;
SELECT count(*) FILTER (WHERE expected = observed) AS matched, count(*) AS probes
  FROM lab_4_probes
\gset lab_4_

ROLLBACK;

\echo 'Expected  every probe matches, and the policy edit and the test writes are rolled back'
\echo 'Observed ' :lab_4_matched 'of' :lab_4_probes 'probes match; rolled back, nothing above was kept'
SELECT :lab_4_matched = :lab_4_probes AS lab_4_passed \gset
\if :lab_4_passed
  \echo 'Lab 4B check passed'
\else
  \echo 'Next      read the rows marked differs. 0 where a number is expected means your'
  \echo '          expression matches nobody; a number where 0 is expected means it matches'
  \echo '          everybody. The bound name is current_setting(''pellier.principal_username'', true).'
  \echo 'Lab 4B check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4B check failed; see the lines above'; END $fail$;
\endif
