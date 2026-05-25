---
title: "Setup"
weight: 1
---

:::alert{type="info"}
**Time:** ~2 min  
**Exercises:** 0  
**Surfaces:** Code Editor · Boutique (`/`) · Atelier (`/atelier`)

One page gets you into the working environment. The CloudFormation bootstrap has already seeded Aurora, created AgentCore Memory, launched Runtime, and started the FastAPI backend on `:8000`. The facilitator confirmed readiness before the room opened — your job is to land in the IDE and open both surfaces side by side.
:::

## Step 1: Open Code Editor

In **Workshop Studio → Event Outputs**, copy **`CodeEditorURL`** and open it in a new tab. When prompted, paste **`CodeEditorPassword`**.

You should land in:

```text
/workshop/sample-pellier-agentic-search-apg/
```

The file tree is on the left, the editor is in the middle, and the integrated terminal is at the bottom. If the terminal is collapsed, press ``Ctrl+` ``.

::::expand{header="Folders you'll touch"}

```text
pellier/backend/services/agent_tools.py       # Act I · Exercise 1 (floor_check)
pellier/backend/agentcore_runtime.py          # Act II · Runtime entrypoint (read-only)
solutions/                                    # escape-hatch copies
```

::::

## Step 2: Open Boutique and Atelier

In Code Editor, open the **Ports** panel and click the forwarded address for port **8000**. The Pellier storefront opens in a new tab.

Look for the small *Pellier · listening* chip in the hero. That means the agent surface is awake.

In a second tab, append `/atelier` to the same URL. Keep both tabs open: you will use the Boutique to create behavior and the Atelier to explain it.

:::alert{type="info"}
Demo mode skips login. Use the chat drawer persona switcher for Marco, Anna, and Theo.
:::

## Key takeaways

- Code Editor is your operator seat for the hour.
- Boutique (`/`) is the shopper experience; Atelier (`/atelier`) is the evidence layer.
- Both surfaces read the same backend, Aurora data (`pellier.product_catalog`, `pellier.warehouse_inventory`, `pellier.tool_audit`), and AgentCore Memory.

:::alert{type="info"}
Optional primer: [pgvector in two minutes](/90-appendix/05-pgvector-primer/).
:::

::::alert{type="success" header="You're in"}
[Act I: Meet Marco →](/10-act-1-the-boutique/01-meet-marco/)
::::
