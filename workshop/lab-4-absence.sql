\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off \pset border 2 \pset linestyle unicode \pset expanded off \pset format wrapped

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
-- This check is supplied; you write nothing here. Decide what the four counts
-- should be before you run it:
--   psql -f workshop/lab-4-absence.sql
--
-- It finds both keys itself and never writes. Both are derived the same way,
-- from an approved review: operator-review:<review id>:<first 32 of its hash>.
--   denied   the over-limit review scripts/lab4_check.py --task 4A sent through
--            the Gateway (its issue names it)
--   allowed  Nadia's approved review of Jessica's case that wrote a credit
-- Because the allowed key is derived, not copied from the credit, a
-- derivation that drifted from the one the desk uses would find no credit for
-- it, and the check would fail rather than vouch for two vacuous zeros.

SET client_min_messages TO warning;

WITH probe AS (
    SELECT a.last_attempt, 'operator-review:' || a.id || ':' || left(a.action_hash, 32) AS key
      FROM pellier.approvals a
     WHERE a.tool = 'give_store_credit' AND a.status = 'approved'
       AND a.issue = 'Lab 4 over-limit probe: covers no order'
     ORDER BY a.id DESC LIMIT 1
)
SELECT EXISTS (SELECT 1 FROM probe) AS has_probe,
       coalesce((SELECT key FROM probe
                  WHERE last_attempt->>'outcome' = 'denied'
                    AND last_attempt->>'rail' = 'gateway-mcp'
                    AND last_attempt->>'policy' = 'DENY'
                    AND last_attempt->>'idempotency_key' = key), '') AS deny_key,
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
       -- The allowed key's row that applied the credit. A call that failed or
       -- was refused before it leaves its own row: an attempt, counted apart.
       (SELECT count(*) FROM pellier.tool_audit
         WHERE args->>'idempotency_key' = :'lab_4_allow_key'
           AND (result->>'status' = 'success'
                AND coalesce(result->>'idempotent_replay', 'false') <> 'true')) AS allowed_audit_rows,
       (SELECT count(*) FROM pellier.tool_audit
         WHERE args->>'idempotency_key' = :'lab_4_allow_key'
           AND (result->>'status' = 'success'
                AND coalesce(result->>'idempotent_replay', 'false') <> 'true') IS NOT TRUE)
         AS allowed_attempt_rows,
       :'lab_4_deny_key' <> '' AS has_deny_key,
       :'lab_4_allow_key' <> '' AS has_allow_key
\gset lab_4_

\echo 'Lab 4: paid exactly once, and the denied $100.01 left nothing'
\echo ''
\if :lab_4_has_deny_key
\else
  \if :lab_4_has_probe
    \echo 'No Gateway denial was recorded for the latest $100.01 request.'
  \else
    \echo 'The $100.01 request from the Lab 4A check is not recorded yet.'
  \endif
  \echo ''
  \echo 'Next  In the guide, read "Prove one credit was written".'
  \echo '      Run the 4A check after you deploy your rule, then run this file again:'
  \echo '      uv run scripts/lab4_check.py --task 4A'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[31m' || true`
  \echo 'Lab 4 absence check failed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  DO $fail$ BEGIN RAISE EXCEPTION 'stopped on purpose; see Next'; END $fail$;
\endif
\if :lab_4_has_allow_key
\else
  \echo 'Jessica has no store credit yet.'
  \echo ''
  \echo 'Next  In the guide, read "Execute again and replay as Nadia".'
  \echo '      In the Operator, approve and execute Jessica''s review as Nadia,'
  \echo '      then run this file again.'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[31m' || true`
  \echo 'Lab 4 absence check failed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  DO $fail$ BEGIN RAISE EXCEPTION 'stopped on purpose; see Next'; END $fail$;
\endif

\echo 'Jessica''s write key ' :lab_4_allow_key
\echo ''
SELECT * FROM (VALUES
    ('Denied $100.01 request', :'lab_4_denied_credit_rows', :'lab_4_denied_audit_rows'),
    ('Jessica''s $100.00 credit', :'lab_4_allowed_credit_rows', :'lab_4_allowed_audit_rows')
) AS counts("Request", "Credit rows", "Tool calls that ran");

SELECT :lab_4_allowed_attempt_rows > 0 AS lab_4_has_attempts,
       format('%s other attempt%s for this key did not apply; the audit keeps %s.',
              :lab_4_allowed_attempt_rows,
              CASE WHEN :lab_4_allowed_attempt_rows = 1 THEN '' ELSE 's' END,
              CASE WHEN :lab_4_allowed_attempt_rows = 1 THEN 'it' ELSE 'them' END)
         AS lab_4_attempts
\gset
\if :lab_4_has_attempts
  \echo :lab_4_attempts
\endif
SELECT :lab_4_allowed_credit_rows = 1 AND :lab_4_allowed_audit_rows = 1 AS lab_4_control_holds,
       :lab_4_denied_audit_rows = 0 AND :lab_4_denied_credit_rows = 0 AS lab_4_absence_holds
\gset
\if :lab_4_control_holds
\else
  \echo 'The search can''t find Jessica''s credit, so the zeros prove nothing.'
  \echo ''
  \echo 'Next  In the guide, read "Prove one credit was written".'
  \echo '      Raise your hand so a facilitator can check the database.'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[31m' || true`
  \echo 'Lab 4 absence check failed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  DO $fail$ BEGIN RAISE EXCEPTION 'stopped on purpose; see Next'; END $fail$;
\endif
\if :lab_4_absence_holds
  \echo 'The same search finds Jessica''s credit, so the two zeros are real.'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[32m' || true`
  \echo 'Lab 4 absence check passed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  -- A catch-up (lab_run.py finish) runs the next step itself, so it asks for no Next.
  \if :{?quiet_next}
  \else
    \echo ''
    \echo 'Next  In the guide, read "Follow one credit end to end".'
    \echo '      Then run: uv run scripts/follow_credit.py'
  \endif
\else
  \echo 'The denied request left rows behind.'
  \echo ''
  \echo 'Next  In the guide, read "Prove one credit was written".'
  \echo '      A denied call must never run. Read those rows by their key.'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[31m' || true`
  \echo 'Lab 4 absence check failed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  DO $fail$ BEGIN RAISE EXCEPTION 'stopped on purpose; see Next'; END $fail$;
\endif
