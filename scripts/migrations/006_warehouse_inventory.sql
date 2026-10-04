-- Migration 006: Per-warehouse inventory for Inventory Agent (Marco's Turn 4).
--
-- The lab content promises Marco gets a real warehouse breakdown when he
-- asks "Is the Hadley shirt at the Brooklyn warehouse?" (Pellier Linen Shirt in ecru):
--
--   "Yes — Brooklyn (BK-01) has the most of the Pellier Linen Shirt in
--    ecru on the floor right now, with smaller counts at Austin (ATX-02)
--    and Portland (PDX-01). Ship window from Brooklyn to your zip is
--    1–2 business days."
--
-- Exact per-warehouse counts are derived from the 40/30/30 split below.
-- Austin and Portland receive FLOOR(30%); Brooklyn receives the remainder,
-- preserving the catalog total exactly and keeping Brooklyn largest.
--
-- 001_schema.sql creates aggregate product_catalog.quantity. This
-- migration adds the per-warehouse structure Inventory Agent needs.
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
--   pellier.warehouse_inventory — per-warehouse, per-curated-product stock.
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
--     -f scripts/migrations/006_warehouse_inventory.sql

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

-- Backward-compat normalization for older workshop tables that used
-- camelCase "productId" (INTEGER) in public.warehouse_inventory.
-- After moving schemas above, normalize to snake_case TEXT so joins/FKs
-- against product_catalog."productId" (TEXT) remain type-safe.
DO $$
DECLARE
    c RECORD;
    target_type text;
BEGIN
    -- Drop any existing FKs on warehouse_inventory first so product_id
    -- type normalization can succeed across legacy schemas.
    FOR c IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'pellier.warehouse_inventory'::regclass
          AND contype = 'f'
    LOOP
        EXECUTE format(
            'ALTER TABLE pellier.warehouse_inventory DROP CONSTRAINT IF EXISTS %I',
            c.conname
        );
    END LOOP;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'pellier'
          AND table_name = 'warehouse_inventory'
          AND column_name = 'productId'
    ) THEN
        EXECUTE 'ALTER TABLE pellier.warehouse_inventory RENAME COLUMN "productId" TO product_id';
        RAISE NOTICE 'Normalized warehouse_inventory."productId" → product_id';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'pellier'
          AND table_name = 'warehouse_inventory'
          AND column_name = 'product_id'
    ) THEN
        SELECT data_type
          INTO target_type
          FROM information_schema.columns
         WHERE table_schema = 'pellier'
           AND table_name = 'product_catalog'
           AND column_name = 'productId'
         LIMIT 1;

        target_type := COALESCE(target_type, 'text');

        IF target_type = 'integer' THEN
            EXECUTE '
                ALTER TABLE pellier.warehouse_inventory
                ALTER COLUMN product_id TYPE integer
                USING product_id::integer
            ';
        ELSE
            EXECUTE '
                ALTER TABLE pellier.warehouse_inventory
                ALTER COLUMN product_id TYPE text
                USING product_id::text
            ';
        END IF;
        RAISE NOTICE 'Normalized warehouse_inventory.product_id type → %', target_type;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'warehouse_inventory_product_id_fkey'
          AND conrelid = 'pellier.warehouse_inventory'::regclass
    ) THEN
        ALTER TABLE pellier.warehouse_inventory
            ADD CONSTRAINT warehouse_inventory_product_id_fkey
            FOREIGN KEY (product_id)
            REFERENCES pellier.product_catalog("productId")
            ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS warehouse_inventory_product_idx
    ON pellier.warehouse_inventory (product_id);

-- ---------------------------------------------------------------------
-- Seed: rebuild the exact 100 x 3 governed inventory matrix. Clearing the
-- existing rows prevents legacy warehouses or stale products from surviving
-- a reset and invalidating the 300-row workshop contract.
-- ---------------------------------------------------------------------
SET LOCAL pellier.inventory_reason = 'seed';

DELETE FROM pellier.warehouse_inventory;
DELETE FROM pellier.warehouses
WHERE id NOT IN ('BK-01', 'ATX-02', 'PDX-01');

-- The leading warehouse rotates with the product ID, so no warehouse is
-- always the largest. The other two each hold 30% of the catalog quantity.
INSERT INTO pellier.warehouse_inventory (warehouse_id, product_id, quantity)
SELECT wh.id, pc."productId",
       GREATEST(0, CASE
         WHEN wh.id = (ARRAY['BK-01','ATX-02','PDX-01'])[(pc."productId"::int % 3) + 1]
           THEN pc.quantity - 2 * FLOOR(pc.quantity * 0.30)::int
         ELSE FLOOR(pc.quantity * 0.30)::int
       END)::smallint
  FROM pellier.warehouses wh
 CROSS JOIN pellier.product_catalog pc
 WHERE wh.id IN ('BK-01', 'ATX-02', 'PDX-01')
   AND pc."productId" ~ '^[0-9]+$'
ON CONFLICT (warehouse_id, product_id) DO UPDATE SET quantity = EXCLUDED.quantity, updated_at = now();

-- Teaching fixtures: exact rows the labs and their checkers depend on.
WITH fixture(product_id, warehouse_id, quantity) AS (VALUES
    ('2', 'BK-01', 0), ('2', 'ATX-02', 6), ('2', 'PDX-01', 14),
    ('14', 'BK-01', 3), ('14', 'ATX-02', 2), ('14', 'PDX-01', 0),
    ('43', 'BK-01', 0), ('43', 'ATX-02', 0), ('43', 'PDX-01', 0),
    ('79', 'BK-01', 0), ('79', 'ATX-02', 0), ('79', 'PDX-01', 0))
UPDATE pellier.warehouse_inventory wi
   SET quantity = f.quantity::smallint, updated_at = now()
  FROM fixture f
 WHERE wi.product_id = f.product_id AND wi.warehouse_id = f.warehouse_id;

-- ---------------------------------------------------------------------
-- Visibility
-- ---------------------------------------------------------------------
DO $$
DECLARE
    nrows  INTEGER;
    nzero  INTEGER;
    invalid_products INTEGER;
    drift_count INTEGER;
BEGIN
    SELECT COUNT(*)                             INTO nrows FROM pellier.warehouse_inventory;
    SELECT COUNT(*) FILTER (WHERE quantity = 0) INTO nzero FROM pellier.warehouse_inventory;
    SELECT count(*)
      INTO invalid_products
      FROM (
          SELECT product_id
            FROM pellier.warehouse_inventory
           GROUP BY product_id
          HAVING count(*) <> 3
      ) AS invalid;
    SELECT count(*)
      INTO drift_count
      FROM pellier.product_catalog pc
     WHERE pc."productId" ~ '^[0-9]+$'
       AND pc.quantity <> (
           SELECT COALESCE(sum(wi.quantity), 0)
             FROM pellier.warehouse_inventory wi
            WHERE wi.product_id = pc."productId"
       );

    IF nrows <> 300 OR invalid_products <> 0 OR drift_count <> 0 THEN
        RAISE EXCEPTION
            'Governed inventory expected 300 rows, 3 warehouses per product and no drift; got % rows, % invalid products and % drifting products.',
            nrows,
            invalid_products,
            drift_count;
    END IF;
    RAISE NOTICE 'pellier.warehouse_inventory: % rows total (% with zero stock)', nrows, nzero;
END $$;

COMMIT;
