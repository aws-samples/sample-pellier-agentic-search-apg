---
title: "Build agentic AI–powered search with Amazon Aurora and Amazon RDS"
weight: 0
---

## *Welcome to Pellier.*

A small editorial boutique with one quiet promise — *a shopper asks for
something in their own words, and the right pieces find them.* Behind
that promise: **pgvector search on Aurora PostgreSQL** (the same
pattern runs unchanged on **Amazon RDS for PostgreSQL**), five
**Strands specialists**, **AgentCore Memory** across turns, and an
**AgentCore Runtime** you'll invoke through a managed endpoint — not
cold-deploy in the room.

![Pellier — the boutique hero, with Marco listening](/static/introduction/pellier-hero.png)

:::alert{type="info"}
**Level 400 · Expert**  ·  60 min (3 framing · **50 hands-on** · 7 close)  ·  Builder's Session — DC Summit
:::

:::alert{type="info" header="What you're really building — RAG with agentic search"}
This is **Retrieval-Augmented Generation** with the retrieval half made
agentic. The shopper's words become a **Cohere Embed v4** vector;
**pgvector** on Aurora (or RDS) returns the candidate rows; a Strands
agent decides *which tool* to call (`find_pieces`, `find_pieces_hybrid`,
`floor_check`); **Cohere Rerank v3.5** reorders the merged candidates;
**Claude Opus 4.6** generates the editorial reply grounded in those
rows. **MCP** lets the same Aurora tools work from any MCP host —
local processes, IDE chat extensions, or AgentCore Gateway in managed
deploys; **AgentCore Memory** keeps the conversation in order;
**AgentCore Runtime** moves
the orchestrator behind a managed endpoint without changing a line of
agent code.
:::

---

## The arc · 60 minutes

```text
   Framing  Setup         Act I              Act II           Act III           Close
   ───────  ────────      ───────────        ──────────       ──────────        ─────
   3 min    7 min         28 min             11 min           7 min             4 min
   slide    open IDE      wire floor_check   verify STM       routing +         takeaways +
            pre-flight    prove rerank       invoke Runtime   MCP / KB read     Q&A
                          ▲                  ▲                ▲
                          build              ship to prod     operate
                          (one tool body)    (no new code)    (no code)
```

| Section | What you do | Time |
|---|---|---|
| **Framing** | Title slide + abstract + the RAG-with-agents shape | ~3 min |
| **Setup** | Open Code Editor, meet Boutique + Atelier, four-check pre-flight, optional [pgvector primer](/00-setup/04-pgvector-primer/) | ~7 min |
| **Act I · The Boutique** | Observe Marco's broken Turn 4, **wire `floor_check`** against `pellier.warehouse_inventory`, then measure vector / hybrid / hybrid+rerank in the Atelier — and read the **HNSW tuning** knobs you'd reach for at scale | ~28 min |
| **Act II · The Ledger** | Read STM through `/api/agent/session/{id}`; inspect the **long-term taste table** in Aurora; **wire one log line** and invoke the pre-launched **AgentCore Runtime** at `bedrock-agentcore:InvokeRuntime` | ~11 min |
| **Act III · The Concierge** | Read the dispatcher + specialists pattern in the Atelier, then [read the MCP config + verify the AWS Labs Postgres server from the terminal, and compare to Bedrock Knowledge Bases](/30-act-3-the-concierge/02-mcp-and-knowledge-bases/) | ~7 min |
| **Close** | "What this maps to in your stack" + Q&A | ~4 min |
| **Appendix** | [The Cast](/90-appendix/01-the-cast/) · [Shipment SQL](/90-appendix/02-shipment-sql/) · [Troubleshooting](/90-appendix/03-when-things-misbehave/) · [Quick start](/90-appendix/quick-start/) | — |

---

## Stack at a glance

| Layer | What's running |
|---|---|
| **Database** | **Aurora PostgreSQL Serverless v2** in this lab · engine 17.7 · pgvector 0.8.0 · HNSW · 1024-dim Cohere Embed v4. **Amazon RDS for PostgreSQL** runs the same pgvector primitives unchanged — pick Aurora for elastic ACU scaling and faster failover; pick RDS for predictable single-AZ workloads, smaller catalogs, or when you already standardize on RDS instance classes (`db.r7g`/`db.r8g`). |
| **Retrieval** | pgvector cosine (`<=>`) · Postgres FTS (`tsvector` + GIN + `ts_rank_cd`) · RRF merge · Cohere Rerank v3.5 — *the retrieval half of RAG, made agentic by tool selection* |
| **Models** | Claude Opus 4.6 (`global.anthropic.claude-opus-4-6-v1`, editorial · `T=0.2–0.4`) · Claude Haiku 4.5 (`global.anthropic.claude-haiku-4-5-20251001-v1:0`, reporting · `T=0.0–0.1`) · Cohere Embed v4 (`us.cohere.embed-v4:0`) · Cohere Rerank v3.5 (`cohere.rerank-v3-5:0`) — all via Bedrock inference profiles |
| **Agent framework** | Strands Agents SDK · `Agent`, `@tool`, `GraphBuilder`, `BeforeToolCallEvent` hooks |
| **Agent infra** | Bedrock AgentCore — Memory (STM) · Runtime (`@app.entrypoint` → `InvokeRuntime`) · Gateway (MCP) · Identity |
| **MCP** | [`awslabs.postgres-mcp-server`](https://github.com/awslabs/mcp/tree/main/src/postgres-mcp-server) installed via `uvx`, read-only against your Aurora cluster — config at `pellier/config/mcp-server-config.json`. Any MCP host (VS Code chat extension, Claude Code, Strands `MCPClient`, AgentCore Gateway) consumes the same JSON contract. See [Act III · MCP and Knowledge Bases](/30-act-3-the-concierge/02-mcp-and-knowledge-bases/) |
| **Server** | FastAPI · Python 3.13 · psycopg3 · boto3 · SSE streaming on `:8000` |
| **Surfaces** | **Boutique** (`/`) — shopper · **Atelier** (`/atelier`) — operator. Same agent, two lenses. |

---

## What you'll ship

```text
   one tool body          → Stock Keeper answers Marco's Turn 4 (Exercise 1, Act I)
   one editorial decision → did rerank earn its latency for Anna?
   one observability hook → see every InvokeRuntime call in the log (Exercise 2, Act II)
   one routing read       → why dispatcher beats LLM-as-router here
```

| You build / prove | You observe |
|---|---|
| **Exercise 1** — `floor_check` body in `services/agent_tools.py` (5 lines between guards) | **STM** — turns persist via `AGENTCORE_MEMORY_ID`, recoverable from API |
| Anna's vector / hybrid / hybrid+rerank delta in Atelier `Performance` | **Runtime** — `agentcore_runtime.py` `@app.entrypoint` reachable on `/api/agent/chat` when `USE_AGENTCORE_RUNTIME=true` |
| **Exercise 2** — one `logger.info(...)` line in `services/agentcore_runtime.py` so every managed invoke shows up in `uvicorn.log` | **Dispatcher** — keyword classify → one specialist · ~60–120 ms |

::::expand{header="⏩ Out of time? Drop in the solutions"}

**Exercise 1 — `floor_check`:**

```bash
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
   pellier/backend/services/agent_tools.py
```

Paste-only the body: `solutions/closing-marcos-gap/services/floor_check_tool_body.py`.

**Exercise 2 — invoke log line:**

```bash
cp solutions/the-ledger/services/agentcore_runtime_with_invoke_log.py \
   pellier/backend/services/agentcore_runtime.py
```

::::

---

## Before you begin

You'll move faster if these are second nature: **PostgreSQL** (DDL,
psql, indexes), **Python 3.10+** (decorators, async basics), **vector
search intuition** (cosine similarity, embedding dims), and the rough
shape of an **agent loop** (system prompt → tool selection → tool
execution → final answer). If you've shipped a RAG system before, this
is the same skeleton with three new bones — **agentic tool selection**
(Strands), **managed runtime** (AgentCore), and **MCP** as the protocol
that lets the same tools work from your IDE.

If you have *not* shipped RAG before, the optional [pgvector primer](/00-setup/04-pgvector-primer/)
in Setup is your two-minute on-ramp.

[Begin with Setup →](/00-setup/01-open-code-editor/)
