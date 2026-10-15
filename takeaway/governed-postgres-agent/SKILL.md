---
name: governed-postgres-agent
description: How a DBA reviews an agent. The review a database engineer brings to an application team's AI agent pull request when the agent reads or writes PostgreSQL (Aurora or RDS) - four contracts (filter before ranking, return bounded facts, bind identity and enforce ownership, approve and deduplicate writes), the questions to ask, the template from the source, and one proof query per claim. Use when reviewing an agent's tools, retrieval or write path, when an agent gets a database role, or when asking "what would prove this agent did the right thing?"
---

# How a DBA reviews an agent

An agent is an application user that writes queries you did not review. Your
instincts already apply: which role it connects as, which rows that role can
see, which statements it can run, what a retry does, and what the audit trail
shows afterwards. This skill turns those instincts into the review you bring to
an agent pull request: four contracts, the questions to put to the team, the
template each one should match, and the query that proves it holds.

The contracts come from Pellier, the retail assistant built for the AWS
re:Invent workshop *Build governed agentic AI search with Aurora, RDS, &
Bedrock AgentCore* (DAT416), and they hold on Aurora PostgreSQL and Amazon RDS
for PostgreSQL alike. The principle behind all four: **the agent proposes,
PostgreSQL decides, and the row is the proof.** A model's output is a proposal.
Predicates, policies, privileges, constraints and keys decide what happens, and
evidence is a row you can query, never a chat transcript or a screen.

## The agent, in terms you already use

| Agent term | What it is to the database |
|---|---|
| A tool | A function with a contract: one bounded query, a status for every outcome |
| The agent's tool list | Its grant. A prompt can name a tool; only the list connects it |
| Caller binding | `SET LOCAL ROLE` plus a session setting the server fills from the token |
| A gateway policy (Cedar) | Authorization before the statement ever reaches you |
| Row-level security | The last line, when the application's own SQL is wrong |
| An idempotency key | A unique constraint that makes a retry find the first write |
| The tool audit table | Application audit: what ran, with which arguments, how long it took |
| Agent memory | Session state. It shapes an answer and authorizes nothing |

## Before you read the diff

1. **Map the paths.** List the role or roles the agent's sessions run as, each
   tool and the SQL it runs, where identity enters (token, session, header) and
   where it reaches the database, and every statement that writes.
2. **Watch it run.** Ask for a test run, then read its workload by role from
   `pg_stat_statements` (`references/proof-queries.sql`, query 0). An agent that
   claims a narrow job but runs wide statements, or runs as the owner, shows up
   here before it shows up in the code.
3. **Review each contract below**: *holds*, *partly* or *missing*, quoting the
   line of code or SQL that makes it hold, or the gap.
4. **Ask for the proof.** For every contract that holds, the team should be able
   to run its query. If no query can show it, it does not hold yet.
5. **Report** one table: contract, status, evidence, the smallest change that
   closes the gap. Lead with the write path; it is where the damage happens.

When the team asks how to build it rather than how you will review it, point
them to the matching reference file and its template. Keep their schema's
names; the pattern is what transfers, not Pellier's tables.

## Contract 1: filter before ranking

Hard constraints (budget, availability, exclusions, tenant, date range) are SQL
predicates applied to every candidate list *before* `LIMIT`. Similarity and
ranking decide order among eligible rows; they never decide eligibility. A retry
or a fallback may relax a preference; it may never drop a constraint.

Ask the team:

- Where do the customer's limits live: in the `WHERE` clause of every branch, or
  in code after the search returns?
- When the strict search comes back sparse, what exactly does the retry change?
- Can you recompute a result's fused score from what you recorded?

Look for:

- [ ] Every candidate branch (vector, full-text, keyword) carries the same
      hard predicates, inside the query, before its `LIMIT`.
- [ ] Nothing filters after fusion or after reranking in application code.
      Post-filtering a top-k list returns short lists and silently drops rows.
- [ ] A fallback path copies the plan and changes only soft fields. Building a
      new plan object from scratch is the classic way constraints vanish.
- [ ] Fusion is arithmetic you can recompute from recorded ranks. Reciprocal
      rank fusion: `1 / (k + rank)` per list, `k = 60`, a missing rank adds
      nothing. Record the ranks so the score can be re-derived later.
- [ ] Under pgvector with a filter, an HNSW scan can come back short.
      `SET hnsw.iterative_scan = strict_order` keeps scanning until `LIMIT`
      is met, in distance order.

Template: `references/01-filter-before-ranking.md`. Prove it: queries 1a to 1c.

## Contract 2: return bounded facts

Each tool answers one bounded question with one query, and returns the
database's answer unchanged. Distinct states stay distinct: not found, zero,
ambiguous and success are four different answers, never collapsed into one. An
agent holds only the tools its job needs, so it cannot answer a question from
the wrong source.

Ask the team:

- What does the tool return when the row does not exist, and is that different
  from what it returns for zero?
- Which tools does this agent hold, and could any of them answer its question
  from the wrong table?
- How many rows can one call return, and who sets that limit?

Look for:

- [ ] The tool's result has an explicit `status` (`success`, `not_found`,
      `ambiguous`, `error`) and the agent repeats it rather than interpreting
      it. "No rows" is not "zero".
- [ ] No tool coerces an absence into a value (`not_found` into `0`, a `NULL`
      sum into `0` with `coalesce`, `NULL` into an empty string that reads as a
      fact). An aggregate with no `GROUP BY` returns one row even when nothing
      matched: test for the row before you aggregate.
- [ ] Row counts are bounded (`LIMIT`, a clamp on caller-supplied limits).
- [ ] The agent that answers stock questions is granted the stock tool and
      not the catalog tools; a prompt that *names* a tool does not grant it.
      Only the tool list the agent is constructed with does.
- [ ] A name lookup is a lookup (`LIKE`, trigram), not a semantic search.

Template: `references/02-bounded-facts.md`. Prove it: queries 2a and 2b.

## Contract 3: bind identity, enforce ownership

The caller comes from the verified token, never from the conversation. The
server sets the customer or tenant on every scoped call before it leaves the
agent runtime, overwriting whatever the model supplied. The database then
enforces ownership on its own, with row-level security bound to a principal set
per transaction, so a wrong query from any path still returns only that
principal's rows and refuses writes in anyone else's name.

Ask the team:

- Where does `customer_id` come from on a scoped call: the token, or the
  model's arguments?
- Which role do the agent's queries run as, and can it bypass row-level
  security, or does it own the tables?
- What does an unbound session see?
- Show me a forged call: the model asks for another customer's rows. What
  leaves the runtime, and what comes back from the database?

Look for:

- [ ] Customer-scoped tool arguments (`customer_id`, `tenant_id`) are set by
      the server from the token, after the model proposes the call.
- [ ] A principal is bound per transaction (`set_config(..., true)` on a GUC
      the policy reads with `current_setting(name, true)`), so an unbound
      session matches nobody rather than everybody.
- [ ] Row-level security is enabled on every customer-owned table, with one
      permissive policy per table using the same expression for `USING` and
      `WITH CHECK`. The agent's role has no `BYPASSRLS`, is not superuser, and
      does not own the tables (or `FORCE ROW LEVEL SECURITY` is set).
- [ ] At a gateway, authorization (Cedar or equivalent) refuses a direct call
      whose customer does not match the token: policy stops a wrong call, RLS
      stops a wrong query. Both are needed.
- [ ] The roles contain a wrong query, not an untrusted session: anyone who
      connects as the owner can reset the role. In production each role gets
      its own login and secret.
- [ ] Remembered context (preferences, history) can shape an answer; it
      carries no authority. Only the token does.
- [ ] A model refusing to read someone else's data proves nothing. The test
      is a forged call sent through the binding: it must leave as the caller.

Template: `references/03-bind-identity-enforce-ownership.md`. Prove it: queries
3a to 3c. The policy shows in the plan too: `EXPLAIN` a wrong query as the
agent's role, bound as one customer, and the bound name is read in an InitPlan
before any row is.

## Contract 4: approve and deduplicate writes

No agent writes money, inventory or commitments on its own. A person approves
the exact terms; the approval row is the thing the write references. A policy
caps the write before the tool runs. A unique idempotency key derived from the
approval makes a retry find the first write instead of making a second. Every
executed call leaves one append-only audit row, and a denied call leaves none.
An ALLOW decision is not proof that anything happened; the row is.

Ask the team:

- What row does a person approve, and does the write function refuse anything
  that row does not name exactly?
- Where does the idempotency key come from, and what happens on a retry?
- Which privileges does the role that writes hold on the tables it writes?
- After an incident, which query tells you who asked, who approved, what ran
  and what changed?

Look for:

- [ ] The write function requires an approval row for these exact arguments
      (customer, amount, reason), and refuses otherwise.
- [ ] The idempotency key is derived from the approval, not minted per call,
      and is `UNIQUE` in the written table.
- [ ] Concurrency is handled in the database: lock the approval, then check
      for an existing row under the key, then write. A replay returns the
      first row; a replay with different arguments is a conflict, not a write.
- [ ] A limit is enforced at the gateway (a `forbid ... unless` that lets
      through only a present, valid amount at or under the cap) and a safety
      ceiling is enforced in the database as a `CHECK` or in the function.
- [ ] The role that writes money holds `EXECUTE` on the write function and no
      privilege on the tables it writes. The function runs with its owner's
      rights (`SECURITY DEFINER`) and a pinned `search_path`, `EXECUTE` is
      revoked from `PUBLIC`, and each path switches to that role per
      transaction. A trigger that guards inserts does not stop an `UPDATE`
      of an approved amount; a role with no `UPDATE` privilege does.
- [ ] One audit row per executed call; none for a denied call; none for a
      replay. The audit table is append-only.
- [ ] The proof is three questions with three sources: *Was it permitted?*
      (policy decision) *Did it run?* (audit row) *Did it change state?*
      (the written row). An absence proof needs a positive control beside it.
- [ ] One query rebuilds a write from the request to the row with joins
      alone: request, approval, key, audit row, written row, affected rows.

Template: `references/04-approve-and-deduplicate-writes.md`. Prove it: queries
4a to 4g.

## Publishing tools over MCP

When the agent reaches its tools through a gateway over the Model Context
Protocol, keep one implementation of each tool for both the in-process and
the gateway path, publish schemas from one source of truth, and bind identity
before the call leaves the runtime. `references/mcp-publishing.md` shows how
Pellier does this with Amazon Bedrock AgentCore Gateway and what to keep when
the gateway is something else.

## The review you hand back

```
| Contract | Status | Evidence | Smallest change |
|---|---|---|---|
| 1 Filter before ranking | partly | vector branch carries price predicate; FTS branch does not (search.py:88) | add the same WHERE to fts_branch_sql |
| 2 Bounded facts | holds | check_stock returns not_found / ambiguous / success (store_tools.py:370) | none |
| 3 Bind identity | missing | customer_id taken from model arguments (agent_tools.py:52) | overwrite from token in the binding step; add RLS policy |
| 4 Approve + dedupe | partly | unique key present; no approval row required | require approval row in the write function |
```

Then the proof query for every row marked *holds*, and the workload by role
from query 0 for the run you watched.
