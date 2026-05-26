---
title: "02: When things misbehave"
weight: 20
---

:::alert{type="warning"}
**Audience:** builders and facilitators  
**Use:** when something refuses to load mid-session  
**Format:** symptom first, command second
:::

Do the smallest check that explains the symptom. Do not burn five minutes debugging alone during a live Builder Session; if the first recovery path fails, raise a hand and keep the room moving.

## First 90 seconds

Run these from the Code Editor terminal.

```bash
# Backend health
curl -s http://localhost:8000/api/health | python3 -m json.tool
# Expected shape: {"status":"healthy", "database":"connected"}

# Database environment
env | grep DB_

# Catalog seeded
psql -c "SELECT count(*) FROM pellier.product_catalog;"
# Expected: 40

# Warehouse seeded
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
# Expected: ~120 rows, three warehouses × forty products

# AgentCore resources present
grep -E 'AGENTCORE_MEMORY_ID|AGENTCORE_RUNTIME_ENDPOINT' \
  /workshop/sample-pellier-agentic-search-apg/pellier/backend/.env

# Audit table reachable
psql -c "SELECT to_regclass('pellier.tool_audit') AS audit_table;"
# Expected: pellier.tool_audit

# Backend logs
tail -f /tmp/pellier/uvicorn.log
```

## By symptom

| Symptom | Likely cause | Run this |
|---|---|---|
| Boutique page is blank or returns 502 | Pellier backend did not start | `tail -n 80 /tmp/pellier/uvicorn.log` |
| Boutique loads but the `Pellier · listening` chip is missing | Frontend bundle is stale | `rebuild-frontend` |
| Hero search returns zero results | Catalog was not seeded | `psql -c "SELECT count(*) FROM pellier.product_catalog;"` |
| Marco's warehouse turn still says stock visibility is unavailable | `floor_check` body is still stubbed or the edited file has an import/syntax error | `tail -n 80 /tmp/pellier/uvicorn.log | grep -iE 'error|traceback'` |
| Atelier still shows `floor_check` as an exercise | Frontend cached the old registry state | Hard-refresh the Atelier tab |
| Anna's out-of-stock language persists after a SQL update | The update hit the wrong row or you are reading a prior turn | Re-run the `UPDATE` with exact `WHERE name = ...`, then create a new turn |
| `psql` says `no such table: pellier.warehouse_inventory` | Schema migration did not run | See [Schema migration did not run](#schema-migration-did-not-run) |
| AgentCore Memory returns no session history | `AGENTCORE_MEMORY_ID` is empty or the session id is wrong | `grep AGENTCORE_MEMORY_ID pellier/backend/.env`, then re-copy `pellier-session-id` from Local Storage |
| `/api/agent/chat` returns fallback behavior | Runtime endpoint is missing or disabled | `grep -E 'AGENTCORE_RUNTIME_ENDPOINT|USE_AGENTCORE_RUNTIME' pellier/backend/.env` |
| Act II `tool_audit` SELECT returns zero rows | The turn never ran, the session id is wrong, or the Runtime path failed before tool execution | Confirm health, re-copy session id, then fire Theo's damaged-return turn again |
| Code Editor itself returns 502 | code-server, nginx, or the EC2 host is unhealthy | Check EC2 system log or ask the facilitator for a fallback environment |

:::alert{type="info" header="Audit reminder"}
`pellier.tool_audit` records every ALLOWed tool call that actually runs, reads and writes alike. DENY decisions do not write a row because the tool never executes. A truly completed tool call with the correct `session_id` should be queryable.
:::

## Bedrock model access denied

If you see `AccessDeniedException` from Bedrock, confirm model access in `us-west-2` for the models used by Pellier: Claude Opus, Claude Haiku, Cohere Embed, and Cohere Rerank.

```bash
python3 scripts/check_model_access.py
```

## Schema migration did not run

If `pellier.product_catalog` or `pellier.warehouse_inventory` is missing, apply the base schema, reseed the catalog, then run the workshop migrations.

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

Validate:

```bash
psql -c "SELECT count(*) FROM pellier.product_catalog;"
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
psql -c "SELECT to_regclass('pellier.tool_audit');"
```

## `floor_check` still looks stubbed

Check the backend log first:

```bash
tail -n 80 /tmp/pellier/uvicorn.log | grep -iE 'error|traceback|floor_check'
```

Common causes:

- The code was pasted outside the challenge markers.
- A Python `SyntaxError` stopped uvicorn from importing `agent_tools.py`.
- The tool body calls a name that is not imported.
- The browser is showing a cached Atelier registry.

Short on time:

```bash
cd /workshop/sample-pellier-agentic-search-apg
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
   pellier/backend/services/agent_tools.py
```

## `tool_audit` SELECT returns zero rows

First confirm you are querying the right session id. Then force a known policy-allowed tool path:

```bash
curl -sN -X POST http://localhost:8000/api/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "My Wabi-Sabi Bowl arrived chipped. Please file a damaged return for Theo.",
    "session_id": "builders-ledger-check"
  }'
```

Then query:

```sql
SELECT created_at, session_id, tool, args, result, latency_ms
FROM pellier.tool_audit
WHERE session_id = 'builders-ledger-check'
ORDER BY created_at DESC
LIMIT 10;
```

If rows are still missing, the tool never executed. Check Runtime health and the backend log before debugging SQL.

## Refresh the catalog: the shipment that just arrived

Optional follow-on, best after the main session. Anna's Beeswax Tapers story is a one-row catalog update; the next search turn picks it up without redeploying.

```bash
psql -c "SELECT \"productId\", name, quantity FROM pellier.product_catalog WHERE name ILIKE '%beeswax%';"
```

Use the exact product name returned by the query:

```sql
UPDATE pellier.product_catalog
   SET quantity = 24
 WHERE name = 'Beeswax Taper Candles';
```

Switch to Anna in the Boutique and re-run the beeswax prompt. In-stock language should return on the next turn.

## Last resort

```bash
sudo systemctl restart pellier
sleep 8
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

For Builder environments without a `pellier` systemd unit:

```bash
start-backend
```

If the health check still fails, ask the table lead for a fallback environment. Keep moving; the lab is designed with escape hatches.
