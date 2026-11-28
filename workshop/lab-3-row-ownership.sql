\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off \pset border 2 \pset linestyle unicode \pset expanded off \pset format wrapped

-- Lab 3, Task 3B: the row-ownership predicate.
--
-- Ask Pellier reads orders and support tickets as the pellier_agent role, with
-- one customer's sign-in name bound on the session as
-- pellier.principal_username. In process, that customer comes from
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
--   psql -f workshop/lab-3-row-ownership.sql
--
-- Everything below runs in one transaction. If every test matches, it
-- commits: your predicate becomes the live policy and the test writes are
-- undone. If any test differs, it rolls back and the live policies stay.

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

ALTER POLICY orders_own_rows ON pellier.orders
    USING (:ownership_predicate) WITH CHECK (:ownership_predicate);
ALTER POLICY support_tickets_own_rows ON pellier.support_tickets
    USING (:ownership_predicate) WITH CHECK (:ownership_predicate);

-- Stamp both policies with your predicate's sha256, so scripts/lab3_row_ownership_check.py
-- can tell the predicate you deployed from the one the database shipped with.
SELECT 'Lab 3B predicate sha256 ' || hash AS stamp
  FROM (SELECT encode(sha256(convert_to(:'ownership_predicate', 'UTF8')), 'hex') AS hash) h
\gset
COMMENT ON POLICY orders_own_rows ON pellier.orders IS :'stamp';
COMMENT ON POLICY support_tickets_own_rows ON pellier.support_tickets IS :'stamp';

-- What the tables hold, read as the owner, which row-level security does not
-- apply to: the numbers each test below must reproduce under your policy.
SELECT (SELECT count(*) FROM pellier.orders WHERE customer_id = 'CUST-THEO') AS theo_orders,
       (SELECT count(*) FROM pellier.support_tickets WHERE customer_id = 'CUST-THEO')
         AS theo_tickets,
       (SELECT count(*) FROM pellier.orders WHERE customer_id = 'CUST-JESSICA') AS jessica_orders,
       (SELECT count(*) FROM pellier.support_tickets WHERE customer_id = 'CUST-JESSICA')
         AS jessica_tickets
\gset owner_

-- The tests run inside a savepoint. Rolling back to it undoes their test
-- writes; your policy edit above stays in the transaction.
SAVEPOINT probes;

-- A denial below proves something only if the role is subject to the policy:
-- no BYPASSRLS, no superuser, not the tables' owner, and exactly one
-- applicable permissive policy per table (these combine with OR, so a
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
       AND permissive = 'PERMISSIVE'
       AND EXISTS (SELECT 1 FROM unnest(roles) AS r(role_name)
                   WHERE CASE WHEN role_name = 'public' THEN true
                         ELSE pg_has_role(current_user, role_name, 'USAGE') END);
    IF permissive_count <> 2 THEN
        RAISE EXCEPTION '% applicable permissive policies on orders and support_tickets; expected one each',
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
-- SQLSTATE the database gave, and the tests below show it in words: 42501 is a
-- row-level security refusal ("blocked"), 00000 is no error ("allowed").
DO $writes$
DECLARE
    state text;
BEGIN
    FOREACH state IN ARRAY ARRAY['CUST-JESSICA', 'CUST-THEO'] LOOP
        BEGIN
            INSERT INTO pellier.support_tickets (ticket_id, customer_id, subject, status, channel)
            VALUES ('TKT-LAB3-' || state, state, 'Lab 3 row-level security probe', 'open', 'chat');
            PERFORM set_config('lab3.write_' || lower(replace(state, 'CUST-', '')), '00000', true);
        EXCEPTION WHEN insufficient_privilege THEN
            PERFORM set_config('lab3.write_' || lower(replace(state, 'CUST-', '')), SQLSTATE, true);
        END;
    END LOOP;
END
$writes$;
SELECT current_setting('lab3.write_jessica') AS write_jessica,
       current_setting('lab3.write_theo') AS write_theo
\gset as_theo_

-- No one signed in: the role must see nothing.
SELECT set_config('pellier.principal_username', '', true) AS bound \gset
SELECT count(*) AS orders FROM pellier.orders \gset as_nobody_

-- Jessica signed in: she must see her own rows. A predicate that names only Theo
-- hides them from her.
SELECT set_config('pellier.principal_username', 'jessica', true) AS bound \gset
SELECT (SELECT count(*) FROM pellier.orders) AS orders,
       (SELECT count(*) FROM pellier.support_tickets) AS tickets
\gset as_jessica_

-- Back to the owner.
RESET ROLE;

-- Every customer, one at a time, as pellier_agent: each must see exactly their
-- own orders and tickets. A predicate that names Theo and Jessica would pass the
-- tests above and still hide everyone else's rows, so it is refused here.
DO $every_customer$
DECLARE
    shopper record;
    seen_orders bigint[];
    seen_tickets text[];
    customers int := 0;
    exact int := 0;
BEGIN
    FOR shopper IN
        SELECT c.cognito_username,
               ARRAY(SELECT o.id FROM pellier.orders o
                      WHERE o.customer_id = c.id ORDER BY o.id) AS own_orders,
               ARRAY(SELECT t.ticket_id FROM pellier.support_tickets t
                      WHERE t.customer_id = c.id ORDER BY t.ticket_id) AS own_tickets
          FROM pellier.customers c ORDER BY c.id
    LOOP
        PERFORM set_config('pellier.principal_username', shopper.cognito_username, true);
        EXECUTE 'SET LOCAL ROLE pellier_agent';
        SELECT ARRAY(SELECT id FROM pellier.orders ORDER BY id),
               ARRAY(SELECT ticket_id FROM pellier.support_tickets ORDER BY ticket_id)
          INTO seen_orders, seen_tickets;
        EXECUTE 'RESET ROLE';
        customers := customers + 1;
        IF seen_orders = shopper.own_orders AND seen_tickets = shopper.own_tickets THEN
            exact := exact + 1;
        END IF;
    END LOOP;
    PERFORM set_config('lab3.customers', customers::text, true);
    PERFORM set_config('lab3.customers_exact', exact::text, true);
END
$every_customer$;
SELECT current_setting('lab3.customers') AS customers,
       current_setting('lab3.customers_exact') AS exact
\gset every_

-- Undo the test writes and settings; your policy edit stays in the transaction.
ROLLBACK TO SAVEPOINT probes;

-- A temporary table, dropped when the transaction ends either way.
CREATE TEMP TABLE lab_3_probes (probe text, bound_as text, expected text, observed text)
    ON COMMIT DROP;
INSERT INTO lab_3_probes VALUES
    ('Theo reads his own orders', 'theo', :'owner_theo_orders', :'as_theo_theo_orders'),
    ('Theo reads his own tickets', 'theo', :'owner_theo_tickets', :'as_theo_theo_tickets'),
    ('Theo reads Jessica''s orders', 'theo', '0', :'as_theo_jessica_orders'),
    ('Theo reads Jessica''s tickets', 'theo', '0', :'as_theo_jessica_tickets'),
    ('Theo writes a ticket in Jessica''s name', 'theo', 'blocked',
     CASE :'as_theo_write_jessica' WHEN '42501' THEN 'blocked' WHEN '00000' THEN 'allowed'
          ELSE 'error' END),
    ('Theo writes a ticket in his own name', 'theo', 'allowed',
     CASE :'as_theo_write_theo' WHEN '42501' THEN 'blocked' WHEN '00000' THEN 'allowed'
          ELSE 'error' END),
    ('No one signed in reads orders', '(nobody)', '0', :'as_nobody_orders'),
    ('Jessica reads her own orders', 'jessica', :'owner_jessica_orders',
     :'as_jessica_orders'),
    ('Jessica reads her own tickets', 'jessica', :'owner_jessica_tickets',
     :'as_jessica_tickets'),
    ('Each customer sees only their own rows', 'everyone',
     :'every_customers', :'every_exact');

\echo 'Lab 3B: Aurora enforces ownership on every path'
\echo ''
SELECT probe AS "Test", bound_as AS "Signed in", expected AS "Should be",
       CASE WHEN expected = observed THEN '' ELSE observed END AS "Is now",
       CASE WHEN expected = observed THEN '✓' ELSE '✗' END AS "OK"
  FROM lab_3_probes;
SELECT count(*) FILTER (WHERE expected = observed) AS matched, count(*) AS probes
  FROM lab_3_probes
\gset lab_3_
-- Which way the predicate is wrong, for the Next line. Each flag is true when its test fails.
SELECT coalesce(bool_or(probe LIKE 'Theo reads Jessica%' AND observed <> expected), false)
         AS sees_hers,
       coalesce(bool_or(probe LIKE 'Theo reads his own%' AND observed <> expected), false)
         AS theo_blind,
       coalesce(bool_or(probe LIKE 'No one signed in%' AND observed <> expected), false)
         AS nobody_sees,
       coalesce(bool_or(probe LIKE 'Jessica reads her own%' AND observed <> expected), false)
         AS jessica_blind,
       coalesce(bool_or(probe LIKE 'Each customer%' AND observed <> expected), false)
         AS some_customer_off
  FROM lab_3_probes
\gset case_

SELECT :lab_3_matched = :lab_3_probes AS lab_3_passed \gset
\if :lab_3_passed
  COMMIT;
  \echo :lab_3_matched 'of' :lab_3_probes 'tests passed. Saved, your predicate is now the live policy.'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[32m' || true`
  \echo 'Lab 3B predicate check passed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  -- A catch-up (lab_run.py finish) runs the next step itself, so it asks for no Next.
  \if :{?quiet_next}
  \else
    \echo ''
    \echo 'Next  In the guide, read "Prove the deployed build".'
    \echo '      When the deploy has finished, in the Pellier workshop terminal run:'
    \echo '      uv run scripts/lab_run.py send --lab 3'
  \endif
\else
  ROLLBACK;
  \echo :lab_3_matched 'of' :lab_3_probes 'tests passed. Your change was undone.'
  \echo 'The live policies are unchanged.'
  \echo ''
  \echo 'Next  In Task 3B, choose "Write it yourself" or "Install the provided fix".'
  \if :case_sees_hers
    \echo '      Your rule matches everyone, so Theo can see Jessica''s orders.'
    \echo '      Make it true only for rows that belong to the signed-in customer.'
  \elif :case_theo_blind
    \echo '      Your rule matches no one, so Theo can''t see his own' :owner_theo_orders 'orders.'
    \echo '      Make it true only for rows that belong to the signed-in customer.'
  \elif :case_nobody_sees
    \echo '      Your rule shows orders when no one is signed in.'
    \echo '      It must match no row unless a customer is signed in.'
  \elif :case_jessica_blind
    \echo '      Your rule works for Theo, but Jessica can''t see her own orders.'
    \echo '      It must follow whoever is signed in, not one customer.'
  \elif :case_some_customer_off
    \echo '      Close. It works for Theo and Jessica but not every customer.'
  \else
    \echo '      A test above is marked ✗. Compare Should be with Is now.'
  \endif
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[31m' || true`
  \echo 'Lab 3B predicate check failed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  DO $fail$ BEGIN RAISE EXCEPTION 'stopped on purpose; see Next'; END $fail$;
\endif
