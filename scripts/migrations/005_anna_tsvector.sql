-- Migration 005: Add tsvector column + GIN index for Anna's hybrid search
--
-- Anna anchors the second Aurora capability on the workshop's learning
-- ladder: hybrid retrieval (pgvector + Postgres full-text search) with
-- Reciprocal Rank Fusion and a Cohere Rerank v3.5 final pass.
--
-- Pure cosine similarity (Marco's foundation) wears thin on queries
-- like "something beautiful under $100" — the embedding sees "beautiful"
-- + "$100" as soft signals, not the hard price filter or the
-- "considered gift" intent that BM25 over name/brand/category/tags
-- would catch immediately. Hybrid + RRF lets each modality contribute
-- what it's best at; Cohere Rerank then reorders the union by relevance.
--
-- This migration adds the tsvector column. Field weights match BM25
-- norms — name + brand carry the most signal (A), category + color
-- are coarse but useful (B), tags are user-supplied so we down-weight
-- them slightly (C), description is the fallback (D).
--
-- The column is GENERATED ALWAYS AS (...) STORED so updates to
-- name/description/etc. automatically refresh the tsvector — and so
-- the GIN index (which can't be built on a virtual generated column)
-- has stable bytes to index.
--
-- The GIN index makes BM25 queries (description_tsv @@ ts_query)
-- index-scan instead of seq-scan. On 92 rows this is decorative,
-- but the workshop story is "this is how you'd do it on 92 million."
--
-- Idempotent: ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.
-- Run: psql $DATABASE_URL -f scripts/migrations/005_anna_tsvector.sql

\set ON_ERROR_STOP on
BEGIN;

ALTER TABLE pellier.product_catalog
    ADD COLUMN IF NOT EXISTS description_tsv tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(name,        '')), 'A')
     || setweight(to_tsvector('english', coalesce(brand,       '')), 'A')
     || setweight(to_tsvector('english', coalesce(category,    '')), 'B')
     || setweight(to_tsvector('english', coalesce(color,       '')), 'B')
     || setweight(to_tsvector('english',
            coalesce(jsonb_path_query_array(tags, '$[*]')::text, '')), 'C')
     || setweight(to_tsvector('english', coalesce(description, '')), 'D')
    ) STORED;

CREATE INDEX IF NOT EXISTS product_catalog_description_tsv_gin_idx
    ON pellier.product_catalog USING GIN (description_tsv);

-- Quick summary so the operator can confirm the column is populated.
DO $$
DECLARE
    populated INT;
    total INT;
BEGIN
    SELECT COUNT(*) INTO total FROM pellier.product_catalog;
    SELECT COUNT(*) INTO populated
      FROM pellier.product_catalog
      WHERE description_tsv IS NOT NULL AND description_tsv != '';
    RAISE NOTICE 'description_tsv populated for %/% products', populated, total;
END $$;

COMMIT;
