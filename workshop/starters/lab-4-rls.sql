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
-- Everything below runs in one transaction. If every probe matches, it
-- commits: your predicate becomes the live policy and the probe writes are
-- undone. If any probe differs, it rolls back and the live policies stay.

SET client_min_messages TO warning;
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '15s';

-- Your build: the one ownership expression.
-- === WORKSHOP - Row ownership - predicate: START ===
SELECT $predicate$
  false
$predicate$ AS ownership_predicate
\gset
-- === WORKSHOP - Row ownership - predicate: END ===

ALTER POLICY orders_owner ON pellier.orders
    USING (:ownership_predicate) WITH CHECK (:ownership_predicate);
ALTER POLICY support_tickets_owner ON pellier.support_tickets
    USING (:ownership_predicate) WITH CHECK (:ownership_predicate);

-- Stamp both policies with your predicate's sha256, so scripts/lab4_rls_check.py
-- can tell the predicate you deployed from the one the database shipped with.
SELECT 'Lab 4B predicate sha256 ' || hash AS stamp, left(hash, 12) AS stamp_short
  FROM (SELECT encode(sha256(convert_to(:'ownership_predicate', 'UTF8')), 'hex') AS hash) h
\gset
COMMENT ON POLICY orders_owner ON pellier.orders IS :'stamp';
COMMENT ON POLICY support_tickets_owner ON pellier.support_tickets IS :'stamp';

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

-- The probes run inside a savepoint. Rolling back to it undoes their test
-- writes; your policy edit above stays in the transaction.
SAVEPOINT probes;

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

-- Back to the owner.
RESET ROLE;

-- Every customer, one at a time, as pellier_agent: each must see exactly their
-- own orders and tickets. A predicate that names Theo and Jessica would pass the
-- probes above and still hide everyone else's rows, so it is refused here.
DO $every_customer$
DECLARE
    names text[];
    own bigint[];
    seen bigint;
    exact int := 0;
BEGIN
    SELECT array_agg(c.cognito_username ORDER BY c.id),
           array_agg((SELECT count(*) FROM pellier.orders o WHERE o.customer_id = c.id)
                     + (SELECT count(*) FROM pellier.support_tickets t
                         WHERE t.customer_id = c.id) ORDER BY c.id)
      INTO names, own
      FROM pellier.customers c;
    FOR i IN 1 .. coalesce(array_length(names, 1), 0) LOOP
        PERFORM set_config('pellier.principal_username', names[i], true);
        EXECUTE 'SET LOCAL ROLE pellier_agent';
        SELECT (SELECT count(*) FROM pellier.orders)
               + (SELECT count(*) FROM pellier.support_tickets) INTO seen;
        EXECUTE 'RESET ROLE';
        IF seen = own[i] THEN
            exact := exact + 1;
        END IF;
    END LOOP;
    PERFORM set_config('lab4.customers', coalesce(array_length(names, 1), 0)::text, true);
    PERFORM set_config('lab4.customers_exact', exact::text, true);
END
$every_customer$;
SELECT current_setting('lab4.customers') AS customers,
       current_setting('lab4.customers_exact') AS exact
\gset every_

-- Undo the probe writes and settings; your policy edit stays in the transaction.
ROLLBACK TO SAVEPOINT probes;

-- A temporary table, dropped when the transaction ends either way.
CREATE TEMP TABLE lab_4_probes (probe text, bound_as text, expected text, observed text)
    ON COMMIT DROP;
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
     :'as_jessica_tickets'),
    ('Customers who see exactly their own orders and tickets', 'each customer',
     :'every_customers', :'every_exact');

\echo 'Lab 4B: your ownership predicate, probed as pellier_agent'
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

\echo 'Expected  every probe matches; then the transaction commits and your predicate is the live policy'
SELECT :lab_4_matched = :lab_4_probes AS lab_4_passed \gset
\if :lab_4_passed
  COMMIT;
  \echo 'Observed ' :lab_4_matched 'of' :lab_4_probes 'probes match; committed, your predicate is now the live policy'
  \echo 'Deployed  your predicate on orders_owner and support_tickets_owner, sha256' :stamp_short
  \echo '          the probe writes were undone before the commit'
  \echo 'Lab 4B check passed'
\else
  ROLLBACK;
  \echo 'Observed ' :lab_4_matched 'of' :lab_4_probes 'probes match; rolled back, the live policies are unchanged'
  \echo 'Next      read the rows marked differs. 0 where a number is expected means your'
  \echo '          expression matches nobody; a number where 0 is expected means it matches'
  \echo '          everybody. The bound name is current_setting(''pellier.principal_username'', true).'
  \echo '          If only the every-customer row differs, your expression names particular'
  \echo '          customers instead of the one bound on the session.'
  \echo 'Lab 4B check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4B check failed; see the lines above'; END $fail$;
\endif
