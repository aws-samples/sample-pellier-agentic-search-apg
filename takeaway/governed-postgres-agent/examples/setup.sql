-- Run once, as an administrator, in an EMPTY DISPOSABLE PostgreSQL database.
-- Creates cluster-wide roles named review_writer and review_support.
-- No network calls, credentials, production data or extensions are required.
-- A name collision stops setup; this file never drops an existing object.
\set ON_ERROR_STOP on
BEGIN;
CREATE SCHEMA review_example;
REVOKE ALL ON SCHEMA review_example FROM PUBLIC;
CREATE ROLE review_writer NOLOGIN NOSUPERUSER NOBYPASSRLS;
CREATE ROLE review_support NOLOGIN NOSUPERUSER NOBYPASSRLS;
GRANT review_writer, review_support TO CURRENT_USER;
GRANT USAGE ON SCHEMA review_example TO review_writer, review_support;

CREATE TABLE review_example.catalog (
    product_id text PRIMARY KEY,
    price numeric NOT NULL,
    quantity integer NOT NULL,
    category text NOT NULL
);
INSERT INTO review_example.catalog VALUES
    ('mug', 25, 8, 'ceramics'), ('candle', 150, 0, 'candles');
CREATE TABLE review_example.search_requests (
    request_id text PRIMARY KEY,
    original_constraints jsonb NOT NULL
);
CREATE TABLE review_example.retrieval_receipts (
    receipt_id text PRIMARY KEY,
    request_id text NOT NULL UNIQUE REFERENCES review_example.search_requests,
    final_plan jsonb NOT NULL,
    returned_product_ids text[] NOT NULL
);
INSERT INTO review_example.search_requests VALUES
    ('search-1', '{"max_price":100,"in_stock_only":true,"exclude":["candles"]}');
INSERT INTO review_example.retrieval_receipts VALUES
    ('receipt-1', 'search-1', '{"max_price":100,"in_stock_only":true,"exclude":["candles"]}', ARRAY['mug']);

CREATE TABLE review_example.expected_stock (
    case_id text PRIMARY KEY, result jsonb NOT NULL
);
CREATE TABLE review_example.stock_receipts (
    case_id text PRIMARY KEY, result jsonb NOT NULL
);
INSERT INTO review_example.expected_stock VALUES
    ('stock-1', '{"status":"success","warehouses":[{"name":"Brooklyn","quantity":0},{"name":"Austin","quantity":6}]}'),
    ('missing-1', '{"status":"not_found"}');
INSERT INTO review_example.stock_receipts SELECT * FROM review_example.expected_stock;

CREATE TABLE review_example.tickets (
    ticket_id text PRIMARY KEY, customer_id text NOT NULL, subject text NOT NULL
);
INSERT INTO review_example.tickets VALUES
    ('ticket-a', 'customer-a', 'My delivery'), ('ticket-b', 'customer-b', 'My return');
ALTER TABLE review_example.tickets ENABLE ROW LEVEL SECURITY;
CREATE POLICY ticket_owner ON review_example.tickets TO review_support
    USING (customer_id = nullif(current_setting('review_example.customer_id', true), ''))
    WITH CHECK (customer_id = nullif(current_setting('review_example.customer_id', true), ''));
GRANT SELECT, INSERT ON review_example.tickets TO review_support;

CREATE TABLE review_example.expenses (
    expense_id text PRIMARY KEY, customer_id text NOT NULL
);
CREATE TABLE review_example.approvals (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    expense_id text NOT NULL REFERENCES review_example.expenses,
    customer_id text NOT NULL,
    args jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'approved', 'declined')),
    approved_by text
);
CREATE TABLE review_example.credits (
    credit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    approval_id bigint NOT NULL UNIQUE REFERENCES review_example.approvals,
    expense_id text NOT NULL UNIQUE REFERENCES review_example.expenses,
    customer_id text NOT NULL,
    amount_cents integer NOT NULL CHECK (amount_cents BETWEEN 1 AND 50000),
    reason text NOT NULL,
    write_key text NOT NULL UNIQUE
);
CREATE TABLE review_example.write_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    credit_id bigint NOT NULL UNIQUE REFERENCES review_example.credits,
    write_key text NOT NULL UNIQUE,
    database_login name NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- The administrator represents a separate trusted approval service.
-- Neither application role can create or edit approvals.
INSERT INTO review_example.expenses VALUES
    ('expense-1', 'customer-a'), ('expense-2', 'customer-a');
INSERT INTO review_example.approvals (expense_id, customer_id, args, status, approved_by) VALUES
    ('expense-1', 'customer-a', '{"customer_id":"customer-a","amount_cents":2500,"reason":"travel"}', 'approved', 'reviewer'),
    ('expense-1', 'customer-a', '{"customer_id":"customer-a","amount_cents":2500,"reason":"travel"}', 'approved', 'reviewer'),
    ('expense-2', 'customer-a', '{"customer_id":"customer-a","amount_cents":2500,"reason":"travel"}', 'pending', NULL);

CREATE FUNCTION review_example.apply_credit(
    p_key text, p_customer text, p_cents integer, p_reason text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_review review_example.approvals%ROWTYPE;
    v_existing review_example.credits%ROWTYPE;
    v_customer text;
    v_id bigint;
BEGIN
    -- Lock the particular approval, not every review for this customer.
    SELECT * INTO v_review FROM review_example.approvals
     WHERE p_key = 'approval:' || id::text FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'approval_required');
    END IF;

    SELECT * INTO v_existing FROM review_example.credits WHERE write_key = p_key;
    IF FOUND THEN
        IF (v_existing.customer_id, v_existing.amount_cents, v_existing.reason)
           IS DISTINCT FROM (p_customer, p_cents, p_reason) THEN
            RETURN jsonb_build_object('status', 'idempotency_conflict');
        END IF;
        RETURN jsonb_build_object('status', 'success', 'replayed', true,
                                  'credit_id', v_existing.credit_id);
    END IF;

    IF v_review.status <> 'approved' OR nullif(v_review.approved_by, '') IS NULL
       OR v_review.customer_id IS DISTINCT FROM p_customer
       OR v_review.args IS DISTINCT FROM jsonb_build_object(
           'customer_id', p_customer, 'amount_cents', p_cents, 'reason', p_reason) THEN
        RETURN jsonb_build_object('status', 'approval_required');
    END IF;
    IF p_cents IS NULL OR p_cents NOT BETWEEN 1 AND 50000 OR p_reason IS NULL THEN
        RETURN jsonb_build_object('status', 'invalid_terms');
    END IF;

    SELECT customer_id INTO v_customer FROM review_example.expenses
     WHERE expense_id = v_review.expense_id FOR UPDATE;
    IF NOT FOUND OR v_customer IS DISTINCT FROM p_customer THEN
        RETURN jsonb_build_object('status', 'invalid_expense');
    END IF;
    IF EXISTS (SELECT 1 FROM review_example.credits WHERE expense_id = v_review.expense_id) THEN
        RETURN jsonb_build_object('status', 'already_paid');
    END IF;

    INSERT INTO review_example.credits
        (approval_id, expense_id, customer_id, amount_cents, reason, write_key)
    VALUES (v_review.id, v_review.expense_id, p_customer, p_cents, p_reason, p_key)
    RETURNING credit_id INTO v_id;
    INSERT INTO review_example.write_audit (credit_id, write_key, database_login)
    VALUES (v_id, p_key, session_user);
    RETURN jsonb_build_object('status', 'success', 'replayed', false, 'credit_id', v_id);
END;
$$;
REVOKE ALL ON FUNCTION review_example.apply_credit(text, text, integer, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION review_example.apply_credit(text, text, integer, text) TO review_writer;
-- No table or sequence privileges are granted to review_writer.
COMMIT;
