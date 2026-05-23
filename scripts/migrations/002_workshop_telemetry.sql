-- =========================================================================
-- Migration 002 — workshop telemetry, audit, customers, and orders
-- =========================================================================
-- This migration is IDEMPOTENT — safe to re-run. It adds six tables that
-- back the PostgresConf Builders Session /workshop route. Every table
-- lives under the ``pellier`` schema so the workshop has one schema —
-- the "Aurora as agent system-of-record" anchor for Theo doesn't have
-- to span ``public`` and ``pellier``:
--
--   pellier.agent_trace_spans  — OTEL span persistence for trace replay.
--   pellier.tools              — pgvector-backed tool registry (Card 7).
--   pellier.tool_audit         — unified audit row per mutating tool call.
--   pellier.customers          — demo customers for MEMORY · PROCEDURAL + approvals.
--   pellier.orders             — demo orders; backs the headline 3-table JOIN panel.
--   pellier.approvals          — Identity-gated sensitive-tool gate (Card 10).
--
-- Runs after 001_schema.sql and scripts/seed_boutique_catalog.py. The
-- product_catalog table is this migration's FK target.
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/002_workshop_telemetry.sql
-- =========================================================================

\set ON_ERROR_STOP on

BEGIN;

-- pgvector is required for tools.description_emb and for the procedural
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

-- -- pellier.agent_trace_spans -------------------------------------------
-- OTEL span persistence. Populated by the Strands OTLP exporter when we
-- ship a custom SpanProcessor that INSERTs alongside the
-- InMemorySpanExporter path. The 24h pg_cron cleanup at the bottom of
-- this file expires old rows so the table doesn't grow unbounded between
-- workshop runs.
CREATE TABLE IF NOT EXISTS pellier.agent_trace_spans (
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
CREATE INDEX IF NOT EXISTS agent_trace_spans_session_idx
    ON pellier.agent_trace_spans (session_id, started_at);
CREATE INDEX IF NOT EXISTS agent_trace_spans_created_idx
    ON pellier.agent_trace_spans (created_at);

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
-- Unified audit log. One row per mutating tool invocation
-- (``_MUTATING_TOOLS = {restock_shelf, process_return}`` in
-- services/policy_hook.py). Half the teaching story on the workshop is
-- that ``SELECT * FROM pellier.tool_audit WHERE session_id = ...``
-- rebuilds the entire turn for debugging — Act II · Exercise 2.
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
-- MEMORY · PROCEDURAL panel can show cohort overlap ("Marco bought
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
    -- product_catalog."productId" is TEXT in the boutique schema.
    -- Keep orders.product_id TEXT too so fresh-cluster bootstrap can
    -- create the FK without type coercion surprises.
    product_id   TEXT NOT NULL
                 REFERENCES pellier.product_catalog("productId")
                 ON DELETE CASCADE,
    quantity     INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
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
-- 24h TTL on pellier.agent_trace_spans. pg_cron runs in the postgres
-- database on Aurora; we wrap the schedule call in a DO block so
-- missing-extension is a WARNING rather than a hard error (workshop
-- envs without the extension can still run this migration and opt
-- into manual cleanup).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule(
            'cleanup_trace_spans',
            '0 * * * *',
            $cleanup$DELETE FROM pellier.agent_trace_spans
                     WHERE created_at < now() - interval '24 hours'$cleanup$
        );
        RAISE NOTICE 'pg_cron job cleanup_trace_spans scheduled';
    ELSE
        RAISE WARNING
            'pg_cron extension not installed — pellier.agent_trace_spans will grow unbounded. '
            'Install with: CREATE EXTENSION pg_cron;';
    END IF;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'pg_cron job cleanup_trace_spans already scheduled';
END $$;

COMMIT;

\echo '✅ Migration 002 complete — pellier.{agent_trace_spans, tools, tool_audit, customers, orders, approvals} ready'
