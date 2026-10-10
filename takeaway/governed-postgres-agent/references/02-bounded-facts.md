# Contract 2: return bounded facts

A tool answers one bounded question with one query and returns the database's
answer unchanged. The agent repeats what the tool returned. It holds only the
tools its job needs.

## Template: the result contract

Four states, never collapsed. From Pellier's `check_stock`:

```python
def check_stock(run, *, product_query: str) -> dict:
    """Warehouse, quantity and ship window for one named product.

    Unknown and zero are different answers. A piece the catalog does not
    carry is ``not_found``; a piece it carries with no units is ``success``
    with ``total_units`` 0 and its warehouse rows. More than one match is
    ``ambiguous`` with the candidates, so the agent asks which one is meant.
    """
    tokens = [t for t in str(product_query or "").split() if t]
    if not tokens:
        return {"status": "not_found", "query": product_query, "message": "Empty product query."}

    # A name is a lookup, not a meaning: one LIKE per word, parameterised.
    clause = " AND ".join(["lower(name) LIKE %s"] * len(tokens))
    candidates = run(f"SELECT product_id, name FROM catalog WHERE {clause}",
                     tuple(f"%{t.lower()}%" for t in tokens))

    if not candidates:
        return {"status": "not_found", "query": product_query,
                "message": "No product matched. Stock can only be reported for catalog products."}
    if len(candidates) > 1:
        return {"status": "ambiguous", "query": product_query,
                "candidates": [{"productId": r["product_id"], "name": r["name"]} for r in candidates],
                "message": "Multiple products match. Ask which one is meant before reporting stock."}

    product = candidates[0]
    warehouses = run("SELECT warehouse_name, quantity, ship_window_min, ship_window_max "
                     "FROM warehouse_inventory WHERE product_id = %s ORDER BY ship_window_min",
                     (product["product_id"],))
    return {"status": "success", "product": product,
            "total_units": sum(w["quantity"] for w in warehouses),
            "warehouses": list(warehouses)}
```

The defect to look for, in the wrapper the agent calls:

```python
result = store_tools.check_stock(run, product_query=q)
if result["status"] == "not_found":
    return {"status": "success", "total_units": 0}   # unknown has become sold out
```

Pass the shared result through unchanged. If the agent needs a friendlier
message, add a message; do not change the status.

## Template: the grant is the tool list

A prompt rule ("every stock answer starts from check_stock") does not let the
agent call the tool. Only the list it is constructed with does. And a tool
that could plausibly answer the same question from the wrong source (a catalog
listing that says "in stock") must not be in that list.

```python
stock_agent = Agent(
    model=sonnet,
    system_prompt=STOCK_PROMPT,
    tools=[check_stock],              # the one tool that reads warehouse rows, and nothing it could answer from instead
)
```

Record the grant with each answer (Pellier writes `Stock agent may call:
check_stock` into the audit row) so a reviewer can see what the agent *could*
have used, not only what it did use.

## Bounded rows

- Clamp caller-supplied limits: `min(max(int(limit), 1), MAX_ROWS)`.
- Read one customer's rows by their id, newest first, with `LIMIT`.
- Never return a whole table to a model.

## Review questions

- Which row supports this claim, and could the agent have answered from
  something else?
- Does any tool turn an absence into a value?
- Does the agent hold a tool it does not need for its job?
