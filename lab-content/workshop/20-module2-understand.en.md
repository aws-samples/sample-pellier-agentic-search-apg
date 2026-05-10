---
title: Module 2 · Understand
weight: 30
---

**Time budget: 70 minutes**
**Surfaces: Architecture → Agents → Tools → Skills → Routing → Memory**

Two full specialist builds with verification moments between them.

- **C1 · Stock Keeper agent** (system prompt)
- **C2 · `floor_check` tool** (the tool that makes Marco's Turn 4 land)
- **Mid-point checkpoint** — 3 minutes, Marco's gap closes
- **C3 · `restock_shelf` tool** (second inventory tool)
- **C4 · `running_low` tool** (third inventory tool)
- **C5 · Experience Guide agent** (system prompt + chaining pattern)

After C2 alone Marco's Turn 4 works. C3–C5 add depth.

---

## C1 · Stock Keeper agent (12 min)

### Why this matters
Marco asked about the Brooklyn warehouse. The Dispatcher correctly matched stock intent — but Stock Keeper ships in stub state, so a voice-matched non-answer came back. You're authoring the agent that closes the gap.

### Where to look
- File: `pellier/backend/agents/inventory_agent.py`
- Challenge block: line 22 (`# === CHALLENGE · Stock Keeper · system prompt: START ===`)

### What to implement
Replace the placeholder `_INVENTORY_SYSTEM_PROMPT` with a real system prompt that:

1. Names the agent — **"You are Pellier's Stock Keeper."**
2. Lists the three tools and when to use each:
   - `floor_check` → overall stock + warehouse health overview
   - `running_low` → items needing restock, ranked by rating
   - `restock_shelf` → only when the user gives a product ID + quantity
3. Sets output discipline (Haiku at 0.0 respects it):
   - Always call a tool first — no text before the tool call
   - After tool results: 1–2 short sentences; no markdown tables, no numbered lists, no emojis
   - Products render as cards; don't list them in text
   - If a tool returns zero/error: brief plain-language explanation

Then flip `_INVENTORY_AGENT_STUBBED = False` at the bottom of the block.

### ⏩ Short on time?
```bash
cp solutions/module2/agents/inventory_agent.py \
   pellier/backend/agents/inventory_agent.py
```

### Verify locally (pytest)
```bash
cd pellier-workshop/pellier/backend
pytest tests/test_inventory_agent.py -v
```

### Verify live
Not yet — Stock Keeper still needs `floor_check` to have a tool to call. On to C2.

---

## C2 · `floor_check` tool (15 min)

### Why this matters
This is **the** tool Marco's Turn 4 needs. After you wire it and flip the stub flag on the agent, clicking Marco's Turn 4 pill returns a real warehouse breakdown. That's the midpoint payoff.

### Where to look
- File: `pellier/backend/services/agent_tools.py`
- Challenge block: find `# === CHALLENGE · Stock Keeper · floor_check: START ===` (≈ line 66)

### What to implement
Replace the stub body with the real tool:

1. Guard on `_db_service` being initialized (return a JSON error if not)
2. `from services.business_logic import BusinessLogic`
3. `logic = BusinessLogic(_db_service)`
4. Call `logic.floor_check()` via `_run_async()` — it's an `async` method
5. Return `json.dumps(result, indent=2)`
6. Wrap the whole block in try/except and return a JSON error envelope on failure

### ⏩ Short on time?
```bash
cp solutions/module2/services/agent_tools__inventory.py \
   pellier/backend/services/agent_tools.py
```

### Verify locally (pytest)
```bash
pytest tests/test_agent_tools.py::test_floor_check -v
```

### Verify live
1. In the Boutique, click Marco's Turn 4 pill: **"Is the Pellier shirt at the Brooklyn warehouse?"**
2. Expected answer: warehouse breakdown with counts — Brooklyn, Austin, Portland.
3. Flip to the Atelier: `/atelier/routing` — the dotted stock-intent arrow is now solid.
4. `/atelier/agents` — Stock Keeper no longer carries the "Your turn" pill.

---

## 🎯 Mid-point checkpoint (3 minutes, whole class)

Pause. Everyone does this together:

1. Make sure Stock Keeper system prompt is wired (C1) AND `floor_check` is wired (C2).
2. Click Marco's **Turn 4 pill** again in the Boutique.
3. Watch the answer change from the graceful non-answer to:

   > *"Yes — Brooklyn (BK-01) has 8 of the Pellier Linen Shirt in ecru on the floor right now. Also 4 at Austin (ATX-02) and 12 at Portland (PDX-01). Ship window from Brooklyn to your zip is 1–2 business days."*

4. Open the Atelier session fixture `/atelier/sessions/marco-midpoint-checkpoint`. Notice the telemetry shows **your** `floor_check` tool running in ~150 ms on Haiku 4.5 at 0.0.

That's the workshop's core moment: your code changed Marco's answer. The Boutique didn't restart. Nothing was re-deployed. You added a capability and the system composed it in.

---

## C3 · `restock_shelf` tool (10 min)

### Why this matters
Stock Keeper can now report inventory, but can't modify it. `restock_shelf` adds write capability — and teaches the Cedar policy hook, which caps restocks at 500 units.

### Where to look
- File: `pellier/backend/services/agent_tools.py`
- Block: `# === CHALLENGE · Stock Keeper · restock_shelf ===`

### What to implement
Wire to `BusinessLogic.restock_shelf(product_id, quantity)`. Same pattern as `floor_check`. Cedar enforces the 500-unit ceiling via `BeforeToolCallEvent`; you don't need to enforce it in the tool.

### ⏩ Short on time?
```bash
cp solutions/module2/services/agent_tools__inventory.py \
   pellier/backend/services/agent_tools.py
```
(Same file, covers all three inventory tools at once.)

### Verify locally
```bash
pytest tests/test_agent_tools.py::test_restock_shelf -v
```

### Verify live
In the Atelier concierge modal (Agents tab), send the query:

> "Restock product 2 by 100 units"

Watch the telemetry — the Cedar policy hook fires before the tool executes. Now try:

> "Restock product 2 by 1000 units"

Cedar blocks with an honest error. The Atelier Guardrails panel shows the policy decision.

---

## C4 · `running_low` tool (8 min)

### Why this matters
The third inventory tool — reports products at ≤5 units, ranked by rating. Short, straightforward, completes Stock Keeper's toolkit.

### Where to look
- File: `pellier/backend/services/agent_tools.py`
- Block: `# === CHALLENGE · Stock Keeper · running_low ===`

### What to implement
Wire to `BusinessLogic.running_low(limit)`. Same pattern.

### ⏩ Short on time?
```bash
cp solutions/module2/services/agent_tools__inventory.py \
   pellier/backend/services/agent_tools.py
```

### Verify locally
```bash
pytest tests/test_agent_tools.py::test_running_low -v
```

### Verify live
Open the Atelier concierge and ask *"What's running low?"* — list of low-stock products with their ratings.

---

## C5 · Experience Guide agent (20 min)

### Why this matters
Stock Keeper is done. Now the second full specialist build. Experience Guide handles returns and care — exactly what Theo needs when his ceramics arrived chipped. Different model (Sonnet 4.6 · 0.2), different voice, different pattern: **tool chaining**.

### Where to look
- File: `pellier/backend/agents/customer_support_agent.py`
- Challenge block: line 31 (`# === CHALLENGE · Experience Guide · system prompt: START ===`)

### What to implement
Replace the placeholder `_SUPPORT_SYSTEM_PROMPT` with a full system prompt that:

1. Names the agent — **"You are Pellier's Experience Guide."**
2. Lists the two tools:
   - `returns_and_care` → return window + care by product category
   - `find_pieces` → when the customer names a product and you need its category first
3. **Teaches the chaining pattern** — this is the interesting part. If the customer mentions a product by name or ID, the agent should:
   - First call `find_pieces` to identify the product's `category`
   - Then call `returns_and_care` with that category
4. Sets the empathy/discipline balance. Sonnet at 0.2 is warm but doesn't wander:
   - Always call a tool first
   - After tool: 1–2 short sentences, conversational
   - No markdown tables, numbered lists, emojis, follow-up questions

Then flip `_SUPPORT_AGENT_STUBBED = False` at the end of the block.

### ⏩ Short on time?
```bash
cp solutions/module2/agents/customer_support_agent.py \
   pellier/backend/agents/customer_support_agent.py
```

### Verify locally
```bash
pytest tests/test_customer_support_agent.py -v
```

### Verify live
Re-open the Atelier session `/atelier/sessions/theo-ceramics-return`. The stub-state brief previously acknowledged the gap honestly ("A return, unresolved"). Now switch to Theo in the Boutique and ask:

> "These ceramics arrived chipped. What now?"

Experience Guide answers with the 30-day return window, prepaid label, refund timing. Theo's second-chance session — the Workshop's secondary payoff — resolves cleanly.

---

## Where you are

You've shipped two full specialists. Stock Keeper answers warehouse questions (Marco's gap, closed). Experience Guide handles returns (Theo's gap, closed). Five tools wired. No one normalized a model. You felt the cost of the wrong model choice in Module 1 and felt the benefit of the right one here.

---

## Theo's write-path tour (5 minutes, whole class)

Now that Experience Guide is wired, the workshop's **third Aurora capability** — Aurora as agent system-of-record — is alive. Take 5 minutes to trace what happens when Theo files a return.

### Trigger the write

Switch to **Theo** in the persona dropdown. Send:

> *My Wabi-Sabi Bowl arrived chipped. Please file a damaged return — my customer id is 'theo'.*

Read the response. *"I've filed the damaged return for the Wabi-Sabi Bowl..."*. Now flip to the Atelier session for that turn (Atelier sidebar → Sessions → `theo-ceramics-return` → Brief tab). The brief enumerates **three Aurora writes in one transaction**:

1. `INSERT INTO returns (customer_id, product_id, reason)` → returns the new `id`
2. `UPDATE pellier.product_catalog SET quantity = GREATEST(quantity - 1, 0)` (only when reason='damaged')
3. `INSERT INTO tool_audit (...)` + `UPDATE tool_audit SET result, latency_ms` from the policy hook

### The two enforcement layers

Open `services/agentcore_policy.py`. Find the `process-return-allowed-reasons` Cedar policy (around line 65). The policy says:

```cedar
forbid (
  principal,
  action == Action::"process_return",
  resource
)
when {
  !(resource.reason in ["damaged","wrong_size","not_as_described","changed_mind","other"])
};
```

This runs in `BeforeToolCallEvent`. A bad reason returns DENY → the tool is canceled with a synthetic result → no SQL fires.

Now open `services/business_logic.py`. Find `process_return()` (around line 187). The first SQL statement:

```sql
SELECT 1 FROM orders
 WHERE customer_id = %s AND product_id = %s
 LIMIT 1;
```

That's the **ownership gate**. Cedar can't enforce it because it requires a JOIN against live data. **Cedar guards what; SQL guards whose.** Two layers, two roles.

### The audit row

Open `services/policy_hook.py`. Find `_MUTATING_TOOLS` (around line 60). It's a set:

```python
_MUTATING_TOOLS = {"restock_shelf", "process_return"}
```

Read tools skip the audit because the Atelier already shows their tool calls in the spans. Mutating tools fire `tool_audit_writer.record_allow()` in `BeforeToolCallEvent` (placeholder INSERT) and `record_after()` in `AfterToolCallEvent` (UPDATE with result + latency).

Now run from psql:

```sql
SELECT audit_id, tool, args, result, latency_ms
  FROM tool_audit
 WHERE tool = 'process_return'
 ORDER BY audit_id DESC
 LIMIT 1;
```

You'll see your turn's args, result, and measured latency in one row. **The whole turn is replayable from a single SELECT.** That's the third capability landing.

### See the WRITE badges

Flip to `/atelier/tools`. Two tools carry burgundy **WRITE** badges: `restock_shelf` and `process_return`. Read tools render no badge (the absence is the badge). The split is visible at a glance, which is the point — workshop-time and production-time, you want to know which tools change state vs just query it.

---

## Where you go next

You've built Marco's gap closure (Stock Keeper + 3 tools), Anna's hybrid path is wired and reranking against the live catalog, and Theo's write path lands three writes in one transaction with two enforcement layers. **Three personas, three Aurora capabilities, all alive at once.**

Next: [Module 3 · Evaluate](30-module3-evaluate.en.md)

*Cross-links: [Theo's full write-path arc](../shared/theo-arc-overview.en.md) · [Aurora capabilities ladder](../shared/aurora-capabilities-arc.en.md)*
