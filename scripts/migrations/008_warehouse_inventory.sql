-- Migration 008: Per-warehouse inventory for Marco's Turn 4 teaching
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
-- could only return aggregate health. This migration adds the missing
-- structure so Stock Keeper has something concrete to lean on.
--
-- Two tables:
--   warehouses          — three locations (BK-01, ATX-02, PDX-01) with
--                         display name, city, ship window in business days.
--   warehouse_inventory — per-warehouse, per-product stock. UNIQUE on
--                         (warehouse_id, productId). Sum across warehouses
--                         is approximately equal to product_catalog.quantity
--                         (deterministic 30/40/30 split with bias).
--
-- The split:
--   * Brooklyn (BK-01) gets 40% — biased high for apparel/linen (Marco's
--     world). It's the headline warehouse Marco asks about.
--   * Austin (ATX-02) gets 30%.
--   * Portland (PDX-01) gets 30%.
--   * For products with quantity < 3 the smallest warehouses round to 0.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS; ON CONFLICT DO UPDATE on the
-- inventory rows so re-running the migration after a quantity refresh
-- recomputes the split.
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/008_warehouse_inventory.sql

\set ON_ERROR_STOP on

BEGIN;

-- warehouses ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouses (
    id              TEXT PRIMARY KEY,        -- code like 'BK-01'
    display_name    TEXT NOT NULL,           -- 'Brooklyn'
    city            TEXT NOT NULL,           -- 'Brooklyn, NY'
    ship_window_min INTEGER NOT NULL,        -- business days, low end
    ship_window_max INTEGER NOT NULL,        -- business days, high end
    CHECK (ship_window_min >= 0 AND ship_window_max >= ship_window_min)
);

INSERT INTO warehouses (id, display_name, city, ship_window_min, ship_window_max)
VALUES
    ('BK-01',  'Brooklyn',  'Brooklyn, NY',  1, 2),
    ('ATX-02', 'Austin',    'Austin, TX',    2, 4),
    ('PDX-01', 'Portland',  'Portland, OR',  3, 5)
ON CONFLICT (id) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    city            = EXCLUDED.city,
    ship_window_min = EXCLUDED.ship_window_min,
    ship_window_max = EXCLUDED.ship_window_max;

-- warehouse_inventory ------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse_inventory (
    warehouse_id    TEXT NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    "productId"     INTEGER NOT NULL
                    REFERENCES blaize_bazaar.product_catalog("productId")
                    ON DELETE CASCADE,
    quantity        SMALLINT NOT NULL DEFAULT 0
                    CHECK (quantity >= 0 AND quantity <= 9999),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (warehouse_id, "productId")
);

CREATE INDEX IF NOT EXISTS warehouse_inventory_product_idx
    ON warehouse_inventory ("productId");

-- Seed: deterministic 40/30/30 split of product_catalog.quantity
-- across BK-01 / ATX-02 / PDX-01. Apparel/linen (Marco's world) keeps
-- the Brooklyn bias at 40% — the lab content frames Brooklyn as the
-- headline warehouse Marco asks about, so the Pellier shirt should
-- have a substantive count there.
INSERT INTO warehouse_inventory (warehouse_id, "productId", quantity)
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
FROM warehouses wh
CROSS JOIN blaize_bazaar.product_catalog pc
ON CONFLICT (warehouse_id, "productId") DO UPDATE SET
    quantity   = EXCLUDED.quantity,
    updated_at = now();

-- Quick visibility on what landed.
DO $$
DECLARE
    nrows  INTEGER;
    nzero  INTEGER;
BEGIN
    SELECT COUNT(*)                             INTO nrows FROM warehouse_inventory;
    SELECT COUNT(*) FILTER (WHERE quantity = 0) INTO nzero FROM warehouse_inventory;
    RAISE NOTICE 'warehouse_inventory: % rows total (% with zero stock)', nrows, nzero;
END $$;

COMMIT;
