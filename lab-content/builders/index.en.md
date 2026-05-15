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

Workshop Studio shows **three parts**. Each part has **sublabs** (the
pages you click through in order). Part numbers (`10`, `11`, `20`…)
sort the sidebar — they are not challenge IDs.

| Part | Sublabs | Minutes | What you do |
|------|---------|---------|-------------|
| **Part I · Marco's arc** | 10 → 11 → 12 | ~26 | Setup, observe the gap, **wire `floor_check`** (one exercise) |
| **Part II · AgentCore** | 20 → 21 | ~19 | Verify STM continuity, invoke pre-launched Runtime |
| **Part III · Operator view** | 30 | ~5 | Routing patterns in the Atelier |

**Back matter:** [Appendix (SQL)](/90-appendix-shipment-sql/) · [Troubleshooting](/99-when-things-misbehave/)

### Part I · Marco's arc

Marco asks five things. Three land; Turn 4 misses because `floor_check`
is stubbed. You wire that tool; Turn 5 was already waiting.

| Sublab | Page |
|--------|------|
| 10 | [Setup — The doors are open](/10-setup-environment/) |
| 11 | [Observe — Meet Marco](/11-meet-marco/) |
| 12 | [Build — Wire `floor_check`](/12-wire-floor-check/) |

### Part II · AgentCore platform

Bootstrap provisioned memory and launched Runtime before you sat down.

| Sublab | Page |
|--------|------|
| 20 | [AgentCore Memory (STM)](/20-agentcore-memory-stm/) |
| 21 | [AgentCore Runtime (demo)](/21-agentcore-runtime/) |

### Part III · How the system routes

| Sublab | Page |
|--------|------|
| 30 | [Routing patterns](/30-routing-patterns/) |

---

### One exercise, two platforms

| You build | You observe |
|-----------|-------------|
| `floor_check` in `agent_tools.py` | STM (`AGENTCORE_MEMORY_ID`) |
| | Runtime (`agentcore_runtime.py` + `/api/agent/chat`) |
| | Dispatcher routing in Atelier |

⏩ **Short on time?**

```bash
cp solutions/closing-marcos-gap/services/agent_tools.py \
   pellier/backend/services/agent_tools.py
```

See `solutions/builders/README.md` for the paste-only tool body.

:::alert{type="info"}
**Level**  ·  400 — Expert
**Duration**  ·  60 minutes (10 min presentation · **45 min hands-on** · 5 min wrap)
**Format**  ·  Builder's Session — DC Summit
:::

![Pellier — the boutique hero, with Marco listening](/static/introduction/pellier-hero.png)

[Begin Part I · Setup →](/10-setup-environment/)
