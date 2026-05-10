-- Migration 010: Rename sub-brand strings in product_catalog
--
-- The Blaize Bazaar → The Pellier brand rename converted
-- 'Blaize Editions / Atelier / Home / Travel / etc.' to
-- 'Pellier Editions / Atelier / Home / Travel / etc.' in the seed
-- script and the catalog CSV. Aurora's live rows were seeded before
-- the rename, so they still carry the old 'Blaize <subbrand>' strings.
-- This migration flips them in place.
--
-- Surface impact: the Curator (recommendation agent) faithfully
-- echoes the brand field from product_catalog rows. With the live DB
-- still on 'Blaize Editions', Anna's reply quoted "Botanical Print
-- Scarf by Blaize Editions" — visible regression after the rename.
--
-- Idempotent: only updates rows whose brand still starts with
-- 'Blaize '. The Hadley Linen Shirt (productId=2) has brand='Hadley'
-- and is not touched.
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/010_rename_brand_strings_in_catalog.sql

\set ON_ERROR_STOP on

BEGIN;

UPDATE pellier.product_catalog
   SET brand = REPLACE(brand, 'Blaize ', 'Pellier ')
 WHERE brand LIKE 'Blaize %';

-- Quick visibility on what landed.
DO $$
DECLARE
    pellier_count INTEGER;
    blaize_count  INTEGER;
    hadley_count  INTEGER;
BEGIN
    SELECT COUNT(*) INTO pellier_count
      FROM pellier.product_catalog WHERE brand LIKE 'Pellier %';
    SELECT COUNT(*) INTO blaize_count
      FROM pellier.product_catalog WHERE brand LIKE 'Blaize %';
    SELECT COUNT(*) INTO hadley_count
      FROM pellier.product_catalog WHERE brand = 'Hadley';
    RAISE NOTICE 'Brand distribution: % Pellier-prefixed, % Hadley, % Blaize-prefixed (should be 0)',
        pellier_count, hadley_count, blaize_count;
END $$;

COMMIT;
