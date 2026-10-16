\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off

-- Lab 4, Task 4B: what the money role may do.
--
-- Every credit is written by one function, pellier.apply_store_credit. It
-- refuses any credit a person did not approve exactly, under that review's own
-- key, and a trigger on pellier.store_credits refuses the same for any insert.
-- Both rails run the credit as the pellier_credit_writer role: in process
-- through DatabaseService.fetch_all_as_credit_writer, on the Gateway through
-- run_as_credit_writer. That role's privileges decide what else a money path
-- could do. The trigger covers inserts only, so a role that may UPDATE
-- pellier.store_credits can change an approved amount after the fact, and no
-- check runs.
--
-- Write the statements between the markers. They are the whole of what
-- pellier_credit_writer may do: this file first takes every privilege away
-- from it and puts the function back to its caller's rights.
--
-- Run with:
--   psql -f workshop/lab-4-credit-writer.sql
--
-- Everything below runs in one transaction. If every probe matches, it
-- commits: your statements become the live privileges and the probe credit is
-- undone. If any probe differs, it rolls back and the live privileges stay.

SET client_min_messages TO warning;
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '15s';

SELECT count(*) AS credits_before FROM pellier.store_credits \gset

-- A clean slate: no table privilege, no row policy, no EXECUTE, invoker's rights.
REVOKE ALL ON pellier.store_credits, pellier.orders, pellier.approvals, pellier.customers
    FROM pellier_credit_writer;
REVOKE ALL ON FUNCTION pellier.apply_store_credit(text, text, integer, text, text)
    FROM pellier_credit_writer, PUBLIC;
ALTER FUNCTION pellier.apply_store_credit(text, text, integer, text, text)
    SECURITY INVOKER RESET ALL;
SELECT format('DROP POLICY %I ON %I.%I', policyname, schemaname, tablename)
  FROM pg_policies WHERE 'pellier_credit_writer' = ANY (roles)
\gexec

-- Your build: what pellier_credit_writer may do.
-- === WORKSHOP - Credit writer - privileges: START ===
SELECT $privileges$
  ALTER FUNCTION pellier.apply_store_credit(text, text, integer, text, text)
      SECURITY DEFINER SET search_path = pg_catalog, pg_temp;
  GRANT EXECUTE ON FUNCTION pellier.apply_store_credit(text, text, integer, text, text)
      TO pellier_credit_writer;
$privileges$ AS privileges
\gset
-- === WORKSHOP - Credit writer - privileges: END ===

SELECT :'privileges' \gexec

-- Stamp the function with your statements' sha256, so a later check can tell
-- the privileges you deployed from the ones the database shipped with.
SELECT 'Lab 4B privileges sha256 ' || hash AS stamp, left(hash, 12) AS stamp_short
  FROM (SELECT encode(sha256(convert_to(:'privileges', 'UTF8')), 'hex') AS hash) h
\gset
COMMENT ON FUNCTION pellier.apply_store_credit(text, text, integer, text, text) IS :'stamp';

-- The probes run inside a savepoint. Rolling back to it undoes the probe
-- customer, its orders, its approved review and its credit; your statements
-- above stay in the transaction.
SAVEPOINT probes;

-- A probe case, written as the owner: two received returns and a review a
-- person approved for $25.00 of them, with the review's own write key.
INSERT INTO pellier.customers (id, name, cognito_username)
VALUES ('CUST-LABFOURPROBE', 'Lab 4 probe', 'lab4-probe');
INSERT INTO pellier.orders (customer_id, product_id, amount_paid_cents, ship_to, return_status)
SELECT 'CUST-LABFOURPROBE', '42', 1250, 'Lab 4 probe', 'received' FROM generate_series(1, 2);
INSERT INTO pellier.approvals (customer_id, tool, args, status, order_ids, action_hash,
                               requester_kind, decided_by, decided_at)
SELECT 'CUST-LABFOURPROBE', 'give_store_credit',
       jsonb_build_object('customer_id', 'CUST-LABFOURPROBE', 'amount_cents', 2500,
                          'reason', 'Lab 4 probe'),
       'approved', array_agg(id ORDER BY id), repeat('b', 64), 'operator', 'lab4-probe', now()
  FROM pellier.orders WHERE customer_id = 'CUST-LABFOURPROBE';
SELECT id AS review, 'operator-review:' || id || ':' || left(action_hash, 32) AS key
  FROM pellier.approvals WHERE customer_id = 'CUST-LABFOURPROBE'
\gset probe_
SELECT set_config('lab4.review', :'probe_review', true) AS review \gset

-- Each money probe runs as pellier_credit_writer. A refusal is recorded as its
-- SQLSTATE and where it came from: 42501 is a privilege the role does not
-- hold; 23514 is a rule the table's trigger enforces.
SET LOCAL ROLE pellier_credit_writer;
SELECT pellier.apply_store_credit(:'probe_key', 'CUST-LABFOURPROBE', 5000, 'Lab 4 probe', NULL)
         ->>'status' AS amount,
       pellier.apply_store_credit(:'probe_key' || '-minted', 'CUST-LABFOURPROBE', 2500,
                                  'Lab 4 probe', NULL)->>'status' AS other_key
\gset refused_
SELECT (pellier.apply_store_credit(:'probe_key', 'CUST-LABFOURPROBE', 2500, 'Lab 4 probe', NULL)
          ->>'credit_id') AS first,
       (pellier.apply_store_credit(:'probe_key', 'CUST-LABFOURPROBE', 2500, 'Lab 4 probe', NULL)
          ->>'credit_id') AS retry
\gset credit_
DO $direct$
DECLARE
    v_constraint text;
    v_rows bigint;
BEGIN
    BEGIN
        INSERT INTO pellier.store_credits (approval_id, customer_id, amount_cents, reason,
                                           idempotency_key)
        VALUES (current_setting('lab4.review')::bigint, 'CUST-LABFOURPROBE', 2500, 'Lab 4 probe',
                'written-by-hand');
        PERFORM set_config('lab4.insert', '00000', true);
        PERFORM set_config('lab4.insert_source', 'the row was written', true);
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        PERFORM set_config('lab4.insert', SQLSTATE, true);
        PERFORM set_config('lab4.insert_source', CASE
            WHEN SQLSTATE = '42501' THEN 'no INSERT privilege on pellier.store_credits'
            WHEN v_constraint <> '' THEN v_constraint || ', a rule the owner can switch off'
            ELSE SQLERRM END, true);
    END;
    BEGIN
        UPDATE pellier.store_credits SET amount_cents = 50000
         WHERE customer_id = 'CUST-LABFOURPROBE';
        GET DIAGNOSTICS v_rows = ROW_COUNT;
        PERFORM set_config('lab4.update', '00000', true);
        PERFORM set_config('lab4.update_source',
                           v_rows || ' row updated: the approved $25.00 credit is now $500.00', true);
    EXCEPTION WHEN OTHERS THEN
        PERFORM set_config('lab4.update', SQLSTATE, true);
        PERFORM set_config('lab4.update_source', CASE
            WHEN SQLSTATE = '42501' THEN 'no UPDATE privilege on pellier.store_credits'
            ELSE SQLERRM END, true);
    END;
END
$direct$;
SELECT current_setting('lab4.insert') AS insert, current_setting('lab4.insert_source') AS insert_source,
       current_setting('lab4.update') AS update, current_setting('lab4.update_source') AS update_source
\gset direct_
RESET ROLE;

-- What the catalog says the role holds, read as the owner.
SELECT (CASE WHEN prosecdef THEN 'definer' ELSE 'invoker' END) || ', '
         || coalesce(array_to_string(proconfig, ' '), 'no settings') AS rights
  FROM pg_proc WHERE oid = 'pellier.apply_store_credit(text, text, integer, text, text)'::regprocedure
\gset fn_
SELECT string_agg(r || ' ' || CASE WHEN has_function_privilege(r,
                 'pellier.apply_store_credit(text, text, integer, text, text)', 'EXECUTE')
                 THEN 'yes' ELSE 'no' END, ', ' ORDER BY ord) AS execute
  FROM unnest(ARRAY['pellier_credit_writer', 'pellier_agent', 'public']) WITH ORDINALITY AS t (r, ord)
\gset fn_
-- One line per table and per policy, so the result fits a laptop-size terminal.
SELECT coalesce(nullif(concat_ws(E'\n', grants, policies), ''), 'none') AS tables
  FROM (SELECT string_agg(table_name || ' ' || privileges, E'\n' ORDER BY table_name) AS grants
          FROM (SELECT table_name, string_agg(privilege_type, ', ' ORDER BY privilege_type)
                         AS privileges
                  FROM (SELECT DISTINCT table_name, privilege_type
                          FROM information_schema.role_table_grants
                         WHERE grantee = 'pellier_credit_writer'
                           AND table_name IN ('store_credits', 'orders', 'approvals')) d
                 GROUP BY table_name) per_table) g,
       (SELECT string_agg(format('policy %s on %s USING (%s): %s', policyname, tablename, qual,
                                 CASE WHEN qual = 'true' THEN 'every customer''s rows'
                                      ELSE 'the rows it names' END), E'\n' ORDER BY policyname)
                 AS policies
          FROM pg_policies
         WHERE 'pellier_credit_writer' = ANY (roles)
           AND tablename IN ('store_credits', 'orders', 'approvals')) p
\gset writer_

-- Undo the probe case and its credit; your statements stay in the transaction.
ROLLBACK TO SAVEPOINT probes;

CREATE TEMP TABLE lab_4_probes (ord serial, probe text, expected text, observed text,
                                 source text) ON COMMIT DROP;
INSERT INTO lab_4_probes (probe, expected, observed, source) VALUES
    ('Insert a credit row directly', '42501', :'direct_insert', :'direct_insert_source'),
    ('Raise the approved credit to $500 directly', '42501', :'direct_update',
     :'direct_update_source'),
    ('The approved key with a different amount', 'approval_mismatch', :'refused_amount',
     'pellier.apply_store_credit'),
    ('The approved amount under another key', 'approval_key_mismatch', :'refused_other_key',
     'pellier.apply_store_credit'),
    ('The approved credit, then its retry', 'written once, then the same credit',
     CASE WHEN :'credit_first' <> '' AND :'credit_first' = :'credit_retry'
          THEN 'written once, then the same credit'
          ELSE 'credit ' || coalesce(nullif(:'credit_first', ''), 'none') || ', then '
               || coalesce(nullif(:'credit_retry', ''), 'none') END,
     'pellier.apply_store_credit'),
    ('The function''s rights', 'definer, search_path=pg_catalog, pg_temp', :'fn_rights',
     'pg_proc'),
    ('Who may execute the function',
     'pellier_credit_writer yes, pellier_agent no, public no', :'fn_execute', 'pg_proc ACL'),
    ('The role''s privileges and row policies on store_credits, orders, approvals', 'none',
     :'writer_tables', 'role_table_grants and pg_policies');

\echo 'Lab 4B: your privileges for pellier_credit_writer, probed'
\echo 'Evidence  pellier.apply_store_credit and the role pellier_credit_writer, rewritten inside this transaction'
\echo '          a probe case: CUST-LABFOURPROBE, two received returns, a $25.00 review a person approved'
\echo ''
-- One block per probe: the verdict and the probe, then what was expected, what was
-- observed and where it came from, each value continuing on its own lines.
\pset tuples_only on
\pset format unaligned
SELECT format(E'%s  %s\n         expected  %s\n         observed  %s\n         source    %s\n',
              CASE WHEN expected = observed THEN 'matches' ELSE 'differs' END, probe,
              replace(expected, E'\n', E'\n                   '),
              replace(observed, E'\n', E'\n                   '), source)
  FROM lab_4_probes ORDER BY ord;
\pset format aligned
\pset tuples_only off
SELECT count(*) FILTER (WHERE expected = observed) AS matched, count(*) AS probes
  FROM lab_4_probes
\gset lab_4_

\echo 'Expected  every probe matches; then the transaction commits and your privileges are live'
SELECT :lab_4_matched = :lab_4_probes AS lab_4_passed \gset
\if :lab_4_passed
  COMMIT;
  SELECT format('store_credits rows before %s, after %s: the probe credit was undone',
                :credits_before, count(*)) AS rows FROM pellier.store_credits \gset credits_
  \echo 'Observed ' :lab_4_matched 'of' :lab_4_probes 'probes match; committed, your privileges are live'
  \echo 'Deployed  your statements for pellier_credit_writer, sha256' :stamp_short
  \echo '         ' :credits_rows
  \echo 'Lab 4B privileges check passed'
\else
  ROLLBACK;
  SELECT format('store_credits rows before %s, after %s', :credits_before, count(*)) AS rows
    FROM pellier.store_credits \gset credits_
  \echo 'Observed ' :lab_4_matched 'of' :lab_4_probes 'probes match; rolled back, the live state is unchanged'
  \echo '         ' :credits_rows
  \echo 'Next      which single privilege does a money path need? In the rows marked differs,'
  \echo '          23514 is the trigger refusing a row your role was allowed to insert: a rule'
  \echo '          the owner can switch off, not a privilege the role lacks. A direct UPDATE'
  \echo '          that goes through changes an approved amount with no check at all.'
  \echo 'Lab 4B privileges check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4B privileges check failed; see the lines above'; END $fail$;
\endif
