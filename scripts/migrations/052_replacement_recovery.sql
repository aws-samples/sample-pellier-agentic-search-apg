-- An approved replacement is one transaction; fulfillment follows its outbox.
-- No existing returns, orders, or warehouse quantities are rewritten.
\set ON_ERROR_STOP on
BEGIN;
ALTER TABLE pellier.execution_receipts DROP CONSTRAINT IF EXISTS execution_receipts_aurora_outcome_check;
ALTER TABLE pellier.execution_receipts ADD CONSTRAINT execution_receipts_aurora_outcome_check
    CHECK (aurora_outcome IN ('PERMITTED', 'DENIED', 'NOT_REACHED', 'NOT_ENFORCED', 'OUTCOME_UNKNOWN'));
ALTER TABLE pellier.write_operations DROP CONSTRAINT IF EXISTS write_operations_operation_check;
ALTER TABLE pellier.write_operations ADD CONSTRAINT write_operations_operation_check
    CHECK (operation IN ('initiate_return', 'restock_inventory', 'issue_credit',
                        'process_return', 'restock_shelf', 'replace_damaged_item'));

CREATE TABLE IF NOT EXISTS pellier.replacements (
    replacement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id BIGINT NOT NULL UNIQUE REFERENCES pellier.approvals(id),
    idempotency_key TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    customer_id TEXT NOT NULL REFERENCES pellier.customers(id),
    order_id BIGINT NOT NULL REFERENCES pellier.orders(id),
    product_id TEXT NOT NULL REFERENCES pellier.product_catalog("productId"),
    return_id BIGINT NOT NULL UNIQUE REFERENCES pellier.returns(id),
    warehouse_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    disposition TEXT NOT NULL CHECK (disposition = 'inspection_required'),
    status TEXT NOT NULL DEFAULT 'reserved' CHECK (status IN (
        'reserved', 'awaiting_fulfillment', 'outcome_unknown', 'accepted', 'shipped'
    )),
    provider_operation_id TEXT UNIQUE,
    workflow_execution_arn TEXT,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (warehouse_id, product_id)
        REFERENCES pellier.warehouse_inventory(warehouse_id, product_id)
);
CREATE INDEX IF NOT EXISTS replacements_customer_idx
    ON pellier.replacements (customer_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pellier.replacement_outbox (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    replacement_id UUID NOT NULL UNIQUE REFERENCES pellier.replacements(replacement_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_until TIMESTAMPTZ,
    lease_token UUID,
    attempts INTEGER NOT NULL DEFAULT 0,
    execution_arn TEXT,
    published_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS replacement_outbox_pending_idx
    ON pellier.replacement_outbox (created_at) WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS pellier.replacement_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    replacement_id UUID NOT NULL REFERENCES pellier.replacements(replacement_id),
    event_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (replacement_id, event_key)
);

ALTER TABLE pellier.replacements ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS replacements_principal_scope ON pellier.replacements;
CREATE POLICY replacements_principal_scope ON pellier.replacements
    TO pellier_agent
    USING (customer_id IN (SELECT customer_id FROM pellier.current_principal_customers()))
    WITH CHECK (customer_id IN (SELECT customer_id FROM pellier.current_principal_customers()));

-- The tool can lock its scoped approval through a narrow function, without
-- receiving SELECT or UPDATE on everybody's approvals.
CREATE OR REPLACE FUNCTION pellier.lock_replacement_approval(p_review BIGINT, p_customer TEXT)
RETURNS pellier.approvals LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pellier AS $$
DECLARE a pellier.approvals%ROWTYPE;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pellier.current_principal_customers()
                    WHERE customer_id = p_customer) THEN
        RAISE EXCEPTION 'replacement_approval_out_of_scope' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO a FROM pellier.approvals
     WHERE id = p_review AND customer_id = p_customer
       AND tool = 'replace_damaged_item' FOR SHARE;
    RETURN a;
END;
$$;
REVOKE ALL ON FUNCTION pellier.lock_replacement_approval(bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pellier.lock_replacement_approval(bigint,text) TO pellier_agent;
GRANT SELECT, INSERT ON pellier.replacements TO pellier_agent;
GRANT SELECT, INSERT ON pellier.replacement_outbox, pellier.replacement_events TO pellier_agent;
GRANT USAGE, SELECT ON SEQUENCE pellier.replacement_events_event_id_seq TO pellier_agent;
ALTER TABLE pellier.replacement_outbox ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS replacement_outbox_scope ON pellier.replacement_outbox;
CREATE POLICY replacement_outbox_scope ON pellier.replacement_outbox TO pellier_agent
    USING (replacement_id IN (SELECT replacement_id FROM pellier.replacements))
    WITH CHECK (replacement_id IN (SELECT replacement_id FROM pellier.replacements));
ALTER TABLE pellier.replacement_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS replacement_events_scope ON pellier.replacement_events;
CREATE POLICY replacement_events_scope ON pellier.replacement_events TO pellier_agent
    USING (replacement_id IN (SELECT replacement_id FROM pellier.replacements))
    WITH CHECK (replacement_id IN (SELECT replacement_id FROM pellier.replacements));

CREATE OR REPLACE FUNCTION pellier.replace_damaged_item(
    p_review_id BIGINT, p_key TEXT, p_hash TEXT, p_customer TEXT,
    p_order BIGINT, p_product TEXT, p_quantity INTEGER, p_disposition TEXT
) RETURNS JSONB
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, pellier
AS $$
DECLARE
    a pellier.approvals%ROWTYPE;
    o pellier.orders%ROWTYPE;
    existing pellier.replacements%ROWTYPE;
    claim pellier.write_operations%ROWTYPE;
    ordered INTEGER;
    returned INTEGER;
    warehouse TEXT;
    rid BIGINT;
    replacement UUID := gen_random_uuid();
    event UUID := gen_random_uuid();
    outcome JSONB;
BEGIN
    IF NULLIF(btrim(p_key), '') IS NULL OR length(p_key) > 128
       OR p_quantity IS NULL OR p_quantity < 1
       OR p_disposition IS DISTINCT FROM 'inspection_required' THEN
        RAISE EXCEPTION 'invalid_replacement_terms' USING ERRCODE = '22023';
    END IF;

    -- Scope before replay: possession of an operation key never grants access.
    SELECT * INTO o FROM pellier.orders
     WHERE id = p_order AND customer_id = p_customer AND product_id = p_product
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'replacement_order_out_of_scope' USING ERRCODE = '42501';
    END IF;

    -- Reuse the shared write ledger so existing keyed receipt reconstruction
    -- can find this operation. The reservation, result and outbox commit together.
    INSERT INTO pellier.write_operations (idempotency_key, operation, request_hash)
    VALUES (p_key, 'replace_damaged_item', p_hash)
    ON CONFLICT (idempotency_key) DO NOTHING;
    SELECT * INTO claim FROM pellier.write_operations WHERE idempotency_key = p_key FOR UPDATE;
    IF claim.operation IS DISTINCT FROM 'replace_damaged_item'
       OR claim.request_hash IS DISTINCT FROM p_hash THEN
        RAISE EXCEPTION 'replacement_idempotency_conflict' USING ERRCODE = '22023';
    END IF;

    -- Lock ordering agrees with checkout: catalog before warehouse. The catalog
    -- lock also serializes legacy product-scoped returns with this exact-line path.
    PERFORM 1 FROM pellier.product_catalog WHERE "productId" = p_product FOR UPDATE;
    a := pellier.lock_replacement_approval(p_review_id, p_customer);
    IF a.id IS NULL OR a.tool IS DISTINCT FROM 'replace_damaged_item'
       OR a.customer_id IS DISTINCT FROM p_customer OR a.order_id IS DISTINCT FROM p_order
       OR a.status IS DISTINCT FROM 'approved' OR a.decided_by IS NULL
       OR a.action_hash IS DISTINCT FROM p_hash
       OR a.args->>'customer_id' IS DISTINCT FROM p_customer
       OR a.args->>'product_id' IS DISTINCT FROM p_product
       OR a.args->>'order_id' IS DISTINCT FROM p_order::text
       OR a.args->>'quantity' IS DISTINCT FROM p_quantity::text
       OR a.args->>'reason' IS DISTINCT FROM 'damaged'
       OR a.args->>'disposition' IS DISTINCT FROM p_disposition THEN
        RAISE EXCEPTION 'replacement_approval_invalid' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO existing FROM pellier.replacements
     WHERE review_id = p_review_id OR idempotency_key = p_key;
    IF FOUND THEN
        IF existing.review_id <> p_review_id OR existing.request_hash <> p_hash
           OR existing.idempotency_key <> p_key THEN
            RAISE EXCEPTION 'replacement_idempotency_conflict' USING ERRCODE = '22023';
        END IF;
        RETURN existing.result || jsonb_build_object('idempotent_replay', true);
    END IF;
    IF claim.result IS NOT NULL THEN
        RAISE EXCEPTION 'replacement_result_inconsistent' USING ERRCODE = '23514';
    END IF;
    -- Expiry applies to first execution. An expired grant cannot hide a result
    -- which already committed and now needs reconciliation.
    IF a.decided_at IS NULL OR a.decided_at < now() - interval '24 hours' THEN
        RAISE EXCEPTION 'replacement_approval_expired' USING ERRCODE = '42501';
    END IF;

    SELECT COALESCE(sum(quantity), 0) INTO returned FROM pellier.returns
     WHERE customer_id = p_customer AND product_id = p_product
       AND status <> 'rejected' AND (order_id = p_order OR order_id IS NULL);
    -- Historical unbound returns are conservatively charged to this order.
    -- Resolve their provenance before granting another remedy.
    ordered := o.quantity;
    IF returned + p_quantity > ordered THEN
        RAISE EXCEPTION 'replacement_quantity_exceeds_order' USING ERRCODE = '23514';
    END IF;

    SELECT warehouse_id INTO warehouse FROM pellier.warehouse_inventory
     WHERE product_id = p_product AND quantity >= p_quantity
     ORDER BY quantity DESC, warehouse_id LIMIT 1 FOR UPDATE;
    IF warehouse IS NULL THEN
        RAISE EXCEPTION 'replacement_stock_changed' USING ERRCODE = '23514';
    END IF;
    PERFORM set_config('pellier.inventory_reason', 'reservation', true);
    PERFORM set_config('pellier.inventory_idempotency_key', p_key, true);
    UPDATE pellier.warehouse_inventory SET quantity = quantity - p_quantity, updated_at = now()
     WHERE warehouse_id = warehouse AND product_id = p_product AND quantity >= p_quantity;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'replacement_stock_changed' USING ERRCODE = '23514';
    END IF;
    UPDATE pellier.product_catalog
       SET quantity = (SELECT COALESCE(sum(quantity), 0) FROM pellier.warehouse_inventory
                        WHERE product_id = p_product), updated_at = now()
     WHERE "productId" = p_product;
    INSERT INTO pellier.returns (customer_id, product_id, order_id, quantity, reason)
    VALUES (p_customer, p_product, p_order, p_quantity, 'damaged') RETURNING id INTO rid;

    outcome := jsonb_build_object(
        'status', 'success', 'replacement_id', replacement, 'return_id', rid,
        'order_id', p_order, 'product_id', p_product, 'quantity', p_quantity,
        'warehouse_id', warehouse, 'disposition', p_disposition,
        'outbox_event_id', event, 'fulfillment_state', 'reserved',
        'idempotent_replay', false
    );
    INSERT INTO pellier.replacements
        (replacement_id, review_id, idempotency_key, request_hash, customer_id,
         order_id, product_id, return_id, warehouse_id, quantity, disposition, result)
    VALUES (replacement, p_review_id, p_key, p_hash, p_customer, p_order,
            p_product, rid, warehouse, p_quantity, p_disposition, outcome);
    INSERT INTO pellier.replacement_outbox (event_id, replacement_id) VALUES (event, replacement);
    INSERT INTO pellier.replacement_events (replacement_id, event_key, event_type, details)
    VALUES (replacement, 'reserved', 'reserved',
            jsonb_build_object('reviewId', p_review_id, 'quantity', p_quantity));
    UPDATE pellier.write_operations SET result = outcome, completed_at = now()
     WHERE idempotency_key = p_key;
    RETURN outcome;
END;
$$;
REVOKE ALL ON FUNCTION pellier.replace_damaged_item(bigint,text,text,text,bigint,text,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pellier.replace_damaged_item(bigint,text,text,text,bigint,text,integer,text) TO pellier_agent;

-- Durable simulator outcomes are separate from application assertions. This is
-- a workshop warehouse adapter, not evidence that a real carrier was contacted.
CREATE TABLE IF NOT EXISTS pellier.replacement_simulator_operations (
    operation_id UUID PRIMARY KEY REFERENCES pellier.replacements(replacement_id),
    status TEXT NOT NULL CHECK (status IN ('accepted', 'shipped')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
REVOKE ALL ON pellier.replacement_simulator_operations FROM PUBLIC, pellier_agent, pellier_query;
CREATE TABLE IF NOT EXISTS pellier.replacement_callbacks (
    replacement_id UUID PRIMARY KEY REFERENCES pellier.replacements(replacement_id),
    task_token TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
REVOKE ALL ON pellier.replacement_callbacks FROM PUBLIC, pellier_agent, pellier_query;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pellier_fulfillment') THEN
        CREATE ROLE pellier_fulfillment NOLOGIN NOINHERIT NOBYPASSRLS;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pellier_fulfillment'
               AND (rolsuper OR rolbypassrls)) THEN
        RAISE EXCEPTION 'Fulfillment role must not bypass RLS';
    END IF;
END $$;
GRANT pellier_fulfillment TO CURRENT_USER;
GRANT USAGE ON SCHEMA pellier TO pellier_fulfillment;
GRANT SELECT ON pellier.replacements, pellier.replacement_outbox,
    pellier.replacement_events, pellier.replacement_simulator_operations TO pellier_fulfillment;
GRANT UPDATE (status, provider_operation_id, workflow_execution_arn, updated_at)
    ON pellier.replacements TO pellier_fulfillment;
GRANT UPDATE ON pellier.replacement_outbox TO pellier_fulfillment;
GRANT INSERT ON pellier.replacement_events, pellier.replacement_simulator_operations TO pellier_fulfillment;
GRANT UPDATE (status) ON pellier.replacement_simulator_operations TO pellier_fulfillment;
GRANT SELECT, INSERT, UPDATE ON pellier.replacement_callbacks TO pellier_fulfillment;
GRANT USAGE, SELECT ON SEQUENCE pellier.replacement_events_event_id_seq TO pellier_fulfillment;
DROP POLICY IF EXISTS replacement_worker ON pellier.replacements;
CREATE POLICY replacement_worker ON pellier.replacements TO pellier_fulfillment USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS replacement_outbox_worker ON pellier.replacement_outbox;
CREATE POLICY replacement_outbox_worker ON pellier.replacement_outbox TO pellier_fulfillment USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS replacement_events_worker ON pellier.replacement_events;
CREATE POLICY replacement_events_worker ON pellier.replacement_events TO pellier_fulfillment USING (true) WITH CHECK (true);
COMMIT;
