---
title: "When things misbehave"
weight: 30
---

:::alert{type="warning"}
*A short runbook. Find your symptom in the left column, run the
command in the right.*
:::

## Quick fixes

Services auto-restart on file save — no manual restart needed for
ordinary edits. Most issues resolve with one of these:

```bash
# Verify the backend is healthy
curl -s http://localhost:8000/api/health | python3 -m json.tool
# Expected: {"status":"healthy","database":"connected"}

# Verify database connection
env | grep DB_

# Verify the catalog seeded
psql -c "SELECT count(*) FROM pellier.product_catalog;"
# Expected: 40

# Verify the warehouse table exists (for Act I · floor_check)
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
# Expected: ~120 (one row per warehouse × product; 3 warehouses × 40 catalog SKUs)

# Tail the Builder backend logs
tail -f /tmp/pellier/uvicorn.log

# If the frontend is stale after an edit
rebuild-frontend   # npm run build + restart app (no sudo — builders: uvicorn; workshop: systemctl)
```

## By symptom

| Symptom | What's likely | Run this |
| --- | --- | --- |
| Boutique page is blank / 502 | Pellier service didn't start | `tail -n 80 /tmp/pellier/uvicorn.log` |
| Boutique loads but `Pellier · listening` chip is missing | Frontend bundle is stale | `rebuild-frontend` |
| Hero search returns 0 results | Catalog never seeded | `psql -c "SELECT count(*) FROM pellier.product_catalog;"` — if 0, see *Catalog empty* below |
| Marco's turn 4 still says "I can't see the warehouse" after you wired `floor_check` | Tool import error or stub body still in place | `tail -n 80 /tmp/pellier/uvicorn.log` |
| Atelier `/atelier/agents` shows Stock Keeper still dashed | Frontend cached the old agent registry | Hard-reload the Atelier tab |
| Anna's "out of stock" message persists after the SQL UPDATE | The UPDATE hit the wrong row, or you are still viewing a stale prior response | Re-run the UPDATE with an exact `WHERE name = ...`; click the pill again to create a new turn |
| `psql` says "no such table `pellier.warehouse_inventory`" | Schema migration didn't run | See *Schema migration didn't run* below |
| Code Editor URL itself 502s | EC2 / nginx / code-server didn't start | EC2 console → instance → *Get system log*; check `/var/log/cloud-init-output.log` |
| AgentCore memory.recall returns nothing for any persona | `AGENTCORE_MEMORY_ID` empty in `.env` | `grep AGENTCORE_MEMORY_ID /workshop/sample-pellier-agentic-search-apg/pellier/backend/.env` |

## Catalog empty

If `SELECT count(*) FROM pellier.product_catalog` returns 0 but the
table exists, the seeder ran into a Bedrock throttle or the
embedding model wasn't accessible from this account. Re-run the
seeder by hand:

```bash
cd /workshop/sample-pellier-agentic-search-apg
set -a && source .env && set +a
python3 scripts/seed_boutique_catalog.py 2>&1 | tee /tmp/seed.log
```

If it fails with `AccessDeniedException` from Bedrock, double-check
that **Cohere Embed v4** and **Cohere Rerank v3.5** model access is
granted in the Bedrock console for `us-west-2`.

## Schema migration didn't run

If `pellier.warehouse_inventory` (or `pellier.product_catalog`)
doesn't exist, the schema migration didn't fire. Apply the base schema,
re-run the seeder, then apply the warehouse migration:

```bash
cd /workshop/sample-pellier-agentic-search-apg
PGPASSWORD="$DB_PASSWORD" psql \
    -h "$DB_HOST" -p "$DB_PORT" \
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
    007_chat_session_tables.sql
do
    PGPASSWORD="$DB_PASSWORD" psql \
        -h "$DB_HOST" -p "$DB_PORT" \
        -U "$DB_USER" -d "$DB_NAME" \
        -v ON_ERROR_STOP=1 \
        -f "scripts/migrations/$migration"
done
```

Then verify `SELECT count(*) FROM pellier.warehouse_inventory;` returns
about 120 rows.

## Pellier service won't start

```bash
# Last 50 lines of the Builder uvicorn log
tail -50 /tmp/pellier/uvicorn.log
```

Common causes:

- A Python `SyntaxError` in a file you edited — the message points at
  the line. Fix and save; uvicorn auto-reloads.
- `agent_tools.py` imports a name that doesn't exist — the traceback
  ends with `ImportError`. Compare your `floor_check` signature
  against the docstring in the stub.
- The frontend build failed in `ExecStartPre` — usually a TypeScript
  error. For Workshop environments, run `journalctl -u pellier -n 80 --no-pager`
  and look for `error TS`.

## Last resort — full restart (Workshop images)

```bash
sudo systemctl restart pellier
sleep 8
curl -s http://localhost:8000/api/health
```

For Builder environments that do not expose a `pellier` systemd unit, use:

```bash
start-backend
```

If the curl still fails, your table lead has a fallback environment
they can switch you to. Don't burn five minutes debugging — raise a
hand and they'll move you over while you keep going on the lab.
