-- Migration 005: Returns table for Theo's write-path teaching
--
-- Theo anchors the third Aurora capability on the workshop's learning
-- ladder: Aurora as agent system-of-record. Marco reads (pgvector
-- semantic search). Anna reads harder (hybrid + rerank). Theo *writes*.
--
-- The teaching shape:
--
--   1. An agent (Experience Guide on Opus 4.6 at 0.2) calls a @tool
--      that mutates Aurora — process_return.
--   2. Cedar gates the call BEFORE it executes (BeforeToolCallEvent).
--      Bad reason → DENY → no row written.
--   3. SQL gates ownership inside the transaction. Customer doesn't
--      own the product → reject before INSERT.
--   4. INSERT into returns + (if reason='damaged') UPDATE quantity in
--      product_catalog. Both in one transaction.
--   5. AfterToolCallEvent persists the call to tool_audit so the
--      mutation has a paper trail readable from /atelier — every
--      mutation is reconstructible from a single SELECT.
--
-- This table is the second source of truth in the workshop. The first
-- (product_catalog) is the read-side index for Anna's retrieval pipeline.
-- The second (returns) is the write-side ledger for Theo's lifecycle.
-- Together they teach why Aurora — not a vector store, not a key-value
-- cache, not Bedrock memory — is the right home for an agentic system's
-- transactional state.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.
-- Run: psql $DATABASE_URL -f scripts/migrations/005_theo_returns.sql

\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS returns (
    id            BIGSERIAL PRIMARY KEY,
    customer_id   TEXT NOT NULL
                  REFERENCES customers(id) ON DELETE CASCADE,
    -- product_catalog."productId" is TEXT in the boutique schema.
    -- Match it here so the FK applies cleanly on fresh Builder clusters.
    product_id    TEXT NOT NULL
                  REFERENCES pellier.product_catalog("productId")
                  ON DELETE CASCADE,
    -- Reasons drive both Cedar policy enforcement and the workflow
    -- branch (only 'damaged' decrements quantity). Constrained at the
    -- DB level so a misbehaving agent can't write a free-form reason
    -- that bypasses our intended state machine.
    reason        TEXT NOT NULL CHECK (reason IN
                  ('damaged','wrong_size','not_as_described','changed_mind','other')),
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN
                  ('pending','approved','rejected','refunded')),
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at   TIMESTAMPTZ
);

-- Index for "show me a customer's recent returns" lookups (Atelier's
-- session brief tab joins this when rendering Theo's ceramics-return
-- folio).
CREATE INDEX IF NOT EXISTS returns_customer_idx
    ON returns (customer_id, requested_at DESC);

-- Index for "how many returns has product X had" — feeds future
-- inventory-quality dashboards. Cheap on 40 products today, future-
-- proof on 40 million.
CREATE INDEX IF NOT EXISTS returns_product_idx
    ON returns (product_id);

-- Quick summary so the operator can confirm the table is reachable.
DO $$
DECLARE
    has_table BOOL;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
         WHERE table_name = 'returns'
    ) INTO has_table;
    IF has_table THEN
        RAISE NOTICE 'returns table ready for process_return writes';
    ELSE
        RAISE NOTICE 'returns table creation appears to have failed';
    END IF;
END $$;

COMMIT;
