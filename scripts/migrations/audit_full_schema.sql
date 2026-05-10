-- Full Aurora schema audit. Read-only. Prints every table, every
-- column with its type, every index, every FK, every row count.
-- Run this and paste the output back to confirm what's actually in
-- Aurora (vs what the migration files claim).
--
-- Usage:
--   PGPASSWORD="$DB_PASSWORD" psql \
--     -h dat4xx-labs-test.cluster-chygmprofdnr.us-west-2.rds.amazonaws.com \
--     -U postgres -d postgres \
--     -f scripts/migrations/audit_full_schema.sql

\pset pager off

\echo
\echo '=========================================================================='
\echo '== SCHEMAS'
\echo '=========================================================================='
SELECT schema_name
  FROM information_schema.schemata
 WHERE schema_name NOT IN ('pg_catalog','information_schema','pg_toast')
 ORDER BY schema_name;

\echo
\echo '=========================================================================='
\echo '== EXTENSIONS'
\echo '=========================================================================='
SELECT extname, extversion FROM pg_extension ORDER BY extname;

\echo
\echo '=========================================================================='
\echo '== TABLES (every schema we own)'
\echo '=========================================================================='
SELECT table_schema, table_name, table_type
  FROM information_schema.tables
 WHERE table_schema NOT IN ('pg_catalog','information_schema')
 ORDER BY table_schema, table_name;

\echo
\echo '=========================================================================='
\echo '== ROW COUNTS'
\echo '=========================================================================='
DO $$
DECLARE
    rec   RECORD;
    cnt   BIGINT;
BEGIN
    FOR rec IN
        SELECT table_schema, table_name
          FROM information_schema.tables
         WHERE table_schema NOT IN ('pg_catalog','information_schema','pg_toast')
           AND table_type = 'BASE TABLE'
         ORDER BY table_schema, table_name
    LOOP
        EXECUTE format('SELECT COUNT(*) FROM %I.%I', rec.table_schema, rec.table_name)
          INTO cnt;
        RAISE NOTICE '  %.%: % rows', rec.table_schema, rec.table_name, cnt;
    END LOOP;
END $$;

\echo
\echo '=========================================================================='
\echo '== pellier.product_catalog COLUMNS (the canonical table)'
\echo '=========================================================================='
SELECT column_name, data_type,
       is_nullable, column_default,
       character_maximum_length AS max_len
  FROM information_schema.columns
 WHERE table_schema = 'pellier' AND table_name = 'product_catalog'
 ORDER BY ordinal_position;

\echo
\echo '=========================================================================='
\echo '== ALL FOREIGN KEYS (which tables reference what)'
\echo '=========================================================================='
SELECT
    tc.table_schema || '.' || tc.table_name AS from_table,
    kcu.column_name                          AS from_col,
    ccu.table_schema || '.' || ccu.table_name AS to_table,
    ccu.column_name                          AS to_col,
    rc.delete_rule                           AS on_delete
  FROM information_schema.table_constraints tc
  JOIN information_schema.key_column_usage kcu
       ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
  JOIN information_schema.constraint_column_usage ccu
       ON ccu.constraint_name = tc.constraint_name
      AND ccu.table_schema = tc.table_schema
  JOIN information_schema.referential_constraints rc
       ON rc.constraint_name = tc.constraint_name
 WHERE tc.constraint_type = 'FOREIGN KEY'
   AND tc.table_schema NOT IN ('pg_catalog','information_schema')
 ORDER BY from_table, from_col;

\echo
\echo '=========================================================================='
\echo '== ALL INDEXES (per table)'
\echo '=========================================================================='
SELECT schemaname || '.' || tablename AS table,
       indexname,
       regexp_replace(indexdef, 'CREATE (UNIQUE )?INDEX [^ ]+ ON [^ ]+ ', '') AS def
  FROM pg_indexes
 WHERE schemaname NOT IN ('pg_catalog','information_schema')
 ORDER BY schemaname, tablename, indexname;

\echo
\echo '=========================================================================='
\echo '== pellier.product_catalog brand distribution'
\echo '=========================================================================='
SELECT brand, COUNT(*) AS n
  FROM pellier.product_catalog
 GROUP BY brand
 ORDER BY n DESC;

\echo
\echo '=========================================================================='
\echo '== Hadley row sanity'
\echo '=========================================================================='
SELECT "productId", name, brand, color, price, quantity
  FROM pellier.product_catalog
 WHERE "productId" = 2;

\echo
\echo '=========================================================================='
\echo '== warehouses + warehouse_inventory snapshot'
\echo '=========================================================================='
SELECT id, display_name, city, ship_window_min || '-' || ship_window_max AS days
  FROM warehouses
 ORDER BY id;

SELECT w.id, COUNT(*) FILTER (WHERE wi.quantity = 0) AS zero_stock,
       COUNT(*) AS total_products,
       SUM(wi.quantity) AS total_units
  FROM warehouses w
  LEFT JOIN warehouse_inventory wi ON wi.warehouse_id = w.id
 GROUP BY w.id
 ORDER BY w.id;
