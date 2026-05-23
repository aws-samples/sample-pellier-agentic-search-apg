---
title: "Operator View · MCP and Bedrock Knowledge Bases"
weight: 20
---

:::alert{type="info"}
**Time:** ~3 min  ·  **Page:** 2 of 2 in Act III  ·  **Exercises on this page:** 0

No code — read the **MCP contract** that wires `pellier.*` tables into
a real MCP server, prove the server is reachable from the integrated
terminal, then compare with **Bedrock Knowledge Bases** as the managed
RAG counterpart on the same Aurora pgvector substrate.
:::

**You'll learn to:**

1. **Read the MCP config** registered against your Aurora cluster — the
   literal artifact that turns a process into an MCP-callable tool host.
2. **Verify the server from the terminal** — `uvx --help` plus the same
   SQL via `psql` to prove the data path the MCP server would proxy.
3. Compare **build-it-yourself pgvector + Strands** (this lab) with
   **Bedrock Knowledge Bases + Aurora** (managed RAG): same retrieval
   substrate, different ops boundary.

The abstract names **MCP** alongside RAG and agentic AI. This is where
that name becomes a config file you can read and a server you can poke.

---

## 1 · Read the MCP config

```bash
cat /workshop/sample-pellier-agentic-search-apg/pellier/config/mcp-server-config.json \
  | python3 -m json.tool
```

You'll see the [AWS Labs Postgres MCP server](https://github.com/awslabs/mcp/tree/main/src/postgres-mcp-server)
registered against your cluster:

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
  and runs it locally — there is no "MCP service in the cloud"
  mystery, just a process speaking JSON-RPC over stdio.
- **`--readonly True` is the safety rail.** Same Aurora cluster the
  Strands agents read; no DDL, no writes, no drift.
- **Any MCP host reads this same shape.** A VS Code chat extension, a
  Claude Code session, a Strands agent using `MCPClient`, Bedrock
  AgentCore Gateway running managed — same JSON contract, different
  hosts.

---

## 2 · Verify the server from the terminal

```bash
uvx awslabs.postgres-mcp-server@latest --help 2>&1 | head -25
```

You'll see the flag surface — `--resource_arn`, `--secret_arn`,
`--readonly`, `--database`, `--region` — proving the server binary is
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
**Same Aurora, same rows — just unwrapped from the protocol envelope.**

::::expand{header="What an MCP `tools/call` looks like in JSON-RPC"}

When an MCP host (say, a chat extension) wants to run that query, it
sends a frame like this over stdio to the running server:

```json
{
  "jsonrpc": "2.0", "id": 7, "method": "tools/call",
  "params": {
    "name": "run_query",
    "arguments": {
      "sql": "SELECT name, brand, price FROM pellier.product_catalog WHERE category = 'shirts' ORDER BY price ASC LIMIT 5;"
    }
  }
}
```

The server runs the query against Aurora (read-only), wraps the rows
in a JSON-RPC response, and the host renders them. The protocol is
all that stands between any MCP-aware client and your data.

::::

---

## 3 · MCP vs Bedrock Knowledge Bases — when to pick which

Both are valid paths to RAG over Aurora pgvector. Different shapes
of operational ownership.

| | This lab — **build-it-yourself** | **Bedrock Knowledge Bases** |
|---|---|---|
| Retrieval | `find_pieces_hybrid` Python tool you can read | Managed retrieve API |
| Vector store | Aurora pgvector (you provision) | Aurora pgvector (Knowledge Bases provisions) **or** OpenSearch Serverless |
| Embeddings | You call Cohere Embed v4 directly | Knowledge Bases calls the embedder for you |
| Chunking | You decide (one row = one product) | Knowledge Bases auto-chunks documents |
| Reranking | Cohere Rerank v3.5 in the agent path | Optional Cohere/Amazon reranker on retrieve |
| Tool calling | Strands `@tool` you wrote | Bedrock Agents (or your own agent loop) |
| Best for | Curated catalogs, custom retrieval (hybrid + RRF), tight latency | Document-heavy RAG (PDFs, S3 buckets, large unstructured corpora) |
| Where this lab fits | ✓ — 40 hand-curated SKUs with editorial copy | Knowledge Bases would be overkill |

**Architectural rule of thumb:** if you can describe your retrieval
SQL in one paragraph, build it yourself on pgvector. If your "retrieval"
is "ingest a folder of PDFs and find me the right paragraphs,"
Knowledge Bases is the faster path.

::::expand{header="The Aurora pgvector substrate is identical"}

Knowledge Bases on Aurora **uses the same `vector(1024)` column type
and HNSW index** you saw in [the pgvector primer](/00-setup/04-pgvector-primer/).
The difference is which side of the AWS line owns the lifecycle:

- **DIY (this lab):** you `CREATE TABLE`, you embed, you query, you
  rerank, you ground the prompt.
- **Knowledge Bases:** AWS creates the table for you (in your Aurora
  cluster, your VPC), embeds new documents on `Sync`, and exposes
  retrieve as an API.

Either way, **Amazon RDS for PostgreSQL works the same** for the DIY
path. Knowledge Bases currently provisions Aurora-only when targeting
PostgreSQL — that's the one Aurora-specific seam in this comparison.

::::

---

## What you've seen

- **MCP is a protocol, not a service.** A local Python process
  advertising a few SQL templates was enough to put `pellier.product_catalog`
  one click away in your IDE.
- **The same MCP shape scales up.** Bedrock AgentCore Gateway is the
  managed-host version of what you just clicked.
- **Bedrock Knowledge Bases ≠ a competitor to this lab.** It's the
  managed RAG path on the same pgvector substrate — pick it for
  document-heavy corpora; pick the build-it-yourself path for
  curated catalogs where you need precise control over hybrid
  retrieval.

:::alert{type="success" header="Close the room"}
Loop closed: question → embed → pgvector retrieve → rerank → ground →
generate → STM → managed Runtime → MCP / Knowledge Bases as upgrade
paths.

**Final read for the table:** [What this maps to in your stack](/90-appendix/04-your-stack/)
— the portability swaps for Aurora ↔ RDS, Cohere ↔ Titan, Strands ↔
Bedrock Agents, AgentCore ↔ Lambda.

Other appendices: [Optional SQL](/90-appendix/02-shipment-sql/) · [When things misbehave](/90-appendix/03-when-things-misbehave/)
:::
