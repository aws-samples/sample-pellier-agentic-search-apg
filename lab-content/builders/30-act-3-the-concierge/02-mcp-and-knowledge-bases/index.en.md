---
title: "02: MCP and Knowledge Bases"
weight: 20
---

:::alert{type="info"}
**Time:** ~3 min  
**Exercises:** 0  
**Surface:** `pellier/config/mcp-server-config.json` · terminal (`uvx`, `psql`)
:::

No code. Read the **MCP contract** that wires `pellier.*` tables into a real MCP server, prove the server is reachable from the integrated terminal, then compare the build-it-yourself retrieval path from this lab with the broader **Knowledge Bases** pattern.

Bedrock Knowledge Bases is one managed AWS option. It should not be the only mental model participants leave with. The architectural decision is larger: when do you own retrieval code, and when do you hand ingestion, chunking, embedding, sync, and retrieve APIs to a knowledge-base layer?

**You will learn to:**

1. **Read the MCP config** registered against your Aurora cluster: the
   literal artifact that turns a process into an MCP-callable tool host.
2. **Verify the server from the terminal**: `uvx --help` plus the same
   SQL via `psql` to prove the data path the MCP server would proxy.
3. Compare **build-it-yourself pgvector + Strands** (this lab) with
   **Knowledge Bases** as a managed or platform-owned retrieval pattern:
   Bedrock Knowledge Bases, OpenSearch-backed retrieval, enterprise
   search, or a custom pgvector service.

The abstract names **MCP** alongside RAG and agentic AI. This is where
that name becomes a config file you can read and a server you can poke.

:::alert{type="info" header="New to MCP?"}
MCP is a tool contract, not a new database. A host starts or connects to
an MCP server, asks what tools it offers, and sends `tools/call` frames
when the model chooses one. In this page, the server is read-only and
points at the same Aurora cluster the agents already use.
:::

---

## 1. Read the MCP config

```bash
cat /workshop/sample-pellier-agentic-search-apg/pellier/config/mcp-server-config.json \
  | python3 -m json.tool
```

You will see the AWS Labs Postgres MCP server registered against your
cluster:

```json
{
  "mcpServers": {
    "awslabs.postgres-mcp-server": {
      "command": "uvx",
      "args": [
        "awslabs.postgres-mcp-server@latest",
        "--resource_arn",  "${DB_CLUSTER_ARN}",
        "--secret_arn",    "${DB_SECRET_ARN}",
        "--database",      "${DB_NAME}",
        "--region",        "${AWS_REGION}",
        "--readonly",      "True"
      ],
      "env": { "AWS_REGION": "${AWS_REGION}", "FASTMCP_LOG_LEVEL": "ERROR" }
    }
  }
}
```

Three things this config tells you:

- **MCP servers are processes.** `uvx` pulls the package on first call
  and runs it locally. There is no mysterious cloud-only MCP service:
  just a process speaking JSON-RPC over stdio.
- **`--readonly True` is the safety rail.** Same Aurora cluster the
  Strands agents read; no DDL, no writes, no drift.
- **Any MCP host reads this same shape.** A VS Code chat extension, a
  Claude Code session, a Strands agent using `MCPClient`, or Bedrock
  AgentCore Gateway running managed: same JSON contract, different hosts.

:::alert{type="info" header="Pattern to borrow"}
MCP is a thin contract between an LLM-aware host and a data source: a
process advertising tool definitions over JSON-RPC, scoped by an ARN,
and gated by a read-only flag. In Pellier the data source is `pellier.*`
on Aurora. In another stack the same shape exposes a claims database to
a copilot, an inventory database to a planning assistant, an EHR to a
clinical scribe, or a finance ledger to an analytics agent: same
protocol, same safety rails, different rows.
:::

---

## 2. Verify the server from the terminal

```bash
uvx awslabs.postgres-mcp-server@latest --help 2>&1 | head -25
```

You will see the flag surface (`--resource_arn`, `--secret_arn`,
`--readonly`, `--database`, `--region`), proving the server binary is
installed and runnable on this box. Any MCP host that reads the config
above spawns this same process under the hood.

To see the rows the server would return, query Aurora directly:

```bash
psql -c "SELECT name, brand, price
           FROM pellier.product_catalog
          WHERE category = 'shirts'
          ORDER BY price ASC
          LIMIT 5;"
```

That SQL is what an MCP `tools/call` against `run_query` would proxy.
**Same Aurora, same rows, just unwrapped from the protocol envelope.**

::::expand{header="What an MCP tools/call looks like in JSON-RPC"}

When an MCP host wants to run that query, it sends a frame like this over
stdio to the running server:

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "tools/call",
  "params": {
    "name": "run_query",
    "arguments": {
      "sql": "SELECT name, brand, price FROM pellier.product_catalog WHERE category = 'shirts' ORDER BY price ASC LIMIT 5;"
    }
  }
}
```

The server runs the query against Aurora (read-only), wraps the rows in
a JSON-RPC response, and the host renders them. The protocol is all that
stands between any MCP-aware client and your data.

::::

---

## 3. Knowledge Bases: when to own retrieval vs. delegate it

Pellier deliberately owns retrieval code. You can read the SQL, tune the
HNSW index, choose the RRF merge, inspect rerank latency, and decide
whether a row-per-product representation is right for a curated catalog.

That is not always the right operating model. A **knowledge base** is the
pattern you reach for when the corpus is more document-shaped: PDFs,
policies, manuals, knowledge articles, S3 folders, contracts, or support
content where ingestion, chunking, embedding, sync, and retrieval should
be a platform capability.

| Decision point | This lab: **build it yourself** | **Knowledge-base pattern** |
|---|---|---|
| Retrieval surface | `find_pieces_hybrid` Python tool you can read | Retrieve API or search endpoint managed by a platform layer |
| Corpus shape | 40 curated SKUs with editorial copy and structured fields | Large document collections, manuals, PDFs, policies, tickets, internal docs |
| Vector/index ownership | You provision and tune Aurora pgvector | Platform owns or integrates with the vector/search backend |
| Chunking | You decide; in Pellier, one row = one product | Platform chunks and syncs documents, often from object storage or connectors |
| Reranking | Cohere Rerank v3.5 inside the agent path | Optional managed rerank, search ranking, or application-level rerank |
| Tool calling | Strands `@tool` you wrote | Bedrock Agents, Strands, LangGraph, custom app logic, or another orchestrator |
| Best for | Curated catalogs, hybrid retrieval control, tight latency, SQL-shaped evidence | Document-heavy RAG where operational ownership matters more than custom retrieval internals |
| Example options | Aurora/RDS pgvector, custom Postgres SQL, OpenSearch query layer | Bedrock Knowledge Bases, OpenSearch-backed knowledge search, enterprise search, vector database-backed RAG |

:::alert{type="info" header="Rule of thumb"}
If you can describe the retrieval SQL in one paragraph and need exact
control over filters, joins, ranking, and evidence, own the pgvector
path. If the workload is *ingest this pile of documents and retrieve the
right passages*, use a knowledge-base layer.
:::

:::alert{type="info" header="Where Bedrock fits"}
Bedrock Knowledge Bases is the AWS managed option for this pattern. It is useful language for AWS builders, but the workshop teaches the pattern first: managed document retrieval over a corpus. That keeps the close relevant for participants whose organizations already use OpenSearch, enterprise search, a custom pgvector service, or another vector database.
:::

---

## What you have seen

- **MCP is a protocol, not a service.** A local Python process
  advertising a few SQL templates was enough to put `pellier.product_catalog`
  one tool call away from any MCP-aware host.
- **The same MCP shape scales up.** Bedrock AgentCore Gateway is the
  managed-host version of the contract you just read; the lab keeps it
  read-only/operator-view rather than making it a build step.
- **Knowledge Bases are a retrieval ownership choice.** Bedrock Knowledge
  Bases is one managed option; the broader pattern is a platform-owned
  retrieval layer for document-heavy corpora.
- **Pellier still needs build-it-yourself retrieval.** A curated product
  catalog with hybrid SQL, rerank control, operational reads, and audit
  evidence is exactly where owning the retrieval path teaches the most.

:::alert{type="success" header="Close the room"}
Loop closed: question → embed → pgvector retrieve → rerank → ground →
generate → memory (working / semantic / episodic / procedural) → managed
Runtime → MCP / Knowledge Bases as upgrade paths.

[Summary and conclusion →](/40-close/)
:::
