---
title: "99 · When Things Misbehave"
weight: 99
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

# Verify the warehouse table exists (for Part I · sublab 12)
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
# Expected: ~120 (one row per warehouse × product; 3 warehouses × 40 catalog SKUs)

# Tail the backend logs
journalctl -fu pellier
# Builder's Session (uvicorn via nohup): tail -f /tmp/pellier/uvicorn.log

# If the frontend is stale after an edit
rebuild-frontend   # npm run build + restart app (no sudo — builders: uvicorn; workshop: systemctl)
```

## By symptom

| Symptom | What's likely | Run this |
| --- | --- | --- |
| Boutique page is blank / 502 | Pellier service didn't start | `journalctl -u pellier --since '5 min ago'` |
| Boutique loads but `Pellier · listening` chip is missing | Frontend bundle is stale | `rebuild-frontend` |
| Hero search returns 0 results | Catalog never seeded | `psql -c "SELECT count(*) FROM pellier.product_catalog;"` — if 0, see *Catalog empty* below |
| Marco's turn 4 still says "I can't see the warehouse" *after* you wired Stock Keeper | Tool import error | `journalctl -u pellier \| grep -i error` |
| Atelier `/atelier/agents` shows Stock Keeper still dashed | Frontend cached the old agent registry | Hard-reload the Atelier tab |
| Anna's "out of stock" message persists after the SQL UPDATE | The UPDATE hit the wrong row, or the agent cached the answer | Re-run the UPDATE; click the same pill again |
| `psql` says "no such table `pellier.warehouse_inventory`" | Schema migration didn't run | See *Schema migration didn't run* below |
| Code Editor URL itself 502s | EC2 / nginx / code-server didn't start | EC2 console → instance → *Get system log*; check `/var/log/cloud-init-output.log` |
| AgentCore memory.recall returns nothing for any persona | `AGENTCORE_MEMORY_ID` empty in `.env` | `cat /workshop/sample-pellier-agentic-search-apg/.env \| grep AGENTCORE_MEMORY_ID` |

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
doesn't exist, the schema migration didn't fire. Apply it by hand:

```bash
cd /workshop/sample-pellier-agentic-search-apg
PGPASSWORD="$DB_PASSWORD" psql \
    -h "$DB_HOST" -p "$DB_PORT" \
    -U "$DB_USER" -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 \
    -f scripts/migrations/000_pellier_schema.sql
```

Then re-run the seeder (above).

## Pellier service won't start

```bash
# What does systemd think?
systemctl status pellier

# Last 50 lines of the service log
journalctl -u pellier -n 50

# The uvicorn log (separate file)
tail -50 /tmp/pellier/uvicorn.log
```

Common causes:

- A Python `SyntaxError` in a file you edited — the message points at
  the line. Fix and save; uvicorn auto-reloads.
- `agent_tools.py` imports a name that doesn't exist — the traceback
  ends with `ImportError`. Compare your `floor_check` signature
  against the docstring in the stub.
- The frontend build failed in `ExecStartPre` — usually a TypeScript
  error. Look for `error TS` in the journalctl output.

## Last resort — full restart

```bash
sudo systemctl restart pellier
sleep 8
curl -s http://localhost:8000/api/health
```

If the curl still fails, your table lead has a fallback environment
they can switch you to. Don't burn five minutes debugging — raise a
hand and they'll move you over while you keep going on the lab.
