---
title: Blaize Bazaar — Builder's Session (60 min)
weight: 10
---

**Level 400 · 60 minutes · DC Summit**

Welcome. In one hour you'll author the system prompt for a real specialist agent, wire the one tool that closes a shopper's gap, and walk through the operator-facing Atelier where every decision the agent stack makes is visible.

Not a tutorial. Not a sandbox. A real build.

## What you'll build (honest scope)

Two artifacts of participant-authored code:

- **Stock Keeper** — one of Blaize's five specialists. You'll author its system prompt (Haiku 4.5 at 0.0 — tightest config in the system).
- **`floor_check`** — the tool that makes Marco's Turn 4 warehouse question land.

Three more tools (`restock_shelf`, `running_low`) and the second specialist (Experience Guide) come pre-wired — you'll see them running in the Atelier but won't build them. That's the 2-hour Workshop. This is the 60-minute cut.

## The narrative

Marco shops Blaize Bazaar. Asks four questions. Three land — Style Advisor, Curator, Value Analyst. The fourth — "Is the Pellier shirt at the Brooklyn warehouse?" — gets a graceful non-answer because Stock Keeper ships in stub state.

**That's the build.** When you wire Stock Keeper + `floor_check`, the same question returns a real warehouse breakdown. Marco's gap closes. You flip to the Atelier and watch the routing arrow turn solid.

See [`../shared/marco-arc-overview.en.md`](../shared/marco-arc-overview.en.md) for the full script.

## Shape of the hour

| Slot | Minutes | What |
|---|---|---|
| Opening talk + Boutique demo | 10 | Participants click Marco's 4 hero pills; presenter narrates model/agent/tool per turn |
| **Module 1 · Observe** | 5 | Quick tour of the Atelier + model-mix sidebar |
| **Module 2 · Understand** | 25 | Build Stock Keeper + `floor_check`. Midpoint checkpoint inside this slot. |
| **Module 3 · Evaluate** | 10 | Performance deep-dive + Experience Guide code read |
| Capstone + Q&A | 10 | 5-turn Marco capstone (click pills, presenter narrates) + Q&A |

## How you verify

Two paths:

1. **`pytest` is the fast loop.** Run after each save — green means the logic works. No frontend needed.
2. **Boutique + Atelier is the victory lap.** Click Marco's Turn 4 pill, flip to Atelier, watch the panels update.

## The escape hatch

Every challenge has a ⏩ **Short on time?** `cp` command that drops a solution file into place:

```bash
cp solutions/module2/agents/inventory_agent.py \
   blaize-bazaar/backend/agents/inventory_agent.py
```

Use it. The goal is the midpoint checkpoint — not to type every character manually.

## Prerequisites

- Python fluency (async/await, imports, light typing)
- LLM comfort (temperature, system prompts, tool use)
- Basic AWS awareness

Next: [Setup](00-setup.en.md)
