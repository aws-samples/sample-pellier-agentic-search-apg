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
- **Aurora MCP Server** — a sidebar panel that lets you browse the
  `pellier.product_catalog` schema and run SQL without leaving the
  IDE.
- **Amazon Q** — AI-assisted code completion. Optional; the lab
  doesn't depend on it.
- **Auto-reload** — every save to a `.py` file restarts the backend
  in about a second. No manual restart commands.

::::

:::alert{type="success"}
Next: open the storefront you'll spend the next hour in.

[Meet the Boutique →](../02-meet-the-boutique/)
:::
