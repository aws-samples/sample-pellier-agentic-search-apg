\set ON_ERROR_STOP on

-- Migration 008: Search-performance indexes for ILIKE-heavy tool paths
--
-- Why:
--   - floor_check resolves product names with tokenized ILIKE clauses.
--   - price/category lookups use category ILIKE in a few reporting paths.
--   - At workshop scale this is tiny, but at production catalog scale
--     trigram indexes prevent sequential scans for fuzzy string lookups.
--
-- Safe to re-run: extension/index creation is idempotent.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS product_catalog_name_trgm_idx
    ON pellier.product_catalog
    USING gin (lower(name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS product_catalog_category_trgm_idx
    ON pellier.product_catalog
    USING gin (lower(category) gin_trgm_ops);

COMMIT;
