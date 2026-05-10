-- Migration 012: Drop duplicate HNSW index on public.tools.description_emb
--
-- The audit (audit_full_schema.sql) revealed two HNSW indexes on the
-- same column:
--   * tools_description_emb_idx        (older, defined in mig 001)
--   * tools_emb_hnsw_idx               (newer, defined later — not in
--                                       a tracked migration file)
--
-- Same column, same index method, same operator class. The duplicate
-- doubles index storage + write cost on every UPSERT to tools.
-- Drop the older one (tools_description_emb_idx); keep the WITH-options
-- variant tools_emb_hnsw_idx (m=16, ef_construction=64) as the
-- canonical index because its parameters are explicit.
--
-- Idempotent: IF EXISTS guard.
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/012_drop_duplicate_hnsw_index.sql

\set ON_ERROR_STOP on

BEGIN;

DROP INDEX IF EXISTS public.tools_description_emb_idx;

DO $$
DECLARE
    n INTEGER;
BEGIN
    SELECT COUNT(*) INTO n
      FROM pg_indexes
     WHERE schemaname = 'public'
       AND tablename = 'tools'
       AND indexdef ILIKE '%description_emb%';
    RAISE NOTICE 'public.tools now has % HNSW index(es) on description_emb (expected 1)', n;
END $$;

COMMIT;
