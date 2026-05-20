# Pellier fresh-cluster migrations

Idempotent SQL migrations for the Builder's Session and workshop app.
Numbered in apply order; running a migration twice is safe.

## Apply order

1. **`001_schema.sql`** — creates `vector`, the `pellier` schema,
   `pellier.product_catalog`, the HNSW index, and the `updated_at`
   trigger. Run before `scripts/seed_boutique_catalog.py`.
2. **`002_workshop_telemetry.sql`** — creates telemetry, tool registry,
   audit, customer, order, and approval tables. Run after the catalog
   seed because `orders.product_id` references `pellier.product_catalog`.
3. **`003_persona_seed.sql`** — seeds Marco / Anna / Theo / Fresh
   customers, persona order history, and `customer_episodic_seed`.
   Theo's return flow depends on the Wabi-Sabi Bowl order here.
4. **`004_anna_hybrid_search.sql`** — adds the generated `tsvector`
   column and GIN index for Anna's Postgres FTS branch.
5. **`005_theo_returns.sql`** — creates the `returns` table for Theo's
   write path.
6. **`006_warehouse_inventory.sql`** — creates `pellier.warehouses` and
   `pellier.warehouse_inventory` for Marco's `floor_check` exercise.
7. **`007_chat_session_tables.sql`** — creates chat/session persistence
   tables in the `pellier` schema.
8. **`008_search_performance_indexes.sql`** — adds `pg_trgm` + GIN trigram
   indexes on `lower(name)` and `lower(category)` for fuzzy ILIKE paths.

## Run

```sh
# From repo root, with .env loaded:
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
    -U "$DB_USER" -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 \
    -f scripts/migrations/001_schema.sql

python3 scripts/seed_boutique_catalog.py

for migration in \
    002_workshop_telemetry.sql \
    003_persona_seed.sql \
    004_anna_hybrid_search.sql \
    005_theo_returns.sql \
    006_warehouse_inventory.sql \
    007_chat_session_tables.sql \
    008_search_performance_indexes.sql
do
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
        -U "$DB_USER" -d "$DB_NAME" \
        -v ON_ERROR_STOP=1 \
        -f "scripts/migrations/$migration"
done
```

Every file sets `ON_ERROR_STOP`, and bootstrap also passes
`-v ON_ERROR_STOP=1`, so failures stop the setup.

## `pg_cron` note

If `pg_cron` isn't installed, `002_workshop_telemetry.sql` emits a
`WARNING` and continues —
`agent_trace_spans` will then grow unbounded unless the workshop
operator schedules a cleanup out-of-band. To install:

```sql
CREATE EXTENSION pg_cron;  -- must run in postgres database as superuser
```

## Testing

Nothing in the test suite invokes these scripts directly yet. Week 1
verifies via:

```sql
\dt customers
\dt orders
\dt agent_trace_spans
\dt tools
\dt tool_audit
\dt approvals

SELECT COUNT(*) FROM pellier.product_catalog;      -- 40
SELECT COUNT(*) FROM customers;                    -- at least 5
SELECT COUNT(*) FROM orders;                       -- at least 20
SELECT COUNT(*) FROM customer_episodic_seed;       -- 9
SELECT COUNT(*) FROM pellier.warehouse_inventory;  -- 120
```
