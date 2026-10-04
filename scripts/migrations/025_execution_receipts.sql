-- Migration 025: pellier.execution_receipts — the missing policy artifact.
--
-- WHY THIS EXISTS
--
-- Migration 021 declined to store a verdict on the review, and gave a good reason:
-- `approvals.status` is the HUMAN axis, and folding a policy decision into it would
-- conflate three independent controls. It then said execution and governance state are
-- "hydrated from their own artifacts: the policy decision, the `tool_audit` receipt,
-- `write_operations`, and the domain rows".
--
-- Three of those four artifacts are real. The policy decision is not. Nothing in
-- Pellier persisted it, so a Cedar verdict existed only in the HTTP response body of
-- the execution call and was gone the moment the operator closed the tab. Measured on
-- 2026-08-27 against three real governed executions:
--
--   review 40  CUST-THEO    policy ALLOW, Aurora PERMITTED  -> return 37 written
--   review 36  CUST-RACHEL  policy DENY                     -> nothing anywhere
--   review 41  CUST-AMARA   policy ALLOW, Aurora DENIED     -> claim released
--
-- Rachel's DENY left NO durable trace of any kind: correctly no `tool_audit` row
-- (a denied call never executes), correctly no idempotency claim, and no verdict.
-- `GET /api/operator/reviews/36` therefore reported `policy: PENDING` for an action
-- Cedar had refused. A workshop whose central question is "was it permitted, and can
-- I prove what happened?" cannot answer the first half from storage.
--
-- WHAT THIS ADDS: one append-only table, one row per governed execution ATTEMPT.
--
-- APPEND-ONLY, ONE ROW PER ATTEMPT
--
-- Not one row per execution turn. `execution_turn_id` is assigned once and reused for
-- every retry of the same logical execution (migration 021), and retries genuinely
-- differ: Theo's first attempt reported `policy NOT_EVALUATED` because the engine
-- state was unreadable, and his replay under the same key reported `policy ALLOW` with
-- `idempotent_replay: true`. Upserting would have destroyed the first reading;
-- keeping only the first would have frozen a verdict a later evaluation superseded.
-- Both attempts are facts, so both get a row and the surface reads the newest.
--
-- WHAT IT DOES NOT DO
--
--   * It does NOT widen `approvals.status`. That column is still only pending /
--     approved / rejected, and 021's argument stands.
--   * It does NOT copy business truth. No membership, no order state, no inventory,
--     no stock. The domain rows remain the only source for those.
--   * It does NOT replace `tool_audit` or `write_operations`. Those answer "what ran"
--     and "what applied exactly once". This answers "what did the governance layers
--     decide", which neither of them records.
--   * It does NOT store the tool result. `write_operations.result` already holds that
--     for a completed write, and duplicating it would create two versions of the same
--     fact that can disagree.
--
-- Forward-only and idempotent: one table, three indexes, no changes to existing
-- objects. No seed rows — a receipt exists only where an execution was attempted.

\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS pellier.execution_receipts (
    receipt_id          BIGSERIAL PRIMARY KEY,

    -- The execution attempt this receipt belongs to. NOT unique: retries of one
    -- logical execution share the turn id and each attempt gets its own row.
    execution_turn_id   TEXT NOT NULL
                        CHECK (execution_turn_id ~ '^turn-[0-9a-f]{32}$'),

    -- The human decision this execution ran under. CASCADE because a receipt
    -- without its review reconstructs nothing, so one must never outlive the
    -- other. It is not how the workshop reset clears them: since migration 047
    -- this table is append-only and the cascade fires that row trigger, so the
    -- reset TRUNCATEs approvals and execution_receipts in one statement
    -- instead (scripts/reset-governed-workshop.sh), which fires no row-level
    -- triggers.
    review_id           BIGINT NOT NULL
                        REFERENCES pellier.approvals(id) ON DELETE CASCADE,

    tool                TEXT NOT NULL,

    -- The Cedar action id that was evaluated, e.g.
    -- pellier-concierge-experience-target___initiate_return. Stored because the
    -- action id is what a policy names, and it is not derivable from `tool` alone
    -- once a target's vocabulary is migrated.
    gateway_action_id   TEXT,

    -- Which rail ran. Only the managed Gateway rail produces a Cedar verdict, so a
    -- NOT_EVALUATED beside 'in-process' is a different fact from a NOT_EVALUATED
    -- beside 'gateway-mcp' — the first is expected, the second is a read failure.
    --
    -- 'refused' is the governed format declining to write without the managed
    -- rail: nothing ran, and this row is the proof that it declined.
    rail                TEXT NOT NULL
                        CHECK (rail IN ('gateway-mcp', 'in-process', 'refused')),

    -- Two principals, and they are not interchangeable. The actor is what AgentCore
    -- Policy authorizes; the customer subject is what Aurora Row-Level Security
    -- scopes. Amara's execution had an actor and NO customer subject, which is
    -- precisely why her write found nothing.
    actor_principal     TEXT NOT NULL,
    customer_subject    TEXT,

    -- The three axes, each from its own artifact at execution time, using the
    -- vocabularies in services/governed_execution.py. Never merged into one status:
    -- an ALLOW beside a DENIED is the most instructive row this table can hold.
    -- EVALUATION_INCOMPLETE is an engine whose answer could not be read (or a
    -- refused execution no engine was asked about); OUTCOME_UNKNOWN is a
    -- Gateway that withheld the tool response. Both are written by the
    -- service, so both are admitted here: a receipt the CHECK refused would be
    -- a governance outcome with no durable trace.
    policy_outcome      TEXT NOT NULL
                        CHECK (policy_outcome IN
                            ('ALLOW', 'DENY', 'WOULD_DENY', 'NOT_EVALUATED',
                             'EVALUATION_INCOMPLETE')),
    aurora_outcome      TEXT NOT NULL
                        CHECK (aurora_outcome IN
                            ('PERMITTED', 'DENIED', 'NOT_REACHED', 'NOT_ENFORCED',
                             'OUTCOME_UNKNOWN')),
    evidence_outcome    TEXT NOT NULL
                        CHECK (evidence_outcome IN
                            ('RECEIPTED', 'POLICY_PROOF', 'ATTEMPT_RECEIPT',
                             'NO_EXECUTION', 'PENDING')),

    -- What produced the verdict. An ALLOW is unattributable without them: the same
    -- word means "permitted" under ENFORCE and "observed, not enforced" under
    -- LOG_ONLY, and the gateway scope and the policy scope use different enums.
    policy_engine_id    TEXT,
    gateway_mode        TEXT,

    -- Forbid policies whose Cedar statement NAMES this action. Not "the policy that
    -- denied it": the same forbid appears on an ALLOW too, because naming the action
    -- is not the same as applying to the call. Measured on the three live outcomes —
    -- `process_return_damaged_only` is listed on Rachel's DENY and on Theo's and
    -- Amara's ALLOWs alike, since it forbids the action only when the reason is not
    -- `damaged`. Read it with `policy_outcome`: a DENY plus a named forbid identifies
    -- which rule fired; an ALLOW plus a named forbid says a conditional rule was
    -- evaluated and did not apply.
    matching_forbids    TEXT[] NOT NULL DEFAULT '{}',

    -- Links this attempt to pellier.write_operations. Present even when no claim row
    -- exists, because "the key that would have been claimed" is what proves Rachel's
    -- execution never entered the tool.
    idempotency_key     TEXT NOT NULL,

    -- The sentences the axes were reported with, so the stored receipt and the
    -- response the operator saw say the same thing.
    notes               JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The read the ReviewRecord surface performs: newest attempt for this review.
CREATE INDEX IF NOT EXISTS execution_receipts_review_idx
    ON pellier.execution_receipts (review_id, receipt_id DESC);

-- The read an evidence reconstruction performs, from a turn id in a log or a URL.
CREATE INDEX IF NOT EXISTS execution_receipts_turn_idx
    ON pellier.execution_receipts (execution_turn_id, receipt_id DESC);

-- "Show me every denial this week", which is the audit question this table exists
-- to make answerable at all.
CREATE INDEX IF NOT EXISTS execution_receipts_policy_idx
    ON pellier.execution_receipts (policy_outcome, created_at DESC);

COMMENT ON TABLE pellier.execution_receipts IS
    'Policy and execution verdicts for one governed execution attempt. Append-only, one row per attempt; retries of the same execution_turn_id each add a row. Distinct from tool_audit (what ran) and write_operations (what applied exactly once).';

COMMENT ON COLUMN pellier.execution_receipts.policy_outcome IS
    'The AgentCore Policy verdict. The artifact migration 021 assumed existed and nothing wrote: without it a Cedar DENY leaves no durable trace anywhere in Pellier.';

COMMENT ON COLUMN pellier.execution_receipts.gateway_mode IS
    'ENFORCE or LOG_ONLY at evaluation time. An ALLOW under LOG_ONLY is an observation, not an authorization, and the word alone cannot tell them apart.';

COMMIT;

-- ---------------------------------------------------------------------
-- Self-probe: prove the constraints before anything depends on them
-- ---------------------------------------------------------------------

DO $$
DECLARE
    v_turn   TEXT := 'migration-025-probe';
    v_exec   TEXT := 'turn-' || repeat('c', 32);
    v_cust   TEXT;
    v_hash   TEXT := repeat('d', 64);
    v_review BIGINT;
    v_failed BOOLEAN;
    v_count  INTEGER;
BEGIN
    SELECT id INTO v_cust FROM pellier.customers ORDER BY id LIMIT 1;
    IF v_cust IS NULL THEN
        RAISE NOTICE 'migration 025: no customers seeded, skipping self-probe';
        RETURN;
    END IF;

  -- The probe runs inside a subtransaction that ends by raising a private
  -- SQLSTATE (P0025) caught below, which discards every row it wrote. Since
  -- migration 047 an execution receipt cannot be deleted at all, so a probe
  -- that committed would leave permanent residue on every apply.
  BEGIN

    INSERT INTO pellier.approvals
        (customer_id, tool, args, status, source_turn_id, issue, action_hash,
         decided_at, decided_by, execution_turn_id)
    VALUES
        (v_cust, 'initiate_return', '{"reason":"damaged"}'::jsonb, 'approved',
         v_turn, 'probe', v_hash, now(), 'probe-operator', v_exec)
    RETURNING id INTO v_review;

    -- 1. a malformed execution turn is refused
    v_failed := FALSE;
    BEGIN
        INSERT INTO pellier.execution_receipts
            (execution_turn_id, review_id, tool, rail, actor_principal,
             policy_outcome, aurora_outcome, evidence_outcome, idempotency_key)
        VALUES
            ('not-a-turn', v_review, 'initiate_return', 'gateway-mcp', 'probe',
             'DENY', 'NOT_REACHED', 'POLICY_PROOF', 'probe-key');
    EXCEPTION WHEN check_violation THEN
        v_failed := TRUE;
    END;
    IF NOT v_failed THEN
        RAISE EXCEPTION 'migration 025: accepted a malformed execution turn id';
    END IF;

    -- 2. an outcome outside the vocabulary is refused
    v_failed := FALSE;
    BEGIN
        INSERT INTO pellier.execution_receipts
            (execution_turn_id, review_id, tool, rail, actor_principal,
             policy_outcome, aurora_outcome, evidence_outcome, idempotency_key)
        VALUES
            (v_exec, v_review, 'initiate_return', 'gateway-mcp', 'probe',
             'MAYBE', 'NOT_REACHED', 'POLICY_PROOF', 'probe-key');
    EXCEPTION WHEN check_violation THEN
        v_failed := TRUE;
    END;
    IF NOT v_failed THEN
        RAISE EXCEPTION 'migration 025: accepted a policy outcome outside the vocabulary';
    END IF;

    -- 3. TWO attempts on one execution turn are both retained. This is the whole
    --    reason the turn id is not unique here.
    INSERT INTO pellier.execution_receipts
        (execution_turn_id, review_id, tool, rail, actor_principal,
         policy_outcome, aurora_outcome, evidence_outcome, idempotency_key)
    VALUES
        (v_exec, v_review, 'initiate_return', 'gateway-mcp', 'probe',
         'NOT_EVALUATED', 'PERMITTED', 'RECEIPTED', 'probe-key'),
        (v_exec, v_review, 'initiate_return', 'gateway-mcp', 'probe',
         'ALLOW', 'PERMITTED', 'RECEIPTED', 'probe-key');
    SELECT count(*) INTO v_count
      FROM pellier.execution_receipts WHERE execution_turn_id = v_exec;
    IF v_count <> 2 THEN
        RAISE EXCEPTION
            'migration 025: expected 2 retained attempts on one execution turn, got %',
            v_count;
    END IF;

    -- 4. review_id cascades, so a receipt cannot outlive the human decision it
    --    belongs to. Read from the catalog rather than exercised: since
    --    migration 047 pellier.execution_receipts is append-only, and a
    --    cascaded DELETE fires that row trigger like any other, so deleting the
    --    review is refused whether or not this block rolls back. What is
    --    provable here is the declaration.
    --
    --    The workshop reset therefore does not clear receipts with a DELETE on
    --    pellier.approvals. It TRUNCATEs approvals and execution_receipts in
    --    one statement (scripts/reset-governed-workshop.sh), which fires no
    --    row-level triggers and leaves nothing orphaned.
    SELECT count(*) INTO v_count
      FROM pg_constraint
     WHERE conrelid = 'pellier.execution_receipts'::regclass
       AND contype = 'f'
       AND confrelid = 'pellier.approvals'::regclass
       AND confdeltype = 'c';
    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'migration 025: execution_receipts.review_id does not CASCADE from '
            'pellier.approvals (found % cascading foreign key(s)); a receipt '
            'could outlive its review', v_count;
    END IF;

    RAISE EXCEPTION 'migration 025 probe complete' USING ERRCODE = 'P0025';
  EXCEPTION WHEN SQLSTATE 'P0025' THEN
    RAISE NOTICE
        'migration 025: execution receipt constraints verified; probe rows '
        'rolled back';
  END;
END $$;
