# Theo's arc — Aurora as agent system-of-record

*Theo is the third persona and anchors the workshop's third Aurora capability. Marco read; Anna read harder; Theo writes — and every write leaves a paper trail that's reconstructible from a single SELECT.*

---

## Who is Theo?

Theo keeps a short list of quiet pieces — ceramics, linen throws, stoneware. He finishes what he buys, slowly. His persona profile mentions "slow craft" and his orders skew home-decor-and-stoneware. When something arrives chipped, he's not looking to chat; he wants the return processed and the inventory adjusted. Quiet, concrete, transactional.

His hero pills cover read-path queries (pour-over rituals, ceramic pairings) — but the **canonical Theo turn for Module 2 is his return turn:**

> *"My Wabi-Sabi Bowl arrived chipped. Please file a damaged return — my customer id is 'theo'."*

That single message triggers four agent calls and **three Aurora writes in one transaction**.

## What happens when Theo files a return

Theo's Experience Guide chains three tools:

1. `find_pieces` — resolve "Wabi-Sabi Bowl" to integer `productId=37` and category `Home Decor`. Pure read; no audit.
2. `returns_and_care` — confirm the 30-day return window for Home Decor. Pure read; no audit.
3. `process_return` — the write. Cedar-gated on the reason value, SQL-gated on ownership.

The third call is where Aurora becomes the source of truth, not just the index.

### Two enforcement layers

**Cedar** runs in `BeforeToolCallEvent`. The policy `process-return-allowed-reasons` checks `reason ∈ {damaged, wrong_size, not_as_described, changed_mind, other}` against the agent's tool args. If the reason is anything else, Cedar returns DENY, the tool call is canceled, and Strands hands the agent a synthetic tool result containing the reason. The Atelier's Policy panel shows the violation. **No SQL ran.**

**SQL** gates ownership inside the transaction. `BusinessLogic.process_return` first runs `SELECT 1 FROM orders WHERE customer_id = %s AND product_id = %s LIMIT 1`. If Theo never ordered this product, the function returns `{"status": "error"}` and the INSERT never fires. Cedar can't enforce this — it requires a JOIN against live data, and a static policy doesn't know what Theo bought.

**Two layers, two roles:** Cedar guards *what* the agent can do; SQL guards *whose* state the agent can mutate.

### Three writes in one transaction

If both gates pass, `BusinessLogic.process_return` runs:

```sql
-- 1. INSERT the return row
INSERT INTO returns (customer_id, product_id, reason)
VALUES ('theo', 37, 'damaged')
RETURNING id;

-- 2. (only when reason='damaged') Decrement quantity
UPDATE pellier.product_catalog
   SET quantity = GREATEST(quantity - 1, 0),
       updated_at = NOW()
 WHERE "productId" = 37
RETURNING "productId", name, quantity;
```

All in one transaction. If anything raises, psycopg's context manager rolls back.

The third write — `tool_audit` — is fired by the policy hook itself, not by `process_return`:

```sql
-- 3. (BeforeToolCallEvent on ALLOW) placeholder INSERT
INSERT INTO tool_audit (session_id, tool, caller, args, result, latency_ms)
VALUES ('persona-theo-...', 'process_return', 'agent',
        '{"customer_id": "theo", "product_id": 37, "reason": "damaged"}'::jsonb,
        NULL, NULL)
RETURNING audit_id;

-- (AfterToolCallEvent) UPDATE with result + measured latency
UPDATE tool_audit
   SET result = '{...}'::jsonb, latency_ms = 184
 WHERE audit_id = ?;
```

Three rows, three tables, one customer-visible action. The Atelier session brief tab for Theo's ceramics-return turn enumerates each write under the `process_return` tool call so a workshop participant can see the full mutation graph in one place.

## The teaching beats

1. **Cedar in `BeforeToolCallEvent` is the workshop's "policy is code, code is enforcement"** moment. The same Cedar engine that gates restock_shelf gates process_return. New mutating tools get protection by adding one entry to `_TOOL_TO_POLICY_ACTION` plus one Cedar policy block.

2. **The two-layer pattern (Cedar + SQL) is the workshop's "don't put dynamic state in static policy"** moment. Cedar should never know what Theo bought; that's what SQL is for. Workshop participants try to add ownership to Cedar, hit the limitation, learn why the SQL JOIN is the right home.

3. **`tool_audit` is the workshop's "every mutation is reconstructible"** moment. After Theo's turn lands, participants run `SELECT * FROM tool_audit WHERE session_id = ...` from psql and see the agent's whole turn replay-able from rows alone — args, result, latency. **Aurora as system of record, not as side-effect-of-the-LLM.**

## Replay Theo's arc

- `/atelier/sessions/theo-pour-over` — read-path baseline. Theo asks about pairings for his stoneware pour-over set.
- `/atelier/sessions/theo-ceramics-return` — the workshop's canonical write turn. Brief tab walks through the three Aurora writes with the schema for each.

In the **Workshop format**, this session ships pre-loaded as a fixture but Experience Guide itself is stubbed — clicking the same query in the live Boutique produces the Dispatcher fall-through ("I can help with style and recommendations, but return handling sits outside what I can answer right now"). Workshop participants run `cp solutions/module2/agents/customer_support_agent.py pellier/backend/agents/` to wire it. After the cp, Theo's chipped-ceramics turn lands end-to-end. **That's the second build moment of the workshop — parallel to wiring Stock Keeper for Marco's Turn 4.**

In the **Builder's Session format**, Experience Guide ships pre-applied via the CloudFormation UserData, so this session resolves cleanly out of the box.

---

*Where to next: re-read [aurora-capabilities-arc.en.md](./aurora-capabilities-arc.en.md) — Marco read, Anna read harder, Theo wrote. The compounding lesson lands.*
