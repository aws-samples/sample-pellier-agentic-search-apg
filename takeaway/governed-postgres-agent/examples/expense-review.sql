-- Only in the disposable database initialized by setup.sql.
-- Deliberately introduce the defect, observe it, then roll it back.
\set ON_ERROR_STOP on
BEGIN;
GRANT UPDATE ON review_example.credits TO PUBLIC;
SET LOCAL ROLE review_writer;
SELECT review_example.apply_credit('approval:1', 'customer-a', 2500, 'travel');
-- No SELECT grant is needed for this unqualified UPDATE. The fixture has one row.
UPDATE review_example.credits SET amount_cents = 50000;
RESET ROLE;
SELECT amount_cents AS unauthorized_amount FROM review_example.credits;
SELECT has_table_privilege('review_writer', 'review_example.credits', 'UPDATE')
    AS writer_can_bypass_function;
ROLLBACK;

-- The rollback removed the grant and the altered credit. Now test the fix.
BEGIN;
SET LOCAL ROLE review_writer;
SELECT review_example.apply_credit('approval:1', 'customer-a', 2500, 'travel');
DO $$ BEGIN
    UPDATE review_example.credits SET amount_cents = 50000;
    RAISE EXCEPTION 'FAIL: direct update was accepted';
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'PASS: direct update refused with SQLSTATE %', SQLSTATE;
END $$;
SELECT review_example.apply_credit('approval:1', 'customer-a', 2500, 'travel');
RESET ROLE;
COMMIT;

SELECT count(*) AS credits, min(amount_cents) AS amount_cents FROM review_example.credits;
SELECT count(*) AS first_write_audit_rows FROM review_example.write_audit;
-- Expected: unauthorized_amount 50000 and writer_can_bypass_function t before rollback.
-- Corrected path: direct update refused, replayed true, credits 1, amount 2500, audit rows 1.
