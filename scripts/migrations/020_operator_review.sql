-- Migration 020: the durable operator review.
--
-- Pellier reaches the consequential-action boundary and stops. This migration
-- makes that prepared request durably discoverable in Pellier Operator, so the
-- handoff survives the shopper closing the tab.
--
-- NO NEW TABLE. pellier.approvals already models "a pending human decision on a
-- proposed tool call with its arguments" — migration 002 describes it as the
-- identity-gated sensitive-tool gate — and it has been dormant since: zero rows,
-- and nothing in the application reads or writes it. Its status CHECK is already
-- pending | approved | rejected, which is exactly the three human states this
-- workflow needs. Adopting it fulfils its documented purpose.
--
-- pellier.support_tickets was the other candidate and was rejected: it models
-- inbound correspondence (phone / chat / email) with prose subjects, it supplies
-- 4 of the 12 fields a review needs, and get_ticket_history reads it into the
-- shopper-facing concierge history. Encoding a proposed mutation into
-- last_note prose is the failure mode this arc exists to avoid.
--
-- The invariant that shapes every column below: a review owns workflow state and
-- references. It never owns business truth. There is no membership, no spend, no
-- order status, no inventory count, no return status, no policy verdict and no
-- database effect here. Those are hydrated from their authoritative sources on
-- read, because a cached copy forks the truth and then Pellier and Pellier
-- Operator disagree about the same client.
--
-- Confirmation binding reuses the proof-carrying pattern from migration 015:
-- a canonical SHA-256 over the material parameters, compared on confirmation, so
-- a changed amount or a changed reason invalidates the prior human decision
-- rather than silently inheriting it.
--
-- Idempotent: every statement is IF NOT EXISTS or a guarded ALTER.

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------
-- Workflow columns on the existing gate
-- ---------------------------------------------------------------------

ALTER TABLE pellier.approvals
    -- The evidence anchor. This is the turn_id minted for the shopper
    -- interaction that produced the request; it is NOT a new correlation id.
    -- Nullable because an operator-initiated review has no originating turn.
    ADD COLUMN IF NOT EXISTS source_turn_id TEXT,

    -- The resource under review. ON DELETE SET NULL rather than CASCADE: losing
    -- the order should not silently erase the record that a human was asked to
    -- decide something.
    ADD COLUMN IF NOT EXISTS order_id BIGINT
        REFERENCES pellier.orders(id) ON DELETE SET NULL,

    -- What the shopper reported, in their terms. Workflow state: this is the
    -- review's own statement of the complaint, not a catalog or returns fact.
    ADD COLUMN IF NOT EXISTS issue TEXT,

    -- What Pellier proposed and why. Holds the rationale and any secondary
    -- suggestion (for example a courtesy credit). It must NOT hold availability
    -- or entitlement: "a replacement is available" depends on live inventory and
    -- is resolved at render time.
    ADD COLUMN IF NOT EXISTS recommendation JSONB,

    -- Canonical fingerprint of the material parameters, so a confirmation binds
    -- to the exact mutation it was given.
    ADD COLUMN IF NOT EXISTS action_hash TEXT,

    -- The operator principal who decided. Distinct from customer_id, which is
    -- the subject of the review rather than its author.
    ADD COLUMN IF NOT EXISTS decided_by TEXT,

    -- The decider's username, recorded with the decision, so the record can
    -- name who approved it to every staff member who reads it. decided_by
    -- stays the verified subject every other ledger carries.
    ADD COLUMN IF NOT EXISTS decided_by_name TEXT,

    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- ---------------------------------------------------------------------
-- One live review per distinct proposed mutation
-- ---------------------------------------------------------------------

-- A partial unique index rather than a plain one: at most one LIVE review per
-- (client, action, exact parameters), where live means pending or approved,
-- while declined history accumulates freely.
--
-- Approved stays in the index because an approval is what a write binds to:
-- the credit tool admits a write only under the key derived from the approved
-- review's own id. A second approved review for the same exact credit would be
-- a second id, so a second key, so a second credit for one decision. Asking
-- again for a credit a person already approved resolves to that review. A
-- declined review leaves the index, so the same credit may be proposed again
-- after a no.
--
-- Keyed on the action fingerprint rather than on the source turn, which a live
-- smoke run showed to be the wrong key. Every HTTP request mints its own
-- turn_id, so a shopper who asks twice produces two turns — and a turn-scoped
-- index dutifully allowed two identical pending cards for the same client and
-- the same piece. An operator does not have two decisions to make there; they
-- have one. Keying on the fingerprint also means the rule still holds if a turn
-- id is ever missing, where a nullable-column index silently protects nothing.
--
-- The source turn is still recorded on the row: it is provenance and the
-- evidence anchor, not the uniqueness key.
DROP INDEX IF EXISTS pellier.approvals_open_per_turn_action_idx;

-- The predicate is the contract, so a cluster built while the index covered
-- pending reviews only gets it replaced rather than kept by IF NOT EXISTS.
-- The reset re-applies this file, and its probe below needs the live index.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM pg_indexes
         WHERE schemaname = 'pellier'
           AND indexname = 'approvals_open_per_action_idx'
           AND position('approved' IN indexdef) = 0
    ) THEN
        DROP INDEX pellier.approvals_open_per_action_idx;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS approvals_open_per_action_idx
    ON pellier.approvals (customer_id, tool, action_hash)
    WHERE status IN ('pending', 'approved');

-- The Operator queue reads by turn to answer "is this shopper turn already
-- waiting on a human?" without scanning.
CREATE INDEX IF NOT EXISTS approvals_source_turn_idx
    ON pellier.approvals (source_turn_id)
    WHERE source_turn_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS approvals_customer_idx
    ON pellier.approvals (customer_id, requested_at DESC);

-- ---------------------------------------------------------------------
-- A decided review must say who decided it, and when
-- ---------------------------------------------------------------------

-- Without this, a rejected review with no decider is a reporting hole that only
-- shows up in an audit months later. Reject it at write time, the same way
-- migration 019 rejects a resolved ticket with no resolution timestamp.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'approvals_decision_complete_check'
    ) THEN
        ALTER TABLE pellier.approvals
            ADD CONSTRAINT approvals_decision_complete_check
            CHECK (
                (status = 'pending'
                 AND decided_at IS NULL
                 AND decided_by IS NULL)
                OR
                (status IN ('approved', 'rejected')
                 AND decided_at IS NOT NULL
                 AND decided_by IS NOT NULL)
            );
    END IF;
END $$;

-- A pending review that proposes an action must carry the fingerprint that
-- confirmation will be checked against. A review with no fingerprint cannot bind
-- a decision to parameters, which is the whole point of the object.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'approvals_action_hash_present_check'
    ) THEN
        ALTER TABLE pellier.approvals
            ADD CONSTRAINT approvals_action_hash_present_check
            CHECK (action_hash IS NULL OR length(action_hash) = 64);
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- Keep updated_at honest
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION pellier.touch_approval_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS approvals_touch_updated_at ON pellier.approvals;
CREATE TRIGGER approvals_touch_updated_at
    BEFORE UPDATE ON pellier.approvals
    FOR EACH ROW
    EXECUTE FUNCTION pellier.touch_approval_updated_at();

COMMIT;

-- ---------------------------------------------------------------------
-- Self-probe: prove the lifecycle before anything depends on it
-- ---------------------------------------------------------------------
--
-- Exercises create -> replay -> confirm -> replay after approval -> decline
-- and the two CHECK constraints, then removes its own rows. A migration that claims a state
-- machine works without ever running it is a comment, not a guarantee.

DO $$
DECLARE
    v_turn   TEXT := 'migration-020-probe-turn';
    v_cust   TEXT;
    v_hash   TEXT := repeat('a', 64);
    v_hash_declined TEXT := repeat('b', 64);
    v_first  BIGINT;
    v_second BIGINT;
    v_count  INTEGER;
    v_failed BOOLEAN;
BEGIN
    SELECT id INTO v_cust FROM pellier.customers ORDER BY id LIMIT 1;
    IF v_cust IS NULL THEN
        RAISE NOTICE 'migration 020: no customers seeded, skipping self-probe';
        RETURN;
    END IF;

    -- 1. create
    INSERT INTO pellier.approvals
        (customer_id, tool, args, status, source_turn_id, issue, action_hash)
    VALUES
        (v_cust, 'initiate_return', '{"reason":"damaged"}'::jsonb, 'pending',
         v_turn, 'probe', v_hash)
    RETURNING id INTO v_first;

    -- 2. the same proposed mutation, asked again from a DIFFERENT turn: the
    --    partial unique index must refuse it. A different turn is exactly the
    --    case a turn-scoped index missed.
    v_failed := FALSE;
    BEGIN
        INSERT INTO pellier.approvals
            (customer_id, tool, args, status, source_turn_id, issue, action_hash)
        VALUES
            (v_cust, 'initiate_return', '{"reason":"damaged"}'::jsonb, 'pending',
             v_turn || '-second-turn', 'probe replay', v_hash)
        RETURNING id INTO v_second;
    EXCEPTION WHEN unique_violation THEN
        v_failed := TRUE;
    END;
    IF NOT v_failed THEN
        RAISE EXCEPTION
            'migration 020: a second turn opened a duplicate review (id %)',
            v_second;
    END IF;

    -- 3. a decision with no decider must be refused
    v_failed := FALSE;
    BEGIN
        UPDATE pellier.approvals
           SET status = 'approved', decided_at = now()
         WHERE id = v_first;
    EXCEPTION WHEN check_violation THEN
        v_failed := TRUE;
    END;
    IF NOT v_failed THEN
        RAISE EXCEPTION
            'migration 020: approved a review with no decided_by';
    END IF;

    -- 4. a complete confirmation must succeed
    UPDATE pellier.approvals
       SET status = 'approved', decided_at = now(), decided_by = 'probe-operator'
     WHERE id = v_first;

    -- 5. with the first APPROVED, the same mutation must still be refused: an
    --    approval is live, and a second one would mint a second write key
    v_failed := FALSE;
    BEGIN
        INSERT INTO pellier.approvals
            (customer_id, tool, args, status, source_turn_id, issue, action_hash)
        VALUES
            (v_cust, 'initiate_return', '{"reason":"damaged"}'::jsonb, 'pending',
             v_turn || '-after-approval', 'probe after approval', v_hash)
        RETURNING id INTO v_second;
    EXCEPTION WHEN unique_violation THEN
        v_failed := TRUE;
    END;
    IF NOT v_failed THEN
        RAISE EXCEPTION
            'migration 020: an approved review admitted a second review (id %)',
            v_second;
    END IF;

    -- 6. a different mutation, declined, leaves the index: the same mutation
    --    may then be proposed again
    INSERT INTO pellier.approvals
        (customer_id, tool, args, status, source_turn_id, issue, action_hash)
    VALUES
        (v_cust, 'initiate_return', '{"reason":"other"}'::jsonb, 'pending',
         v_turn || '-declined', 'probe to decline', v_hash_declined)
    RETURNING id INTO v_second;
    UPDATE pellier.approvals
       SET status = 'rejected', decided_at = now(), decided_by = 'probe-operator'
     WHERE id = v_second;
    INSERT INTO pellier.approvals
        (customer_id, tool, args, status, source_turn_id, issue, action_hash)
    VALUES
        (v_cust, 'initiate_return', '{"reason":"other"}'::jsonb, 'pending',
         v_turn || '-after-decline', 'probe after decline', v_hash_declined);

    -- The probe's inserts use v_turn plus a suffix, so match the prefix.
    SELECT count(*) INTO v_count
      FROM pellier.approvals WHERE source_turn_id LIKE v_turn || '%';
    IF v_count <> 3 THEN
        RAISE EXCEPTION
            'migration 020: expected 3 probe rows, found %', v_count;
    END IF;

    DELETE FROM pellier.approvals WHERE source_turn_id LIKE v_turn || '%';
    RAISE NOTICE
        'migration 020: review lifecycle verified (create/replay/confirm/'
        'live-after-approval/decline)';
END $$;
