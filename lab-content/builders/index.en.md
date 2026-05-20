---
title: "Build agentic AI–powered search with Amazon Aurora and Amazon RDS"
weight: 0
---

## *Welcome to Pellier.*

A small editorial boutique with one quiet promise — *a shopper asks for
something in their own words, and the right pieces find them.* Behind
that promise: **Aurora pgvector search**, five **Strands specialists**,
**AgentCore Memory** across turns, and an **AgentCore Runtime** you'll
invoke through a managed endpoint — not cold-deploy in the room.

![Pellier — the boutique hero, with Marco listening](/static/introduction/pellier-hero.png)

:::alert{type="info"}
**Level 400 · Expert**  ·  60 min (10 framing · **45 hands-on** · 5 close)  ·  Builder's Session — DC Summit
:::

---

## The arc · 60 minutes

```text
   Setup           Act I              Act II            Act III
   ─────────       ───────────        ──────────        ──────────
   ~5 min          ~30 min            ~10 min           ~4 min
   open IDE        wire floor_check   verify STM        read routing
   verify lights   prove rerank       invoke Runtime    in Atelier
                   ▲                  ▲                 ▲
                   build              ship to prod      operate
                   (one tool body)    (no new code)     (no code)
```

| Section | What you do | Time |
|---|---|---|
| **Setup** | Open Code Editor, meet Boutique + Atelier, run the four-check pre-flight | ~5 min |
| **Act I · The Boutique** | Observe Marco's broken Turn 4, **wire `floor_check`** against `pellier.warehouse_inventory`, then measure vector / hybrid / hybrid+rerank in the Atelier | ~30 min |
| **Act II · The Ledger** | Read STM through `/api/agent/session/{id}`; invoke the pre-launched **AgentCore Runtime** at `bedrock-agentcore:InvokeRuntime` | ~10 min |
| **Act III · The Concierge** | Dispatcher + specialists vs. Agents-as-Tools vs. Graph — read all three in the Atelier | ~4 min |
| **Appendix** | [The Cast](/90-appendix/01-the-cast/) · [Shipment SQL](/90-appendix/02-shipment-sql/) · [Troubleshooting](/90-appendix/03-when-things-misbehave/) · [Quick start](/90-appendix/quick-start/) | — |

---

## Stack at a glance

| Layer | What's running |
|---|---|
| **Database** | Aurora PostgreSQL Serverless v2 · engine 17.7 · pgvector 0.8.0 · HNSW · 1024-dim Cohere Embed v4 |
| **Retrieval** | pgvector cosine · Postgres FTS (`tsvector` + GIN + `ts_rank_cd`) · RRF merge · Cohere Rerank v3.5 |
| **Models** | Claude Opus 4.6 (editorial · `T=0.2–0.4`) · Claude Haiku 4.5 (reporting · `T=0.0–0.1`) — Bedrock inference profiles |
| **Agent framework** | Strands Agents SDK · `Agent`, `@tool`, `GraphBuilder`, `BeforeToolCallEvent` hooks |
| **Agent infra** | Bedrock AgentCore — Memory (STM) · Runtime (`@app.entrypoint` → `InvokeRuntime`) · Gateway (MCP) · Identity |
| **Server** | FastAPI · Python 3.13 · psycopg3 · boto3 · SSE streaming on `:8000` |
| **Surfaces** | **Boutique** (`/`) — shopper · **Atelier** (`/atelier`) — operator. Same agent, two lenses. |

---

## What you'll ship

```text
   one tool body          → Stock Keeper answers Marco's Turn 4
   one editorial decision → did rerank earn its latency for Anna?
   one managed invoke     → same agent, behind AgentCore Runtime
   one routing read       → why dispatcher beats LLM-as-router here
```

| You build / prove | You observe |
|---|---|
| `floor_check` body in `services/agent_tools.py` (5 lines between guards) | **STM** — turns persist via `AGENTCORE_MEMORY_ID`, recoverable from API |
| Anna's vector / hybrid / hybrid+rerank delta in Atelier `Performance` | **Runtime** — `agentcore_runtime.py` `@app.entrypoint` reachable on `/api/agent/chat` when `USE_AGENTCORE_RUNTIME=true` |
| | **Dispatcher** — keyword classify → one specialist · ~60–120 ms |

::::expand{header="⏩ Out of time? Drop in the solution"}

```bash
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
   pellier/backend/services/agent_tools.py
```

Paste-only the body: `solutions/closing-marcos-gap/services/floor_check_tool_body.py`.

::::

---

## Before you begin

You'll move faster if these are second nature: **PostgreSQL** (DDL,
psql, indexes), **Python 3.10+** (decorators, async basics), **vector
search intuition** (cosine similarity, embedding dims), and the rough
shape of an **agent loop** (system prompt → tool selection → tool
execution → final answer). If you've shipped a RAG system before, this
is the same skeleton with one new bone — managed runtime.

[Begin with Setup →](/00-setup/01-open-code-editor/)
