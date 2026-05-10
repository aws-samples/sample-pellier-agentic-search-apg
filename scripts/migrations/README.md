# Workshop telemetry migrations

Idempotent SQL migrations for the DAT406 `/workshop` telemetry surface.
Numbered in apply order; running a migration twice is a no-op.

## Apply order

1. **`001_workshop_telemetry.sql`** — creates the 6 tables the
   `/workshop` surface reads/writes (`agent_trace_spans`, `tools`,
   `tool_audit`, `customers`, `orders`, `approvals`) plus a `pg_cron`
   24h TTL job on `agent_trace_spans`. Depends on
   `scripts/seed-database.sh` having run first (the `orders` FK points
   at `pellier.product_catalog`).
2. **`002_workshop_seed.sql`** — seeds 8 demo customers + ~32 orders
   with intentional cohort overlap so the `MEMORY · PROCEDURAL`
   showcase panel returns interesting rows. Uses `WHERE EXISTS` guards
   so it's safe against stripped-down catalog loads that lack some
   product ids.
3. **`003_workshop_episodic_seed.sql`** — creates `customer_episodic_seed`
   (the AgentCore Memory **offline fallback** for episodic recall) and
   seeds 3 episodes per demo customer. Backs the Atelier's
   welcome-back `POST /api/workshop/resume` turn — pick a seeded
   customer from the chat's "shop as" picker with no prior session
   and the `MEMORY · EPISODIC` panel reads from here.

## Run

```sh
# From repo root, with .env loaded:
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
    -U "$DB_USER" -d "$DB_NAME" \
    -f scripts/migrations/001_workshop_telemetry.sql

PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
    -U "$DB_USER" -d "$DB_NAME" \
    -f scripts/migrations/002_workshop_seed.sql

PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
    -U "$DB_USER" -d "$DB_NAME" \
    -f scripts/migrations/003_workshop_episodic_seed.sql
```

Both files `\set ON_ERROR_STOP on` so a CI wrapper gets a non-zero
exit on failure.

## `pg_cron` note

If `pg_cron` isn't installed, 001 emits a `WARNING` and continues —
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

SELECT cron.jobid, cron.jobname FROM cron.job
WHERE jobname = 'cleanup_trace_spans';  -- 1 row when pg_cron installed
```
