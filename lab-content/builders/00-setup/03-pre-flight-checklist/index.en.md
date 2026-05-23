---
title: "Pre-flight checklist"
weight: 30
---

:::alert{type="info"}
**Setup.** About one minute. Confirm the lights are on before Marco walks in.
:::

Run these five checks in your Code Editor terminal. If any one
fails, jump to [When things misbehave](/90-appendix/03-when-things-misbehave/)
and rejoin the workshop flow when you're back.

## 1 · Backend health

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

Expect:

```json
{"status": "healthy", "database": "connected"}
```

## 2 · Catalog seeded

```bash
psql -c "SELECT count(*) FROM pellier.product_catalog;"
```

Expect **40** — ten pieces per persona, each with a Cohere Embed v4
vector and an HNSW index.

## 3 · Warehouse seeded

```bash
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
```

Expect **~120** — three warehouses (`BK-01`, `ATX-02`, `PDX-01`) ×
40 products.

## 4 · AgentCore Memory id

```bash
grep -E 'AGENTCORE_MEMORY_ID|AGENTCORE_RUNTIME_ENDPOINT' \
  /workshop/sample-pellier-agentic-search-apg/pellier/backend/.env
```

Expect a non-empty `AGENTCORE_MEMORY_ID`. If `AGENTCORE_RUNTIME_ENDPOINT`
is also present, Runtime is launched too — that's a bonus, not a
requirement.

## 5 · Bedrock model access

```bash
python3 scripts/check_model_access.py
```

Verifies all four Bedrock models the lab calls are reachable from this
account and region:

| Model | Used for |
|---|---|
| `global.anthropic.claude-opus-4-6-v1` | Editorial specialists (Style Advisor, Curator, Experience Guide) |
| `global.anthropic.claude-haiku-4-5-20251001-v1:0` | Reporting specialists (Value Analyst, Stock Keeper) |
| `us.cohere.embed-v4:0` | 1024-dim catalog embeddings |
| `cohere.rerank-v3-5:0` | Cross-encoder rerank on hybrid retrieval |

**This is the most common live failure** — Bedrock model access is
account-and-region scoped. If a row reports `AccessDeniedException`,
the [When things misbehave](/90-appendix/03-when-things-misbehave/)
runbook has the one-click console step to enable it.

## All five green

| Check | Expected |
| --- | --- |
| Backend health | `healthy` |
| Catalog count | 40 |
| Warehouse count | ~120 |
| `AGENTCORE_MEMORY_ID` | Non-empty |
| Bedrock model access | All four green |

:::alert{type="success" header="You're in"}
Next: meet Marco and watch where the system breaks.

[Act I · Meet Marco →](/10-act-1-the-boutique/01-meet-marco/)
:::
