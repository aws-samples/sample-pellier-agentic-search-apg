---
title: "Shipment SQL · The shipment that just arrived"
weight: 20
---

:::alert{type="info"}
*Optional follow-on (~10 minutes), best after the main session. Not part
of the 45-minute hands-on block.*
:::

Anna's Beeswax Tapers story: one `UPDATE` to refresh catalog quantity, then
the agent notices on the next search turn.

```bash
psql -c "SELECT \"productId\", name, quantity FROM pellier.product_catalog WHERE name ILIKE '%beeswax%';"
```

Use the exact product name returned by your `SELECT` to avoid updating
multiple rows accidentally:

```sql
UPDATE pellier.product_catalog
   SET quantity = 24
 WHERE name = 'Beeswax Taper Candles';
```

Switch to **Anna** in the Boutique and re-run the beeswax pill — in-stock
language should return without a redeploy.
