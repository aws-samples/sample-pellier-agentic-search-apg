\set ON_ERROR_STOP on
-- Lab 4 build artifact (Build 4b): PROVE A DENIED ACTION LEFT NOTHING BEHIND.
--
-- A Cedar DENY receipt records that the Gateway refused a call. It cannot
-- prove that nothing ran: a receipt is not its own alibi. The proof is a keyed
-- search of every table an executed give_store_credit writes, for the exact
-- idempotency key the denied call carried, beside the same search for the key
-- an allowed call carried. Empty for the denied key alone means nothing.
-- Empty for the denied key AND exactly one finalized write for the allowed
-- key means the search looks in the right place and the absence is real. One
-- finalized write, not two, is also the replay proof: the second allowed
-- invocation reused the key and added no effect.
--
-- Complete the query between the markers. This script never writes.
--
-- Run with the keys Lab 4's proof driver recorded:
--   psql -X -v ON_ERROR_STOP=1 -P pager=off \
--     -v deny_key="$DENY_KEY" -v allow_key="$ALLOW_KEY" \
--     -f workshop/lab-4-absence.sql
\if :{?deny_key}
\else
  \echo 'Lab 4 absence build needs -v deny_key=... (the denied call''s idempotency key)'
  DO $fail$ BEGIN RAISE EXCEPTION 'lab worksheet failed; see the line above'; END $fail$;
\endif
\if :{?allow_key}
\else
  \echo 'Lab 4 absence build needs -v allow_key=... (the allowed call''s idempotency key)'
  DO $fail$ BEGIN RAISE EXCEPTION 'lab worksheet failed; see the line above'; END $fail$;
\endif

-- === WORKSHOP - Keyed absence - deny proof: START ===
-- WORKSHOP_EXERCISE_STUB
--
-- Replace the five NULL placeholders with counts read from the tables an
-- executed give_store_credit writes, for the exact keys passed in:
--
--   pellier.tool_audit        args->>'idempotency_key' = :'deny_key'   an execution row
--   pellier.write_operations  idempotency_key = :'deny_key'            a claimed write
--   pellier.write_operations  ... AND completed_at IS NOT NULL
--                                 AND result->>'status' = 'success'    a finalized write
--   pellier.inventory_ledger  idempotency_key = :'deny_key'            a stock movement
--
-- and, as the positive control, the finalized writes for :'allow_key'. That
-- last count is what makes the four zeros above mean something: the same
-- search finds the one write the allowed call made, so an empty result for
-- the denied key is an absence, not a query that looked in the wrong place.
-- Read every count from the tables. Nothing here may come from a receipt.
SELECT
    NULL::bigint AS denied_execution_rows,
    NULL::bigint AS denied_write_rows,
    NULL::bigint AS denied_finalized_writes,
    NULL::bigint AS denied_ledger_rows,
    NULL::bigint AS allowed_finalized_writes
\gset lab_4_
-- === WORKSHOP - Keyed absence - deny proof: END ===

-- A NULL placeholder leaves its variable unset, so an unauthored region
-- fails here rather than reading as four reassuring zeros.
SELECT (
    :{?lab_4_denied_execution_rows}
    AND :{?lab_4_denied_write_rows}
    AND :{?lab_4_denied_finalized_writes}
    AND :{?lab_4_denied_ledger_rows}
    AND :{?lab_4_allowed_finalized_writes}
) AS lab_4_authored
\gset
\if :lab_4_authored
\else
  \echo 'Lab 4 absence build failed: the counts between the markers are still NULL placeholders'
  DO $fail$ BEGIN RAISE EXCEPTION 'lab worksheet failed; see the line above'; END $fail$;
\endif

\echo 'Lab 4 absence for denied key' :'deny_key'
\echo '  execution rows (tool_audit):          ' :lab_4_denied_execution_rows
\echo '  claimed writes (write_operations):    ' :lab_4_denied_write_rows
\echo '  finalized writes (write_operations):  ' :lab_4_denied_finalized_writes
\echo '  stock movements (inventory_ledger):   ' :lab_4_denied_ledger_rows
\echo 'Positive control for allowed key' :'allow_key'
\echo '  finalized writes (write_operations):  ' :lab_4_allowed_finalized_writes

SELECT
    (:lab_4_denied_execution_rows = 0
     AND :lab_4_denied_write_rows = 0
     AND :lab_4_denied_finalized_writes = 0
     AND :lab_4_denied_ledger_rows = 0)              AS lab_4_absence_holds,
    (:lab_4_allowed_finalized_writes = 1)            AS lab_4_control_holds
\gset
\if :lab_4_control_holds
\else
  \echo 'Lab 4 absence build failed: the allowed key did not finalize exactly one write, so this search cannot vouch for an absence'
  DO $fail$ BEGIN RAISE EXCEPTION 'lab worksheet failed; see the line above'; END $fail$;
\endif
\if :lab_4_absence_holds
  \echo 'Lab 4 absence build passed: the denied key left no execution, write, or ledger row, and the allowed key finalized exactly one'
\else
  \echo 'Lab 4 absence build failed: the denied key left rows behind'
  DO $fail$ BEGIN RAISE EXCEPTION 'lab worksheet failed; see the line above'; END $fail$;
\endif
