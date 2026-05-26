---
title: "Summary and conclusion"
weight: 40
---

:::alert{type="info"}
**Time:** ~3 min  
**Exercises:** 0  
**Mode:** capstone and hand-off
:::

Close the loop: recap what you proved, name the seams worth carrying back, and leave with a concrete expansion path.

## The loop you walked

```text
question → embed → pgvector retrieve → rerank → ground →
generate → memory substrates → managed Runtime → MCP → Knowledge Bases
```

One Aurora PostgreSQL cluster sat under the full path: catalog rows, warehouse inventory, customer events, profile signals, and the `pellier.tool_audit` evidence ledger. One Bedrock account served embeddings, reranking, and specialist model calls. The architecture did not get more mysterious as you moved from Act I to Act III; it became more inspectable.

That is the real outcome of the workshop: **not just an agent that answers, but an agentic system that leaves evidence behind.**

## What you shipped and proved

- **A deterministic tool read against live Aurora.** In Act I, you wired `floor_check` so Marco's warehouse question resolved against `pellier.warehouse_inventory` instead of a stub. The proof was visible in Boutique trace chips and the Atelier tool registry.
- **A retrieval-quality decision, not a retrieval slogan.** You compared vector search, hybrid retrieval, and rerank behavior for Anna's gift query, then decided whether the more expensive path earned its latency for that query class.
- **AgentCore Memory-backed session continuity.** You read the session timeline through `/api/agent/session/{session_id}` and verified that working memory rehydrates after a page reload.
- **A managed Runtime invocation boundary.** You invoked the same orchestrator through `/api/agent/chat`, watched the `session → chunk → done` event stream, and connected the managed path back to the same application behavior.
- **A durable Aurora audit read path.** In Act II, the mandatory exercise was one `SELECT` against `pellier.tool_audit`: every Cedar-allowed tool call that actually runs writes a row, reads and writes alike. DENY decisions do not appear in the table because the tool never executes.
- **A routing and portability read.** In Act III, you inspected the dispatcher, the two-routers-per-turn seam, the MCP contract, and the Knowledge Bases decision point.

:::alert{type="success" header="The short version"}
You did not just build a chatbot. You walked the production shape of agentic search: retrieve when the corpus is enough, call tools when systems of record matter, remember when continuity matters, route when specialization is clearer, and audit when operators need evidence.
:::

## The seams to carry back

| Seam | Pellier proof | Pattern to reuse |
|---|---|---|
| **Domain-corpus retrieval** | `find_pieces` and `find_pieces_hybrid` over `pellier.product_catalog` | Search over support tickets, policy docs, clinical protocols, product reviews, service manuals, or internal knowledge articles |
| **Deterministic tool read** | `floor_check` reads warehouse inventory | Eligibility status, claim state, account standing, asset telemetry, parts availability, case status |
| **Memory substrates** | Working, semantic, episodic, and procedural surfaces | Separate session timeline, durable profile, event history, and tool-choice evidence instead of calling everything "memory" |
| **Managed invocation boundary** | `/api/agent/chat` invokes AgentCore Runtime | Move the same orchestrator behind an ops-owned, versioned, managed execution surface |
| **Policy and audit evidence** | Cedar-allowed tool calls land in `pellier.tool_audit` | Record tool name, arguments, result, latency, and session so behavior is replayable by query |
| **Dispatcher routing** | Rules-first classifier selects one specialist | Use deterministic routing for curated intents before reaching for an LLM router |
| **MCP and Knowledge Bases** | Read-only Postgres MCP config plus managed retrieval comparison | Decide which boundary owns tool hosting and retrieval lifecycle: your app, an MCP host, or a managed Knowledge Base |

## What you did not build: adding a sixth specialist

If you wanted to extend Pellier with a sixth specialist — for example, a **Stylist** for occasion-based outfit recommendations — the path is intentionally small and explicit.

| File | What you would add | Why it matters |
|---|---|---|
| `pellier/backend/services/agent_tools.py` | A new `@tool` function such as `outfit_match`, with a precise docstring and typed arguments | The decorator declares the tool contract; the docstring is what capability discovery indexes |
| `pellier/backend/agents/stylist.py` | A new specialist module with system prompt, model choice, tool list, and hooks | Specialists are independently versioned units, not one giant prompt |
| `pellier/backend/services/chat.py` | A new branch in `classify_intent` plus a `stylist` entry in the dispatcher map | Rules-first routing cannot discover an intent it has not been told about |
| `skills/the-stylists-edit/SKILL.md` *(optional)* | A markdown playbook for voice, constraints, and response framing | Skills change handling and tone without changing retrieval SQL or retraining a model |

**Automatic vs. manual:** a well-written tool docstring makes a capability discoverable to specialists that use the registry. A new specialist still needs an explicit route, because Pellier chooses predictable routing over a router LLM for curated storefront intents.

## Two questions for the walk back

1. **What is your equivalent of `pellier.tool_audit`?** Where does durable tool-call evidence live today, and can an operator reconstruct the agent's action with one query?
2. **Where is your dispatcher hidden?** Most production systems already route by intent. The question is whether that route is deterministic, observable, and intentionally chosen.

:::alert{type="info" header="Read next"}
Carry the architecture back through [What this maps to in your stack](/90-appendix/03-your-stack/). Return to [Reference](/90-appendix/01-reference/) for the cast, pgvector primer, and quick-start commands, or [When things misbehave](/90-appendix/02-when-things-misbehave/) for the operational runbook.
:::
