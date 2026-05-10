---
title: Setup
weight: 15
---

**Time budget: 3 minutes**

Your lab environment is already running. One URL, one smoke test, one glance at the Atelier.

## From Workshop Studio

- **Code Editor URL** — VS Code Server. Tree opens to `pellier-workshop/`.
- **Boutique URL** — the customer-facing shopper surface.
- **Atelier** — same host as the Boutique, at `/atelier`.

## Smoke test

Terminal in Code Editor:

```bash
cd pellier-workshop/pellier/backend
curl -s http://localhost:8000/api/products/count
# Expected: { "count": 40 }
```

If it returns 40, you're set. If it returns anything else, flag an instructor.

## Open both tabs

- **Boutique** — click persona pill → pick **Marco**. Scroll to the hero; you'll see Marco's 5 pills. **Don't click any yet**; the opening demo runs as a class.
- **Atelier** → `/atelier/sessions`. Click **Agents** in the sidebar. Notice Stock Keeper's "**Your turn**" pill. That's the build.

Quick look at the model tags on the Agents page — five rows, three different configurations. The reasoning is in Module 1.

Next: [Presentation (10 min talk)](05-presentation.en.md)
