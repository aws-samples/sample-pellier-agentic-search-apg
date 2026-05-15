---
title: "04 · Step Into the Atelier"
weight: 25
---

:::alert{type="info"}
*About seven minutes. No code, no SQL — a guided tour of three surfaces
the agent uses every turn.*
:::

## The operator's side of the boutique

The Atelier is the same agent, photographed from the other side. If
the Boutique is the storefront window, the Atelier is the back office
— where you can watch the agent reason, replay any session, and
inspect the tools and memory it leans on.

Switch to your Atelier tab. The breadcrumb at the top shows where
you are; the small *Pellier · listening* chip in the upper-right is
the same atom that appears on the Boutique's hero — same agent,
both surfaces.

We'll visit three surfaces. Each one has a *See in Boutique*
cross-link that drops you back into the storefront with a query
that exercises that surface. Use them.

---

## Memory — *what the agent remembers about you*

Click **Memory** in the left sidebar (under **UNDERSTAND**).

![The Atelier's Memory orbit — Marco at the centre, STM on the inner ring, LTM on the outer ring](/static/introduction/atelier-memory.png)

A two-tier diagram fills the canvas: a persona at the centre, an
inner ring of short-term memory items (the current session — Marco's
last few turns, the items he opened, the trace of his clicks), and
an outer ring of long-term memory (his palette preferences, the
sizes he's bought, the trips he's taken).

Each ring item is a small dot connected to the centre by a thin
line. Hover one — the agent's full memory of that fact lights up
in a side panel. *"Last March, Marco bought the Linen Camp Shirt
in size 41. Before that, the Field Jacket in olive. He's mentioned
Lisbon twice and Porto once."*

Click *See this in the Boutique* (top-right of the page). The
storefront opens with a chat prompt pre-filled — *"Pick up where I
left off"* — and the agent answers from memory in a single sentence.

::::expand{header="What's underneath"}

Short-term memory uses Bedrock AgentCore Memory (STM). The boot
path provisioned a `PellierSTM` resource and stored its ID in
`.env`. Every turn appends events; events expire after 30 days.

Long-term memory is Aurora pgvector — `pellier.customer_episodic_seed`
and a few related tables — read with the same vector machinery the
catalog uses. The Atelier surface above is reading both.

::::

---

## Tools — *what the agent can reach for*

Click **Tools** in the sidebar.

![The Atelier's Tools registry — eight cards, the floor_check one bordered burgundy because you wired it](/static/introduction/atelier-tools.png)

A row of tool cards: `find_pieces`, `pairing.score`, `inventory.live`,
`memory.recall`, `cart.holds`, `experience.return`, `palette.match`,
and — burgundy-bordered now, where it was dashed before you touched it
— `floor_check`. The tool you wrote.

Above the cards, a small discovery card with a search box. Type a
natural-language query:

> *something to keep my linen pieces organized*

Click **Discover**. The registry runs cosine similarity over the
1024-dim Cohere embeddings of every tool's description, ranks them,
and returns the top three. `find_pieces` lands first; the cosine
distance is shown to four decimal places.

This is how the orchestrator picks tools when no specialist agent
is the obvious owner — the same primitive that powers product
search, applied to capabilities.

::::expand{header="Why does this matter?"}

In production, you ship dozens of tools. Hard-coding which agent
gets which tool doesn't scale. Letting the orchestrator discover
the right tool from a query lets you add a new tool without
touching the orchestrator — write the tool, register it, the
agent finds it on the next turn.

::::

---

## Agents — *who the system has on staff*

Click **Agents** in the sidebar.

![The Atelier's Agents board — five specialists, Stock Keeper bordered burgundy because you wired it](/static/introduction/atelier-agents.png)

Five rows. Three were sage-bordered before you arrived
(Recommendation, Experience Guide, Curator). One you wired up
yourself (Stock Keeper). The fifth — Search — is the default agent
that handles untyped intent.

Each row shows the model the agent uses (mixed across Sonnet,
Haiku, and Opus depending on cost and reasoning depth required), the
tools it can reach for, and a *Test* button.

::::expand{header="Why a model mix?"}

Per-agent model choice is an architectural decision, not a knob to
tune. Stock Keeper answers terse warehouse questions in a single
turn — Haiku is fast and exact. Recommendation reasons across
palette, occasion, and pairing — Sonnet handles that comfortably.
The Curator generates editorial copy with a strong voice — Opus
earns its cost there.

Normalizing to one model would either underspend on the hard
turns or overspend on the easy ones. The Atelier surfaces the mix
so you can audit it.

::::

Click *See in Boutique* on the Stock Keeper card. Marco's chat
drawer opens with *"Is the Hadley shirt at the Brooklyn warehouse?"*
pre-filled. Click **Send**. Stock Keeper — the agent you wired —
answers in three seconds.

---

## What the Atelier is for

| Surface | Read it when |
| --- | --- |
| **Memory** | A turn went sideways and you want to see what the agent remembered (or didn't) |
| **Tools** | A new requirement lands and you need to know whether the system already has a tool that covers it |
| **Agents** | You need to decide whether to extend an existing specialist or add a new one |
| **Sessions** | A specific shopper interaction needs auditing — replay any turn, end-to-end |
| **Performance** | A latency regression appeared and you need to see which agent / tool / model is responsible |

The Boutique gives you the experience. The Atelier gives you the
paper trail. Together they're how you ship a system you can trust.

---

## *One more — and the bridge to what's next*

Pellier ships **AgentCore Identity** scaffolding wired into the
backend. The service that builds each Memory namespace (`user:{id}:
session:{sid}` for authenticated shoppers, `anon:{sid}` for everyone
else) lives at `pellier/backend/services/agentcore_identity.py` —
imported by every route that touches the agent. On this 60-minute
deploy you've been hitting the anonymous branch the whole time, the
same branch a returning shopper would hit before signing in.

The 120-minute workshop exercises the authenticated branch. Click
**Architecture · Identity** in the Atelier sidebar to read the
explainer.

Identity is what turns *"the agent answered"* into *"the agent
answered, on Marco's behalf, with the same scoped credentials that
Marco himself would have at the warehouse API."* Each specialist
agent's tool call carries a token scoped to exactly what that
shopper is allowed to read and write. Stock Keeper might see
Brooklyn's count; an agent acting for an anonymous visitor sees
only what's public. Same code path, different identity claim,
different result.

You don't wire any of that today — that's the longer workshop. But
you'll see why every trace chip you've watched fire in this hour
deserves an identity claim alongside the tool name.

---

## You're done

In the last forty-five minutes you:

- Toured a live agentic boutique with a returning customer (Module 01)
- Wired a tool and a specialist agent that closed a real gap in the
  shopper experience (Module 02)
- Logged a shipment, saw the agent's answer change on the next turn
  with no redeploy (Module 03)
- Walked the operator's side of the same system (Module 04)

That's the shape of agentic shopping at re:Invent scale.

:::alert{type="success" header="Q&A — ten minutes"}
Questions? Bring them to your table lead. Common ones live in
[*When Things Misbehave*](/99-when-things-misbehave/) along with
the quick-fix commands.

If anything tripped on the way through, that page is also where you'll
find the runbook.
:::
