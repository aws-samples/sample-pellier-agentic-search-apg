---
title: "Setup"
weight: 1
---

You have **~7 minutes** before Act I opens.

Setup is verification, not installation. The CloudFormation bootstrap already seeded Aurora, created AgentCore Memory, launched Runtime, and started the FastAPI backend on `:8000`.

:::alert{type="warning" header="📷 Capture asset before ship"}
**6-second loop** — Marco's chat drawer opens (`⌘K`), query types in *"what linen do you have for Goa"*, response streams with editorial copy + three product cards, trace chip appears: `Style Advisor · Opus 4.6 · find_pieces`. Loop seamlessly. Target: `/static/setup/marco-chat-loop.webp` (~1200×750, &lt;2MB).
:::

<!-- Once asset is captured, REPLACE the alert above with the line below:
![Marco asks Pellier for linen for Goa — response streams with three product cards and a trace chip](/static/setup/marco-chat-loop.webp)
-->

## Setup path

1. [Open the workspace](./01-open-workspace/) — enter Code Editor, confirm the backend, and open Boutique plus Atelier side by side.
2. [Run pre-flight checks](./02-pre-flight/) — verify Aurora data, AgentCore resources, and the audit ledger before Marco's flow.

## Key takeaways

- The lab is already deployed; you are proving it is ready.
- Boutique (`/`) creates shopper behavior. Atelier (`/atelier`) explains it.
- Green checks now keep the build focused on Marco, not infrastructure.

:::alert{type="info"}
Optional primer: [pgvector in two minutes](/90-appendix/05-pgvector-primer/).
:::

::::alert{type="success" header="Begin setup"}
[Open the workspace →](./01-open-workspace/)
::::
