-- Migration 010: governed invocation receipts and seeded forensic incident
--
-- The execution ledger stays in pellier.tool_audit: one row means a tool
-- actually ran. This migration adds a separate governed receipt table for
-- identity and policy evidence that belongs to the Gateway/Cedar rail.
--
-- Why a second table:
--   * tool_audit answers "what executed?"
--   * governed_receipts answers "which authenticated principal was allowed
--     to invoke it, on which rail, with which policy decision?"
--
-- The seeded incident is intentionally deterministic. It lets the two-hour
-- governed lab ask participants to reconstruct a disputed return without
-- depending on a live JWT decode landing inside the Lambda event.

\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS pellier.governed_receipts (
    receipt_id       BIGSERIAL PRIMARY KEY,
    audit_id         BIGINT REFERENCES pellier.tool_audit(audit_id)
                     ON DELETE SET NULL,
    session_id       TEXT NOT NULL,
    principal_id     TEXT NOT NULL,
    principal_label  TEXT NOT NULL,
    tool             TEXT NOT NULL,
    caller           TEXT NOT NULL CHECK (caller IN ('gateway', 'runtime')),
    decision         TEXT NOT NULL CHECK (decision IN ('ALLOW', 'DENY')),
    args             JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_engine_id TEXT,
    policy_name      TEXT,
    token_fingerprint_sha256 TEXT,
    verified_subject TEXT,
    verified_username TEXT,
    issuer           TEXT,
    client_id        TEXT,
    identity_source  TEXT NOT NULL DEFAULT 'legacy'
                     CHECK (identity_source IN ('cognito', 'seeded', 'legacy')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE pellier.governed_receipts
    ADD COLUMN IF NOT EXISTS token_fingerprint_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS verified_subject TEXT,
    ADD COLUMN IF NOT EXISTS verified_username TEXT,
    ADD COLUMN IF NOT EXISTS issuer TEXT,
    ADD COLUMN IF NOT EXISTS client_id TEXT,
    ADD COLUMN IF NOT EXISTS identity_source TEXT NOT NULL DEFAULT 'legacy';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'pellier.governed_receipts'::regclass
           AND conname = 'governed_receipts_identity_source_check'
    ) THEN
        ALTER TABLE pellier.governed_receipts
            ADD CONSTRAINT governed_receipts_identity_source_check
            CHECK (identity_source IN ('cognito', 'seeded', 'legacy'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS governed_receipts_session_idx
    ON pellier.governed_receipts (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS governed_receipts_principal_idx
    ON pellier.governed_receipts (principal_id, created_at DESC);
CREATE INDEX IF NOT EXISTS governed_receipts_tool_idx
    ON pellier.governed_receipts (tool, caller, decision, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS governed_receipts_seed_incident_uidx
    ON pellier.governed_receipts (session_id, tool, principal_id)
    WHERE session_id = 'gateway-marco-for-theo-incident';

-- Seed the disputed action:
--   principal_id     = CUST-MARCO  (who was allowed to call)
--   args.customer_id = theo        (who the return was for)
--   caller           = gateway     (Cedar evaluated before execution)
--
-- Product is looked up by name so the seed survives product id reshuffles.
WITH product AS (
    SELECT "productId" AS product_id
      FROM pellier.product_catalog
     WHERE name = 'Wabi-Sabi Bowl'
     LIMIT 1
),
seed_return AS (
    INSERT INTO pellier.returns (customer_id, product_id, reason, status, requested_at)
    SELECT 'theo', product_id, 'damaged', 'approved', TIMESTAMPTZ '2026-07-01 09:15:00+00'
      FROM product
     WHERE NOT EXISTS (
        SELECT 1
          FROM pellier.returns r
         WHERE r.customer_id = 'theo'
           AND r.product_id = product.product_id
           AND r.reason = 'damaged'
           AND r.requested_at = TIMESTAMPTZ '2026-07-01 09:15:00+00'
     )
    RETURNING id
),
incident_return AS (
    SELECT id FROM seed_return
    UNION ALL
    SELECT r.id
      FROM pellier.returns r
      JOIN product p ON p.product_id = r.product_id
     WHERE r.customer_id = 'theo'
       AND r.reason = 'damaged'
       AND r.requested_at = TIMESTAMPTZ '2026-07-01 09:15:00+00'
     LIMIT 1
),
seed_audit AS (
    INSERT INTO pellier.tool_audit
        (session_id, tool, caller, args, result, latency_ms, created_at)
    SELECT
        'gateway-marco-for-theo-incident',
        'process_return',
        'gateway',
        jsonb_build_object(
            'customer_id', 'theo',
            'product_id', (SELECT product_id FROM product),
            'reason', 'damaged'
        ),
        jsonb_build_object(
            'status', 'success',
            'return_id', (SELECT id FROM incident_return),
            'product_id', (SELECT product_id FROM product),
            'reason', 'damaged',
            'seeded_incident', true
        ),
        184,
        TIMESTAMPTZ '2026-07-01 09:15:02+00'
      FROM product
     WHERE NOT EXISTS (
        SELECT 1
          FROM pellier.tool_audit
         WHERE session_id = 'gateway-marco-for-theo-incident'
           AND tool = 'process_return'
           AND caller = 'gateway'
     )
    RETURNING audit_id
),
incident_audit AS (
    SELECT audit_id FROM seed_audit
    UNION ALL
    SELECT audit_id
      FROM pellier.tool_audit
     WHERE session_id = 'gateway-marco-for-theo-incident'
       AND tool = 'process_return'
       AND caller = 'gateway'
     ORDER BY audit_id
     LIMIT 1
)
INSERT INTO pellier.governed_receipts
    (audit_id, session_id, principal_id, principal_label, tool, caller,
     decision, args, policy_engine_id, policy_name, verified_subject,
     verified_username, issuer, client_id, identity_source, created_at)
SELECT
    (SELECT audit_id FROM incident_audit),
    'gateway-marco-for-theo-incident',
    'CUST-MARCO',
    'Marco (Cognito JWT)',
    'process_return',
    'gateway',
    'ALLOW',
    jsonb_build_object(
        'customer_id', 'theo',
        'product_id', (SELECT product_id FROM product),
        'reason', 'damaged'
    ),
    'seeded-workshop-policy-engine',
    'process_return_damaged_only',
    'seeded:CUST-MARCO',
    'seeded:marco',
    'seeded:workshop',
    'seeded:workshop',
    'seeded',
    TIMESTAMPTZ '2026-07-01 09:15:02+00'
  FROM product
 WHERE NOT EXISTS (
    SELECT 1
      FROM pellier.governed_receipts
     WHERE session_id = 'gateway-marco-for-theo-incident'
       AND tool = 'process_return'
       AND principal_id = 'CUST-MARCO'
 );

DO $$
DECLARE
    n_receipts INTEGER;
BEGIN
    SELECT count(*) INTO n_receipts
      FROM pellier.governed_receipts
     WHERE session_id = 'gateway-marco-for-theo-incident';

    IF n_receipts <> 1 THEN
        RAISE EXCEPTION
            'Governed forensic seed expected 1 receipt, got %. Check product seed and Theo orders.',
            n_receipts;
    END IF;

    RAISE NOTICE 'Governed receipts ready (% seeded forensic incident)', n_receipts;
END $$;

COMMIT;
