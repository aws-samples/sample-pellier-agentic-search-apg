\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off

-- Lab 4: prove the denied credit moved nothing, beside the one that did.
--
-- A Cedar DENY says the Gateway refused a call. It cannot prove nothing ran.
-- The proof is a search, by idempotency key, of the two tables an executed
-- give_store_credit writes: pellier.tool_audit (the tool ran) and
-- pellier.store_credits (money moved). For the denied key both counts must be
-- 0. For the key Nadia's approved credit carried, store_credits must hold
-- exactly 1: that positive control is what makes the two zeros an absence
-- rather than a search that looked in the wrong place.
--
-- This check is supplied; you write nothing here. Predict the three counts
-- first, then run:
--   psql -X -P pager=off -f workshop/lab-4-absence.sql
--
-- It finds both keys itself and never writes. Both are derived the same way,
-- from an approved review: operator-review:<review id>:<first 32 of its hash>.
--   denied   the over-limit review scripts/lab4_policy_check.py sent through
--            the Gateway (its issue names it)
--   allowed  Nadia's approved review of Jessica's case that wrote a credit
-- Because the allowed key is derived, not copied from the credit, a
-- derivation that drifted from the one the desk uses would find no credit for
-- it, and the check would fail rather than vouch for two vacuous zeros.

SET client_min_messages TO warning;

SELECT coalesce((SELECT 'operator-review:' || a.id || ':' || left(a.action_hash, 32)
                   FROM pellier.approvals a
                  WHERE a.tool = 'give_store_credit'
                    AND a.status = 'approved'
                    AND a.issue = 'Lab 4 over-limit probe: covers no order'
                  ORDER BY a.id DESC
                  LIMIT 1), '') AS deny_key,
       coalesce((SELECT 'operator-review:' || a.id || ':' || left(a.action_hash, 32)
                   FROM pellier.approvals a
                  WHERE a.tool = 'give_store_credit'
                    AND a.status = 'approved'
                    AND a.customer_id = 'CUST-JESSICA'
                    AND a.issue IS DISTINCT FROM 'Lab 4 over-limit probe: covers no order'
                    AND EXISTS (SELECT 1 FROM pellier.store_credits c
                                 WHERE c.approval_id = a.id)
                  ORDER BY a.id DESC
                  LIMIT 1), '') AS allow_key
\gset lab_4_

SELECT (SELECT count(*) FROM pellier.tool_audit
         WHERE args->>'idempotency_key' = :'lab_4_deny_key') AS denied_audit_rows,
       (SELECT count(*) FROM pellier.store_credits
         WHERE idempotency_key = :'lab_4_deny_key') AS denied_credit_rows,
       (SELECT count(*) FROM pellier.store_credits
         WHERE idempotency_key = :'lab_4_allow_key') AS allowed_credit_rows,
       (SELECT count(*) FROM pellier.tool_audit
         WHERE args->>'idempotency_key' = :'lab_4_allow_key') AS allowed_audit_rows,
       :'lab_4_deny_key' <> '' AS has_deny_key,
       :'lab_4_allow_key' <> '' AS has_allow_key
\gset lab_4_
SELECT format('%s, %s and %s (the allowed key also has %s tool_audit row)',
              :lab_4_denied_audit_rows, :lab_4_denied_credit_rows,
              :lab_4_allowed_credit_rows, :lab_4_allowed_audit_rows) AS observed
\gset lab_4_

\echo 'Lab 4: the denied credit moved nothing, beside the one that did'
\if :lab_4_has_deny_key
\else
  \echo 'Expected  the over-limit review the Lab 4A check sent through the Gateway'
  \echo 'Observed  none yet: no approved review is named Lab 4 over-limit probe'
  \echo 'Next      run python3 scripts/lab4_policy_check.py after deploying your rule, then run this again.'
  \echo 'Lab 4 absence check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4 absence check failed; see the lines above'; END $fail$;
\endif
\if :lab_4_has_allow_key
\else
  \echo 'Expected  the store credit Nadia''s approval of Jessica''s case wrote'
  \echo 'Observed  none yet: Jessica has no store credit'
  \echo 'Next      in the Operator, approve and execute Jessica''s review as Nadia, then run this again.'
  \echo 'Lab 4 absence check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4 absence check failed; see the lines above'; END $fail$;
\endif

\echo 'Evidence  denied key  ' :lab_4_deny_key
\echo '          allowed key ' :lab_4_allow_key
\echo ''
SELECT * FROM (VALUES
    ('tool_audit rows for the denied key', '0', :'lab_4_denied_audit_rows'),
    ('store_credits rows for the denied key', '0', :'lab_4_denied_credit_rows'),
    ('store_credits rows for the allowed key', '1', :'lab_4_allowed_credit_rows')
) AS counts(count, expected, observed);

\echo 'Expected  0, 0 and 1: nothing ran or moved for the denied key, and the same search finds the one allowed credit'
\echo 'Observed ' :lab_4_observed
SELECT :lab_4_allowed_credit_rows = 1 AS lab_4_control_holds,
       :lab_4_denied_audit_rows = 0 AND :lab_4_denied_credit_rows = 0 AS lab_4_absence_holds
\gset
\if :lab_4_control_holds
\else
  \echo 'Next      the allowed key does not find exactly one credit, so this search cannot vouch for an absence.'
  \echo 'Lab 4 absence check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4 absence check failed; see the lines above'; END $fail$;
\endif
\if :lab_4_absence_holds
  \echo 'Lab 4 absence check passed'
\else
  \echo 'Next      the denied key left rows behind: read them by that key; a denied call must never run.'
  \echo 'Lab 4 absence check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 4 absence check failed; see the lines above'; END $fail$;
\endif
