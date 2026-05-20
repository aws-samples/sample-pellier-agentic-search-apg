---
title: "Build · Wire `floor_check`"
weight: 20
---

:::alert{type="warning" header="Exercise 1 of 2 — the core build moment"}
**Time:** ~15 min  ·  **Page:** 2 of 3 in Act I  ·  **File:** `pellier/backend/services/agent_tools.py`

You'll replace one stubbed tool body — `floor_check` — between the
`START` / `END` markers, then verify Marco's Turn 4 lands against
live Aurora warehouse data. **⏩ Out of time?** A one-line `cp` from
`solutions/closing-marcos-gap/` swaps in the reference implementation —
the act still completes.
:::

**You'll learn to:**

1. Read a real Aurora schema (`pellier.warehouse_inventory`) and
   confirm the data is real before assuming the tool is broken.
2. Wire a Strands `@tool` body that bridges agent intent to a
   `BusinessLogic` source of truth — the everyday production shape.
3. Verify the wiring **two ways**: the Atelier's tool registry strip
   (11/12 → 12/12 shipped) and a replay of Marco's Turn 4 in the
   Boutique with a real trace chip and duration.
4. Diagnose a failed save from `uvicorn.log` instead of guessing.

The Stock Keeper specialist exists. Its system prompt is finished.
The orchestrator already routes warehouse questions to it. Only
the **body** of `floor_check` is stubbed — when Marco asks Turn 4,
Stock Keeper calls `floor_check(product_query="Hadley shirt")` and
the stub returns a placeholder JSON envelope. **Your job: replace
the stub with a small implementation that calls
`BusinessLogic.floor_check()` against Aurora.**

::::expand{header="Out of time? Drop in the solution"}

```bash
cd /workshop/sample-pellier-agentic-search-apg
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
   pellier/backend/services/agent_tools.py
```

Paste-only option: `solutions/closing-marcos-gap/services/floor_check_tool_body.py`.

Then jump to step 4 (Verify in the Atelier).

::::

## 1 · Read the warehouse

In the terminal:

```bash
psql -c "\d pellier.warehouse_inventory"
```

Three columns: `warehouse_id`, `product_id`, `quantity`. Composite
primary key on `(warehouse_id, product_id)`.

```bash
psql -c "SELECT w.id, w.display_name, count(*) AS items, sum(wi.quantity) AS units \
         FROM pellier.warehouses w \
         JOIN pellier.warehouse_inventory wi ON wi.warehouse_id = w.id \
         GROUP BY 1,2 ORDER BY 1;"
```

Three warehouses are seeded — `BK-01` (Brooklyn), `ATX-02` (Austin),
`PDX-01` (Portland). Each holds a deterministic 40/30/30 split of
the catalog quantity. **That's what `floor_check` reads.**

## 2 · Open `agent_tools.py`

Open `pellier/backend/services/agent_tools.py` in Code Editor and
search for `=== CHALLENGE · Stock Keeper · floor_check: START ===`.
You'll find this stub:

```python
@tool
def floor_check(product_query: str = "") -> str:
    """Inventory check across the catalog and three warehouses.

    Pass product_query whenever the customer mentions a specific product.
    Call without arguments only for aggregate inventory-health questions.
    """
    # === CHALLENGE · Stock Keeper · floor_check: START ===
    # WORKSHOP_EXERCISE_STUB
    return json.dumps({
        "error": "floor_check is in stub state",
        "hint": "Implement the tool body or run the cp command.",
        "received_product_query": product_query,
    })
    # === CHALLENGE · Stock Keeper · floor_check: END ===
```

The other tools in this file (e.g. `whats_trending`, `price_intelligence`,
`running_low`) follow the same shape. **Read one of them as a
working example before you write yours.**

## 3 · Write the body

Replace the `return json.dumps({...})` block between the `START` /
`END` markers with this shape:

```python
if not _db_service:
    return json.dumps({"error": "Database service not initialized"})

try:
    from services.business_logic import BusinessLogic
    logic = BusinessLogic(_db_service)
    query = (product_query or "").strip() or None
    result = _run_async(logic.floor_check(product_query=query))
    return json.dumps(result, indent=2)
except Exception as e:
    return json.dumps({"error": str(e)})
```

**A short block between the guards.** That's it.

::::expand{header="Why this shape (the handoff from app code to agent behavior)"}

`BusinessLogic.floor_check()` is a normal backend function —
ordinary application code. `@tool def floor_check(...)` is the
**contract** the agent can discover, call, and cite. The name and
docstring teach the agent *when* the capability applies; the body
decides *what source of truth* it reaches.

This is the everyday shape of agent work in production: the system
already knows the *plan* (which agent, which tool, with what
arguments). The wiring is a small, careful connection between a
tool's intent and its source of truth.

::::

Save the file. The backend auto-reloads (~1 s). Watch the log if
you want to confirm:

```bash
tail -f /tmp/pellier/uvicorn.log
```

If you see an `ImportError` or `SyntaxError`, fix the line the
traceback points at and save again.

::::expand{header="Reference solution — only peek if you're stuck"}

```python
@tool
def floor_check(product_query: str = "") -> str:
    """Inventory check across the catalog and three warehouses.

    Pass product_query whenever the customer mentions a specific product.
    Call without arguments only for aggregate inventory-health questions.
    """
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        query = (product_query or "").strip() or None
        result = _run_async(logic.floor_check(product_query=query))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
```

::::

## 4 · Verify in the Atelier

Switch to the Atelier tab. Under **UNDERSTAND → Tools**, the
`floor_check` card was previously dashed-bordered with an *Exercise*
pill. The progress strip read **11/12 shipped**.

After your save, hard-reload the Atelier tab. The strip should now
read **12/12 shipped** and `floor_check` has a solid border with a
sage *Shipped* pill.

Then click **Discover** and run:

> warehouse stock check

`floor_check` should land in the top three with a cosine score above
0.4 — the registry seeing your tool's docstring (which you didn't
edit) and matching it semantically.

::::expand{header="If the strip still says 11/12"}

```bash
tail -n 80 /tmp/pellier/uvicorn.log | grep -iE "error|traceback"
```

A common cause is a Python syntax error — uvicorn auto-reloads but
logs the failure to import. Fix and save again.

::::

## 5 · Replay Turn 4 in the Boutique

Switch to the Boutique tab. Click pill 4 again — *"Is the Hadley
shirt at the Brooklyn warehouse?"*

This time Stock Keeper's reply names Brooklyn, the quantity, the
ship window, and the other warehouses' counts. The trace chips read
`floor_check` with a real duration. **The stub envelope is gone.**

![Marco's turn 4, after you wired floor_check](/static/introduction/marco-pill-4-fixed.png)

That's the gap closed.

## What you've learned

A few lines of Python. But what those lines did:

- **Connected Stock Keeper** (already wired, already prompted, already
  trusted by the orchestrator) to real warehouse data — proving the
  agent already knew the *plan*; only the wiring was missing.
- **Closed Marco's Turn 4.** Turn 5 (`style_match`) already worked;
  this change isolated and fixed the stock-specific path.
- **Bumped the Atelier's tool inventory** from 11 shipped + 1 exercise
  to 12 shipped — in real time, without restarting anything.
- **Internalized the production shape** of agent work: the `@tool`
  decorator declares the contract the agent discovers; the body
  decides which source of truth answers the question.

:::alert{type="success" header="Exercise 2 next — Anna's skill"}
Turn 4 lands. Switch to Anna, prove whether hybrid + rerank earns
its latency, then **edit one rule in `the-gift-table` skill (Exercise 2)**
and verify it landed with SQL.

[Prove rerank earns its cost →](../03-prove-rerank/)
:::
