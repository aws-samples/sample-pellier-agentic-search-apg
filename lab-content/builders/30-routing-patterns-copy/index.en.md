---
title: "Act II · Operator View — Routing Patterns"
weight: 30
---

:::alert{type="info"}
**Act II · Platform + operator view.** About four minutes. No code —
how the Boutique picks a specialist, and where AgentCore fits.*
:::

In the one-hour session, keep this page tight (4-5 minutes): confirm the two
routers model, then close with takeaways instead of deep architecture debate.

## Open Routing in the Atelier

Click **Routing** under **UNDERSTAND**.

Three orchestration patterns ship. Only one is **active** for the storefront.

---

## Production storefront: Dispatcher + specialists

The Boutique (`/api/chat/stream`, pattern `dispatcher`) uses:

1. **`classify_triage`** — deterministic greetings / meta / thanks (no LLM)
2. **`classify_intent`** — keyword rules in `services/chat.py` (no LLM)
3. **One specialist** — Strands agent + tools, usually temperature 0 on reports

**Why this pattern for e-commerce concierge:**

- **Predictable** — Marco's pills route the same way every demo
- **Fast** — no router LLM; classification is ~60–120 ms
- **Cheap** — one model call per turn
- **Auditable** — intent → specialist is visible in logs and Atelier

Scroll to **What you type maps to one specialist** — that's the literal
keyword map from code.

---

## Two routers, one turn

Pellier runs two different routing decisions in sequence:

1. **Intent router** (`classify_intent` in `services/chat.py`) picks the
   specialist (`search`, `pricing`, `inventory`, `support`, or `recommendation`).
2. **Skill router** (`POST /api/atelier/skills/route`) decides whether to
   inject persona overlays like `the-gift-table` into that specialist's prompt.

Use this mental model in reviews:

- Wrong specialist = intent-router issue.
- Right specialist, wrong voice/framing = skill-router issue.

---

## When to use the other patterns

| Pattern | Where | Use when |
|---------|-------|----------|
| **Agents-as-Tools** | Atelier mode strip / `/api/agent/chat` in-process | Teaching multi-agent routing; Haiku orchestrator + specialists as `@tool` |
| **Graph** | Atelier telemetry | Multi-step workflows with explicit edges |
| **AgentCore Runtime** | `/api/agent/chat` + `USE_AGENTCORE_RUNTIME=true` | Same orchestrator, managed microVM, ops-owned deploy |
| **Gateway semantic search** | Tools discovery card | Hundreds of tools — embed descriptions, don't stuff every tool in prompt |

**Industry upgrade path** when keywords aren't enough:

```text
triage (rules) → intent (rules) → low confidence? → small classifier or Haiku T=0
                              → else → one specialist (one LLM call)
```

Use **embedding-based tool discovery** for catalog-scale capabilities — not
as the default per-turn router for curated storefront intents.

---

## Capstone

Replay Marco's Turn 4 in the Boutique. Open **Sessions → marco-midpoint-checkpoint**
if your table finished section 02. Note **Performance**: Haiku stock turn ~150 ms
vs Opus editorial turns ~1.0–1.4 s — same architecture lesson, two surfaces.

[Optional SQL appendix →](/90-appendix-shipment-sql/) · [When things misbehave →](/99-when-things-misbehave/)
