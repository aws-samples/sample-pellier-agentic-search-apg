---
title: "Run pre-flight checks"
weight: 20
---

:::alert{type="info"}
**Time:** ~4 min  
**Goal:** run five checks before Act I.
:::

Run each command in the Code Editor terminal. If a check fails, use [When things misbehave](/90-appendix/03-when-things-misbehave/) and rejoin the flow once the signal is green.

## Check 1: Backend health

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

Expect a healthy status and a connected database.

## Check 2: Catalog seeded

```bash
psql -c "SELECT count(*) FROM pellier.product_catalog;"
```

Expect **40** products.

## Check 3: Warehouse seeded

```bash
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
```

Expect about **120** rows: three warehouses × forty products.

## Check 4: AgentCore resources present

```bash
grep -E 'AGENTCORE_MEMORY_ID|AGENTCORE_RUNTIME_ENDPOINT' \
  /workshop/sample-pellier-agentic-search-apg/pellier/backend/.env
```

`AGENTCORE_MEMORY_ID` should be non-empty. Runtime is a bonus if the endpoint is present.

## Check 5: Audit ledger reachable

```bash
psql -c "SELECT to_regclass('pellier.tool_audit') AS audit_table;"
```

Expect `pellier.tool_audit`. It may be empty; Act II creates the row.

## Key takeaways

- The catalog, warehouse, memory id, and audit table are the readiness proof points.
- Empty data is not the same as missing infrastructure.
- Once these are green, move on. Tiny pre-flight, big payoff.

::::alert{type="success" header="You're in"}
[Act I: Meet Marco →](/10-act-1-the-boutique/01-meet-marco/)
::::
