-- Migration 008: Per-warehouse inventory for Stock Keeper (Marco's Turn 4).
--
-- The lab content promises Marco gets a real warehouse breakdown when he
-- asks "Is the Pellier shirt at the Brooklyn warehouse?":
--
--   "Yes — Brooklyn (BK-01) has 8 of the Pellier Linen Shirt in ecru on
--    the floor right now. Also 4 at Austin (ATX-02) and 12 at Portland
--    (PDX-01). Ship window from Brooklyn to your zip is 1–2 business days."
--
-- Migration 004 only added an aggregate `quantity` SMALLINT to
-- product_catalog — there was no per-warehouse data, so floor_check
-- could only return aggregate health. This migration adds the per-
-- warehouse structure Stock Keeper needs.
--
-- Schema placement: every operational table lives under `pellier.*`
-- (see memory: pellier_schema_decisions). Older revisions of this
-- migration created `warehouses` / `warehouse_inventory` at the
-- `public` schema; the renames at the bottom move existing rows in
-- place when an older deploy is upgraded, then `IF NOT EXISTS` keeps
-- a fresh deploy idempotent.
--
-- Two tables:
--   pellier.warehouses          — three locations (BK-01, ATX-02, PDX-01)
--                                  with display name, city, ship window.
--   pellier.warehouse_inventory — per-warehouse, per-product stock.
--                                  PK on (warehouse_id, product_id).
--
-- The split:
--   Brooklyn (BK-01) gets 40% — biased high for apparel/linen
--   (Marco's world); the lab content frames Brooklyn as the headline
--   warehouse Marco asks about.
--   Austin (ATX-02) gets 30%.
--   Portland (PDX-01) gets 30%.
--
-- Note on the product_id type: `pellier.product_catalog."productId"`
-- is TEXT (the seeder casts integer IDs to strings). This table's
-- `product_id` column is also TEXT so the foreign key applies cleanly
-- without a cast — fixing a regression where this migration tried to
-- declare an INTEGER FK against the TEXT column and failed.
--
-- Idempotent: every CREATE/INSERT uses IF NOT EXISTS / ON CONFLICT.
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/008_warehouse_inventory.sql

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------
-- One-time relocation: move legacy public.* tables into pellier.*
--
-- Earlier deploys of this migration created the tables at `public`.
-- We rename them in place rather than drop + recreate so existing
-- rows survive. ALTER TABLE ... SET SCHEMA preserves indexes, FKs,
-- triggers, and data.
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'warehouse_inventory'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'pellier' AND table_name = 'warehouse_inventory'
    ) THEN
        ALTER TABLE public.warehouse_inventory SET SCHEMA pellier;
        RAISE NOTICE 'Moved public.warehouse_inventory → pellier.warehouse_inventory';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'warehouses'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'pellier' AND table_name = 'warehouses'
    ) THEN
        ALTER TABLE public.warehouses SET SCHEMA pellier;
        RAISE NOTICE 'Moved public.warehouses → pellier.warehouses';
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- pellier.warehouses
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pellier.warehouses (
    id              TEXT PRIMARY KEY,        -- code like 'BK-01'
    display_name    TEXT NOT NULL,           -- 'Brooklyn'
    city            TEXT NOT NULL,           -- 'Brooklyn, NY'
    ship_window_min INTEGER NOT NULL,        -- business days, low end
    ship_window_max INTEGER NOT NULL,        -- business days, high end
    CHECK (ship_window_min >= 0 AND ship_window_max >= ship_window_min)
);

INSERT INTO pellier.warehouses (id, display_name, city, ship_window_min, ship_window_max)
VALUES
    ('BK-01',  'Brooklyn',  'Brooklyn, NY',  1, 2),
    ('ATX-02', 'Austin',    'Austin, TX',    2, 4),
    ('PDX-01', 'Portland',  'Portland, OR',  3, 5)
ON CONFLICT (id) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    city            = EXCLUDED.city,
    ship_window_min = EXCLUDED.ship_window_min,
    ship_window_max = EXCLUDED.ship_window_max;

-- ---------------------------------------------------------------------
-- pellier.warehouse_inventory
--
-- product_id is TEXT to match pellier.product_catalog."productId".
-- Plain snake_case identifiers; no quoting required.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pellier.warehouse_inventory (
    warehouse_id  TEXT NOT NULL
                  REFERENCES pellier.warehouses(id) ON DELETE CASCADE,
    product_id    TEXT NOT NULL
                  REFERENCES pellier.product_catalog("productId")
                  ON DELETE CASCADE,
    quantity      SMALLINT NOT NULL DEFAULT 0
                  CHECK (quantity >= 0 AND quantity <= 9999),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (warehouse_id, product_id)
);

CREATE INDEX IF NOT EXISTS warehouse_inventory_product_idx
    ON pellier.warehouse_inventory (product_id);

-- ---------------------------------------------------------------------
-- Seed: deterministic 40/30/30 split of product_catalog.quantity
-- across BK-01 / ATX-02 / PDX-01.
-- ---------------------------------------------------------------------
INSERT INTO pellier.warehouse_inventory (warehouse_id, product_id, quantity)
SELECT
    wh.id,
    pc."productId",
    GREATEST(
        0,
        FLOOR(
            pc.quantity * CASE wh.id
                WHEN 'BK-01'  THEN 0.40
                WHEN 'ATX-02' THEN 0.30
                WHEN 'PDX-01' THEN 0.30
            END
        )::SMALLINT
    )
FROM pellier.warehouses wh
CROSS JOIN pellier.product_catalog pc
ON CONFLICT (warehouse_id, product_id) DO UPDATE SET
    quantity   = EXCLUDED.quantity,
    updated_at = now();

-- ---------------------------------------------------------------------
-- Visibility
-- ---------------------------------------------------------------------
DO $$
DECLARE
    nrows  INTEGER;
    nzero  INTEGER;
BEGIN
    SELECT COUNT(*)                             INTO nrows FROM pellier.warehouse_inventory;
    SELECT COUNT(*) FILTER (WHERE quantity = 0) INTO nzero FROM pellier.warehouse_inventory;
    RAISE NOTICE 'pellier.warehouse_inventory: % rows total (% with zero stock)', nrows, nzero;
END $$;

COMMIT;
