---
title: "Meet the Boutique"
weight: 20
---

:::alert{type="info"}
**Setup.** About two minutes. Open the storefront and the operator's surface.
:::

Pellier ships as **two surfaces that share one agent.** The Boutique
is the customer-facing storefront; the Atelier is the operator's
observatory. You'll switch between them constantly for the next hour.

## 1 · Open the Boutique

In Code Editor, find the **Ports** panel at the bottom and click the
forwarded address next to port **8000**. The Pellier storefront
opens in a new tab — a full-bleed editorial photograph with a
search bar floating over the cream wall.

A small *Pellier · listening* chip pulses in the upper-left corner
of the hero. **That pulse is the agent.** It means the system is
awake.

:::alert{type="info"}
The Boutique runs in **demo mode** for the next sixty minutes — no
login screen. You'll switch between Marco, Anna, and Theo by picking
a persona in the chat drawer; that's the same UI a returning shopper
would use after signing in.
:::

## 2 · Open the Atelier

In a second browser tab, append `/atelier` to the same URL. The
Atelier loads with a sidebar grouped into three orbits:
**OBSERVE**, **UNDERSTAND**, **EVALUATE**.

Same agent, different lens. Keep both tabs open.

::::expand{header="Boutique vs. Atelier — at a glance"}

| | Boutique (`/`) | Atelier (`/atelier`) |
|---|---|---|
| Audience | Shopper | Operator |
| Tone | Editorial | Telemetry-first |
| Shows | Product cards, chat drawer, persona pills | Trace chips, tool calls, memory reads, routing, performance comparisons |
| Persona switch | Chat drawer | Header dropdown |
| Source of truth | Same backend agent · same Aurora (or RDS) data · same AgentCore memory |

::::

:::alert{type="success"}
Next: a one-screen checklist that confirms everything is wired.

[Pre-flight checklist →](../03-pre-flight-checklist/)
:::
