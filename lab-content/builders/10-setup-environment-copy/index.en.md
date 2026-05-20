---
title: "Act I · Setup — The Doors Are Open"
weight: 10
---

:::alert{type="info"}
**Act I · Build + prove.** About five minutes — step in, verify the
lights are on, and confirm AgentCore ids in `.env`. The whole session
has one core coding exercise (`floor_check`) plus one short coding extension
(Anna skill edit).*
:::

## 60-minute facilitator flow (code-first)

For a one-hour Builder's Session, use this page as the pacing source of truth.
Participants should spend most of their time in code, not prose.

| Time | Segment | Mode |
| --- | --- | --- |
| 0-5 min | Setup + health checks (this page) | Read + terminal |
| 5-12 min | Marco pills + identify the gap (`11-meet-marco`) | Click + observe |
| 12-30 min | Wire `floor_check` (`12-wire-floor-check`) | **Code** |
| 30-40 min | Verify in Boutique/Atelier + Anna rerank proof (`13-prove-rerank`) | Test + compare |
| 40-48 min | **Second coding moment:** edit `skills/the-gift-table/SKILL.md`, re-run Anna, verify chips + SQL | **Code** |
| 48-55 min | Routing + Runtime skim (`30`, `21`) | Operator view |
| 55-60 min | Debrief: model mix, tool wiring, skill overlays, DB tradeoffs | Group close |

Target ratio for this format: **~40 minutes hands-on code/verification, ~20 minutes reading/discussion**.

## Step in

Open your **Event Outputs** tab on the Workshop Studio dashboard and
click **CodeEditorUrl**. Code Editor opens in a new browser tab —
Workshop Studio handled the sign-in for you, so you land directly
in the IDE.

A welcome terminal opens automatically with the workshop layout and
a few aliases (`workshop`, `pellier`, `backend`, `frontend`, `psql`).

The Boutique itself runs in demo mode for the next sixty minutes —
no login screen. You'll switch between Marco, Anna, and Theo by
picking a persona in the chat drawer; that's the same UI control a
returning shopper would use after signing in.

---

## Verify the lights are on

The Aurora cluster, the FastAPI backend, the React frontend, and the
AgentCore memory are already running. The boot path provisioned
everything before you sat down. Let's confirm.

### The backend

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
grep -E 'AGENTCORE_MEMORY_ID|AGENTCORE_RUNTIME_ENDPOINT|USE_AGENTCORE_RUNTIME' \
  /workshop/sample-pellier-agentic-search-apg/pellier/backend/.env || true
```

You should see `AGENTCORE_MEMORY_ID` set. If bootstrap launched Runtime,
`AGENTCORE_RUNTIME_ENDPOINT` and `USE_AGENTCORE_RUNTIME=true` appear too.

You should see:

```json
{"status": "healthy", "database": "connected"}
```

### The catalog

```bash
psql -c "SELECT count(*) FROM pellier.product_catalog;"
```

You should see **40**. That's the boutique — ten pieces per persona,
each with a Cohere Embed v4 vector and an HNSW index.

### The boutique

In Code Editor, open the **Ports** tab in the bottom panel. Click the
forwarded address next to port **8000**. The Pellier storefront
opens in a new tab — a full-bleed editorial photograph with a search
bar floating over the cream wall, and a small *Pellier · listening*
chip pulsing in the upper-left corner of the hero.

That pulse is the agent. It means it's awake.

---

## Two surfaces, one system

Pellier ships as two surfaces that share one agent.

The **Boutique** (port 8000) is the shopper-facing storefront. It's
what Marco sees when he opens his laptop on a Sunday morning.

The **Atelier** is the operator's surface. Same domain, different
route — visit `/atelier`. It's where you watch the agent think:
which tools it called, which memory it recalled, which agent it
handed off to.

Open the Atelier in a second browser tab now. Keep both open for
the rest of the session — you'll cross between them constantly.

::::expand{header="What you have in your IDE"}

- **Aurora MCP Server** — browse the `pellier.product_catalog`
  schema, inspect columns, query the embedding column directly from
  the MCP sidebar.
- **Amazon Q** — AI-assisted code completion in your sidebar.
  Optional, not required — the lab guides don't depend on it.
- **Auto-reload** — every save to a `.py` file restarts the backend
  in about a second. No manual restart commands.

::::

---

## Pre-flight checklist

| Check | Expected |
| --- | --- |
| Code Editor | Open in a browser tab |
| Backend health | `curl localhost:8000/api/health` returns `healthy` |
| Catalog count | `psql -c "SELECT count(*) FROM pellier.product_catalog;"` returns 40 |
| Boutique | Loads on port 8000, hero displays "Search, re:Engineered." |
| Atelier | Loads at `/atelier`, sidebar shows OBSERVE / UNDERSTAND / EVALUATE |

If any check fails, jump to [99 · When Things Misbehave](/99-when-things-misbehave/)
and rejoin the rest of the table when you're back.

:::alert{type="success" header="You're in"}
Next: meet Marco and watch where the system breaks.

[Act I · Meet Marco →](/11-meet-marco/)
:::
