-- Migration 009: Rename schema blaize_bazaar → pellier
--
-- After the Blaize Bazaar → The Pellier brand rename, all backend SQL
-- references the schema as `pellier.product_catalog`. Aurora still
-- holds the old schema name `blaize_bazaar`. This migration renames
-- the schema in place.
--
-- Idempotent: checks for the old schema before renaming. If
-- `pellier` already exists (someone ran this before, or a fresh DB
-- was seeded directly into `pellier`), this is a no-op.
--
-- Safety: ALTER SCHEMA RENAME is a metadata-only operation. It does
-- not move data. All FK references, views, triggers, and indexes
-- defined against the schema follow automatically because Postgres
-- stores them by schema OID, not by name. The only thing that breaks
-- is hard-coded SQL strings that name the old schema — and the code
-- rename has already updated those.
--
-- After this migration runs, every existing row in
-- product_catalog/orders/customers/etc. is reachable via
-- `pellier.<table>` and the live boutique resumes working.
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/009_rename_schema_to_pellier.sql

\set ON_ERROR_STOP on

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.schemata
        WHERE schema_name = 'blaize_bazaar'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.schemata
        WHERE schema_name = 'pellier'
    ) THEN
        ALTER SCHEMA blaize_bazaar RENAME TO pellier;
        RAISE NOTICE 'Renamed schema blaize_bazaar → pellier';
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.schemata
        WHERE schema_name = 'pellier'
    ) THEN
        RAISE NOTICE 'Schema pellier already exists — skipping rename';
    ELSE
        RAISE EXCEPTION 'Neither blaize_bazaar nor pellier schema exists; nothing to rename';
    END IF;
END $$;

-- Quick visibility on what landed.
DO $$
DECLARE
    tablecount INTEGER;
BEGIN
    SELECT COUNT(*) INTO tablecount
      FROM information_schema.tables
     WHERE table_schema = 'pellier';
    RAISE NOTICE 'pellier schema now contains % tables', tablecount;
END $$;
