-- Migration 017: Clean up legacy CUST-000N customers + their orphan orders
--
-- The audit found:
--   * 12 rows in public.customers (4 personas + 8 legacy CUST-000N)
--   * 6 rows in public.orders with product_id outside the 40-row catalog
--   * All 6 orphans belong to CUST-000{3,5,6,7,8} — the legacy seeds
--
-- These CUST-000N customers come from a now-deleted seed pipeline
-- (probably the old seed-database.sh + product-catalog-cohere-v4.csv
-- pipeline that referenced 92+ products). The active seeders only
-- create CUST-MARCO / CUST-ANNA / CUST-THEO / CUST-FRESH.
--
-- Cleaning the legacy rows:
--   1. unblocks migration 014 (the FK pre-flight will pass)
--   2. brings live customers/orders state into agreement with the
--      active seeders
--   3. removes a footgun for future "why does customer N have orders
--      for products that don't exist" debugging
--
-- Idempotent: WHERE clauses are no-ops if the rows are already gone.
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/017_cleanup_legacy_customers.sql

\set ON_ERROR_STOP on

BEGIN;

-- Pre-flight visibility: how many legacy rows are we touching?
DO $$
DECLARE
    legacy_customers   INTEGER;
    legacy_orders      INTEGER;
    legacy_episodes    INTEGER;
    legacy_returns     INTEGER;
    legacy_approvals   INTEGER;
BEGIN
    SELECT COUNT(*) INTO legacy_customers
      FROM public.customers
     WHERE id LIKE 'CUST-0%';

    SELECT COUNT(*) INTO legacy_orders
      FROM public.orders
     WHERE customer_id LIKE 'CUST-0%';

    SELECT COUNT(*) INTO legacy_episodes
      FROM public.customer_episodic_seed
     WHERE customer_id LIKE 'CUST-0%';

    SELECT COUNT(*) INTO legacy_returns
      FROM public.returns
     WHERE customer_id LIKE 'CUST-0%';

    SELECT COUNT(*) INTO legacy_approvals
      FROM public.approvals
     WHERE customer_id LIKE 'CUST-0%';

    RAISE NOTICE 'Pre-cleanup legacy CUST-0* rows: % customers, % orders, % episodes, % returns, % approvals',
        legacy_customers, legacy_orders, legacy_episodes, legacy_returns, legacy_approvals;
END $$;

-- DELETE the legacy customers. ON DELETE CASCADE on the FK from
-- orders/customer_episodic_seed/returns/approvals → customers means
-- the dependent rows go with them. (Confirmed via audit_full_schema.sql
-- that all four reference customers(id) ON DELETE CASCADE.)
DELETE FROM public.customers
 WHERE id LIKE 'CUST-0%';

-- Post-cleanup visibility.
DO $$
DECLARE
    n_customers   INTEGER;
    n_orders      INTEGER;
    n_orphans     INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_customers FROM public.customers;
    SELECT COUNT(*) INTO n_orders    FROM public.orders;
    SELECT COUNT(*) INTO n_orphans
      FROM public.orders o
     WHERE NOT EXISTS (
        SELECT 1 FROM pellier.product_catalog pc
         WHERE pc."productId" = o.product_id
     );
    RAISE NOTICE 'Post-cleanup: % customers, % orders, % orphan orders (should be 0)',
        n_customers, n_orders, n_orphans;
END $$;

INSERT INTO public.schema_migrations (version, name, applied_at)
VALUES ('017', 'cleanup_legacy_customers', now())
ON CONFLICT (version) DO NOTHING;

COMMIT;
