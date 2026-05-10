---
title: Module 2 · Understand
weight: 30
---

**Time budget: 25 minutes**
**Surfaces: Agents → Tools**

Two builds that close Marco's gap:

- **C1 · Stock Keeper agent** — author the system prompt
- **C2 · `floor_check` tool** — wire the tool that answers Marco's Turn 4

Midpoint checkpoint inside this slot.

---

## C1 · Stock Keeper agent (10 min)

### Why this matters
Marco asked about the Brooklyn warehouse. The Dispatcher matched stock intent, but Stock Keeper ships in stub state — voice-matched non-answer. You're authoring the agent that closes the gap.

### Where to look
- File: `pellier/backend/agents/inventory_agent.py`
- Challenge block: line ~22 (`# === CHALLENGE · Stock Keeper · system prompt: START ===`)

### What to implement
Replace the placeholder `_INVENTORY_SYSTEM_PROMPT` with a real prompt that:

1. Names the agent — **"You are Pellier's Stock Keeper."**
2. Lists the three tools and when to use each:
   - `floor_check` → overall stock + warehouse health
   - `running_low` → items needing restock, ranked by rating
   - `restock_shelf` → only when user provides product ID + quantity
3. Sets output discipline (Haiku at 0.0 respects it):
   - Always call a tool first; no text before the tool call
   - After tool: 1–2 short sentences; no markdown tables, no emojis
   - If tool returns zero/error: brief plain-language explanation

Then flip `_INVENTORY_AGENT_STUBBED = False`.

### ⏩ Short on time?
```bash
cp solutions/module2/agents/inventory_agent.py \
   pellier/backend/agents/inventory_agent.py
```

### Verify locally
```bash
cd pellier-workshop/pellier/backend
pytest tests/test_inventory_agent.py -v
```
Green? On to C2.

---

## C2 · `floor_check` tool (12 min)

### Why this matters
The tool Marco's Turn 4 needs. With it wired, clicking Marco's Turn 4 pill returns a real warehouse breakdown. Midpoint payoff.

### Where to look
- File: `pellier/backend/services/agent_tools.py`
- Challenge block: `# === CHALLENGE · Stock Keeper · floor_check: START ===` (≈ line 66)

### What to implement
Replace the stub body:

1. Guard on `_db_service` being initialized
2. `from services.business_logic import BusinessLogic`
3. `logic = BusinessLogic(_db_service)`
4. Call `logic.floor_check()` via `_run_async()` — it's `async`
5. Return `json.dumps(result, indent=2)`
6. try/except → JSON error envelope on failure

### ⏩ Short on time?
```bash
cp solutions/module2/services/agent_tools__inventory.py \
   pellier/backend/services/agent_tools.py
```

### Verify locally
```bash
pytest tests/test_agent_tools.py::test_floor_check -v
```

---

## 🎯 Mid-point checkpoint (3 minutes, whole class)

Everyone pause.

1. Confirm Stock Keeper (C1) and `floor_check` (C2) are both wired (pytest green).
2. **Click Marco's Turn 4 pill** in the Boutique: *"Is the Pellier shirt at the Brooklyn warehouse?"*
3. Expected answer:

   > "Yes — Brooklyn (BK-01) has 8 of the Pellier Linen Shirt in ecru on the floor right now. Also 4 at Austin (ATX-02) and 12 at Portland (PDX-01). Ship window 1–2 business days."

4. Flip to Atelier. `/atelier/agents` — Stock Keeper's "Your turn" pill is gone. `/atelier/routing` — the dotted stock arrow is solid. `/atelier/performance` — Stock Keeper's latency bar is populated (~150 ms on Haiku 4.5 at 0.0).

Your code just changed the system's answer. The Boutique didn't restart. That's the lesson.

---

## Where the other tools went

In the Builder's Session format, `restock_shelf` + `running_low` were pre-applied by CloudFormation at lab start. You didn't write them, but you'll see them wired in the Atelier. Open the full 2-hour Workshop to build them yourself.

Experience Guide (the returns/care specialist) is also pre-applied for the same reason. Theo's ceramics-return session works out of the box in this format.

---

## Theo's write-path tour (3 minutes, whole class)

Before you go, a quick look at the **third Aurora capability** — Aurora as agent system-of-record.

Switch to **Theo** in the persona dropdown. Type:

> *My Wabi-Sabi Bowl arrived chipped. Please file a damaged return — my customer id is 'theo'.*

Watch the response: *"I've filed the damaged return for the Wabi-Sabi Bowl..."*. The Experience Guide chained three tools:

1. `find_pieces` — resolved "Wabi-Sabi Bowl" to integer `productId=37`
2. `returns_and_care` — confirmed the 30-day window for Home Decor
3. **`process_return`** — wrote the return to Aurora

That third call ran a single-transaction sequence:
- Cedar policy `process-return-allowed-reasons` checked `reason ∈ {damaged, wrong_size, ...}` → **ALLOW**
- SQL ownership gate: `SELECT 1 FROM orders WHERE customer_id='theo' AND product_id=37` → matched
- `INSERT INTO returns (...)` → returned new `id=2`
- `UPDATE pellier.product_catalog SET quantity = GREATEST(quantity-1, 0) WHERE "productId"=37` (because reason='damaged')

Plus — fired by the policy hook, not the tool itself:
- `INSERT INTO tool_audit (...)` in `BeforeToolCallEvent` (placeholder row)
- `UPDATE tool_audit SET result=..., latency_ms=...` in `AfterToolCallEvent`

Three tables changed in one customer-visible action. Open `/atelier/tools` — `process_return` carries a burgundy **WRITE** badge. Open the same session in `/atelier/sessions/theo-ceramics-return` — the brief tab walks the full mutation graph. Run `SELECT * FROM tool_audit WHERE tool='process_return' ORDER BY audit_id DESC LIMIT 1;` from psql and the entire turn replays from one row.

That's the third capability: **Cedar gates what; SQL gates whose; tool_audit makes every mutation reconstructible.**

Next: [Module 3 · Evaluate](30-module3-evaluate.en.md)

*Cross-links: [Theo's full write-path arc](../shared/theo-arc-overview.en.md) · [Aurora capabilities ladder](../shared/aurora-capabilities-arc.en.md)*
