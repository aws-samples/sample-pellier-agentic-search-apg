-- Migration 019: Store credits, support tickets, and the Aurora semantic cache.
--
-- Runs after:
--   001_schema.sql                   (pgvector, product_catalog)
--   002_workshop_telemetry.sql       (customers, orders)
--   018_client_book.sql              (membership, the client book)
--
-- Why this exists
-- ---------------
-- Three capabilities that reference retail-concierge architectures reach for
-- a separate AWS service to provide. Each one is done here in Aurora
-- PostgreSQL, because that is the actual architectural claim this workshop
-- makes: the access patterns an agent generates are not, by themselves, a
-- reason to add another engine.
--
--   pellier.store_credits    service recovery. A goodwill credit is a money
--                            movement, so it gets its own durable row rather
--                            than being smuggled in as a note on a return.
--                            A return is not a credit.
--
--   pellier.support_tickets  past interactions, so the concierge can reason
--                            over what already happened to a client instead
--                            of re-asking.
--
--   pellier.semantic_cache   the paraphrase cache. Commonly delegated to an
--                            external cache; here it is a vector column plus
--                            an HNSW index. A repeat or reworded question
--                            skips both the embedding call and the model
--                            call, which is where the cost actually is.
--
-- Cross-channel fan-out uses LISTEN/NOTIFY, not an external stream. The
-- operator issues a credit and a listening shopper session is told. One
-- caveat, stated because it decides deployment: NOTIFY is delivered on the
-- Aurora *writer*. It is not propagated to reader endpoints, so a listener
-- must hold a writer connection.
--
-- Policy note: the <= $500 goodwill ceiling is enforced by a CHECK
-- constraint, deliberately. Agent policy decides what may be attempted;
-- the database decides what may actually be written. A ceiling that lives
-- only in a prompt or a tool schema is a suggestion.
--
-- Idempotent: tables use IF NOT EXISTS, seed rows upsert on natural keys.

\set ON_ERROR_STOP on

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------
-- Store credits
-- ---------------------------------------------------------------------
-- Amounts are integer cents. Money in a float is a defect waiting for a
-- rounding report to disagree with the ledger.
CREATE TABLE IF NOT EXISTS pellier.store_credits (
    credit_id       BIGSERIAL PRIMARY KEY,
    customer_id     TEXT NOT NULL
                    REFERENCES pellier.customers(id) ON DELETE CASCADE,
    amount_cents    INTEGER NOT NULL
                    CHECK (amount_cents > 0 AND amount_cents <= 50000),
    currency        TEXT NOT NULL DEFAULT 'USD',
    reason          TEXT NOT NULL,
    -- The verified operator `sub` from the token. NULL only for seed rows,
    -- which are labelled as such in `reason`.
    issued_by       TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    order_id        BIGINT REFERENCES pellier.orders(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS store_credits_customer_idx
    ON pellier.store_credits (customer_id, created_at DESC);

COMMENT ON TABLE pellier.store_credits IS
    'Goodwill and service-recovery credits. One row per idempotency_key.';
COMMENT ON COLUMN pellier.store_credits.amount_cents IS
    'Integer cents. CHECK enforces the <= $500 goodwill ceiling in the database.';

-- ---------------------------------------------------------------------
-- Support tickets
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pellier.support_tickets (
    ticket_id   TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL
                REFERENCES pellier.customers(id) ON DELETE CASCADE,
    subject     TEXT NOT NULL,
    status      TEXT NOT NULL
                CHECK (status IN ('open', 'pending', 'resolved', 'closed')),
    channel     TEXT NOT NULL DEFAULT 'email',
    last_note   TEXT,
    opened_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS support_tickets_customer_idx
    ON pellier.support_tickets (customer_id, opened_at DESC);

-- A resolved ticket with no resolution timestamp is a reporting bug that
-- only shows up in a dashboard months later. Reject it at write time.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'support_tickets_resolved_at_check'
    ) THEN
        ALTER TABLE pellier.support_tickets
            ADD CONSTRAINT support_tickets_resolved_at_check
            CHECK (
                (status IN ('resolved', 'closed') AND resolved_at IS NOT NULL)
                OR (status IN ('open', 'pending') AND resolved_at IS NULL)
            );
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- Semantic cache
-- ---------------------------------------------------------------------
-- The lookup is a cosine-distance nearest neighbour over stored query
-- embeddings. A hit means an earlier, differently-worded question already
-- has an answer, so this turn skips the embedding call and the model call.
CREATE TABLE IF NOT EXISTS pellier.semantic_cache (
    cache_id        BIGSERIAL PRIMARY KEY,
    -- Scope keeps one shopper's personalized answer from being served to
    -- another. 'global' is for answers that carry no customer context.
    scope           TEXT NOT NULL DEFAULT 'global',
    query_text      TEXT NOT NULL,
    query_embedding vector(1024) NOT NULL,
    answer_json     JSONB NOT NULL,
    hit_count       INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_hit_at     TIMESTAMPTZ
);

-- Cosine, matching how the catalog embeddings are compared elsewhere.
CREATE INDEX IF NOT EXISTS semantic_cache_embedding_idx
    ON pellier.semantic_cache
    USING hnsw (query_embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS semantic_cache_scope_idx
    ON pellier.semantic_cache (scope, created_at DESC);

COMMENT ON TABLE pellier.semantic_cache IS
    'Paraphrase cache. A vector column plus an HNSW index, in place of an external semantic cache.';

-- ---------------------------------------------------------------------
-- Widen the durable write-event allow-list to admit credits.
-- ---------------------------------------------------------------------
-- `pellier.write_operations.operation` is CHECK-constrained to an allow-list
-- created by migration 011. Adding a third governed write means widening it
-- here rather than editing 011, because 011 has already been applied on every
-- existing cluster and would not re-run.
--
-- The allow-list is the point: an operation name nothing recognises must not
-- be able to claim an idempotency key. This migration's self-test at the
-- bottom exercises the credit write end to end, so a forgotten entry here
-- fails the migration instead of failing the first real credit.
ALTER TABLE pellier.write_operations
    DROP CONSTRAINT IF EXISTS write_operations_operation_check;

ALTER TABLE pellier.write_operations
    ADD CONSTRAINT write_operations_operation_check
    CHECK (operation IN ('initiate_return', 'restock_inventory', 'issue_credit'));

-- ---------------------------------------------------------------------
-- The governed write: apply a store credit exactly once.
-- ---------------------------------------------------------------------
-- Mirrors the claim/verify/replay shape of the existing idempotent write
-- functions from migration 011, so a credit produces the same durable
-- evidence every other governed write produces: one pellier.write_operations
-- row per idempotency_key, carrying the result.
--
-- A replay returns the original result with `idempotent_replay: true` rather
-- than issuing a second credit. Reusing one key with different arguments is
-- an `idempotency_conflict`, not a silent overwrite.
--
-- Named `apply_store_credit`, without the `_idempotent` suffix the two older
-- functions carry. Those keep their names because renaming them would need
-- their GRANTs in migration 016 reissued on every deployed cluster.
CREATE OR REPLACE FUNCTION pellier.apply_store_credit(
    p_idempotency_key TEXT,
    p_request_hash TEXT,
    p_customer_id TEXT,
    p_amount_cents INTEGER,
    p_reason TEXT,
    p_issued_by TEXT DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_claimed  BOOLEAN;
    v_rows     INTEGER;
    v_existing pellier.write_operations%ROWTYPE;
    v_name     TEXT;
    v_credit   BIGINT;
    v_total    INTEGER;
    v_result   JSONB;
BEGIN
    IF NULLIF(btrim(p_idempotency_key), '') IS NULL THEN
        RETURN jsonb_build_object(
            'status', 'error', 'message', 'idempotency_key is required.');
    END IF;
    IF p_amount_cents IS NULL OR p_amount_cents <= 0 THEN
        RETURN jsonb_build_object(
            'status', 'error', 'message', 'Credit amount must be positive.');
    END IF;
    -- The CHECK constraint on the table is the real backstop. This returns a
    -- readable envelope instead of letting the agent see a raw SQL error.
    IF p_amount_cents > 50000 THEN
        RETURN jsonb_build_object(
            'status', 'policy_blocked',
            'message', format(
                'Credit of $%s exceeds the $500.00 goodwill ceiling. '
                'Escalate for approval.',
                to_char(p_amount_cents / 100.0, 'FM999999.00')));
    END IF;
    IF NULLIF(btrim(COALESCE(p_reason, '')), '') IS NULL THEN
        RETURN jsonb_build_object(
            'status', 'error', 'message', 'A reason is required for a credit.');
    END IF;

    INSERT INTO pellier.write_operations
        (idempotency_key, operation, request_hash)
    VALUES
        (p_idempotency_key, 'issue_credit', p_request_hash)
    ON CONFLICT (idempotency_key) DO NOTHING;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    v_claimed := v_rows = 1;

    SELECT * INTO v_existing
      FROM pellier.write_operations
     WHERE idempotency_key = p_idempotency_key
     FOR UPDATE;

    IF v_existing.operation <> 'issue_credit'
       OR v_existing.request_hash <> p_request_hash THEN
        RETURN jsonb_build_object(
            'status', 'idempotency_conflict',
            'message', 'Idempotency key was already used with different arguments.');
    END IF;
    IF NOT v_claimed AND v_existing.result IS NOT NULL THEN
        RETURN v_existing.result || jsonb_build_object('idempotent_replay', true);
    END IF;

    SELECT name INTO v_name
      FROM pellier.customers
     WHERE id = p_customer_id
     FOR UPDATE;

    IF v_name IS NULL THEN
        v_result := jsonb_build_object(
            'status', 'error',
            'message', format('Customer %s not found.', p_customer_id));
    ELSE
        INSERT INTO pellier.store_credits
            (customer_id, amount_cents, reason, issued_by, idempotency_key)
        VALUES
            (p_customer_id, p_amount_cents, btrim(p_reason),
             NULLIF(btrim(COALESCE(p_issued_by, '')), ''), p_idempotency_key)
        RETURNING credit_id INTO v_credit;

        SELECT COALESCE(SUM(amount_cents), 0)::INTEGER INTO v_total
          FROM pellier.store_credits
         WHERE customer_id = p_customer_id;

        v_result := jsonb_build_object(
            'status', 'success',
            'credit_id', v_credit,
            'customer_id', p_customer_id,
            'customer_name', v_name,
            'amount_cents', p_amount_cents,
            'amount', to_char(p_amount_cents / 100.0, 'FM999999.00'),
            'balance_cents', v_total,
            'reason', btrim(p_reason),
            'issued_by', NULLIF(btrim(COALESCE(p_issued_by, '')), ''),
            'idempotent_replay', false);
    END IF;

    UPDATE pellier.write_operations
       SET result = v_result,
           completed_at = now()
     WHERE idempotency_key = p_idempotency_key;
    RETURN v_result;
END;
$$;

-- ---------------------------------------------------------------------
-- Cross-channel fan-out via LISTEN/NOTIFY
-- ---------------------------------------------------------------------
-- Channel: pellier_data_changed. Payload is JSON so a listener can filter
-- by customer without a follow-up query.
--
-- pg_notify is used rather than bare NOTIFY because the channel payload is
-- dynamic. The 8000-byte payload limit is well clear of these fields.
CREATE OR REPLACE FUNCTION pellier.notify_data_changed()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    payload JSON;
BEGIN
    payload := json_build_object(
        'entity',      TG_ARGV[0],
        'customerId',  NEW.customer_id,
        'changedAt',   to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SSOF')
    );
    PERFORM pg_notify('pellier_data_changed', payload::text);
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS store_credits_notify ON pellier.store_credits;
CREATE TRIGGER store_credits_notify
    AFTER INSERT ON pellier.store_credits
    FOR EACH ROW EXECUTE FUNCTION pellier.notify_data_changed('store_credit');

DROP TRIGGER IF EXISTS support_tickets_notify ON pellier.support_tickets;
CREATE TRIGGER support_tickets_notify
    AFTER INSERT OR UPDATE ON pellier.support_tickets
    FOR EACH ROW EXECUTE FUNCTION pellier.notify_data_changed('support_ticket');

-- ---------------------------------------------------------------------
-- Seed. Theo's two tickets give his lab a real case; Jessica keeps her
-- disputed refund. No store credit is seeded.
-- ---------------------------------------------------------------------
INSERT INTO pellier.support_tickets
    (ticket_id, customer_id, subject, status, channel, last_note, opened_at, resolved_at)
VALUES
    ('TKT-2026-3015', 'CUST-JESSICA',
     'Return received, refund amount disputed', 'pending', 'chat',
     'Return logged for the catchall and the robe. Client expected a full refund including original shipping.',
     now() - INTERVAL '11 days', NULL),
    ('TKT-2026-5021', 'CUST-THEO',
     'Wabi-Sabi Bowl arrived chipped', 'open', 'chat',
     'Customer reports a chip on the rim of the bowl from his last order. Awaiting an update.',
     now() - INTERVAL '3 days', NULL),
    ('TKT-2026-1874', 'CUST-THEO',
     'Pour-over set delivery date moved', 'resolved', 'email',
     'Delivery moved by two days at the customer''s request and confirmed.',
     now() - INTERVAL '40 days', now() - INTERVAL '38 days')
ON CONFLICT (ticket_id) DO UPDATE SET
    subject     = EXCLUDED.subject,
    status      = EXCLUDED.status,
    channel     = EXCLUDED.channel,
    last_note   = EXCLUDED.last_note,
    opened_at   = EXCLUDED.opened_at,
    resolved_at = EXCLUDED.resolved_at;

-- ---------------------------------------------------------------------
-- Verification. Fail loud, matching 003 and 018.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    n_tickets   INTEGER;
    n_open      INTEGER;
    has_hnsw    BOOLEAN;
    ceiling_ok  BOOLEAN;
BEGIN
    SELECT COUNT(*) INTO n_tickets FROM pellier.support_tickets;

    -- Theo's lab depends on his open chipped-bowl ticket. If the seed did not
    -- land, the lab points at a case that does not exist.
    SELECT COUNT(*) INTO n_open
      FROM pellier.support_tickets
     WHERE customer_id = 'CUST-THEO' AND status = 'open';

    SELECT EXISTS (
        SELECT 1 FROM pg_indexes
         WHERE schemaname = 'pellier' AND indexname = 'semantic_cache_embedding_idx'
    ) INTO has_hnsw;

    -- Prove the ceiling is enforced by the database, not just documented.
    BEGIN
        INSERT INTO pellier.store_credits
            (customer_id, amount_cents, reason, idempotency_key)
        VALUES ('CUST-JESSICA', 50001, 'ceiling probe', 'ceiling-probe-must-fail');
        ceiling_ok := FALSE;
    EXCEPTION WHEN check_violation THEN
        ceiling_ok := TRUE;
    END;

    IF n_tickets < 3 THEN
        RAISE EXCEPTION 'Expected >= 3 seeded support tickets, found %.', n_tickets;
    END IF;

    IF n_open < 1 THEN
        RAISE EXCEPTION
            'Theo has no open ticket. His lab needs the chipped-bowl case.';
    END IF;

    IF NOT has_hnsw THEN
        RAISE EXCEPTION
            'semantic_cache_embedding_idx is missing. Without the HNSW index '
            'the paraphrase lookup degrades to a sequential scan.';
    END IF;

    IF NOT ceiling_ok THEN
        RAISE EXCEPTION
            'store_credits accepted an amount above the $500 ceiling. The '
            'CHECK constraint is the enforcement point, not the prompt.';
    END IF;

    -- Prove the governed write applies exactly once, and that a replay
    -- returns the original result instead of issuing a second credit. A
    -- write path whose idempotency is only asserted in a comment is not
    -- idempotent.
    DECLARE
        r1 JSONB;
        r2 JSONB;
        r3 JSONB;
        n_after INTEGER;
    BEGIN
        r1 := pellier.apply_store_credit(
            'probe-apply-store-credit', 'probe-hash',
            'CUST-JESSICA', 2500, 'Migration self-test', 'probe-operator');
        r2 := pellier.apply_store_credit(
            'probe-apply-store-credit', 'probe-hash',
            'CUST-JESSICA', 2500, 'Migration self-test', 'probe-operator');
        r3 := pellier.apply_store_credit(
            'probe-apply-store-credit', 'different-hash',
            'CUST-JESSICA', 9900, 'Migration self-test', 'probe-operator');

        SELECT COUNT(*) INTO n_after
          FROM pellier.store_credits
         WHERE idempotency_key = 'probe-apply-store-credit';

        IF r1->>'status' <> 'success' THEN
            RAISE EXCEPTION 'apply_store_credit failed on first call: %', r1;
        END IF;
        IF (r2->>'idempotent_replay')::BOOLEAN IS NOT TRUE THEN
            RAISE EXCEPTION 'apply_store_credit replay did not report idempotent_replay: %', r2;
        END IF;
        IF r3->>'status' <> 'idempotency_conflict' THEN
            RAISE EXCEPTION
                'Reusing one idempotency key with different arguments must be a '
                'conflict, got: %', r3;
        END IF;
        IF n_after <> 1 THEN
            RAISE EXCEPTION
                'Expected exactly 1 credit row for the probe key, found %.', n_after;
        END IF;

        -- Leave no probe residue behind, by rolling the probe back rather than
        -- deleting its rows. Migration 047 makes a COMPLETED
        -- pellier.write_operations row undeletable, so the DELETE that used to
        -- clean up here aborts this migration on any cluster that already has
        -- 047, which is every re-apply: the workshop reset and a second
        -- bootstrap both run 019 again. Raising a private SQLSTATE that this
        -- same block catches discards every row the probe wrote, and asks for
        -- no exemption from the immutability rule. Same shape as 047's own
        -- self-probe.
        RAISE EXCEPTION 'migration 019 credit probe complete' USING ERRCODE = 'P0019';
    EXCEPTION WHEN SQLSTATE 'P0019' THEN
        RAISE NOTICE 'Credit write probe verified; probe rows rolled back';
    END;

    RAISE NOTICE
        'Operator desk ready: % tickets, HNSW present, $500 ceiling enforced, credit write idempotent',
        n_tickets;
END $$;

COMMIT;
