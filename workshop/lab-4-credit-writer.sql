\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off \pset border 2 \pset linestyle unicode \pset expanded off \pset format wrapped

-- Lab 4, Task 4B: what the credit-writer role may do.
--
-- Every credit is written by one function, pellier.give_store_credit. It
-- refuses any credit a person did not approve exactly, under that review's own
-- key, and a trigger on pellier.store_credits refuses the same for any insert.
-- Both callers run the credit as the pellier_credit_writer role: in process
-- through DatabaseService.fetch_all_as_credit_writer, on the Gateway through
-- run_as_credit_writer. That role's privileges decide what else a credit path
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
-- Everything below runs in one transaction. If every test matches, it
-- commits: your statements become the live privileges and the test credit is
-- undone. If any test differs, it rolls back and the live privileges stay.

SET client_min_messages TO warning;
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '15s';

-- A clean slate: no table or column privilege, no row policy, no EXECUTE, invoker's rights.
REVOKE ALL ON ALL TABLES IN SCHEMA pellier
    FROM pellier_credit_writer;
REVOKE ALL ON FUNCTION pellier.give_store_credit(text, text, integer, text, text)
    FROM pellier_credit_writer, PUBLIC;
ALTER FUNCTION pellier.give_store_credit(text, text, integer, text, text)
    SECURITY INVOKER RESET ALL;
SELECT format('DROP POLICY %I ON %I.%I', policyname, schemaname, tablename)
  FROM pg_policies WHERE 'pellier_credit_writer' = ANY (roles)
\gexec

-- Your build: what pellier_credit_writer may do.
-- === WORKSHOP - Credit writer - privileges: START ===
SELECT $privileges$
  GRANT SELECT, INSERT, UPDATE ON pellier.store_credits TO pellier_credit_writer;
  GRANT SELECT, UPDATE ON pellier.orders, pellier.approvals TO pellier_credit_writer;
  GRANT SELECT ON pellier.customers TO pellier_credit_writer;
  CREATE POLICY orders_credit_writer ON pellier.orders TO pellier_credit_writer USING (true);
  GRANT EXECUTE ON FUNCTION pellier.give_store_credit(text, text, integer, text, text)
      TO pellier_credit_writer;
$privileges$ AS privileges
\gset
-- === WORKSHOP - Credit writer - privileges: END ===

-- lab_4_reach: what the role can reach in each relation of the pellier schema, including
-- what it holds through PUBLIC and through the roles it inherits from or can SET ROLE to,
-- and where each privilege comes from. A privilege on a column is listed with its columns.
-- A direct table grant shows as the bare privilege. One line per relation and per policy,
-- so the result fits a laptop-size terminal.
CREATE TEMP VIEW lab_4_reach AS
WITH holders (oid, label) AS (
    SELECT oid, 'direct grant' FROM pg_roles WHERE rolname = 'pellier_credit_writer'
    UNION ALL SELECT 0, 'PUBLIC'
    UNION ALL SELECT oid, 'role ' || rolname FROM pg_roles
     WHERE rolname <> 'pellier_credit_writer'
       AND (pg_has_role('pellier_credit_writer', oid, 'USAGE')
            OR pg_has_role('pellier_credit_writer', oid, 'SET'))
), targets AS (
    SELECT c.oid AS relid, c.relname, 0 AS attnum, '' AS attname, p.priv,
           coalesce(c.relacl, acldefault('r', c.relowner)) AS acl
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      CROSS JOIN unnest(ARRAY['DELETE', 'INSERT', 'MAINTAIN', 'REFERENCES', 'SELECT', 'TRIGGER',
                              'TRUNCATE', 'UPDATE']) AS p (priv)
     WHERE n.nspname = 'pellier' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
    UNION ALL
    SELECT c.oid, c.relname, a.attnum, a.attname, p.priv, a.attacl
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
      CROSS JOIN unnest(ARRAY['INSERT', 'REFERENCES', 'SELECT', 'UPDATE']) AS p (priv)
     WHERE n.nspname = 'pellier' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
), hits AS (
    SELECT t.*, h.label FROM targets t CROSS JOIN holders h
     WHERE EXISTS (SELECT 1 FROM aclexplode(t.acl) a
                    WHERE a.grantee = h.oid AND a.privilege_type = t.priv)
        OR (h.oid > 0 AND h.label <> 'direct grant'
            AND NOT EXISTS (SELECT 1 FROM aclexplode(t.acl) a
                             WHERE a.grantee = 0 AND a.privilege_type = t.priv)
            AND CASE WHEN t.attnum = 0 THEN has_table_privilege(h.oid, t.relid, t.priv)
                     ELSE has_column_privilege(h.oid, t.relid, t.attnum::smallint, t.priv) END)
), reach AS (
    SELECT relname, attnum, attname, priv, array_agg(label ORDER BY label) AS labels
      FROM hits h
     WHERE attnum = 0 OR NOT EXISTS (SELECT 1 FROM hits t WHERE t.relid = h.relid
                                      AND t.attnum = 0 AND t.priv = h.priv
                                      AND t.label = h.label)
     GROUP BY relid, relname, attnum, attname, priv
), items AS (
    SELECT relname, attnum > 0 AS by_column, priv,
           CASE WHEN labels = ARRAY['direct grant'] THEN ''
                ELSE ' via ' || array_to_string(labels, ' and ') END AS via,
           string_agg(attname, ', ' ORDER BY attnum) FILTER (WHERE attnum > 0) AS columns
      FROM reach GROUP BY relname, attnum > 0, priv, labels
)
SELECT coalesce(nullif(concat_ws(E'\n', grants, policies), ''), 'none') AS tables
  FROM (SELECT string_agg(relname || ' ' || list, E'\n' ORDER BY relname) AS grants
          FROM (SELECT relname,
                       string_agg(priv || coalesce(' (' || columns || ')', '') || via, ', '
                                  ORDER BY by_column, priv, columns) AS list
                  FROM items GROUP BY relname) per_table) g,
       (SELECT string_agg(format('policy %s on %s USING (%s): %s', policyname, tablename, qual,
                                 CASE WHEN qual = 'true' THEN 'every customer''s rows'
                                      ELSE 'the rows it names' END), E'\n' ORDER BY policyname)
                 AS policies
          FROM pg_policies
         WHERE 'pellier_credit_writer' = ANY (roles)
           AND schemaname = 'pellier') p;
-- Read before your statements run: anything the role reaches now comes from outside them.
SELECT tables AS reach, tables <> 'none' AS outside FROM lab_4_reach \gset before_

SELECT :'privileges' \gexec

-- Stamp the function with your statements' sha256, so a later check can tell
-- the privileges you deployed from the ones the database shipped with.
SELECT 'Lab 4B privileges sha256 ' || hash AS stamp
  FROM (SELECT encode(sha256(convert_to(:'privileges', 'UTF8')), 'hex') AS hash) h
\gset
COMMENT ON FUNCTION pellier.give_store_credit(text, text, integer, text, text) IS :'stamp';

-- The tests run inside a savepoint. Rolling back to it undoes the test
-- customer, its orders, its approved review and its credit; your statements
-- above stay in the transaction.
SAVEPOINT probes;

-- A test case, written as the owner: two received returns and a review a
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

-- Each credit test runs as pellier_credit_writer. A direct write is recorded in words:
-- "blocked" is SQLSTATE 42501, a privilege the role does not hold; "allowed" is no error;
-- anything else is the table's trigger refusing a write the role was allowed to try.
SET LOCAL ROLE pellier_credit_writer;
SELECT pellier.give_store_credit(:'probe_key', 'CUST-LABFOURPROBE', 5000, 'Lab 4 probe', NULL)
         ->>'status' AS amount,
       pellier.give_store_credit(:'probe_key' || '-minted', 'CUST-LABFOURPROBE', 2500,
                                  'Lab 4 probe', NULL)->>'status' AS other_key
\gset refused_
SELECT (pellier.give_store_credit(:'probe_key', 'CUST-LABFOURPROBE', 2500, 'Lab 4 probe', NULL)
          ->>'credit_id') AS first,
       (pellier.give_store_credit(:'probe_key', 'CUST-LABFOURPROBE', 2500, 'Lab 4 probe', NULL)
          ->>'credit_id') AS retry
\gset credit_
DO $direct$
DECLARE
    v_rows bigint;
BEGIN
    BEGIN
        INSERT INTO pellier.store_credits (approval_id, customer_id, amount_cents, reason,
                                           idempotency_key)
        VALUES (current_setting('lab4.review')::bigint, 'CUST-LABFOURPROBE', 2500, 'Lab 4 probe',
                'written-by-hand');
        PERFORM set_config('lab4.insert', 'allowed', true);
    EXCEPTION WHEN OTHERS THEN
        PERFORM set_config('lab4.insert', CASE WHEN SQLSTATE = '42501' THEN 'blocked'
                           ELSE 'blocked by a trigger only' END, true);
    END;
    BEGIN
        UPDATE pellier.store_credits SET amount_cents = 50000
         WHERE customer_id = 'CUST-LABFOURPROBE';
        GET DIAGNOSTICS v_rows = ROW_COUNT;
        PERFORM set_config('lab4.update', CASE WHEN v_rows > 0
                           THEN 'allowed, $25 became $500'
                           ELSE 'no credit to change' END, true);
    EXCEPTION WHEN OTHERS THEN
        PERFORM set_config('lab4.update', CASE WHEN SQLSTATE = '42501' THEN 'blocked'
                           ELSE 'error' END, true);
    END;
END
$direct$;
SELECT current_setting('lab4.insert') AS insert, current_setting('lab4.update') AS update
\gset direct_
RESET ROLE;

-- What the catalog says the role holds, read as the owner.
SELECT (CASE WHEN prosecdef THEN 'definer' ELSE 'invoker' END) || ', '
         || coalesce(array_to_string(proconfig, ' '), 'no settings') AS rights
  FROM pg_proc WHERE oid = 'pellier.give_store_credit(text, text, integer, text, text)'::regprocedure
\gset fn_
SELECT string_agg(r || ' ' || CASE WHEN has_function_privilege(r,
                 'pellier.give_store_credit(text, text, integer, text, text)', 'EXECUTE')
                 THEN 'yes' ELSE 'no' END, ', ' ORDER BY ord) AS execute
  FROM unnest(ARRAY['pellier_credit_writer', 'pellier_agent', 'public']) WITH ORDINALITY AS t (r, ord)
\gset fn_
SELECT tables FROM lab_4_reach
\gset writer_

-- Undo the test case and its credit; your statements stay in the transaction.
ROLLBACK TO SAVEPOINT probes;

CREATE TEMP TABLE lab_4_probes (ord serial, probe text, expected text, observed text)
    ON COMMIT DROP;
INSERT INTO lab_4_probes (probe, expected, observed) VALUES
    ('Insert a credit row directly', 'blocked', :'direct_insert'),
    ('Change an approved credit to $500', 'blocked', :'direct_update'),
    ('Approved key, different amount', 'approval_mismatch', :'refused_amount'),
    ('Approved amount, another key', 'approval_key_mismatch', :'refused_other_key'),
    ('Approved credit, then its retry', 'paid once, then the same credit',
     CASE WHEN :'credit_first' <> '' AND :'credit_first' = :'credit_retry'
          THEN 'paid once, then the same credit'
          ELSE 'credit ' || coalesce(nullif(:'credit_first', ''), 'none') || ', then '
               || coalesce(nullif(:'credit_retry', ''), 'none') END),
    ('The function runs with', 'definer, search_path=pg_catalog, pg_temp', :'fn_rights'),
    ('Who may run the function',
     'pellier_credit_writer yes, pellier_agent no, public no', :'fn_execute'),
    ('Role''s direct table access', 'none',
     :'writer_tables');

\echo 'Lab 4B: the database limits what the credit writer can change'
\echo ''
-- One table, one row per test: what the test wants and, when it fails, what it got, in a few
-- words. The rights test says what it wants, not its value: the value is the Build task's answer.
SELECT probe AS "Test",
       CASE ord WHEN 3 THEN 'refused' WHEN 4 THEN 'refused'
                WHEN 5 THEN 'paid once'
                WHEN 6 THEN 'owner''s rights'
                WHEN 7 THEN 'writer only'
                ELSE expected END AS "Should be",
       CASE WHEN expected = observed THEN ''
            ELSE CASE ord
                 WHEN 3 THEN 'not refused'
                 WHEN 4 THEN 'not refused'
                 WHEN 5 THEN 'not paid once'
                 WHEN 6 THEN CASE WHEN observed LIKE 'definer%' THEN 'owner''s rights, wrong path'
                                  ELSE 'caller''s rights' END
                 WHEN 7 THEN 'wrong roles can run it'
                 WHEN 8 THEN format('%s table%s%s', n.tables, CASE WHEN n.tables = 1 THEN '' ELSE 's' END,
                                    CASE WHEN n.policies = 0 THEN ''
                                         ELSE format(' + %s row polic%s', n.policies,
                                                     CASE WHEN n.policies = 1 THEN 'y' ELSE 'ies' END)
                                    END)
                 ELSE observed END END AS "Is now",
       CASE WHEN expected = observed THEN '✓' ELSE '✗' END AS "OK"
  FROM lab_4_probes p
  CROSS JOIN LATERAL (SELECT count(*) FILTER (WHERE l NOT LIKE 'policy %') AS tables,
                             count(*) FILTER (WHERE l LIKE 'policy %') AS policies
                        FROM regexp_split_to_table(p.observed, E'\n') AS l) n
 ORDER BY p.ord;
SELECT count(*) FILTER (WHERE expected = observed) AS matched, count(*) AS probes
  FROM lab_4_probes
\gset lab_4_
-- Point a failed run's next step at the first kind of test that differs: table access,
-- then the function's rights, then what the function itself refused or wrote.
SELECT bool_or(expected <> observed) FILTER (WHERE ord IN (1, 2, 8)) AS tables_differ,
       bool_or(expected <> observed) FILTER (WHERE ord = 6) AS rights_differ
  FROM lab_4_probes
\gset lab_4_
-- What the role reaches, on one line for a Next that is about access.
SELECT CASE WHEN length(one_line.now) > 54 THEN left(one_line.now, 51) || '...'
            ELSE one_line.now END AS lab_4_reach_now
  FROM (SELECT replace(:'writer_tables', E'\n', '; ') AS now) one_line
\gset

SELECT :lab_4_matched = :lab_4_probes AS lab_4_passed \gset
\if :lab_4_passed
  COMMIT;
  \echo :lab_4_matched 'of' :lab_4_probes 'tests passed. Saved, your privileges are live.'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[32m' || true`
  \echo 'Lab 4B privileges check passed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  -- A catch-up (lab_run.py finish) runs the next step itself, so it asks for no Next.
  \if :{?quiet_next}
  \else
    \echo ''
    \echo 'Next  In the guide, read "Prove the role writes only through the function".'
    \echo '      Then run: uv run scripts/lab4_check.py --task 4B'
  \endif
\else
  ROLLBACK;
  \echo :lab_4_matched 'of' :lab_4_probes 'tests passed. Your change was undone.'
  \echo 'The live state is unchanged.'
  \echo ''
  \echo 'Next  In Task 4B, choose "Write it yourself" or "Install the provided fix".'
  \if :before_outside
    \echo '      The role reaches:' :lab_4_reach_now
    \echo '      Part of it predates your file. Ask a facilitator.'
  \elif :lab_4_tables_differ
    \echo '      The role still reaches:' :lab_4_reach_now
    \echo '      Give it only EXECUTE on the function.'
  \elif :lab_4_rights_differ
    \echo '      The function must run with its owner''s rights and a fixed search path.'
  \else
    \echo '      The role touches no table, so the function must.'
    \echo '      Grant EXECUTE to the credit writer alone.'
  \endif
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[31m' || true`
  \echo 'Lab 4B privileges check failed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  DO $fail$ BEGIN RAISE EXCEPTION 'stopped on purpose; see Next'; END $fail$;
\endif
