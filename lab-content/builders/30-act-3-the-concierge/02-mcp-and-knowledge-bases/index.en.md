---
title: "Operator View · MCP and Bedrock Knowledge Bases"
weight: 20
---

:::alert{type="info"}
**Time:** ~3 min  ·  **Page:** 2 of 2 in Act III  ·  **Exercises on this page:** 0

No code — read how the **same Aurora schema** is reachable as **MCP
tools** in your IDE, and where this build-it-yourself path differs
from the **managed Bedrock Knowledge Bases** path. The takeaway: same
primitives, different operational seam.
:::

**You'll learn to:**

1. **Open the Aurora MCP sidebar** in Code Editor and run a query that
   the agent could call with the same contract.
2. Read `pellier/config/mcp.json` — the literal config that surfaces
   `pellier.product_catalog` as an MCP tool.
3. Compare **build-it-yourself pgvector + Strands** (this lab) with
   **Bedrock Knowledge Bases + Aurora** (managed RAG): same retrieval
   substrate, different ops boundary.

The abstract names **MCP** alongside RAG and agentic AI. This is where
that name becomes a click and a config file you can copy.

---

## 1 · Open the Aurora MCP sidebar

In Code Editor, look at the left sidebar. Find the **Aurora MCP** panel
(diamond icon). Click to expand. You should see entries for:

- `pellier.product_catalog`
- `pellier.warehouse_inventory`
- `pellier.customers`
- `pellier.customer_episodic_seed`

Click `pellier.product_catalog` and choose **Run query**. Paste:

```sql
SELECT name, brand, price
  FROM pellier.product_catalog
 WHERE category = 'shirts'
 ORDER BY price ASC
 LIMIT 5;
```

The result lands inline in the IDE. **You did not write a single line
of Python**. That's the MCP contract working: a tool description,
a parameter schema, and a server that knows how to execute it.

::::expand{header="What just happened (the MCP shape)"}

Code Editor spoke **Model Context Protocol** to the local Aurora MCP
server. The server advertises capabilities (tables, query templates,
schemas) and the client (your IDE, or a Strands agent, or any MCP
host) calls them through a single uniform interface. The **same
contract** any LLM client uses works in your IDE — that's why MCP is
the abstract's third pillar after RAG and agentic AI.

::::

---

## 2 · Read the config

```bash
cat /workshop/sample-pellier-agentic-search-apg/pellier/config/mcp.json | python3 -m json.tool | head -40
```

You'll see one server entry per registered MCP server. The Aurora
entry roughly looks like:

```json
{
  "mcpServers": {
    "aurora": {
      "command": "python3",
      "args": ["-m", "aurora_mcp_server"],
      "env": {
        "DB_HOST": "${DB_HOST}",
        "DB_NAME": "${DB_NAME}",
        "DB_USER": "${DB_USER}"
      }
    }
  }
}
```

Two takeaways:

- **MCP servers are processes.** They speak stdio or HTTP/SSE. There
  is no "MCP service in the cloud" mystery — it's a local process
  with a well-defined protocol.
- **Bedrock AgentCore Gateway is an MCP server**, just deployed to
  AWS-managed infrastructure. The Strands agents in this lab can
  reach Gateway tools the same way your IDE reaches the local Aurora
  server — same protocol, different host.

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
