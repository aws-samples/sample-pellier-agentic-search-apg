---
title: "Build agentic AI-powered search with Amazon Aurora and Amazon RDS"
weight: 0
---

:::alert{type="info"}
**Level:** 400 (Expert)  
**Duration:** 60 minutes  
**Format:** Guided build + architecture walkthrough  
**Outcome:** Build and inspect a production-shaped agentic search system with persistent memory, tool use, routing, observability, and managed runtime invocation on Aurora PostgreSQL and Amazon Bedrock AgentCore.
:::

## Welcome to Pellier

Pellier is a small editorial boutique with one quiet promise: *a shopper asks in their own words, and the right pieces find them.*

In this workshop, that promise becomes a working agentic system. You will use Aurora PostgreSQL with pgvector for retrieval, combine semantic and keyword signals through hybrid search, rerank results for relevance, route requests through specialist agents, preserve short-term memory across turns, and invoke the orchestrator through an AgentCore Runtime endpoint.

![Pellier in motion – the storefront and Atelier in action](/static/introduction/pellier-demo.webp)

:::alert{type="success" header="What you will walk away with"}
By the end of the session, you will understand how to move from a classic RAG search box to an agentic search architecture that can retrieve, reason, remember, use tools, enforce policy, and expose operator evidence.
:::

## Why this workshop

Many teams already have a Retrieval-Augmented Generation (RAG) application: a corpus, embeddings, a vector index, and a prompt that grounds an answer. The next production step is deciding what happens when retrieval is not enough.

Pellier makes that step concrete. You will keep the retrieval foundation, then add the seams that make an agentic application operational: deterministic tools over systems of record, session memory, dispatcher-style routing, policy-aware tool execution, managed invocation, and an evidence trail an operator can inspect.

The domain is retail, but the pattern is portable. In your environment, Pellier's product catalog might be clinical protocols, policy documents, service manuals, claims, contracts, tickets, product reviews, or operational records.

## System architecture

```mermaid
flowchart LR
    subgraph Surfaces["Surfaces"]
        Boutique["Boutique<br/>shopper view"]
        Atelier["Atelier<br/>operator view"]
        CodeEditor["Code Editor<br/>builder IDE"]
    end

    subgraph App["FastAPI · :8000"]
        Dispatcher["Dispatcher<br/>intent routing"]
        Specialists["5 Strands specialists<br/>Style Advisor · Curator ·<br/>Value Analyst · Stock Keeper ·<br/>Experience Guide"]
        Tools["13 @tool functions<br/>find_pieces · floor_check ·<br/>process_return · ..."]
        Policy["Cedar policy hook<br/>mutation boundary"]
    end

    subgraph Data["Aurora PostgreSQL"]
        Catalog["product_catalog<br/>pgvector + FTS"]
        Warehouse["warehouse_inventory<br/>system of record"]
        Audit["tool_audit<br/>operator ledger"]
        Profiles["episodic + profile<br/>rows"]
    end

    subgraph Bedrock["Bedrock + AgentCore"]
        Models["Foundation models<br/>Claude · Cohere"]
        Memory["AgentCore Memory<br/>working + semantic"]
        Runtime["AgentCore Runtime<br/>managed invoke"]
    end

    subgraph MCP["MCP layer"]
        LocalMCP["Postgres MCP<br/>read-only"]
        Gateway["AgentCore Gateway<br/>managed MCP host"]
    end

    Boutique --> Dispatcher
    Atelier --> App
    CodeEditor --> App
    Dispatcher --> Specialists
    Specialists --> Tools
    Tools --> Policy
    Policy --> Catalog
    Policy --> Warehouse
    Policy --> Audit
    Specialists --> Models
    Specialists --> Memory
    Runtime --> Dispatcher
    LocalMCP --> Catalog
    Gateway --> LocalMCP
    Catalog --> Profiles

    classDef default fill:#f8f5ec,stroke:#8a7a5a,stroke-width:1.2px,color:#3d2f15;
    classDef cluster fill:#fdfaf1,stroke:#6b5a3a,stroke-width:1.5px,color:#3d2f15;
    class Surfaces,App,Data,Bedrock,MCP cluster;
```

## Learning outcomes

By the end of this workshop, you will be able to:

- Explain how Pellier combines **Aurora PostgreSQL**, **pgvector**, **hybrid retrieval**, **reranking**, **specialist agents**, **memory**, and **runtime invocation** into one agentic search architecture.
- Build and validate a local development loop in **Code Editor** without losing sight of the managed services behind the lab.
- Wire a **Strands** `@tool` body to a real **Aurora** system-of-record table and verify the result from the shopper and operator views.
- Compare **vector search**, **hybrid retrieval**, and **reranking** as query-class decisions rather than defaults.
- Inspect **AgentCore Memory**, **AgentCore Runtime** events, routing decisions, and Aurora `tool_audit` rows as production evidence.
- Describe how **Model Context Protocol (MCP)**, **AgentCore Gateway**, **Cedar** policy, and **Knowledge Bases** fit into a production-oriented agent workflow.
- Translate the Pellier retail example into your own domain: healthcare operations, financial services, manufacturing, public sector, software operations, or another corpus-plus-tools workload.

## Prerequisites

You will move faster if you are comfortable with:

- AWS Workshop Studio and basic AWS console navigation.
- Terminal commands, environment variables, and reading logs.
- Python 3.10+ syntax, decorators, and basic async flow.
- PostgreSQL basics: `psql`, tables, indexes, JSONB, and simple `SELECT` statements.
- RAG concepts: embeddings, vector search, semantic similarity, and grounded generation.
- API and application architecture concepts such as request routing, authentication boundaries, and observability.

The workshop environment is pre-provisioned. You do not need to install packages locally or deploy infrastructure from scratch during the session.

## Module map

| Section | Focus | Time |
|---|---|---|
| [Introduction](/00-introduction/) | Open the environment, understand the surfaces, and frame the architecture. | ~5 min |
| [Act I: The Boutique](/10-act-1-the-boutique/) | Local development: observe Marco, wire `floor_check`, and measure retrieval quality. | ~30 min |
| [Act II: The Ledger](/20-act-2-the-ledger/) | Platform evidence: validate memory, invoke Runtime, and read the Aurora audit ledger. | ~12 min |
| [Act III: The Concierge](/30-act-3-the-concierge/) | Production patterns: routing, MCP, and managed RAG with Knowledge Bases. | ~8 min |
| [Summary and conclusion](/40-close/) | Close the loop and map the architecture back to your own stack. | ~3 min |
| [Appendix](/90-appendix/) | Reference, troubleshooting, portability maps, and facilitator notes. | Optional |

::::alert{type="success" header="Start here"}
[Introduction →](/00-introduction/)
::::
