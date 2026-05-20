---
title: "Act I · Build — Wire `floor_check`"
weight: 12
---

:::alert{type="info"}
**Act I · Build + prove.** About fifteen minutes. The
**only coding exercise** in the session — one tool body in `floor_check`,
then Marco's Turn 4 lands.
:::

For a one-hour run, this is the core build block. Timebox this section to
about 18 minutes max, including verification, then move to Anna's proof and
the short skill-edit extension.

::::expand{header="Out of time? Drop in the solution"}

```bash
cd /workshop/sample-pellier-agentic-search-apg
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
   pellier/backend/services/agent_tools.py
```

Paste-only the tool body: `solutions/closing-marcos-gap/services/floor_check_tool_body.py`.

Then jump to [Verify in the Atelier](#verify-in-the-atelier).

::::

---

## What you're building

One tool body. The Stock Keeper specialist agent already exists with
a finished system prompt. The orchestrator already knows when to
route to Stock Keeper. The `floor_check` tool exists too — but its
body is stubbed. When Marco asks turn 4 (*"Is the Hadley shirt at
the Brooklyn warehouse?"*), the orchestrator routes to Stock Keeper,
Stock Keeper calls `floor_check(product_query="Hadley shirt")`, and
the stub returns:

```json
{ "error": "floor_check is in stub state",
  "hint": "This is the Builder exercise. Implement the tool body or run the cp command from lab 12.",
  "received_product_query": "Hadley shirt" }
```

That JSON is what makes turn 4 fail gracefully. Your job is to
replace the stub with a small implementation that calls
`BusinessLogic.floor_check(product_query=...)` against Aurora and
returns its result.

This is the handoff from ordinary application code to agent behavior:
`BusinessLogic.floor_check()` is a normal backend function, while
`@tool def floor_check(...)` is the contract the agent can discover, call,
and cite. The name and docstring teach the agent when the capability applies;
the body decides what source of truth it reaches.

---

## Read the warehouse

In the terminal:

```bash
psql -c "\d pellier.warehouse_inventory"
```

Three columns: `warehouse_id` (text, references `pellier.warehouses`),
`product_id` (text, references `pellier.product_catalog`),
`quantity` (smallint, 0–9999). Composite primary key on
`(warehouse_id, product_id)`.

```bash
psql -c "\
  SELECT w.id, w.display_name, count(*) AS items, sum(wi.quantity) AS units \
    FROM pellier.warehouses w \
    JOIN pellier.warehouse_inventory wi ON wi.warehouse_id = w.id \
   GROUP BY w.id, w.display_name \
   ORDER BY w.id;"
```

Three warehouses are seeded — `BK-01` (Brooklyn), `ATX-02` (Austin),
`PDX-01` (Portland). Each holds a deterministic 40/30/30 split of
the catalog quantity. That's what `floor_check` reads.

---

## The exercise — wire `floor_check`

Open `pellier/backend/services/agent_tools.py` in Code Editor.

Search for `=== CHALLENGE · Stock Keeper · floor_check: START ===`.
You'll find this stub block:

```python
@tool
def floor_check(product_query: str = "") -> str:
    """Inventory check across the catalog and three warehouses.

    Pass product_query whenever the customer mentions a specific product.
    Call without arguments only for aggregate inventory-health questions.
    """
    # === CHALLENGE · Stock Keeper · floor_check: START ===
    # WORKSHOP_EXERCISE_STUB
    #
    # Wire this tool to BusinessLogic.floor_check() so Stock Keeper
    # can answer Marco's Turn 4: "Is the Hadley shirt at the
    # Brooklyn warehouse?" (Hadley · Pellier Linen Shirt in ecru.)
    #
    # Steps:
    #   1. Guard on _db_service being initialized (return a JSON
    #      error if not).
    #   2. Import BusinessLogic from services.business_logic.
    #   3. Normalize product_query and pass it to logic.floor_check()
    #      via _run_async() — it's an async method.
    #   4. Return the result as a JSON string (use json.dumps with
    #      indent=2).
    #   5. Catch exceptions and return a JSON error envelope.
    return json.dumps({
        "error": "floor_check is in stub state",
        "hint": (
            "This is the Builder exercise. Implement the tool body or run "
            "the cp command from lab 12."
        ),
        "received_product_query": product_query,
    })
    # === CHALLENGE · Stock Keeper · floor_check: END ===
```

The stub spells out the implementation in five steps. The other
tools in this file (e.g., `whats_trending`, `price_intelligence`,
`running_low`) follow the exact same shape — read one of them as a
working example before you write yours.

### Hint — the shape of every tool in this file

```python
if not _db_service:
    return json.dumps({"error": "Database service not initialized"})

try:
    from services.business_logic import BusinessLogic
    logic = BusinessLogic(_db_service)
    result = _run_async(logic.<method_name>(<args>))
    return json.dumps(result, indent=2)
except Exception as e:
    return json.dumps({"error": str(e)})
```

The only thing that changes per tool is which `BusinessLogic.*`
method to call. For `floor_check`, the method is also called
`floor_check`. Normalize `product_query` first: an empty string means
"aggregate inventory health"; a real value like `"Hadley shirt"` means
"look up that product and join the warehouse rows."

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

Six lines between the guards. That's it.

::::

Save the file. The backend auto-reloads (~1 s). Watch the builders
log in your terminal — you should see uvicorn pick up the change
without errors:

```bash
tail -f /tmp/pellier/uvicorn.log
```

If you see an `ImportError` or `SyntaxError`, fix the line the
traceback points at and save again.

---

## Verify in the Atelier

Switch to your Atelier tab. In the left sidebar under
**UNDERSTAND**, click **Tools**. The `floor_check` tool card was
previously dashed-bordered with an *Exercise* status pill (the
workshop-progress strip at the top tracks shipped vs exercise tools
— before your edit it read 11/12 shipped).

After saving, the strip should now read **12/12 shipped** and
`floor_check` should have a solid border and a sage *Shipped* pill.

::::expand{header="If the strip still says 11/12"}

The frontend caches the tool registry briefly. Hard-reload the
Atelier tab. If it still reads 11/12 after a reload, run:

```bash
tail -n 80 /tmp/pellier/uvicorn.log | grep -iE "error|traceback"
```

A common cause is a Python syntax error in your edit — uvicorn
auto-reloads, but logs the failure to import.

::::

Now click **Discover** on the Tools surface with this query:

> warehouse stock check

`floor_check` should land in the top three with a cosine score
above 0.4. That's the registry seeing your tool's docstring (which
your stub already had — you didn't edit it) and matching it
semantically. The point: the agent didn't know about the *body* of
your tool, only its name and docstring, and that was enough for the
discovery layer.

---

## Replay turn 4 in the Boutique

Switch to the Boutique tab and the chat drawer Marco was using.
Click pill 4 again — *"Is the Hadley shirt at the Brooklyn
warehouse?"*

This time the orchestrator routes to Stock Keeper (it always did),
Stock Keeper calls `floor_check(product_query="Hadley shirt")` — and
now the tool returns real data. Stock Keeper's reply names Brooklyn,
the quantity, the ship window, and the other warehouses' counts. The
trace chips under the answer read `floor_check` with a real duration;
the stub's "in stub state" error envelope is gone.

![Marco's turn 4, after you wired floor_check](/static/introduction/marco-pill-4-fixed.png)

That's the gap closed.

---

## *What you actually built*

A few lines of Python. But what those lines did:

- Connected Stock Keeper (already wired, already prompted, already
  trusted by the orchestrator) to the real warehouse data
- Closed Marco's turn 4 — turn 5 (cart hold) was already wired and
  has been waiting for turn 4 to land
- Bumped the Atelier's tool inventory from 11 shipped + 1 exercise
  to 12 shipped, in real time, without restarting anything

In production this is the everyday shape of agent work: the system
already knows the *plan* (which agent, which tool, with what
arguments). The wiring is a small connection between a tool's
intent (its docstring) and its source of truth (Aurora). That's
where most of an agentic system's code lives.

:::alert{type="success" header="Act I · Anna's rerank proof"}
Turn 4 lands. Next you switch to Anna and prove whether hybrid + rerank
actually changes the result set enough to earn its latency and cost.

[Act I · Prove rerank earns its cost →](/13-prove-rerank/)
:::
