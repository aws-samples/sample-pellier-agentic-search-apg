-- Migration 004: Add `quantity` column to product_catalog
--
-- The boutique schema shipped without stock tracking. This migration
-- adds a NOT NULL quantity column with a CHECK(0..9999) constraint
-- and seeds realistic stock numbers based on tier + rating:
--
--   Tier 1 (hero pieces):      15-45 units, highest-rated get more
--   Tier 2 (mid-range):         5-25 units
--   Tier 3 (niche / new):       0-12 units, some intentionally low/zero
--
-- The distribution mimics a real boutique where hero SKUs are
-- restocked aggressively and niche pieces run thin. Products with
-- rating >= 4.8 get a small stock bump (popular → restocked faster).
-- A handful of tier-3 items land at 0-2 so the Inventory specialist
-- has real "critical" items to surface.
--
-- Idempotent: IF NOT EXISTS on the column add; the UPDATE is safe
-- to re-run (overwrites with the same deterministic formula).
--
-- Run: psql $DATABASE_URL -f scripts/migrations/004_add_quantity.sql

-- Add the column if it doesn't exist yet.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'pellier'
      AND table_name   = 'product_catalog'
      AND column_name  = 'quantity'
  ) THEN
    ALTER TABLE pellier.product_catalog
      ADD COLUMN quantity SMALLINT NOT NULL DEFAULT 20
      CHECK (quantity >= 0 AND quantity <= 9999);
    RAISE NOTICE 'Added quantity column to product_catalog';
  ELSE
    RAISE NOTICE 'quantity column already exists — skipping ADD COLUMN';
  END IF;
END $$;

-- Seed stock using a deterministic formula based on productId, tier, rating.
-- The formula uses modular arithmetic on the product id to create
-- variation within each tier band so quantities aren't all identical.
UPDATE pellier.product_catalog
SET quantity = CASE
  -- Tier 1: hero pieces, well-stocked (15-45)
  WHEN tier = 1 THEN
    15 + ("productId" % 20) + (CASE WHEN rating >= 4.8 THEN 10 ELSE 0 END)

  -- Tier 2: mid-range (5-25)
  WHEN tier = 2 THEN
    5 + ("productId" % 15) + (CASE WHEN rating >= 4.7 THEN 5 ELSE 0 END)

  -- Tier 3: niche / new arrivals, deliberately thin (0-12)
  -- Some land at 0-2 so the inventory specialist has real criticals.
  ELSE
    GREATEST(0, ("productId" % 8) - 1) + (CASE WHEN rating >= 4.8 THEN 3 ELSE 0 END)
END;

-- Quick summary for the operator.
DO $$
DECLARE
  total INT;
  low INT;
  zero INT;
BEGIN
  SELECT COUNT(*) INTO total FROM pellier.product_catalog;
  SELECT COUNT(*) INTO low   FROM pellier.product_catalog WHERE quantity <= 5;
  SELECT COUNT(*) INTO zero  FROM pellier.product_catalog WHERE quantity = 0;
  RAISE NOTICE 'Seeded quantity for % products: % low-stock (<=5), % out-of-stock (0)',
    total, low, zero;
END $$;
