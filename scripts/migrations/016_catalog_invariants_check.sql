-- Migration 016: Catalog invariants check (non-destructive tripwire)
--
-- The Pellier boutique catalog is a hand-curated 40-row dataset that
-- lives in pellier.product_catalog. It can be wiped or corrupted by:
--   * scripts/seed_boutique_catalog.py rerunning (DELETE + INSERT;
--     this is the authoritative seeder, but a stale invocation could
--     overwrite hand-edits made directly in Aurora)
--   * an operator hand-truncating the table
--
-- This migration is a SELECT-only assertion battery. It RAISES an
-- exception if any of the boutique invariants are violated. Running
-- it periodically (or as a CI gate) catches accidental wipes early.
--
-- Invariants asserted:
--   1. pellier.product_catalog has exactly 40 rows.
--   2. productIds are contiguous 1..40 with no gaps.
--   3. productId=2 is the Hadley Linen Shirt (the workshop's headline SKU).
--   4. Every brand starts with 'Pellier ' or equals 'Hadley'.
--   5. Every row has an embedding (1024-dim vector).
--   6. Every row has a non-empty name and category.
--
-- Idempotent. Read-only. Safe to run anytime.
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/016_catalog_invariants_check.sql

\set ON_ERROR_STOP on

DO $$
DECLARE
    n_rows           INTEGER;
    n_distinct_ids   INTEGER;
    min_id           INTEGER;
    max_id           INTEGER;
    n_bad_brands     INTEGER;
    n_no_embedding   INTEGER;
    n_no_name        INTEGER;
    hadley_name      TEXT;
    hadley_brand     TEXT;
    hadley_present   INTEGER;
BEGIN
    -- 1+2: Row count + contiguous ID range
    SELECT COUNT(*),
           COUNT(DISTINCT "productId"),
           MIN("productId"),
           MAX("productId")
      INTO n_rows, n_distinct_ids, min_id, max_id
      FROM pellier.product_catalog;

    IF n_rows <> 40 THEN
        RAISE EXCEPTION 'Catalog invariant violated: expected 40 rows, found %', n_rows;
    END IF;

    IF n_distinct_ids <> 40 OR min_id <> 1 OR max_id <> 40 THEN
        RAISE EXCEPTION 'Catalog invariant violated: productIds not contiguous 1..40 '
                        '(distinct=%, min=%, max=%)', n_distinct_ids, min_id, max_id;
    END IF;

    -- 3: Hadley Linen Shirt sanity
    SELECT name, brand, COUNT(*) OVER ()
      INTO hadley_name, hadley_brand, hadley_present
      FROM pellier.product_catalog
     WHERE "productId" = 2;

    IF hadley_present <> 1 THEN
        RAISE EXCEPTION 'Catalog invariant violated: productId=2 not present';
    END IF;
    IF hadley_name <> 'Hadley Linen Shirt' OR hadley_brand <> 'Hadley' THEN
        RAISE EXCEPTION 'Catalog invariant violated: productId=2 is %/% (expected Hadley Linen Shirt/Hadley)',
            hadley_name, hadley_brand;
    END IF;

    -- 4: Brand prefix discipline
    SELECT COUNT(*) INTO n_bad_brands
      FROM pellier.product_catalog
     WHERE NOT (brand LIKE 'Pellier %' OR brand = 'Hadley');

    IF n_bad_brands > 0 THEN
        RAISE EXCEPTION 'Catalog invariant violated: % rows with brand not in '
                        '{Pellier *, Hadley}', n_bad_brands;
    END IF;

    -- 5: Every row has an embedding
    SELECT COUNT(*) INTO n_no_embedding
      FROM pellier.product_catalog
     WHERE embedding IS NULL;

    IF n_no_embedding > 0 THEN
        RAISE EXCEPTION 'Catalog invariant violated: % rows with NULL embedding '
                        '(run scripts/migrations/011_refresh_embeddings.py)', n_no_embedding;
    END IF;

    -- 6: Name + category are non-empty
    SELECT COUNT(*) INTO n_no_name
      FROM pellier.product_catalog
     WHERE name IS NULL OR name = '' OR category IS NULL OR category = '';

    IF n_no_name > 0 THEN
        RAISE EXCEPTION 'Catalog invariant violated: % rows with empty name or category', n_no_name;
    END IF;

    RAISE NOTICE '✓ All catalog invariants pass (% rows, contiguous 1..%, Hadley@2, all brands valid, all embeddings present)',
        n_rows, max_id;
END $$;
