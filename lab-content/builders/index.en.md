---
title: "DAT4XX | Build Agentic AI-Powered Search with Amazon Aurora and Amazon Bedrock AgentCore"
weight: 0
---

## *Welcome to Pellier.*

Pellier is a small editorial boutique with one quiet promise — a
shopper asks for something in their own words, and the right pieces
find them. Behind that promise sits Aurora pgvector search, Strands
specialists, **AgentCore Memory (STM)**, and an **AgentCore Runtime**
you'll invoke — not cold-deploy in the room.

In the next sixty minutes: about ten minutes of framing, **forty-five
minutes of hands-on**, five minutes to close.

---

## How this lab is organized

Workshop Studio shows a handful of pages, but the Builder's Session
has **two acts**:

1. **Build the missing capability** — observe Marco's gap, wire
   `floor_check`, then prove Anna's hybrid + rerank path.
2. **Read the platform around it** — verify AgentCore Memory, invoke
   Runtime, and close with the operator routing view.

Numbers (`10`, `11`, `20`…) only sort the sidebar. They are not extra
modules or extra coding exercises.

| Act | Pages | Minutes | What you do |
|------|-------|---------|-------------|
| **Act I · Build + prove** | 10 → 11 → 12 → 13 | ~35 | Setup, observe Marco's gap, **wire `floor_check`**, then prove rerank earns its cost |
| **Act II · Platform + operator view** | 20 → 21 → 30 | ~15 | Verify STM continuity, invoke pre-launched Runtime, read routing in the Atelier |

**Back matter:** [Appendix (SQL)](/90-appendix-shipment-sql/) · [Troubleshooting](/99-when-things-misbehave/)

### Act I · Build + Prove

Marco asks five things. First, you read the anatomy of the agent that answers
him: model, instructions, skills, tools, state, and telemetry. Three turns
land; Turn 4 misses because `floor_check` is stubbed. You wire that tool;
Turn 5 was already waiting. Then Anna asks a messier gift query and you prove
whether hybrid + rerank is worth the latency and cost.

| Page | What opens |
|------|------------|
| 10 | [Setup — The doors are open](/10-setup-environment/) |
| 11 | [Observe — Meet Marco](/11-meet-marco/) |
| 12 | [Build — Wire `floor_check`](/12-wire-floor-check/) |
| 13 | [Measure — Prove rerank earns its cost](/13-prove-rerank/) |

### Act II · Platform + Operator View

Bootstrap provisioned Memory and launched Runtime before you sat down.
You are not building another module here; you are reading the production
shape around the capability you just wired.

| Page | What opens |
|------|------------|
| 20 | [AgentCore Memory (STM)](/20-agentcore-memory-stm/) |
| 21 | [AgentCore Runtime (demo)](/21-agentcore-runtime/) |
| 30 | [Routing patterns](/30-routing-patterns/) |

---

### One Build, Two Proofs

| You build / prove | You observe |
|-----------|-------------|
| `floor_check` in `agent_tools.py` | STM (`AGENTCORE_MEMORY_ID`) |
| Anna's retrieval comparison in Atelier | Runtime (`agentcore_runtime.py` + `/api/agent/chat`) |
| | Dispatcher routing in Atelier |

⏩ **Short on time?**

```bash
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
   pellier/backend/services/agent_tools.py
```

Paste-only option: `solutions/closing-marcos-gap/services/floor_check_tool_body.py`.

:::alert{type="info"}
**Level**  ·  400 — Expert
**Duration**  ·  60 minutes (10 min presentation · **45 min hands-on** · 5 min wrap)
**Format**  ·  Builder's Session — DC Summit
:::

![Pellier — the boutique hero, with Marco listening](/static/introduction/pellier-hero.png)

[Begin Act I · Setup →](/10-setup-environment/)
