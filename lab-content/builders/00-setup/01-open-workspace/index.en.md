---
title: "Open the workspace"
weight: 10
---

:::alert{type="info"}
**Time:** ~3 min  
**Goal:** enter the IDE, confirm the backend, and open the shopper and operator surfaces.
:::

One page gets you into the working environment: Code Editor for edits and commands, Boutique for shopper behavior, and Atelier for operator evidence.

## Step 1: Open Code Editor

In **Workshop Studio → Event Outputs**, copy **`CodeEditorURL`** and open it in a new tab. When prompted, paste **`CodeEditorPassword`**.

You should land in:

```text
/workshop/sample-pellier-agentic-search-apg/
```

The file tree is on the left, the editor is in the middle, and the integrated terminal is at the bottom. If the terminal is collapsed, press ``Ctrl+` ``.

::::expand{header="Folders you'll touch"}

```text
pellier/backend/services/agent_tools.py       # Exercise 1
pellier/backend/agentcore_runtime.py          # Runtime entrypoint, read-only
pellier/backend/services/agentcore_runtime.py # optional log seam
solutions/                                   # escape-hatch copies
```

::::

## Step 2: Confirm the backend

Run:

```bash
curl -s http://localhost:8000/api/health | jq
```

Any parsed JSON response means FastAPI is up and hot-reload is on.

::::expand{header="Health check failed?"}

```bash
sudo journalctl -u pellier-backend -n 30 --no-pager
```

Then use [When things misbehave](/90-appendix/03-when-things-misbehave/#backend-wont-start) for the recovery path.

::::

## Step 3: Open Boutique and Atelier

In Code Editor, open the **Ports** panel and click the forwarded address for port **8000**. The Pellier storefront opens in a new tab.

Look for the small *Pellier · listening* chip in the hero. That means the agent surface is awake.

In a second tab, append `/atelier` to the same URL. Keep both tabs open: you will use the Boutique to create behavior and the Atelier to explain it.

:::alert{type="info"}
Demo mode skips login. Use the chat drawer persona switcher for Marco, Anna, and Theo.
:::

## Key takeaways

- Code Editor is your operator seat for the hour.
- Boutique is the shopper experience; Atelier is the evidence layer.
- Both surfaces read the same backend, Aurora data, and AgentCore memory.

::::alert{type="success" header="Next"}
[Run pre-flight checks →](../02-pre-flight/)
::::
