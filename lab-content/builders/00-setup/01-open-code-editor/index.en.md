---
title: "Open Code Editor"
weight: 10
---

:::alert{type="info"}
**Setup.** About two minutes. Open the IDE that runs the Boutique.
:::

::::tabs{variant="container"}
:::tab{label="I am in an AWS instructor-led event"}

1. Open the [workshop dashboard](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/en-US).
   In the **Event Outputs** panel, find **CodeEditorURL** and click it.
   Workshop Studio handles the sign-in for you.

2. The editor opens in a new tab with a welcome terminal already
   maximized and the workshop layout loaded. The aliases `workshop`,
   `pellier`, `backend`, `frontend`, and `psql` are available from the
   prompt.

3. Close any non-essential popups. You should land in
   `/workshop/sample-pellier-agentic-search-apg`.

:::
:::tab{label="I will use my own AWS account"}

> **Cost note:** This stack runs Aurora Serverless v2, an EC2
> `m5.large`, a NAT Gateway, and CloudFront — roughly **$0.20–0.25/hr**.
> Bedrock model calls bill separately at standard Claude Opus 4.6 and
> Haiku 4.5 rates. Delete the stack after the session.

1. Launch the **Pellier Builder's Session** CloudFormation template
   from the [`sample-pellier-agentic-search-apg` repo](https://github.com/aws-samples/sample-pellier-agentic-search-apg)
   (`lab-content/builders/static/pellier-builders.yml`).

2. Wait for the stack to complete (~12–15 minutes). Open the **Outputs**
   tab, find **CodeEditorURL**, and click it.

3. Use the value of **CodeEditorPassword** to sign in.

4. The editor opens with a welcome terminal. You should land in
   `/workshop/sample-pellier-agentic-search-apg`.

:::
::::

::::expand{header="What you have in your IDE"}

- **Code Editor (code-server)** — VS Code in the browser. Same
  keybindings, same extensions API.
- **AWS Labs Postgres MCP server** — the bootstrap installs
  [`awslabs.postgres-mcp-server`](https://github.com/awslabs/mcp/tree/main/src/postgres-mcp-server)
  via `uvx` and registers it against your Aurora cluster (read-only,
  secret-backed). The config lives at
  `pellier/config/mcp-server-config.json`. Any MCP host reads that
  shape: VS Code chat extensions, Claude Code, a Strands agent using
  `MCPClient`, or Bedrock AgentCore Gateway in managed deploys. You'll
  poke it from the integrated terminal in
  [Act III · MCP and Knowledge Bases](/30-act-3-the-concierge/02-mcp-and-knowledge-bases/).
- **Auto-reload** — every save to a `.py` file restarts the backend
  in about a second. No manual restart commands.

::::

::::expand{header="Aurora vs Amazon RDS for PostgreSQL — which one am I using?"}

This Builder's Session uses **Aurora PostgreSQL Serverless v2** because
the workshop pool needs elastic ACU scaling for parallel attendees. In
your own stack, **Amazon RDS for PostgreSQL** runs the exact same
pgvector primitives — `CREATE EXTENSION vector`, `vector(1024)` columns,
HNSW indexes, the `<=>` operator. Nothing in this lab is Aurora-specific.

| | Aurora PostgreSQL | RDS for PostgreSQL |
|---|---|---|
| Scaling | ACU-based (Serverless v2), seconds | Instance-class step (`db.r7g.xlarge` → `db.r7g.2xlarge`) |
| Failover | < 30 s typical | Multi-AZ failover ~60–120 s |
| Storage | Decoupled, auto-grow to 128 TiB | EBS, max 64 TiB |
| pgvector | 0.8.0 (engine 17.x) | 0.8.0 (engine 17.x) |
| Cost shape | Pay per ACU-second | Pay per instance-hour |
| Best for | Bursty workshop / spiky catalogs | Predictable single-AZ, smaller catalogs |

The retrieval, reranking, and agent code in this lab is **pgvector + Postgres**, not Aurora-specific.

::::

:::alert{type="success"}
Next: open the storefront you'll spend the next hour in.

[Meet the Boutique →](../02-meet-the-boutique/)
:::
