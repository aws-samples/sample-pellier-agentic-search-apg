---
title: "Introduction"
weight: 1
---

:::alert{type="info"}
**Time:** ~5 min  
**Exercises:** 0  
**Surfaces:** Code Editor · Boutique (`/`) · Atelier (`/atelier`)
:::

The lab environment is already deployed. CloudFormation has seeded Aurora, created AgentCore Memory, launched Runtime, and started the FastAPI backend on `:8000`. Your job is to enter the workspace, keep the shopper and operator views side by side, and use the evidence they expose throughout the session.

If you already have a RAG application, this workshop shows the next production step: adding tools, memory, routing, managed invocation, and operator evidence without throwing away your retrieval foundation.

Pellier's boutique search experience is the teaching surface. The underlying pattern is broader: an agentic search architecture that retrieves from a domain corpus, calls deterministic tools when generated text is not enough, remembers the session, routes to specialists, enforces policy around sensitive actions, and leaves behind evidence an operator can inspect.

## Agentic AI systems in this lab

In this workshop, an agentic system means more than a model call. The system accepts a natural-language request, decides which specialist should handle it, retrieves from a domain corpus, calls tools when it needs authoritative data, preserves session context, and records evidence for later inspection.

That is the distinction from a classic search box. Retrieval still matters, but the application also needs judgment: when to retrieve, when to call a tool, when to remember, when to hand off, and when to refuse or escalate.

## Why MCP matters

Model Context Protocol (MCP) gives the agent ecosystem a portable way to expose tools and data. Pellier uses MCP to show how a PostgreSQL-backed capability can be described once and reached from different hosts: a local MCP-aware tool, an IDE session, a Strands-based agent, or a managed AgentCore Gateway path.

In this lab, the MCP path is intentionally small and readable. The important idea is the contract: a tool host advertises what it can do, the caller invokes it through a standard envelope, and the data path remains scoped by the same credentials and safety rails.

## Pellier architecture primer

You will work in three places:

- **Code Editor** is your builder workspace. You will read code, make one focused tool change, and run validation commands.
- **Boutique** (`/`) is the shopper experience. It shows natural-language requests, streaming responses, product cards, and trace chips.
- **Atelier** (`/atelier`) is the operator lens. It shows retrieval comparisons, tool traces, memory behavior, routing choices, Runtime events, and Aurora-backed evidence.

The core request path is:

```text
shopper turn → dispatcher → specialist → retrieval/tool call → answer → trace + memory + audit evidence
```

## Aurora PostgreSQL and pgvector

Aurora is not just the vector store in this workshop. It holds the catalog, warehouse inventory, audit ledger, and longer-lived customer context. `pgvector` adds the embedding column and similarity search that power product retrieval; PostgreSQL full-text search and `pg_trgm` support the literal side of hybrid retrieval and lookup performance.

You will see Aurora in three roles:

1. **Retrieval substrate** for semantic and hybrid search over `pellier.product_catalog`.
2. **System of record** for operational reads such as `pellier.warehouse_inventory`.
3. **Evidence ledger** for tool calls in `pellier.tool_audit`.

## Data overview

Pellier's dataset is deliberately small enough to inspect in a live session:

- 40 curated product records with editorial copy and Cohere Embed English v3 vectors.
- Three personas: Marco, Anna, and Theo, plus a signed-out baseline experience.
- Three warehouse locations with seeded inventory.
- Orders, returns, and episodic rows that support memory and post-purchase flows.
- A `tool_audit` table for reconstructing tool activity from Aurora.

The small domain makes the mechanics visible. In your organization, the same pattern could sit over claims, support tickets, eligibility records, product reviews, service manuals, contracts, policies, or maintenance logs.

## Open the environment

1. In **Workshop Studio → Event Outputs**, open `CodeEditorURL`. The URL includes a one-time token that signs you into Code Editor automatically; you do not need to type a password.
2. In Code Editor, open the forwarded address for port **8000**. This is the Boutique.
3. In a second browser tab, append `/atelier` to the same URL. This is the Atelier.
4. Keep both tabs open for the rest of the session.

:::alert{type="info" header="Authentication and policy scope"}
The Builder Session keeps shopper interactions in demo mode, but the platform path is production-like: Cognito-backed user identity and AgentCore Identity workload credentials are prewired as required infrastructure, alongside Cedar policy checks for sensitive tool actions.

There is one workshop Cognito user pool per environment, not one pool per persona. Marco, Anna, and Theo are seeded shopping personas in application data.
:::

## What you will build

This is not a type-everything-from-scratch lab. There are two focused hands-on moments:

1. Wire `floor_check` in `pellier/backend/services/agent_tools.py` so Marco's warehouse question resolves against live Aurora inventory.
2. Generate a tool call, then read the Aurora ledger path in Act II by querying `pellier.tool_audit`. If time allows, optionally add one `logger.info(...)` seam for Runtime invocation visibility.

Everything else is already running so you can spend the session inspecting the full system: pgvector retrieval, hybrid search, reranking, tool use, memory, routing, streaming, policy boundaries, and traceability.

## Session flow

| Stage | What you do | Time |
|---|---|---|
| **Introduction: Enter the environment** | Open Code Editor, land in Boutique and Atelier, and read the surface tour. | ~5&nbsp;min |
| **Act I: The Boutique** | Follow Marco's journey, wire the missing `floor_check` tool, and compare retrieval strategies on the live Aurora catalog. | ~30&nbsp;min |
| **Act II: The Ledger** | Verify memory across turns, invoke the managed Runtime, and query `pellier.tool_audit` to reconstruct what the agent did. | ~12&nbsp;min |
| **Act III: The Concierge** | Read the routing layer, then compare dispatcher, agents-as-tools, graph, MCP, and managed RAG patterns. | ~8&nbsp;min |
| **Buffer and recovery** | Reserved time for facilitator pacing, table questions, and recovery. | ~5&nbsp;min |

## Evidence you will inspect

Operator evidence is part of the architecture, not an afterthought. Across the session, you will read:

- Product cards and trace chips in the Boutique.
- Retrieval comparisons in the Atelier.
- Session history from AgentCore Memory.
- Runtime events from `/api/agent/chat`.
- Audit rows from `pellier.tool_audit`.
- Routing decisions in the Atelier.
- MCP configuration and the managed RAG comparison with Knowledge Bases.

## Key takeaways

- **Aurora PostgreSQL is more than a vector store.** It anchors retrieval, operational reads, audit rows, and inspectable evidence in one engine.
- **Agentic search is RAG with judgment.** Retrieve when the corpus is enough, call tools when the system of record matters, remember when continuity matters, route when specialists are clearer than one mega-agent, and enforce policy when actions carry risk.
- **Production-grade agent systems need evidence.** Traces, session timelines, runtime events, policy decisions, and durable audit records make behavior inspectable instead of mysterious.
- **Pellier is intentionally specific, but the patterns are portable.** The same architecture maps cleanly to healthcare, financial services, manufacturing, public sector, software operations, and retail workloads.

:::alert{type="info" header="Reference material"}
Use the appendix for supporting context: [Reference](/90-appendix/01-reference/) (cast, pgvector primer, quick-start commands), [When things misbehave](/90-appendix/02-when-things-misbehave/) (runbook plus recovery paths), and [What this maps to in your stack](/90-appendix/03-your-stack/) (service map, industry patterns, Aurora ↔ RDS portability).
:::

::::alert{type="success" header="Start the build"}
[Act I: The Boutique →](/10-act-1-the-boutique/)
::::
