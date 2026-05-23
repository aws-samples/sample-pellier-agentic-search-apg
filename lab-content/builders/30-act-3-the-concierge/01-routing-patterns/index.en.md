---
title: "Operator View · Routing Patterns"
weight: 10
---

:::alert{type="info"}
**Time:** ~4 min  ·  **Page:** 1 of 1 in Act III  ·  **Exercises on this page:** 0

No code — read how the Boutique picks a specialist, where AgentCore
Runtime fits, and the **two-routers-one-turn** seam that separates
intent bugs from voice bugs. Keep this page tight; close with the
takeaways, not a deep architecture debate.
:::

**You'll learn to:**

1. Read the **Dispatcher + specialists** pattern as the production
   default — and explain why it beats LLM-as-router on predictability,
   latency (~60–120 ms), and cost (one model call per turn).
2. Recognize the **two-routers-one-turn seam**: `classify_intent`
   picks the specialist; `POST /api/atelier/skills/route` picks the
   persona overlay. **Wrong specialist ≠ wrong voice.**
3. **Match pattern to problem** across Dispatcher, Agents-as-Tools,
   Graph, AgentCore Runtime, and Gateway semantic search — without
   reaching for the most powerful one by default.
4. Sketch the **upgrade path** from rules → small classifier / Haiku
   T=0 → embedding-based tool discovery, and know when each step
   earns its complexity.

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

## When the agent shouldn't try to answer

Routing decides **which** specialist runs. The harder design decision is
when **none** of them should — when the honest answer is "this needs a
human."

Pellier ships an `escalate_to_stylist` tool wired into Style Advisor and
Experience Guide. It returns a structured handoff payload that the chat
renders as a contact card; no DB write, no real human on the other end
in the workshop. The system prompts pin its use to three cases:

- **Style Advisor**: nuanced personal-style coaching beyond the
  catalog's 40 pieces — body-image or pregnancy fit, cultural dressing
  norms the agent doesn't know, shopper distress.
- **Experience Guide**: returns the Cedar policy can't process —
  damaged-in-transit past the window, special-order pieces,
  sentimental exceptions, or anything `process_return` would silently
  drop.
- **Either**: catalog misses where another `find_pieces` call won't
  help.

Try it in the Boutique chat as Marco:

```text
What should I wear to a Bengali wedding as the groom's cousin?
```

`escalate_to_stylist` fires, the chat replaces the product grid with
the stylist handoff card, and the `Hands off to a human stylist`
capability claim on the hero strip is now backed by something real.

**The teaching point:** every agent needs an escape hatch — a tool the
prompt explicitly permits the model to call when no other tool would
be honest. Most demos skip this; it's the single cheapest credibility
move an agent can make.

---

## When to use the other patterns

| Pattern | Where | Use when |
|---------|-------|----------|
| **Agents-as-Tools** | Atelier mode strip / `/api/agent/chat` in-process | Teaching multi-agent routing; Haiku orchestrator + specialists as `@tool` |
| **Graph** | Atelier telemetry | Multi-step workflows with explicit edges |
| **AgentCore Runtime** | `/api/agent/chat` + `USE_AGENTCORE_RUNTIME=true` | Same orchestrator, managed microVM, ops-owned deploy |
| **Gateway semantic search (MCP)** | Tools discovery card | Hundreds of tools — embed descriptions, don't stuff every tool in prompt; Gateway is the managed-host MCP server you reach across accounts |
| **Bedrock Knowledge Bases** | Managed RAG | Document-heavy corpora (PDFs, S3 buckets) where you don't want to own ingestion or chunking — see [§02](../02-mcp-and-knowledge-bases/) |

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
if your table finished [Build — Wire `floor_check`](/10-act-1-the-boutique/02-wire-floor-check/).
Note **Performance**: Haiku stock turn ~150 ms
vs Opus editorial turns ~1.0–1.4 s — same architecture lesson, two surfaces.

---

## What you've learned

- **The dispatcher is the production default for curated intents.**
  Predictable, fast, cheap, auditable — four properties LLM-as-router
  trades away by default.
- **There are two routers in every turn**, and they fail differently.
  Wrong specialist = `classify_intent` issue. Right specialist, wrong
  voice = skill router issue.
- **Pattern choice is a fit problem, not a power ranking.** Graph,
  Agents-as-Tools, Runtime, and Gateway each fit specific shapes of
  work; reaching for the most flexible one by default is how teams
  accidentally pay for capability they don't use.
- **Embedding-based tool discovery is an upgrade path, not a default.**
  Reach for it at catalog scale (hundreds of tools) — not as the
  per-turn router for a curated storefront.
- **The loop closes here.** Question → vector search → specialist →
  memory → managed Runtime is the full Pellier path you've now
  walked end-to-end.
- **Every agent needs an escape hatch.** `escalate_to_stylist` makes
  the hero strip's *Hands off to a human stylist when it should*
  claim verifiable. The capability isn't the email address — it's the
  agent knowing when no tool would be honest.

:::alert{type="success" header="One closing read — MCP and Knowledge Bases"}
The concierge view is one half of "what this maps to in your stack."
The other half is the **MCP / Bedrock Knowledge Bases comparison** —
how the same Aurora pgvector substrate reaches your IDE today and
your managed RAG path tomorrow.

[MCP and Bedrock Knowledge Bases →](../02-mcp-and-knowledge-bases/)
:::
