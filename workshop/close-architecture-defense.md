# Close: defend the architecture from your own evidence

Use the closing five minutes, while policy cleanup runs, to read the evidence
from this 100-minute workshop. Choose the contradiction and one architecture
question. The full three-move discussion below is optional facilitator material
for a longer session; it is not additional required work.

Run it in three moves: the contradiction, the four questions, the translation.

---

## Move 1 — The contradiction (3 minutes)

Put this evidence set on screen. It is an **illustration**, not a row read from
this box: a constructed shape used to ask one question. The live query below is
where the box speaks for itself.

```text
Policy decision      ALLOW
tool_audit           row present   (audit_id 4127)
write_operations     no matching row
Domain state         pellier.returns unchanged
```

Ask the room:

> **Did the return happen?**

Let them answer before you do. The instinctive answer is yes: the action was
authorized and the tool ran. Both halves of that are true, and the conclusion
still does not follow.

The correct answer:

> The invocation was authorized and reached the tool boundary. **No durable
> business effect is proven by this evidence set.** Read the keyed durable
> outcome before concluding refusal, rollback, or success. An ALLOW alone
> establishes none of them.

This is the anti-lesson the whole workshop is built around: **authorization,
execution, and commit are three separate state transitions**, and each one needs
its own evidence. A single green check that spanned all three would be the most
dangerous thing on the screen.

### Produce it from live evidence

Better than a slide. This searches **this run** for a keyed consequential call
that was authorized, reached the tool, and left nothing durable behind:

```sql
-- Authorized, reached the tool, left no durable effect -- in this run,
-- for one named write, with both durable-effect tables checked.
WITH run AS (
    SELECT run_id, started_at
      FROM pellier.workshop_runs
     ORDER BY started_at DESC
     LIMIT 1
)
SELECT gr.receipt_id,
       gr.decision,
       ta.audit_id,
       ta.tool,
       ta.args->>'idempotency_key' AS operation_key,
       ta.result->>'status'        AS tool_reported_status,
       wo.completed_at,
       led.ledger_rows
  FROM run
  JOIN pellier.governed_receipts gr
    ON gr.run_id = run.run_id
    OR (gr.run_id IS NULL AND gr.created_at >= run.started_at)
  JOIN pellier.tool_audit ta
    ON ta.audit_id = gr.audit_id
  LEFT JOIN pellier.write_operations wo
         ON wo.idempotency_key = ta.args->>'idempotency_key'
  CROSS JOIN LATERAL (
        SELECT count(*) AS ledger_rows
          FROM pellier.inventory_ledger il
         WHERE il.idempotency_key = ta.args->>'idempotency_key'
       ) led
 WHERE gr.decision = 'ALLOW'
   -- Only a named write can have its absence proved. An unkeyed read has
   -- no durable effect to look for, so it is not a contradiction.
   AND ta.args ? 'idempotency_key'
   -- Migration 010 seeds a *successful* historical return whose audit row
   -- carries no key. Without these two lines it answers this query and the
   -- room is shown a false contradiction.
   AND gr.identity_source <> 'seeded'
   AND coalesce(ta.result->>'seeded_incident', 'false') <> 'true'
   -- Durable effect means either table. Neither one alone is the answer.
   AND wo.completed_at IS NULL
   AND led.ledger_rows = 0
 ORDER BY gr.receipt_id DESC
 LIMIT 5;
```

An empty result is the common outcome, and worth saying out loud precisely:
**no contradiction was found in the rows this query searched** -- this run's
keyed writes, excluding seeded history. That is a narrower claim than "every
authorized execution committed", and the narrower claim is the one the evidence
supports. Say the scope out loud; it is the same discipline the receipt applies
when it prints `UNCHECKED`.

---

## Move 2 — Four questions, answered from their own receipt (3 minutes)

Have participants run:

```bash
receipt
```

Then ask each question and have them point at the line that answers it. The
receipt reports `PROVED`, `NOT YET`, or `UNCHECKED`, and the third one matters
here: "I could not look" is not "it did not happen".

The receipt is scoped to the run id minted by `workshop-start`, so each line
speaks to that participant's own workshop run rather than to whatever the shared
cluster saw most recently. A receipt whose header reads `Run: none` is still
true, but it is answering a broader question than the participant asked.

| Question | What answers it | Why that and not something else |
|---|---|---|
| What established Marco's inventory truth? | `01.execution_row` — a `tool_audit` row for `check_inventory` | The answer text is not evidence. The audit row proves the typed tool ran; it does not prove the *stock figure*, which comes from the inventory tables. |
| What excluded Anna's ineligible result? | `02.hybrid_receipt` — a receipt carrying vector ranks, lexical ranks, and their fusion | A result list alone does not establish why a candidate was included or excluded. Read the recorded branch ranks and the deterministic eligibility gate. |
| What proved your Runtime revision executed? | The build fingerprint on the managed receipt | A successful invocation proves the service answered. Only the fingerprint comparison distinguishes your package from the previous deployment, because `qualifier=DEFAULT` reads the same for both. |
| What separated Jessica's policy decision from PostgreSQL's outcome? | `04.deny_did_not_execute` beside `04.durable_effect` | Cedar decided whether the action was permitted. PostgreSQL decided, independently, whether the row was allowed to change. Either can refuse, and the two refusals are different evidence. |

If a participant's receipt says `NOT YET` on one of these, that is a better
teaching moment than a full set. Ask what evidence would have to exist, and
where it would live.

---

## Move 3 — Make it portable (2 minutes)

Nobody in the room is going home to build a boutique. The boundaries transfer;
the domain does not.

| Pellier boundary | The same boundary elsewhere |
|---|---|
| Warehouse inventory tool | Account entitlement, claim status, bed capacity, part availability |
| Product eligibility gate | Coverage rules, compliance constraints, tenant scope |
| Managed Runtime deployment | A hosted operational or support agent |
| Governed return | Refund, credit, claim adjustment, access grant |
| `tool_audit` ledger | Any append-only record of what an agent actually invoked |
| Cedar DENY with no execution row | Any "we refused, and here is proof nothing ran" |

Close on the question the workshop exists to answer:

> Can an agent use live evidence, cross a managed execution boundary, attempt a
> consequential action, and prove which human, policy, application, and
> PostgreSQL controls governed the outcome?

Participants can now point to the evidence for each boundary. Their own receipt
establishes what they can prove and which checks remain `NOT YET` or `UNCHECKED`.

---

## What this close still does not prove

Say this part. It is the most L400 thing in the session.

- **One box is not a fleet.** Everything proved here ran against one Aurora
  cluster with one participant's traffic. Nothing observed today speaks to
  contention, replica lag, or policy evaluation under load.
- **A receipt is a record, not an attestation.** The evidence rows prove what
  the system recorded. They are not signed, and a sufficiently privileged actor
  could write them directly. The workshop's trust boundary is the database role
  model, which is exactly why Lab 4 tests the role rather than the policy text.
- **Absence of an execution row is evidence only where the row was searched
  for.** That is why the receipt distinguishes `NOT YET` from `UNCHECKED`, and
  why the identity-boundary script keys its absence check rather than
  time-windowing it.
- **A green invocation is not a deployed revision** — until the fingerprints
  match. That is the one participants are most likely to forget first.
