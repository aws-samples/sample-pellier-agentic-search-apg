-- =========================================================================
-- Migration 001 — /workshop telemetry surface (DAT406 Week 1)
-- =========================================================================
-- This migration is IDEMPOTENT — safe to re-run. It adds six tables that
-- back the PostgresConf Builders Session /workshop route:
--
--   agent_trace_spans  — OTEL span persistence for trace replay (Card 9).
--   tools              — pgvector-backed tool registry (Card 7, teaching).
--   tool_audit         — unified audit row per LLM / SQL tool call.
--   customers          — demo customers for MEMORY · PROCEDURAL + approvals.
--   orders             — demo orders; backs the headline 3-table JOIN panel.
--   approvals          — Identity-gated sensitive-tool gate (Card 10).
--
-- Runs after scripts/seed-database.sh. The product_catalog table from that
-- script is this migration's FK target; re-running seed-database.sh after
-- this migration leaves these tables intact (both the seed and the
-- migration use IF NOT EXISTS / ON CONFLICT semantics for the bulk of
-- their DDL, and the orders FK cascades on product delete).
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/001_workshop_telemetry.sql
-- =========================================================================

\set ON_ERROR_STOP on

BEGIN;

-- pgvector is required for tools.description_emb and for the procedural
-- memory query that JOINs orders ⋈ product_catalog ⋈ customers on a
-- cosine similarity comparison. seed-database.sh already creates it; the
-- IF NOT EXISTS keeps this migration self-contained if run first.
CREATE EXTENSION IF NOT EXISTS vector;

-- -- agent_trace_spans ----------------------------------------------------
-- OTEL span persistence. Populated by the Strands OTLP exporter (Week 5+)
-- when we ship a custom SpanProcessor that INSERTs alongside the
-- InMemorySpanExporter path. The 24h pg_cron cleanup at the bottom of
-- this file expires old rows so the table doesn't grow unbounded between
-- workshop runs.
CREATE TABLE IF NOT EXISTS agent_trace_spans (
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
    ON agent_trace_spans (session_id, started_at);
CREATE INDEX IF NOT EXISTS agent_trace_spans_created_idx
    ON agent_trace_spans (created_at);

-- -- tools ---------------------------------------------------------------
-- Aurora-teaching tool registry. Sits next to GatewayToolsPanel on
-- /workshop so attendees see the same discovery concept implemented
-- both ways. description_emb is populated by the Week 2 seeder (one
-- row per @tool the orchestrator registers, embedded via Cohere v4).
CREATE TABLE IF NOT EXISTS tools (
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
    ON tools USING hnsw (description_emb vector_cosine_ops);

-- -- tool_audit ----------------------------------------------------------
-- Unified audit log. One row per tool invocation, whether it's a SQL
-- tool call or an LLM call (``tool = 'llm:claude-haiku-4-5'`` vs
-- ``tool = 'sql:check_inventory'``). Half the teaching story on the
-- workshop is that ``SELECT * FROM tool_audit WHERE session_id = ...``
-- rebuilds the entire turn for debugging.
CREATE TABLE IF NOT EXISTS tool_audit (
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
    ON tool_audit (session_id, created_at);

-- -- customers ----------------------------------------------------------
-- Demo customer shell. Kept minimal because the /workshop surface isn't
-- a real storefront — it just needs identifiable actors so the
-- MEMORY · PROCEDURAL panel can show cohort overlap ("Marco bought
-- these 3 items your current pick is closest to").
CREATE TABLE IF NOT EXISTS customers (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    preferences_summary   TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -- orders -------------------------------------------------------------
-- Demo order log. product_id is CHAR(10) to match
-- pellier.product_catalog."productId" — see live schema (audit_full_schema.sql).
-- Note: a previous version of this comment claimed CHAR(10) PK with
-- category-prefixed ids (PSPRT0044). The live boutique catalog actually
-- uses INTEGER ids 1..40. Migration 014 adds the FK; the column types
-- match (INTEGER on both sides).
--
-- ON DELETE CASCADE keeps the demo set self-consistent when a customer
-- is re-seeded (dev workflow: rewind + re-run the seed script).
CREATE TABLE IF NOT EXISTS orders (
    id           BIGSERIAL PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    product_id   CHAR(10) NOT NULL
                 REFERENCES pellier.product_catalog("productId")
                 ON DELETE CASCADE,
    quantity     INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    placed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS orders_customer_idx
    ON orders (customer_id, placed_at DESC);
CREATE INDEX IF NOT EXISTS orders_product_idx
    ON orders (product_id);

-- -- approvals ----------------------------------------------------------
-- Identity-gated approvals queue for sensitive tools (place_order,
-- restock, etc.). Card 5 on /workshop shows pending rows; the
-- GUARDRAIL · APPROVAL panel fires when a tool call lands here
-- instead of executing inline. Status is a free-form TEXT rather than
-- an ENUM so Week 6 can evolve the state machine without a migration.
CREATE TABLE IF NOT EXISTS approvals (
    id             BIGSERIAL PRIMARY KEY,
    customer_id    TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    tool           TEXT NOT NULL,
    args           JSONB NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS approvals_status_idx
    ON approvals (status, requested_at);

-- -- pg_cron cleanup ---------------------------------------------------
-- 24h TTL on agent_trace_spans. pg_cron runs in the postgres database
-- on Aurora; we wrap the schedule call in a DO block so missing-extension
-- is a WARNING rather than a hard error (workshop envs without the
-- extension can still run this migration and opt into manual cleanup).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule(
            'cleanup_trace_spans',
            '0 * * * *',
            $cleanup$DELETE FROM agent_trace_spans
                     WHERE created_at < now() - interval '24 hours'$cleanup$
        );
        RAISE NOTICE 'pg_cron job cleanup_trace_spans scheduled';
    ELSE
        RAISE WARNING
            'pg_cron extension not installed — agent_trace_spans will grow unbounded. '
            'Install with: CREATE EXTENSION pg_cron;';
    END IF;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'pg_cron job cleanup_trace_spans already scheduled';
END $$;

COMMIT;

\echo '✅ Migration 001 complete — 6 workshop telemetry tables created'
