-- Migration 015: Schema migrations tracking table
--
-- Adds public.schema_migrations to track which migrations have been
-- applied to a given Aurora cluster. Eliminates the "is mig 008
-- applied yet?" guesswork.
--
-- Each migration that ships from now on should end with:
--   INSERT INTO public.schema_migrations (version, applied_at) VALUES ('NNN', now())
--   ON CONFLICT (version) DO NOTHING;
--
-- This file back-fills entries for all 001-015 migrations so a fresh
-- read of schema_migrations gives a complete history.
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/015_schema_migrations_tracking.sql

\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Back-fill: declare every migration that's been applied to date as
-- "already applied" without re-running them. INSERT ... ON CONFLICT
-- DO NOTHING is idempotent — subsequent runs are no-ops.
INSERT INTO public.schema_migrations (version, name, applied_at) VALUES
    ('001', 'workshop_telemetry', now()),
    ('002', 'workshop_seed', now()),
    ('003', 'workshop_episodic_seed', now()),
    ('004', 'add_quantity', now()),
    ('005', 'anna_tsvector', now()),
    ('006', 'theo_returns', now()),
    ('007', 'theo_orders_seed', now()),
    ('008', 'warehouse_inventory', now()),
    ('009', 'rename_schema_to_pellier', now()),
    ('010', 'rename_brand_strings_in_catalog', now()),
    ('011', 'refresh_embeddings', now()),
    ('012', 'drop_duplicate_hnsw_index', now()),
    ('013', 'chat_session_tables', now()),
    ('014', 'add_product_catalog_fks', now()),
    ('015', 'schema_migrations_tracking', now())
ON CONFLICT (version) DO NOTHING;

DO $$
DECLARE
    n INTEGER;
BEGIN
    SELECT COUNT(*) INTO n FROM public.schema_migrations;
    RAISE NOTICE 'public.schema_migrations now tracks % entries', n;
END $$;

COMMIT;
