---
title: Setup
weight: 10
---

**Time budget: 5 minutes**

Everything you need is already running in your lab environment. This page is a 60-second smoke test to confirm it.

## Your lab environment at a glance

When your Workshop Studio event launched, CloudFormation stood up:

- **Amazon Aurora PostgreSQL Serverless v2** with pgvector 0.8.0, seeded with the 40-product Blaize Bazaar catalog (10 products × 4 persona bands, real Cohere Embed v4 1024-dim embeddings)
- **Amazon Cognito User Pool** with three pre-seeded personas (Marco, Anna, Theo)
- **VS Code Server** on Graviton c6g.2xlarge, fronted by CloudFront, with this repo cloned to `/home/workshop/blaize-bazaar-workshop/`
- **FastAPI backend** on port `8000` (uvicorn, hot-reload enabled) via `systemctl`
- **Vite frontend** on port `5173` via `systemctl`

## Open two URLs

From your Workshop Studio event page, find:

1. **Code Editor URL** — the VS Code Server where you'll edit files. Tree is open to `blaize-bazaar-workshop/`.
2. **Boutique URL** — this is the customer-facing shopper surface. It's what your code affects.

The **Atelier** is served from the same host as the Boutique, at `/atelier`. You'll have both tabs open all day.

## 60-second smoke test

Open a terminal in Code Editor:

```bash
cd blaize-bazaar-workshop/blaize-bazaar/backend

# 1. Aurora is up and seeded
curl -s http://localhost:8000/api/products/count | head
# Expected: { "count": 40 }

# 2. Vector search is live
curl -s -X POST http://localhost:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"something for slow Sunday mornings","limit":3}' \
  | head -20
# Expected: 3 products with similarity scores > 0.7

# 3. The test suite is green on everything already implemented
pytest tests/ -q --ignore=tests/test_inventory_agent.py \
               --ignore=tests/test_agent_tools.py \
               --ignore=tests/test_customer_support_agent.py
# Expected: all green (we ignore the three suites you're about to make green)
```

If all three pass, you're set. If any fails, flag an instructor — this is much easier to sort now than mid-Module-2.

## Open the Boutique, meet Marco

1. Visit the Boutique URL
2. Click the persona pill in the header (top right). Pick **Marco**.
3. The storefront tunes to Marco's signals — hero photograph, Curated grid, Weekend Edit headline, Because-you-asked editorial cards all reshape.
4. Scroll to the hero search. Below the Ask Blaize input you'll see Marco's suggestion pills:
   - "What linen do you have for 10 days in Goa?"
   - "What would go with the Pellier shirt?"
   - "What's the price range for linen shirts?"
   - "Is the Pellier shirt at the Brooklyn warehouse?"
   - "What pairs with the Ecru overshirt?"

These aren't random — they're Marco's exact 4-turn workshop sequence plus a capstone pill. **Don't click anything yet** — the opening demo runs as a class in Module 1.

## Open the Atelier, find Stock Keeper

1. In the header, click **Atelier** (toggle next to the bag icon)
2. You land on `/atelier/sessions` — a list of replay-able Blaize conversations. You'll see Marco's three workshop sessions plus Anna and Theo's supporting sessions.
3. Click **Agents** in the left sidebar (under UNDERSTAND).
4. Notice the five specialists. **Stock Keeper** carries a burgundy **"Your turn"** pill. That's the build.
5. Notice every agent row's **model tag**. Five rows, three different model configurations. No normalization. The reasoning lives in the model-mix sidebar, coming next.

You're ready.

Next: [Module 1 · Observe](10-module1-observe.en.md)
