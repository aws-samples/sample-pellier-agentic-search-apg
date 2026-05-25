---
title: "Facilitator pre-flight"
weight: 60
---

:::alert{type="info"}
**Audience:** table leads and SAs running this 60-minute session.
**Builders no longer run pre-flight in-room** — these checks belong to whoever opens the room. The CFN bootstrap should already pass all five; this page is the hand-verification path.
:::

Run before the room opens. If any check fails, jump to [When things misbehave](../03-when-things-misbehave/) before letting builders in.

## Check 1: Backend health

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

Expect a healthy status and a connected database.

## Check 2: Catalog seeded

```bash
psql -c "SELECT count(*) FROM pellier.product_catalog;"
```

Expect **40** products (ten pieces per persona, each with a Cohere Embed v4 vector and an HNSW index).

## Check 3: Warehouse seeded

```bash
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
```

Expect about **120** rows: three warehouses (`BK-01`, `ATX-02`, `PDX-01`) × forty products.

## Check 4: AgentCore resources present

```bash
grep -E 'AGENTCORE_MEMORY_ID|AGENTCORE_RUNTIME_ENDPOINT' \
  /workshop/sample-pellier-agentic-search-apg/pellier/backend/.env
```

`AGENTCORE_MEMORY_ID` should be non-empty. Runtime endpoint is a bonus.

## Check 5: Audit ledger reachable

```bash
psql -c "SELECT to_regclass('pellier.tool_audit') AS audit_table;"
```

Expect `pellier.tool_audit`. It may be empty until Act II creates a row.

## All five green

Open the room. Builders land in [Setup](/00-setup/), open Boutique + Atelier, and head straight into Act I.
