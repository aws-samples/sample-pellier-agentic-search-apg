---
title: "Appendix · The shipment that just arrived (SQL)"
weight: 90
---

:::alert{type="info"}
*Optional — not on the 45-minute clock. Main path ends at Part III.*
:::

:::alert{type="info"}
*Optional after the session — not part of the 45-minute hands-on block.*
:::

Anna's Beeswax Tapers story: one `UPDATE` to refresh catalog quantity, then
the agent notices on the next search turn. Full steps lived in the earlier
Builder's v1 guide — run when you have ten extra minutes.

```bash
psql -c "SELECT \"productId\", name, quantity FROM pellier.product_catalog WHERE name ILIKE '%beeswax%';"
```

```sql
UPDATE pellier.product_catalog
   SET quantity = 24
 WHERE name ILIKE '%Beeswax Taper%';
```

Switch to **Anna** in the Boutique and re-run the beeswax pill — in-stock
language should return without a redeploy.
