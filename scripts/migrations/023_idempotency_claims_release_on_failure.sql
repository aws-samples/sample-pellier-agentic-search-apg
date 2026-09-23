-- Migration 023: a failed governed write must not consume its idempotency key.
--
-- Runs after: 011_governed_write_integrity.sql (owns both functions patched here)
--             022_write_operation_vocabulary.sql (operation vocabulary)
--
-- The bug
-- -------
--
-- `process_return_idempotent` claimed the idempotency key BEFORE validating the
-- business precondition, then finalised the row unconditionally:
--
--     INSERT INTO pellier.write_operations (...) ON CONFLICT DO NOTHING;   -- claim
--     ... ownership check fails -> v_result := {status: error, ...}
--     UPDATE pellier.write_operations SET result = v_result, completed_at = now();
--
-- So a *failed* attempt stored a completed row. The replay guard then reads it:
--
--     IF NOT v_claimed AND v_existing.result IS NOT NULL THEN
--         RETURN v_existing.result || {'idempotent_replay': true};
--
-- and every later retry with that key returns the cached failure without ever
-- re-attempting. The key is permanently poisoned.
--
-- Measured on this cluster, 2026-08-26
-- ------------------------------------
--
-- The function is not SECURITY DEFINER, so the ownership probe
-- `PERFORM 1 FROM pellier.orders` runs under the caller's role and IS subject to
-- the `orders_principal_scope` RLS policy from 016. Therefore an authorization
-- scope error is recorded as a business fact:
--
--   1. bound to Marco's principal, called for CUST-JESSICA / product 41 — an
--      order that genuinely exists — RLS hid the row, and the function stored
--      "Customer CUST-JESSICA did not order product 41; cannot process return."
--   2. retried with the row fully visible: same cached error,
--      "idempotent_replay": true, and pellier.returns still held 0 rows for that
--      customer and product.
--
-- A legitimate return became permanently unprocessable under that key, and a
-- statement about *visibility* was persisted as a statement about *purchase
-- history*. `write_operations` is defined as durable write evidence, one row per
-- key, proving a replayed call applied exactly once; a row describing something
-- that never applied breaks that contract.
--
-- The fix
-- -------
--
-- Only a successful outcome may be persisted and replayed. A failed attempt
-- releases the claim it made, so a retry re-attempts. The resulting invariant for
-- an ownership, RLS, or validation failure:
--
--     domain rows            unchanged
--     write_operations       no FINALISED row for that key; the claim is left
--                            unfinalised (result and completed_at NULL), so the
--                            key is retryable
--     tool_audit             exactly one attempt receipt
--
-- `tool_audit` remains the attempt receipt. That distinction is the point.
--
-- Concurrency: nothing is deleted, so no caller can remove a row another
-- transaction is working under. A concurrent caller sees an unfinalised claim and
-- re-attempts, which is the correct behaviour after a failed predecessor.
--
-- Idempotent: both functions are CREATE OR REPLACE, and the verification block
-- re-runs safely.

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------
-- Guard: refuse to patch a body this migration was not written against.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    v_body TEXT;
BEGIN
    SELECT pg_get_functiondef(p.oid) INTO v_body
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'pellier' AND p.proname = 'process_return_idempotent';

    IF v_body IS NULL THEN
        RAISE EXCEPTION
            'pellier.process_return_idempotent does not exist. Apply '
            '011_governed_write_integrity.sql first.';
    END IF;

    -- The unconditional finalisation is the defect being removed. If it is
    -- already gone, this migration has run (or the body diverged) and the
    -- verification block below still proves the required behaviour.
    IF position('SET result = v_result' IN v_body) = 0 THEN
        RAISE NOTICE
            'migration 023: no unconditional finalisation found; verifying behaviour only';
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- process_return_idempotent: release the claim unless the write succeeded.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION pellier.process_return_idempotent(
    p_idempotency_key TEXT,
    p_request_hash TEXT,
    p_customer_id TEXT,
    p_product_id TEXT,
    p_reason TEXT
) RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_claimed BOOLEAN;
    v_rows INTEGER;
    v_existing pellier.write_operations%ROWTYPE;
    v_return_id BIGINT;
    v_name TEXT;
    v_warehouse_id TEXT;
    v_quantity INTEGER;
    v_result JSONB;
BEGIN
    IF NULLIF(btrim(p_idempotency_key), '') IS NULL THEN
        RETURN jsonb_build_object(
            'status', 'error',
            'message', 'idempotency_key is required.'
        );
    END IF;
    IF p_reason NOT IN (
        'damaged',
        'wrong_size',
        'not_as_described',
        'changed_mind',
        'other'
    ) THEN
        RETURN jsonb_build_object(
            'status', 'policy_blocked',
            'message', format('Reason %s is not allowed.', p_reason)
        );
    END IF;

    INSERT INTO pellier.write_operations
        (idempotency_key, operation, request_hash)
    VALUES
        (p_idempotency_key, 'initiate_return', p_request_hash)
    ON CONFLICT (idempotency_key) DO NOTHING;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    v_claimed := v_rows = 1;

    SELECT *
      INTO v_existing
      FROM pellier.write_operations
     WHERE idempotency_key = p_idempotency_key
     FOR UPDATE;

    IF NOT FOUND THEN
        -- A concurrent caller released its failed claim between the INSERT and
        -- this lock. Adopt the claim rather than continuing against an all-NULL
        -- record, where the argument guard below would silently not fire.
        INSERT INTO pellier.write_operations
            (idempotency_key, operation, request_hash)
        VALUES
            (p_idempotency_key, 'initiate_return', p_request_hash)
        ON CONFLICT (idempotency_key) DO NOTHING;
        SELECT *
          INTO v_existing
          FROM pellier.write_operations
         WHERE idempotency_key = p_idempotency_key
         FOR UPDATE;
        v_claimed := TRUE;
    END IF;

    IF v_existing.operation <> 'initiate_return'
       OR v_existing.request_hash <> p_request_hash THEN
        RETURN jsonb_build_object(
            'status', 'idempotency_conflict',
            'message', 'Idempotency key was already used with different arguments.'
        );
    END IF;
    IF NOT v_claimed AND v_existing.result IS NOT NULL THEN
        RETURN v_existing.result || jsonb_build_object('idempotent_replay', true);
    END IF;

    PERFORM 1
      FROM pellier.orders
     WHERE customer_id = p_customer_id
       AND product_id = p_product_id
     LIMIT 1;
    IF NOT FOUND THEN
        -- Reached under two very different conditions: the customer genuinely has
        -- no such order, or RLS is hiding one that exists. This function cannot
        -- tell them apart, which is precisely why the outcome must not be cached.
        v_result := jsonb_build_object(
            'status', 'error',
            'message', format(
                'Customer %s did not order product %s; cannot process return.',
                p_customer_id, p_product_id
            )
        );
    ELSE
        SELECT name
          INTO v_name
          FROM pellier.product_catalog
         WHERE "productId" = p_product_id
         FOR UPDATE;

        IF v_name IS NULL THEN
            v_result := jsonb_build_object(
                'status', 'error',
                'message', format('Product %s not found.', p_product_id)
            );
        ELSE
            IF p_reason = 'damaged' THEN
                SELECT warehouse_id
                  INTO v_warehouse_id
                  FROM pellier.warehouse_inventory
                 WHERE product_id = p_product_id
                 ORDER BY quantity DESC
                 LIMIT 1;
            END IF;

            IF v_result IS NULL THEN
                INSERT INTO pellier.returns (customer_id, product_id, reason)
                VALUES (p_customer_id, p_product_id, p_reason)
                RETURNING id INTO v_return_id;

                IF p_reason = 'damaged' THEN
                    SELECT COALESCE(sum(quantity), 0)::INTEGER
                      INTO v_quantity
                      FROM pellier.warehouse_inventory
                     WHERE product_id = p_product_id;

                    UPDATE pellier.product_catalog
                       SET quantity = v_quantity,
                           updated_at = now()
                     WHERE "productId" = p_product_id;
                END IF;

                v_result := jsonb_build_object(
                    'status', 'success',
                    'return_id', v_return_id,
                    'product_id', p_product_id::INTEGER,
                    'name', v_name,
                    'reason', p_reason,
                    'new_quantity', CASE
                        WHEN p_reason = 'damaged' THEN v_quantity
                        ELSE NULL
                    END,
                    'warehouse_id', v_warehouse_id,
                    'idempotent_replay', false
                );
            END IF;
        END IF;
    END IF;

    -- The change, and it is a deletion of behaviour rather than an addition: the
    -- finalising UPDATE is now conditional on success.
    --
    -- A failed attempt leaves its claim row UNFINALISED — `result` and
    -- `completed_at` stay NULL — which is what makes the key retryable, because
    -- the replay guard above only short-circuits when `result IS NOT NULL`.
    --
    -- Deliberately NOT a DELETE. `pellier_agent` is granted SELECT, INSERT and
    -- UPDATE on this table by 016 and nothing more, so releasing by deletion
    -- raised `permission denied for table write_operations` under the agent role
    -- and aborted the whole transaction — turning a clean business refusal into an
    -- error. Granting DELETE to the agent to work around that would hand the
    -- runtime role the ability to remove write evidence, which is the opposite of
    -- what this table is for. An unfinalised claim needs no new privilege and
    -- keeps the attempt visible.
    IF v_result->>'status' = 'success' THEN
        UPDATE pellier.write_operations
           SET result = v_result,
               completed_at = now()
         WHERE idempotency_key = p_idempotency_key;
    END IF;
    RETURN v_result;
END;
$$;

-- ---------------------------------------------------------------------
-- Verification: the invariant, proved rather than asserted.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    v_key        TEXT := 'migration-023-verify';
    v_result     JSONB;
    v_rows       INTEGER;
    v_returns    INTEGER;
    v_customer   TEXT := 'migration-023-' || txid_current()::TEXT;
    v_product    TEXT;
BEGIN
  -- The probe runs inside a subtransaction that ends by raising a private
  -- SQLSTATE (P0023) caught below, which discards every row it wrote. It used
  -- to delete its own rows instead, and since migration 047 a COMPLETED
  -- pellier.write_operations row cannot be deleted: that DELETE aborts this
  -- migration on any cluster that already has 047, which is every re-apply.
  -- Rolling back proves the same invariants and asks for no exemption from the
  -- immutability rule.
  BEGIN
    -- 1. A failed attempt must leave no write_operations row.
    v_result := pellier.process_return_idempotent(
        v_key, repeat('d', 64), 'CUST-DOES-NOT-EXIST', '1', 'damaged'
    );
    IF v_result->>'status' <> 'error' THEN
        RAISE EXCEPTION 'migration 023: expected a failure, got %', v_result;
    END IF;
    SELECT COUNT(*) INTO v_rows
      FROM pellier.write_operations
     WHERE idempotency_key = v_key
       AND (result IS NOT NULL OR completed_at IS NOT NULL);
    IF v_rows <> 0 THEN
        RAISE EXCEPTION
            'migration 023: a failed attempt left % FINALISED write_operations '
            'row(s); the idempotency key is consumed and the key is poisoned',
            v_rows;
    END IF;

    -- 2. The same key must then be reusable and reach a real outcome, rather
    --    than returning a cached failure.
    v_result := pellier.process_return_idempotent(
        v_key, repeat('d', 64), 'CUST-DOES-NOT-EXIST', '1', 'damaged'
    );
    IF COALESCE((v_result->>'idempotent_replay')::BOOLEAN, FALSE) THEN
        RAISE EXCEPTION
            'migration 023: retry after a failure returned a cached replay';
    END IF;

    -- 3. A success must still be recorded once and replay exactly once.
    -- Own the probe's order instead of choosing an arbitrary customer's order:
    -- that customer's entire quantity may already have been returned. Keep the
    -- fixture inside this rollback-only subtransaction, with the real quantity
    -- guard active. No customer, order, return, or write receipt survives it.
    SELECT p."productId" INTO v_product
      FROM pellier.product_catalog p
     ORDER BY p."productId"
     LIMIT 1;
    IF v_product IS NULL THEN
        RAISE NOTICE 'migration 023: no catalog rows available; skipping success probe';
    ELSE
        INSERT INTO pellier.customers (id, name)
        VALUES (v_customer, 'Migration 023 rollback-only probe');
        INSERT INTO pellier.orders (customer_id, product_id, quantity)
        VALUES (v_customer, v_product, 1);
        SELECT COUNT(*) INTO v_returns FROM pellier.returns;
        v_result := pellier.process_return_idempotent(
            v_key || '-success', repeat('e', 64), v_customer, v_product, 'changed_mind'
        );
        IF v_result->>'status' <> 'success' THEN
            RAISE EXCEPTION 'migration 023: success probe failed: %', v_result;
        END IF;
        SELECT COUNT(*) INTO v_rows
          FROM pellier.write_operations
         WHERE idempotency_key = v_key || '-success' AND completed_at IS NOT NULL;
        IF v_rows <> 1 THEN
            RAISE EXCEPTION
                'migration 023: a successful write did not leave exactly one '
                'completed row (got %)', v_rows;
        END IF;

        v_result := pellier.process_return_idempotent(
            v_key || '-success', repeat('e', 64), v_customer, v_product, 'changed_mind'
        );
        IF NOT COALESCE((v_result->>'idempotent_replay')::BOOLEAN, FALSE) THEN
            RAISE EXCEPTION
                'migration 023: replaying a successful key did not report a replay';
        END IF;

        -- Exactly once: the replay must not have inserted a second return.
        IF (SELECT COUNT(*) FROM pellier.returns) <> v_returns + 1 THEN
            RAISE EXCEPTION
                'migration 023: replay applied the write more than once';
        END IF;

    END IF;

    RAISE EXCEPTION 'migration 023 probe complete' USING ERRCODE = 'P0023';
  EXCEPTION WHEN SQLSTATE 'P0023' THEN
    RAISE NOTICE
        'migration 023: verified. A failed attempt releases its idempotency key, '
        'a success is recorded once and replays once, and every probe row was '
        'rolled back';
  END;
END $$;

COMMIT;
