-- Pellier Builder's Session — schema bootstrap (runs FIRST).
--
-- pellier-database.yml provisions an empty Aurora cluster. This
-- migration is the bridge between "empty cluster" and "schema ready
-- for seed_boutique_catalog.py to INSERT rows."
--
-- What it creates:
--
--   1. pgvector extension (Cohere Embed v4 → 1024-dim vectors)
--   2. pellier schema
--   3. pellier.product_catalog table (boutique source of truth)
--   4. HNSW index on the embedding column for sub-millisecond
--      cosine-similarity search
--   5. updated_at trigger for soft tracking
--
-- Idempotent: every statement uses IF NOT EXISTS / OR REPLACE. Safe
-- to re-run during dev iteration; second run on a populated table is
-- a no-op.
--
-- Dimension note: 1024 matches Cohere Embed v4. If we ever swap
-- embedding models, update vector(1024) AND drop+rebuild the HNSW
-- index — pgvector cannot reshape an existing index in place.
--
-- Numbered 000 so bootstrap-labs.sh applies it before any other
-- migration. Migrations 001-017 in this directory are workshop-
-- format teaching artifacts (telemetry, episodic seed, etc.) and
-- the 60-min Builder's Session does NOT run them — only this
-- 000_pellier_schema.sql + the seed_boutique_catalog.py loader.
--
-- Apply with:
--   PGPASSWORD="$DB_PASSWORD" psql \
--     -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
--     -v ON_ERROR_STOP=1 \
--     -f scripts/migrations/000_pellier_schema.sql

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------
-- 1. Extension
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------
-- 2. Schema
-- ---------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS pellier;

-- ---------------------------------------------------------------------
-- 3. Product catalog
--
-- Column set matches scripts/seed_boutique_catalog.py exactly. The
-- seeder INSERTs 40 rows (10 per persona × Marco / Anna / Theo /
-- Fresh) with Cohere Embed v4 embeddings already generated.
--
-- "productId" is text (the seeder casts integer IDs to strings) so a
-- future SKU rename like "P-2026-04-127" lands in place. Quoted
-- camelCase column names match the FastAPI ORM expectations.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pellier.product_catalog (
    "productId"   text          PRIMARY KEY,
    name          text          NOT NULL,
    brand         text          NOT NULL,
    color         text,
    price         numeric(10,2) NOT NULL,
    description   text,
    category      text,
    tags          jsonb         NOT NULL DEFAULT '[]'::jsonb,
    rating        numeric(3,2)  NOT NULL DEFAULT 0,
    reviews       integer       NOT NULL DEFAULT 0,
    "imgUrl"      text,
    badge         text,
    tier          integer       NOT NULL DEFAULT 1,
    quantity      integer       NOT NULL DEFAULT 0,
    embedding     vector(1024),
    created_at    timestamptz   NOT NULL DEFAULT now(),
    updated_at    timestamptz   NOT NULL DEFAULT now()
);

-- updated_at trigger — cheap, idempotent, only fires on real changes.
CREATE OR REPLACE FUNCTION pellier.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS product_catalog_set_updated_at
    ON pellier.product_catalog;
CREATE TRIGGER product_catalog_set_updated_at
    BEFORE UPDATE ON pellier.product_catalog
    FOR EACH ROW EXECUTE FUNCTION pellier.set_updated_at();

-- ---------------------------------------------------------------------
-- 4. HNSW index for vector similarity search
--
-- m=16 / ef_construction=64 are the workshop's tuned defaults.
-- vector_cosine_ops matches the Cohere Embed v4 normalization we use
-- at query time (the `<=>` operator in find_pieces / hybrid_search).
--
-- pgvector lets you build HNSW on an empty table — the index grows
-- incrementally as inserts arrive, so the 40-row seed inherits it
-- automatically. No REINDEX needed after seeding.
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS product_catalog_embedding_hnsw
    ON pellier.product_catalog
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Lightweight btree on category for boutique grid filters.
CREATE INDEX IF NOT EXISTS product_catalog_category_idx
    ON pellier.product_catalog (category);

-- ---------------------------------------------------------------------
-- 5. Visibility
-- ---------------------------------------------------------------------
DO $$
DECLARE
    rowcount integer;
BEGIN
    SELECT count(*) INTO rowcount FROM pellier.product_catalog;
    RAISE NOTICE 'pellier.product_catalog ready (% rows)', rowcount;
END $$;
