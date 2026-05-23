---
title: "What this maps to in your stack"
weight: 40
---

:::alert{type="info"}
*The closing slide — 4 minutes. Read it as the room finishes; it is
the takeaway worth carrying out the door.*
:::

You walked through one boutique. Here is the two-axis translation
table for **any agentic search application** you'd build on AWS, with
the swaps that make this pattern portable.

---

## The substrate is portable

| What this lab uses | What you'd swap for in your stack |
|---|---|
| **Aurora PostgreSQL Serverless v2** | **Amazon RDS for PostgreSQL** (predictable workloads), Aurora provisioned (steady high QPS), or Aurora Global Database (multi-region read) — pgvector behaves identically on all three |
| **pgvector 0.8.0 · HNSW · `vector(1024)`** | Same. The extension is GA on Aurora and RDS for PostgreSQL on engine 14+. |
| **Cohere Embed v4 (1024-dim)** | Titan Text v2 (1024-dim) keeps your column shape. Cohere Embed Multilingual if you serve non-English. **Changing dimension means rebuilding the HNSW index.** |
| **Cohere Rerank v3.5** | Optional. Skip for vector-only paths. Substitute Amazon Rerank when generally available. |
| **Postgres FTS (`tsvector` + `ts_rank_cd`)** | Same — built-in. Add `pg_trgm` for typo tolerance; don't reach for ElasticSearch unless you outgrow Postgres FTS at 10M+ rows of unstructured text. |
| **Claude Opus 4.6 (editorial) + Haiku 4.5 (reporting)** | The "two-tier" pattern is the takeaway: a slow, expressive model for taste and a fast, cheap model for facts. Substitute Nova Pro / Nova Micro if you standardize on Amazon foundation models. |
| **Strands Agents SDK** | Bedrock Agents (managed), LangGraph, LlamaIndex agents — the `@tool` contract is portable; only the runtime differs. |
| **AgentCore Memory** | Cheap path: a Postgres table with a TTL job. Managed: AgentCore Memory or DynamoDB with TTL. **The `turns[]` shape is what the agent reads — own that contract before picking storage.** |
| **AgentCore Runtime** | Lambda with a 15-minute deadline (small agents), ECS/Fargate (long-lived sessions), or AgentCore Runtime when you want microVM isolation per session without owning the cluster. |
| **MCP (`awslabs.postgres-mcp-server` over Aurora)** | The lab uses the open-source [AWS Labs Postgres MCP server](https://github.com/awslabs/mcp/tree/main/src/postgres-mcp-server) installed via `uvx`. Any MCP host reads the same config — VS Code chat extensions, Claude Code, a Strands agent using `MCPClient`, or Bedrock AgentCore Gateway in managed deploys. Swap servers as needed; the protocol stays the same. |

---

## The retrieval pattern is portable

```text
user words
   ↓
embed (Cohere v4 / Titan v2 / your choice)
   ↓
hybrid retrieve (pgvector cosine ⊕ Postgres FTS, RRF merge)
   ↓
optional rerank (Cohere Rerank v3.5 / Amazon Rerank)
   ↓
ground prompt (Opus / Haiku / Nova / your choice)
   ↓
agent decides next tool, or returns
```

Every box is a **paste-able primitive**. None of them are Aurora-specific.
None of them require Strands. The architecture is the takeaway, not
the libraries.

---

## The decisions worth making first

If you walk out remembering only four things:

1. **Pick your retrieval shape per query class, not per app.** Vector
   only is fine for soft taste queries. Hybrid earns its cost for
   queries that mix taste with literal constraints. Rerank earns its
   cost when phrasing matters more than tags.
2. **Two memories, one agent.** Bound short-term memory; let long-term
   live in your durable store (Aurora, Dynamo). Don't conflate them.
3. **Dispatcher first, LLM-as-router only when keywords run out.**
   The cheapest, most auditable router is the one that doesn't call
   a model.
4. **Aurora vs RDS is a workload-shape choice, not a capability
   choice.** pgvector, FTS, and HNSW work the same on both. Pick by
   scaling pattern (ACU vs instance) and failover SLA.

---

## Where to go next

| If you're going to… | Read |
|---|---|
| Replicate this pattern in your account | The CFN templates in `lab-content/builders/static/pellier-*.yml` |
| Move from Aurora to RDS | The pgvector docs — you'll change `aws rds create-db-cluster` to `aws rds create-db-instance`; everything inside the database is identical |
| Add Bedrock Knowledge Bases on top | Aurora is a supported KB store for PostgreSQL — point it at the same cluster and a new schema |
| Productionize tool discovery at scale (>100 tools) | AgentCore Gateway docs on MCP — the same protocol behind `awslabs.postgres-mcp-server` you read today |
| Tune retrieval at 10M+ rows | `hnsw.iterative_scan`, `halfvec`, `binary_quantize`, `SET LOCAL work_mem`, the pgvector README |

:::alert{type="success" header="That's the workshop"}
You walked the full loop: **embed → retrieve → rerank → ground →
generate → memory → managed runtime → MCP**, on the same Aurora
cluster (or RDS, your call). That's agentic AI–powered search on
Amazon Aurora and Amazon RDS, end to end.
:::
