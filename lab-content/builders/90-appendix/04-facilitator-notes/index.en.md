---
title: "04: Facilitator notes"
weight: 40
---

:::alert{type="info"}
**Audience:** table leads and SAs (not surfaced to builders in-room)  
**Use:** before, during, and after the 60-minute session  
**Surfaces covered:** pre-flight checks · pacing · failure modes · cost shape · cleanup
:::

## Pre-flight checks (facilitator only)

Run these five checks before the room opens. The CFN bootstrap should already pass them; these are the hand-verification path if something looks off. **Builders no longer run pre-flight in-room** (saves ~4 min); make sure all five are green before Marco walks in.

```bash
# 1. Backend health
curl -s http://localhost:8000/api/health | python3 -m json.tool
# Expect: healthy + database connected

# 2. Catalog seeded
psql -c "SELECT count(*) FROM pellier.product_catalog;"
# Expect: 40

# 3. Warehouse seeded
psql -c "SELECT count(*) FROM pellier.warehouse_inventory;"
# Expect: ~120 (3 warehouses × 40 products)

# 4. AgentCore resources present
grep -E 'AGENTCORE_MEMORY_ID|AGENTCORE_RUNTIME_ENDPOINT' \
  /workshop/sample-pellier-agentic-search-apg/pellier/backend/.env
# Expect: AGENTCORE_MEMORY_ID non-empty (Runtime endpoint is a bonus)

# 5. Audit ledger reachable
psql -c "SELECT to_regclass('pellier.tool_audit') AS audit_table;"
# Expect: pellier.tool_audit (may be empty until Act II)
```

If any check fails, jump to [When things misbehave](../02-when-things-misbehave/) before opening the room.

---

## The clock

| Block | Budget | What it has to land | Cut to here if running long |
|---|---|---|---|
| Setup + Marco hello | 8 min | Boutique loads; persona switcher works; `Pellier · listening` chip | Skip the slide tour; the room sees the demo |
| Act I: Build (`floor_check`) | 12 min | Marco's Turn 4 returns BK-01 | Drop in `solutions/closing-marcos-gap/...` and read the diff |
| Act I: Measure (Anna's rerank decision) | 9 min | All four strategies render in Atelier → Performance | Skim agentic; hold the question on hybrid + rerank |
| Act II: working-memory read | 6 min | `/api/agent/session/{id}` returns ordered turns; the other three substrates (semantic, episodic, procedural) are visible in the Atelier | Skim §1, §3 only; namespace narrative is the keeper |
| Act II: Aurora SQL ledger (Exercise 2) | 5 min | One row from `pellier.tool_audit` for Theo's `process_return` | Run the canned `tool_audit_recap.sql` instead of teaching the SELECT |
| Act III: Routing read | 4 min | One paragraph: dispatcher beats LLM-as-router for known intents | none |
| Q&A / overflow | 6 min | none | none |

The room runs long when the floor_check edit and the Aurora SQL
exercise both stall in the same table. Decide which one is the
"real" build moment for that table early, and drop in the solution
for the other.

---

## Two failure modes that eat the most time

1. **Bedrock model access not granted.** Cohere Embed English v3 + Cohere
   Rerank v3.5 + Anthropic Claude Haiku 4.5 must be enabled in
   `us-west-2`. Pre-flight: `python3 scripts/seed_boutique_catalog.py
   --dry-run`. If access is missing, the seeder fails with
   `AccessDeniedException` and the whole catalog is empty.
2. **Aurora SQL ledger returns 0 rows.** The mandatory Exercise 2
   only works on *write* turns. If a builder runs Marco's
   `floor_check` curl and queries `pellier.tool_audit`, they will
   see nothing. The runbook in
   [When things misbehave](../02-when-things-misbehave/) has the
   Theo damaged-return remedy curl. Point them at it before they
   try to debug the writer.

---

## Cost shape of one workshop instance

Order-of-magnitude only; actuals vary with region and on-demand
pricing. Assume a 60-minute live session, ~30 builders.

| Service | What's running | Why it costs |
|---|---|---|
| **Aurora PostgreSQL Serverless v2** | 1 cluster, 0.5–2 ACU autoscaling, ~120 catalog rows | Compute-time, not row-count. Idle ACU floor is the dominant cost during slow blocks. |
| **Bedrock: Cohere Embed English v3** | 40 catalog seedings + ~3 query embeddings per builder turn | Per-token, embed-only. Seeding is one-shot at bootstrap; in-room calls are tiny. |
| **Bedrock: Cohere Rerank v3.5** | 1 call per agentic search turn | Per-document scored. Workshop catalog caps at 40, so each call is bounded. |
| **Bedrock: Claude Haiku 4.5** | Structured-filter extraction at T=0 + agent prose | Per-input/output token. Haiku is the cheapest of the named models; leave it on. |
| **Bedrock: Claude Opus 4.6** | Editorial specialist turns (Style Advisor, Curator, Experience Guide) | Higher per-token than Haiku; biggest cost lever if a table over-runs. |
| **Bedrock AgentCore: Memory** | 1 resource per workshop (holds the working + semantic substrates), 30-day TTL | Per-event storage + retrieval. |
| **Bedrock AgentCore: Runtime** | 1 launched runtime per workshop, microVM cold-starts on idle | Per-second compute when invoked. |
| **EC2 (Code Editor host)** | 1 t3.medium-class instance per builder | Hourly compute. The single biggest line item if instances are left running. |

The two costs that compound past the session are the **EC2 Code
Editor instances** (hourly) and the **idle Aurora ACU floor**.
Everything else is per-call and stops when the room empties.

---

## Cleanup: run after the room empties

Run in this order. The teardown script in `scripts/teardown.sh`
(if present in your fork) wraps these. If running by hand:

```bash
# 1. Stop the per-builder EC2 instances. CloudFormation/Terraform
#    that provisioned them is the right destroy path; manual
#    'terminate-instances' works but loses the audit trail.
aws cloudformation delete-stack --stack-name pellier-workshop-instances

# 2. Delete the AgentCore Runtime resource. Idle runtimes still
#    bill for cold-start surface area.
agentcore delete --agent pellier-agent --region us-west-2

# 3. Delete the AgentCore Memory resource. Working memory has a 30-day
#    TTL but the resource itself bills for storage (and holds the
#    semantic preferences too).
aws bedrock-agentcore-control delete-memory \
  --memory-id "$AGENTCORE_MEMORY_ID" --region us-west-2

# 4. Drop the Aurora cluster last; it is the table that holds
#    tool_audit rows you may want to inspect post-session before
#    teardown. Only delete after you have downloaded what you need.
aws rds delete-db-cluster \
  --db-cluster-identifier pellier-workshop \
  --skip-final-snapshot --delete-automated-backups
```

**Bedrock model access does not need to be revoked.** Granting access
to a model is free; only invocations bill.

---

## Two artifacts builders sometimes ask for after the session

1. **The full `tool_audit` ledger** for their session. Export with
   `psql -c "COPY (SELECT * FROM pellier.tool_audit WHERE session_id =
   '...') TO STDOUT WITH CSV HEADER" > session.csv`.
2. **The agentic strategy's extractedFilters payload.** It lives in
   the Atelier → Performance card response under
   `searchStrategies[].extractedFilters` and is the cleanest demo of
   how Haiku 4.5 turned a conversational query into a structured
   WHERE clause + a residual taste phrase.

Both are recoverable up to the cleanup window. Once the Aurora
cluster is dropped, the audit rows are gone.
