-- Migration 014: Add foreign keys from public.* tables to pellier.product_catalog.
--
-- The audit (audit_full_schema.sql) revealed three tables that store
-- product_id/productId values but have no FK to pellier.product_catalog:
--
--   * public.orders.product_id              INTEGER
--   * public.returns.product_id             INTEGER
--   * public.warehouse_inventory."productId" INTEGER
--
-- All three column types match pellier.product_catalog."productId" (INTEGER).
-- Adding the FK enforces referential integrity:
--   * Orphan product_ids in orders/returns/warehouse_inventory become impossible.
--   * Deleting a product CASCADEs cleanup.
--
-- Idempotent: each ALTER is wrapped in a DO block that checks for the
-- constraint name first.
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/014_add_product_catalog_fks.sql

\set ON_ERROR_STOP on

BEGIN;

-- Pre-flight: any existing rows that would violate the FK?
DO $$
DECLARE
    orphans INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphans
      FROM public.orders o
     WHERE NOT EXISTS (
        SELECT 1 FROM pellier.product_catalog pc WHERE pc."productId" = o.product_id
     );
    IF orphans > 0 THEN
        RAISE EXCEPTION 'public.orders has % rows with product_id not in pellier.product_catalog. '
                        'Clean these up before adding the FK.', orphans;
    END IF;

    SELECT COUNT(*) INTO orphans
      FROM public.returns r
     WHERE NOT EXISTS (
        SELECT 1 FROM pellier.product_catalog pc WHERE pc."productId" = r.product_id
     );
    IF orphans > 0 THEN
        RAISE EXCEPTION 'public.returns has % rows with product_id not in pellier.product_catalog.', orphans;
    END IF;

    SELECT COUNT(*) INTO orphans
      FROM public.warehouse_inventory wi
     WHERE NOT EXISTS (
        SELECT 1 FROM pellier.product_catalog pc WHERE pc."productId" = wi."productId"
     );
    IF orphans > 0 THEN
        RAISE EXCEPTION 'public.warehouse_inventory has % rows with productId not in pellier.product_catalog.', orphans;
    END IF;

    RAISE NOTICE 'Pre-flight clean: no orphan product_ids in orders/returns/warehouse_inventory.';
END $$;

-- public.orders.product_id → pellier.product_catalog."productId"
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'orders_product_fk'
    ) THEN
        ALTER TABLE public.orders
            ADD CONSTRAINT orders_product_fk
            FOREIGN KEY (product_id)
            REFERENCES pellier.product_catalog("productId")
            ON DELETE CASCADE;
        RAISE NOTICE 'Added FK orders.product_id → pellier.product_catalog';
    ELSE
        RAISE NOTICE 'FK orders_product_fk already exists — skipping';
    END IF;
END $$;

-- public.returns.product_id → pellier.product_catalog."productId"
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'returns_product_fk'
    ) THEN
        ALTER TABLE public.returns
            ADD CONSTRAINT returns_product_fk
            FOREIGN KEY (product_id)
            REFERENCES pellier.product_catalog("productId")
            ON DELETE CASCADE;
        RAISE NOTICE 'Added FK returns.product_id → pellier.product_catalog';
    ELSE
        RAISE NOTICE 'FK returns_product_fk already exists — skipping';
    END IF;
END $$;

-- public.warehouse_inventory."productId" → pellier.product_catalog."productId"
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'warehouse_inventory_product_fk'
    ) THEN
        ALTER TABLE public.warehouse_inventory
            ADD CONSTRAINT warehouse_inventory_product_fk
            FOREIGN KEY ("productId")
            REFERENCES pellier.product_catalog("productId")
            ON DELETE CASCADE;
        RAISE NOTICE 'Added FK warehouse_inventory.productId → pellier.product_catalog';
    ELSE
        RAISE NOTICE 'FK warehouse_inventory_product_fk already exists — skipping';
    END IF;
END $$;

COMMIT;
