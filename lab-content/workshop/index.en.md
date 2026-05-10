---
title: Pellier — Agentic Composition Workshop
weight: 0
---

**Level 400 · 120 minutes · re:Invent 2026**

Welcome. For the next two hours you'll build inside a working agentic system — not a toy, not a sandbox. Pellier is a real boutique with a real catalog, a real agent stack, and a real operator-facing Atelier where every decision the system makes is visible. You'll leave having closed a specific gap in Marco's shopping journey, and you'll see the architectural reasoning behind model selection, skill loading, memory, and guardrails light up in the panels as you work.

## What you'll build

By the end of 120 minutes you'll have shipped:

- **Stock Keeper** — one of five boutique specialists. You'll author its system prompt and wire all three of its tools (`floor_check`, `restock_shelf`, `running_low`).
- **Experience Guide** — another full specialist build. You'll author the system prompt and teach it the find-first-then-lookup chaining pattern.
- **A lived-in understanding** of per-agent model selection (Sonnet for voice, Haiku for reports), stubbed/wired state transitions, Dispatcher routing fall-through, and the Atelier's role as a production-grade operator surface.

Two agents, five tools, and a capstone where Marco's full shopping journey ends with every specialist firing on its own model at its own temperature — the lesson made visible.

## The narrative spine

See the Marco arc overview at [`../shared/marco-arc-overview.en.md`](../shared/marco-arc-overview.en.md).

Marco shops Pellier. Asks four questions. Three land; the fourth — a warehouse-stock question — gets a voice-matched non-answer because Stock Keeper ships in stub state. **That's the build.** After participants wire the agent + tools, Marco's same question returns a real Brooklyn warehouse answer with count and ship ETA. The workshop narrates itself through Marco's pill clicks.

## The three modules

The Atelier's own left sidebar names the verbs. The workshop follows them:

| Module | Atelier surfaces | Minutes | What you do |
|---|---|---|---|
| **1 · Observe** | Sessions → Observatory | 20 | Tour the system. Replay Marco's opening demo. Read the model-mix sidebar. A 5-minute "swap a model" hands-on exercise. |
| **2 · Understand** | Architecture → Agents → Tools → Skills → Routing → Memory | 70 | Build Stock Keeper (agent + 3 tools). Mid-point checkpoint. Build Experience Guide (agent + tool wiring). |
| **3 · Evaluate** | Performance → Evaluations | 20 | Per-agent latency deep-dive. Optional stretch lab: try Style Advisor on Opus 4.6. Capstone Marco journey. |

## How to verify each build

Two paths, by design:

1. **`pytest` is the fast loop.** Every challenge has a dedicated test file. Run it after you save. Green means the logic works — no frontend required.
2. **The Boutique + Atelier is the victory lap.** Click a Marco hero pill, flip to the Atelier, watch the panels update. That's the "I just shipped this" moment.

Each challenge page shows both the pytest command and the Boutique/Atelier observation to look for.

## If you fall behind — the `cp` escape hatch

Every challenge has a ⏩ **Short on time?** block with a one-line `cp` command that drops the solution file into place:

```bash
cp solutions/module2/agents/inventory_agent.py \
   pellier/backend/agents/inventory_agent.py
```

The solution file is a plain copy of working code. No merge logic, no variant. Run the `cp`, save, move on. The goal is to get everyone to the capstone — not to pass every sub-challenge manually.

## Honest difficulty bar

This is Level 400. We assume:

- Python fluency, including `async`/`await` and typing
- Comfort reading 200-line modules and finding the right insertion point
- Familiarity with LLM concepts (temperature, tool calling, system prompts)
- Basic AWS + Bedrock awareness (you don't need to have deployed an agent, but you should know what "model invoke" means)

If you're finding any of those shaky, lean on the `cp` escape hatches hard. You'll still see the architectural lesson land.

## Getting set up

Next: [Setup](00-setup.en.md)
