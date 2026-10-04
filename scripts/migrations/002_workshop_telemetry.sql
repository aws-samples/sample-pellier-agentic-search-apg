-- =========================================================================
-- Migration 002 — workshop telemetry, audit, customers, and orders
-- =========================================================================
-- This migration is IDEMPOTENT — safe to re-run. It adds six tables that
-- back the workshop telemetry and audit routes. Every table
-- lives under the ``pellier`` schema so the workshop has one schema —
-- the "Aurora as agent system-of-record" anchor for Theo doesn't have
-- to span ``public`` and ``pellier``:
--
--   pellier.observatory_spans  — OTEL span persistence for trace replay.
--   pellier.tools              — pgvector-backed tool registry (Card 7).
--   pellier.tool_audit         — unified audit row per tool call (read + write).
--   pellier.customers          — demo customers for personalization + approvals.
--   pellier.orders             — demo orders; backs the headline 3-table JOIN panel.
--   pellier.approvals          — Identity-gated sensitive-tool gate (Card 10).
--
-- Runs after 001_schema.sql and scripts/seed_pellier_catalog.py. The
-- product_catalog table is this migration's FK target.
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/002_workshop_telemetry.sql
-- =========================================================================

\set ON_ERROR_STOP on

BEGIN;

-- pgvector is required for tools.description_emb and for the cohort-overlap
-- memory query that JOINs orders ⋈ product_catalog ⋈ customers on a
-- cosine similarity comparison. seed-database.sh already creates it; the
-- IF NOT EXISTS keeps this migration self-contained if run first.
CREATE EXTENSION IF NOT EXISTS vector;

-- The pellier schema is created by 001_schema.sql; restated here so this
-- migration is safe to apply against an older Aurora cluster that has
-- the public.* tables but not the schema.
CREATE SCHEMA IF NOT EXISTS pellier;

-- ---------------------------------------------------------------------
-- One-time relocation: move legacy public.* tables into pellier.*
--
-- Earlier deploys of this migration created the six tables at `public`.
-- We rename them in place rather than drop + recreate so existing rows
-- survive — ALTER TABLE ... SET SCHEMA preserves indexes, FKs,
-- triggers, and data. Mirrors the pattern in 006_warehouse_inventory.sql.
--
-- Order matters: relocate parents first (customers, product_catalog
-- already-in-pellier) so FK refs from orders/approvals/returns follow
-- cleanly.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'customers',
        'orders',
        'approvals',
        'tool_audit',
        -- Legacy name on purpose: this array names tables to relocate out
        -- of `public`, and an old cluster has `public.agent_trace_spans`.
        -- It lands in `pellier` here and is renamed to `observatory_spans`
        -- by the block further down, which runs after this one.
        'agent_trace_spans',
        'tools'
    ]
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = t
        ) AND NOT EXISTS (
            SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'pellier' AND table_name = t
        ) THEN
            EXECUTE format('ALTER TABLE public.%I SET SCHEMA pellier', t);
            RAISE NOTICE 'Moved public.% → pellier.%', t, t;
        END IF;
    END LOOP;
END $$;

-- -- pellier.observatory_spans -------------------------------------------
-- Renamed from `agent_trace_spans` when the inspection surface became the
-- Observatory. The ALTER runs first and is idempotent: on a cluster that
-- already has the old table it renames in place, and on a fresh cluster it
-- is a no-op that the CREATE below satisfies. Without it, a re-provisioned
-- box would carry both tables and the TTL job would expire only one.
DO $rename$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
         WHERE table_schema = 'pellier' AND table_name = 'agent_trace_spans'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.tables
         WHERE table_schema = 'pellier' AND table_name = 'observatory_spans'
    ) THEN
        ALTER TABLE pellier.agent_trace_spans RENAME TO observatory_spans;
        ALTER INDEX IF EXISTS pellier.agent_trace_spans_session_idx
            RENAME TO observatory_spans_session_idx;
        ALTER INDEX IF EXISTS pellier.agent_trace_spans_created_idx
            RENAME TO observatory_spans_created_idx;
        -- The primary key's implicit index carries the old table name too. A
        -- fresh cluster names it `observatory_spans_pkey` from the table, so
        -- without this a re-provisioned box and a new one disagree on one
        -- index name — the kind of drift that makes two clusters diff.
        ALTER INDEX IF EXISTS pellier.agent_trace_spans_pkey
            RENAME TO observatory_spans_pkey;
    END IF;
END
$rename$;

-- Reserved Aurora span cache. The shipped runtime exports managed telemetry to
-- CloudWatch/AgentCore and captures in-process spans in memory; it does not
-- currently INSERT those spans here. Keep the schema for compatibility and
-- bounded workshop experiments, but do not treat an empty table as missing
-- execution evidence. Canonical durable proof lives in the receipt tables and
-- migration 043's typed projection. The 24h pg_cron cleanup below protects any
-- future or experimental cache writer from unbounded growth.
CREATE TABLE IF NOT EXISTS pellier.observatory_spans (
    trace_id        UUID NOT NULL,
    span_id         UUID PRIMARY KEY,
    parent_span_id  UUID,
    span_name       TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    attributes      JSONB NOT NULL DEFAULT '{}'::jsonb,
    session_id      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS observatory_spans_session_idx
    ON pellier.observatory_spans (session_id, started_at);
CREATE INDEX IF NOT EXISTS observatory_spans_created_idx
    ON pellier.observatory_spans (created_at);

-- -- pellier.tools -------------------------------------------------------
-- Aurora-teaching tool registry. Sits next to GatewayToolsPanel on
-- /workshop so attendees see the same discovery concept implemented
-- both ways. description_emb is populated by the seeder (one row per
-- @tool the orchestrator registers, embedded via Cohere v4).
CREATE TABLE IF NOT EXISTS pellier.tools (
    tool_id            TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    description        TEXT NOT NULL,
    description_emb    vector(1024),
    schema             JSONB,
    enabled            BOOLEAN NOT NULL DEFAULT true,
    owner_agent        TEXT,
    requires_approval  BOOLEAN NOT NULL DEFAULT false,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tools_description_emb_idx
    ON pellier.tools USING hnsw (description_emb vector_cosine_ops);

-- -- pellier.tool_audit --------------------------------------------------
-- Unified execution log. One row means a tool actually ran. The
-- in-process Strands rail writes caller='agent' rows through
-- services/tool_audit_writer.py; the managed Gateway rail writes
-- caller='gateway' rows from the Lambda-backed tool target after Cedar
-- has already allowed the call. A Gateway/Cedar DENY leaves no
-- tool_audit row because the Lambda never executes. The ordinary
-- in-process rail is not a Cedar rail and must not be used as proof of
-- DENY absence.
--
-- Half the teaching story on the workshop is that
-- ``SELECT * FROM pellier.tool_audit WHERE session_id = ...``
-- rebuilds the entire turn for debugging — Act II: Exercise 2 — and
-- the same table feeds operational history's "which tool ran and how fast"
-- which intent" aggregate.
CREATE TABLE IF NOT EXISTS pellier.tool_audit (
    audit_id    BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    tool        TEXT NOT NULL,
    caller      TEXT NOT NULL,
    args        JSONB,
    result      JSONB,
    latency_ms  INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tool_audit_session_idx
    ON pellier.tool_audit (session_id, created_at);

-- -- pellier.customers ---------------------------------------------------
-- Demo customer shell. Kept minimal because the /workshop surface isn't
-- a real storefront — it just needs identifiable actors so the
-- the recommendation panel can show cohort overlap ("Marco bought
-- these 3 items your current pick is closest to").
CREATE TABLE IF NOT EXISTS pellier.customers (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    preferences_summary   TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -- pellier.orders ------------------------------------------------------
-- Demo order log. product_id is TEXT to match
-- pellier.product_catalog."productId" from 001_schema.sql.
-- ON DELETE CASCADE keeps the demo set self-consistent when a customer
-- is re-seeded by 003_persona_seed.sql.
CREATE TABLE IF NOT EXISTS pellier.orders (
    id           BIGSERIAL PRIMARY KEY,
    customer_id  TEXT NOT NULL
                 REFERENCES pellier.customers(id) ON DELETE CASCADE,
    -- product_catalog."productId" is TEXT in the Pellier catalog schema.
    -- Keep orders.product_id TEXT too so fresh-cluster bootstrap can
    -- create the FK without type coercion surprises.
    product_id   TEXT NOT NULL
                 REFERENCES pellier.product_catalog("productId")
                 ON DELETE CASCADE,
    quantity     INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    -- What the customer paid per unit, in minor units, fixed at purchase.
    -- Never derived from product_catalog.price, which changes.
    amount_paid_cents INTEGER NOT NULL CHECK (amount_paid_cents >= 0),
    currency     CHAR(3) NOT NULL DEFAULT 'USD',
    placed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS orders_customer_idx
    ON pellier.orders (customer_id, placed_at DESC);
CREATE INDEX IF NOT EXISTS orders_product_idx
    ON pellier.orders (product_id);

-- -- pellier.approvals ---------------------------------------------------
-- Identity-gated approvals queue for sensitive tools (place_order,
-- restock, etc.). Card 5 on /workshop shows pending rows; the
-- GUARDRAIL · APPROVAL panel fires when a tool call lands here
-- instead of executing inline. Status is a free-form TEXT rather than
-- an ENUM so future state-machine evolution doesn't need a migration.
CREATE TABLE IF NOT EXISTS pellier.approvals (
    id             BIGSERIAL PRIMARY KEY,
    customer_id    TEXT NOT NULL
                   REFERENCES pellier.customers(id) ON DELETE CASCADE,
    tool           TEXT NOT NULL,
    args           JSONB NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS approvals_status_idx
    ON pellier.approvals (status, requested_at);

-- -- pg_cron cleanup ----------------------------------------------------
-- 24h TTL on pellier.observatory_spans. pg_cron runs in the postgres
-- database on Aurora; we wrap the schedule call in a DO block so
-- missing-extension is a WARNING rather than a hard error (workshop
-- envs without the extension can still run this migration and opt
-- into manual cleanup).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        -- Pre-check rather than relying on EXCEPTION: different pg_cron
        -- versions raise different SQLSTATEs on re-registration
        -- (duplicate_object 42710 vs unique_violation 23505), and an
        -- uncaught exception inside a DO block aborts the whole
        -- migration under ON_ERROR_STOP. Pre-checking avoids the
        -- guessing game entirely. The COALESCE handles the case where
        -- the cron schema/table doesn't exist yet.
        IF NOT EXISTS (
            SELECT 1 FROM cron.job WHERE jobname = 'cleanup_trace_spans'
        ) THEN
            PERFORM cron.schedule(
                'cleanup_trace_spans',
                '0 * * * *',
                $cleanup$DELETE FROM pellier.observatory_spans
                         WHERE created_at < now() - interval '24 hours'$cleanup$
            );
            RAISE NOTICE 'pg_cron job cleanup_trace_spans scheduled';
        ELSE
            RAISE NOTICE 'pg_cron job cleanup_trace_spans already scheduled';
        END IF;
    ELSE
        RAISE WARNING
            'pg_cron extension not installed — the reserved pellier.observatory_spans '
            'cache has no automatic retention if an experimental writer is enabled. '
            'Install with: CREATE EXTENSION pg_cron;';
    END IF;
EXCEPTION
    -- Belt-and-suspenders: if some future pg_cron version raises on
    -- the schedule call despite the pre-check (e.g. concurrent
    -- registration), swallow the duplicate-style SQLSTATEs rather than
    -- aborting the migration. Anything else still propagates.
    WHEN unique_violation OR duplicate_object THEN
        RAISE NOTICE 'pg_cron job cleanup_trace_spans already scheduled (caught %)',
            SQLSTATE;
END $$;

COMMIT;

\echo '✅ Migration 002 complete — pellier.{observatory_spans, tools, tool_audit, customers, orders, approvals} ready'
