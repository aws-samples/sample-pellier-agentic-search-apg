---
title: "01: Routing patterns"
weight: 10
---

:::alert{type="info"}
**Time:** ~5 min  
**Exercises:** 0  
**Surface:** Atelier → Routing · `services/chat.py` (intent + skill routers)
:::

No code. Read how the Boutique picks a specialist, where AgentCore Runtime fits, and the **two-routers-one-turn** seam that separates intent bugs from voice bugs. Keep this page tight; close with the takeaways, not a deep architecture debate.

**You will learn to:**

1. Read the **Dispatcher + specialists** pattern as the production
   default, and explain why it beats an LLM router on predictability,
   latency (~60–120 ms), and cost (one model call per turn).
2. Recognize the **two-routers-one-turn seam**: `classify_intent`
   picks the specialist; `POST /api/atelier/skills/route` picks the
   persona overlay. **Wrong specialist ≠ wrong voice.**
3. Match **Dispatcher**, **Agents-as-Tools**, **Graph**, **AgentCore
   Runtime**, **Gateway semantic search**, **MCP**, and **Knowledge
   Bases** to the problems they actually fit.
4. Sketch the upgrade path from rules → small classifier / Haiku T=0 →
   embedding-based tool discovery, and know when each step earns its
   complexity.

:::alert{type="info" header="New to routing?"}
Think of routing as the agent's triage desk. The model still writes the
answer, but the application decides which specialist, tools, memory, and
policy boundary are allowed to participate in that turn.
:::

## Open Routing in the Atelier

Click **Routing** under **UNDERSTAND**.

Three orchestration patterns ship. Only one is **active** for the
storefront.

---

## Production storefront: Dispatcher + specialists

The Boutique (`/api/chat/stream`, pattern `dispatcher`) uses:

1. **`classify_triage`**: deterministic greetings / meta / thanks (no LLM)
2. **`classify_intent`**: keyword rules in `services/chat.py` (no LLM)
3. **One specialist**: Strands agent + tools, usually temperature 0 on reports

**Why this pattern for the Pellier concierge:**

- **Predictable.** Marco's pills route the same way every demo.
- **Fast.** No router LLM; classification is ~60–120 ms.
- **Cheap.** One model call per turn.
- **Auditable.** intent → specialist is visible in logs and Atelier.

Scroll to **What you type maps to one specialist**. That is the literal
keyword map from code.

:::alert{type="info" header="Pattern to borrow"}
The dispatcher is rules-first routing for curated intents: a deterministic
triage step, a keyword map to specialists, and one model call per turn.
In Pellier the specialists are five storefront roles. In another stack
the same shape routes a contact-center turn to the right queue, a claims
intake to the right adjudicator, an IT ticket to the right team, or a
field-service request to the right operations workflow. The pattern
stays; only the specialist roster changes.
:::

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

## When the agent should not try to answer

Routing decides **which** specialist runs. The harder design decision is
when **none** of them should: when the honest answer is *this needs a
human*.

Pellier ships an `escalate_to_stylist` tool wired into Style Advisor and
Experience Guide. It returns a structured handoff payload that the chat
renders as a contact card; no database write and no real human on the
other end in the workshop. The prompts pin its use to three cases:

- **Style Advisor**: nuanced personal-style coaching beyond the
  catalog's 40 pieces: body-image or pregnancy fit, cultural dressing
  norms the agent does not know, or shopper distress.
- **Experience Guide**: returns the Cedar policy cannot process:
  damaged-in-transit past the window, special-order pieces,
  sentimental exceptions, or anything `process_return` would silently
  drop.
- **Either**: catalog misses where another `find_pieces` call will not
  help.

Try it in the Boutique chat as Marco:

```text
What should I wear to a Bengali wedding as the groom's cousin?
```

`escalate_to_stylist` fires, the chat replaces the product grid with the
stylist handoff card, and the hero strip's *hands off to a human stylist
when it should* claim becomes verifiable.

**Pattern:** every agent needs an escape hatch: a tool the prompt
explicitly permits the model to call when no other tool would be honest.
Most demos skip this; it is one of the cheapest credibility moves an
agent can make.

---

## When to use the other patterns

| Pattern | Where | Use when |
|---------|-------|----------|
| **Agents-as-Tools** | Atelier mode strip / `/api/agent/chat` in-process | Teaching multi-agent routing; Haiku orchestrator + specialists as `@tool` |
| **Graph** | Atelier telemetry | Multi-step workflows with explicit edges and durable state transitions |
| **AgentCore Runtime** | `/api/agent/chat` + `USE_AGENTCORE_RUNTIME=true` | Same orchestrator, managed execution boundary, ops-owned deploy |
| **Gateway semantic search (MCP)** | Tools discovery card | Hundreds of tools: embed descriptions, retrieve relevant tools, and avoid stuffing every tool into the prompt |
| **MCP** | `mcp-server-config.json` | Tool portability across hosts: local IDE, Strands agent, Claude Code, or a managed Gateway |
| **Knowledge Bases** | Managed/document retrieval comparison | Document-heavy corpora where you want a platform to own ingestion, chunking, embedding, sync, and retrieval |

**Industry upgrade path when keywords are not enough:**

```text
triage (rules) → intent (rules) → low confidence? → small classifier or Haiku T=0
                              → else → one specialist (one LLM call)
```

Use **embedding-based tool discovery** for catalog-scale capabilities,
not as the default per-turn router for curated storefront intents.

---

## Capstone

Replay Marco's Turn 4 in the Boutique. Open **Sessions → marco-midpoint-checkpoint**
if your table finished [Wire `floor_check`](/10-act-1-the-boutique/02-wire-floor-check/).

Note **Performance**: Haiku stock turn ~150 ms vs Opus editorial turns
~1.0–1.4 s. Same architecture lesson, two surfaces.

---

## What you have learned

- **The dispatcher is the production default for curated intents.**
  Predictable, fast, cheap, auditable: four properties an LLM router
  trades away by default.
- **There are two routers in every turn**, and they fail differently.
  Wrong specialist = `classify_intent` issue. Right specialist, wrong
  voice = skill-router issue.
- **Pattern choice is a fit problem, not a power ranking.** Graph,
  Agents-as-Tools, Runtime, Gateway, MCP, and Knowledge Bases each fit
  specific shapes of work.
- **Embedding-based tool discovery is an upgrade path, not a default.**
  Reach for it at catalog scale (hundreds of tools), not as the
  per-turn router for a curated storefront.
- **Every agent needs an escape hatch.** `escalate_to_stylist` is the
  visible proof that the agent knows when no tool would be honest.
- **The loop closes here.** Question → vector search → specialist →
  memory → managed Runtime is the Pellier path you have now walked
  end-to-end.

:::alert{type="success" header="Next: MCP and Knowledge Bases"}
The concierge view is one half of *what this maps to in your stack*.
The other half is the **MCP / Knowledge Bases comparison**: how the
same Aurora pgvector substrate can reach your IDE today and a managed
or platform-owned retrieval path tomorrow.

[MCP and Knowledge Bases →](../02-mcp-and-knowledge-bases/)
:::
