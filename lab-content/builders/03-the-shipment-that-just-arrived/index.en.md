---
title: "03 · The Shipment That Just Arrived"
weight: 20
---

:::alert{type="info"}
*About seven minutes. The catalog is wrong. You'll fix it with one line of
SQL and watch the agent notice on the very next turn.*
:::

## The other shopper

Switch persona in the Boutique to **Anna** — open the chat drawer,
click the small avatar in the upper-left of the drawer, choose
*Anna · gift-giver*. Anna shops for thoughtful gifts. Her opening
prompt today is one of the suggested pills:

> *"Show me the Beeswax Tapers — they're for a housewarming."*

Click it.

The agent runs the search. It surfaces the Tapers, but the answer
includes a strange sentence:

> *"The Pellier Beeswax Tapers are out of stock right now — I can
> show you a similar piece from another maker if you'd like."*

That's odd. The Beeswax Tapers are one of Pellier's signature
gifts; "out of stock" isn't a sentence Anna should be reading
at all. Let's see what's going on.

---

## Look at the catalog

```bash
psql -c "SELECT \"productId\", name, quantity FROM pellier.product_catalog WHERE name ILIKE '%beeswax%';"
```

You should see:

```
 productId |          name           | quantity
-----------+-------------------------+----------
        21 | Beeswax Taper Candles   |        0
```

There it is. Quantity zero. The agent is reading live inventory
on every turn — exactly what `inventory.live` is supposed to do —
and it's correctly reporting what the table says.

So the bug isn't in the agent. The bug is in the data. A shipment
of Beeswax Tapers arrived at the Brooklyn warehouse this morning,
and nobody updated the catalog.

::::expand{header="Why didn't bootstrap-labs.sh seed this with stock?"}

`seed_boutique_catalog.py` runs once at deploy time and seeds every
product with a default quantity of 50. Between deploys, the catalog
drifts — pieces sell out, new shipments arrive, restock orders
land. In production this is wired through an inventory service
that pushes to Aurora; in the workshop, *you* are the inventory
service.

::::

---

## Log the shipment

You're going to log a fresh shipment of Beeswax Tapers — 12 units
landed at the Brooklyn warehouse — in two places, because the
boutique reads from two tables.

The first is the **catalog**, which the boutique surfaces in search
results:

```bash
psql -c "UPDATE pellier.product_catalog SET quantity = 12, updated_at = now() WHERE \"productId\" = '21';"
```

The second is the **warehouse inventory**, which Stock Keeper
reads (the table you queried in Module 02):

```bash
psql -c "\
  INSERT INTO pellier.warehouse_inventory (warehouse_id, product_id, quantity) \
  VALUES ('BK-01', '21', 12) \
  ON CONFLICT (warehouse_id, product_id) DO UPDATE \
    SET quantity = EXCLUDED.quantity, \
        updated_at = now();"
```

Two writes. No restart. No redeploy. No re-embedding the catalog.

::::expand{header="Why no re-embedding?"}

The product's vector encodes what the *piece* is — its name,
description, materials, palette. None of that changed. Only the
quantity did, and quantity isn't part of the embedding. The agent's
search hits stay identical; what changed is the live-inventory
filter that gets applied to those hits.

This is why "live data" is something the agent reads on every
turn, not something baked into the index.

::::

---

## Watch the agent notice

In the Boutique chat drawer, click the *Show me the Beeswax Tapers*
pill again — same pill, same Anna, same prompt.

The answer comes back without the "out of stock" sentence. Instead:

> *"The Pellier Beeswax Tapers are back — twelve at the Brooklyn
> warehouse. Beautifully wrap-ready, and they pair with the Linen
> Tea Towel I showed you last week. Want me to set a pair aside?"*

Two things to notice. The agent picked up the new quantity on the
*next* turn — no cache, no restart. And it remembered Anna had
looked at the Linen Tea Towel on a previous visit (that's a
`memory.recall` trace under the answer).

---

## A bonus: ask Stock Keeper directly

Now ask the agent — still in Anna's session — *"How many Beeswax
Tapers at Brooklyn?"*. The orchestrator routes this to Stock
Keeper, and the `floor_check` tool **you** wired in Module 02
fires. Stock Keeper sees the twelve units at `BK-01` and answers
with the number, the warehouse name, and the ship window.

Two specialists you've touched this session — Stock Keeper reading
`warehouse_inventory`, and the Curator reading
`pellier.product_catalog` — are both reflecting the write you just
made. That's not because they share state. It's because Aurora is
the shared state.

---

## What you saw

| | |
| --- | --- |
| The agent reads live | Quantity=0 produced "out of stock"; quantity=12 produced "back in stock" — same code path, different answer |
| The data is the agent's world | Two SQL writes, no redeploy, immediate behavioral change |
| Shared state, not shared cache | Two specialists (Curator, Stock Keeper) saw the same write because they read the same tables |
| Memory persists across turns | Anna's *"the Linen Tea Towel I showed you last week"* came from `memory.recall` — that thread didn't reset when you switched personas |

Two hands-on moments down — the `floor_check` tool body in Module 02,
the SQL writes here in Module 03. Five turns of Marco's afternoon
and two of Anna's are now backed by the data path you closed.

The last seven minutes are not coding. They're a tour of what's
been running underneath everything you just saw.

:::alert{type="success" header="Last stop"}
[Module 04 · *Step Into the Atelier* →](/04-step-into-the-atelier/)
:::
