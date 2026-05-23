---
title: "Act III · The Concierge"
weight: 30
---

*Operator view. ~7 minutes — no code, two closing reads.*

:::alert{type="info" header="Act III · The Concierge"}
**Time:** ~7 min  ·  **Exercises:** 0 (operator-grade read)  ·  **Surfaces:** Atelier → Routing · `/api/chat/stream` · `/api/agent/chat` · IDE → Aurora MCP

Every boutique needs a concierge — someone who, before the customer
ever sees a hesitation, decides which specialist will answer this
turn. **Act I built the agent. Act II proved it in production. Act III
is the concierge's read of the room — and the takeaway slide on how
this maps to MCP and Bedrock Knowledge Bases for your own stack.**

Marco's restock question is not Anna's gift question; Anna's gift
question is not Theo's returns question. Behind the calm of the
storefront, a **dispatcher** is reading intent and handing off — fast,
cheap, auditable. You step into the Atelier and watch the routing
decision happen in real time, then close with the MCP / Knowledge
Bases comparison.
:::

A boutique with five specialists has a quiet decision to make on
every turn: *who answers this one?*

Three orchestration patterns ship in the codebase: the dispatcher
behind Marco's turns (production), plus two alternates exposed as
toggles so you can read the shape of each without redeploying. Four
minutes, no code, and the loop closes:
**question → vector search → specialist → memory → managed Runtime.**

---

## The arc · ~7 minutes

```text
   Routing patterns       MCP + Knowledge Bases
   ~4 min                 ~3 min
   read the dispatcher    open Aurora MCP sidebar,
   live, then the two     compare to Bedrock
   alternates             Knowledge Bases
   ▲                      ▲
   operator view          portability — what this
                          maps to in your stack
```

---

## Learning objectives

By the end of Act III you will be able to:

1. **Read the Dispatcher + specialists pattern** as the production
   default for storefront concierge work — and explain why it beats
   LLM-as-router on predictability, latency, and cost for curated
   intents.
2. **Recognize the two-routers-one-turn shape**: an **intent router**
   picks the specialist, a **skill router** picks the persona overlay.
   Wrong specialist vs wrong voice are different bugs.
3. **Match pattern to problem** across Dispatcher, Agents-as-Tools,
   Graph, AgentCore Runtime, and Gateway semantic search — without
   reaching for the most powerful one by default.
4. **Use embedding-based tool discovery** as the upgrade path for
   catalog-scale capabilities (hundreds of tools), not as the default
   per-turn router for curated storefront intents.

---

## Core concepts ladder

The orchestration territory you'll meet, in the order it shows up in
the Atelier:

| Concept | What you'll see |
|---|---|
| **Dispatcher pattern** | `classify_triage` (rules) → `classify_intent` (keyword map) → one specialist · ~60–120 ms · one model call per turn |
| **Two routers per turn** | `classify_intent` picks specialist; `POST /api/atelier/skills/route` picks persona overlay (e.g. `the-gift-table`) |
| **Agents-as-Tools** | Haiku orchestrator that treats specialists as `@tool` — useful for teaching multi-agent routing |
| **Graph** | Explicit edges for multi-step workflows where order matters |
| **AgentCore Runtime as deploy boundary** | Same orchestrator, managed microVM, ops-owned deploy contract |
| **Gateway semantic search for tools** | Embed tool descriptions; retrieve by cosine when the registry is too large to stuff into a prompt |

---

## What you'll do

| Page | Activity | Time |
|---|---|---|
| 01 · [Routing patterns](01-routing-patterns/) | Read the live dispatcher, the two-routers seam, and the decision tree | ~4 min |
| 02 · [MCP and Bedrock Knowledge Bases](02-mcp-and-knowledge-bases/) | Open Aurora MCP in the IDE, run a query, compare to managed Knowledge Bases | ~3 min |

---

## What you'll have read

```text
   the dispatcher              → keyword classify → one specialist, ~60–120 ms
   the two-routers seam        → intent vs skill — different bugs, different fixes
   the upgrade path            → rules → small classifier / Haiku T=0 → embedding discovery
   the closing loop            → Marco Turn 4 replayed, end-to-end, on the same architecture
```

::::expand{header="Why end the workshop on routing?"}

Routing is the architectural choice that pays off only after you've
lived inside one specialist (Marco's `floor_check`) and one platform
(AgentCore). Ending here gives participants the operator-grade frame:
you don't pick "the most powerful" pattern — you pick the one whose
predictability, latency, cost, and auditability match the turn you're
serving. That's the takeaway worth walking out of the room with.

::::

:::alert{type="success" header="Begin Act III"}
[Operator View · Routing Patterns →](01-routing-patterns/)
:::
